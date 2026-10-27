"""Two native-QA regressions via the shipped main layout/event chains offline."""
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('case',['delete-notification','unsent-default-new'])
def test_real_main_event_chain_preserves_notification_and_pending_choice(case):
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--exercise',case],cwd=ROOT,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr


async def exercise(case):
    import asyncio
    import queue
    from types import SimpleNamespace
    import gradio as gr
    from gradio.state_holder import SessionState
    from modules.agent.store import owner_identity
    from main_chat_preview import build
    app=build().queue()
    # Load the class only after the offline installer replaces production config.
    from modules.models.OpenAIAgents import OpenAIAgentsClient
    state=SessionState(app)
    config=app.get_config_file();fns=app.fns
    initial=next(i for i,f in enumerate(fns) if f.fn and f.fn.__name__=='initial')
    current=fns[initial].outputs[0]
    request=gr.Request(session_hash='native-followup-offline')
    model=OpenAIAgentsClient('OpenAI Agent',owner=owner_identity(''),api_key='synthetic-unused')
    model.model_name='gpt-6.1-sol';model._reasoning='medium'
    model._state=dict(outcome='completed',session_id='old-session',turn_id='old-turn',generation='old-generation')
    model._session_settings=dict(model=model.model_name,reasoning='medium',instructions=model.system_prompt,tools=model._tool_settings)
    model.history=[{'role':'user','content':'old question'},{'role':'assistant','content':'old answer'}]
    model.chatbot=model._display=[['old question','old answer']]
    state[current._id]=model
    async def call(index,inputs,event_id=None):
        return await app.process_api(index,inputs,state=state,request=request,session_hash=request.session_hash,event_id=event_id)
    def descendants(index):
        while True:
            matches=[i for i,d in enumerate(config['dependencies']) if d['trigger_after']==index and fns[i].fn]
            if not matches:return
            assert len(matches)==1,matches
            index=matches[0];yield index
    async def follow(index):
        results=[]
        for index in descendants(index):
            inputs=[None if isinstance(component,gr.State) else component.value for component in fns[index].inputs]
            results.append((index,await call(index,inputs)))
        return results
    try:
        if case=='delete-notification':
            model._state['outcome']='in_progress';model.auto_save(model.chatbot)
            delete=next(i for i,f in enumerate(fns) if f.fn and f.fn.__name__=='delete_chat_history')
            assert config['dependencies'][delete]['queue'] is not False
            event_id='delete-followup-event';event=SimpleNamespace(_id=event_id,session_hash=request.session_hash,alive=True)
            app._queue.active_jobs=[[event]]
            messages=queue.Queue();app._queue.pending_messages_per_session[request.session_hash]=messages
            result=await call(delete,[None,model.history_file_path],event_id)
            assert '云端任务停止未确认' in result['data'][0]
            after=await follow(delete)
            assert state[current._id] is not model and state[current._id]._state['outcome']=='not_started'
            # Actual Queue.log_message/send_message, not a mocked gr.Warning.
            notice=messages.get_nowait()
            assert notice.level=='warning' and notice.event_id==event_id and '云端任务停止未确认' in notice.log
            reset_index,reset_result=after[0]
            status=next(component for component in fns[reset_index].outputs if getattr(component,'elem_id',None)=='status-display')
            assert reset_result['data'][fns[reset_index].outputs.index(status)]==''
            assert '云端任务停止未确认' not in str(reset_result['data'][-1]),'warning must not be added to tool activity'
            assert messages.empty()
            assert model._store().deletion_receipt(model._owner,model.history_file_path,model._conversation_id)['remote_stop_confirmed'] is False
        else:
            choose=next(i for i,f in enumerate(fns) if f.fn and f.fn.__name__=='choose_settings')
            reasoning=fns[choose].inputs[2]
            await call(choose,[None,model.model_name,'default',7,model.agent_choice_target])
            assert model._reasoning=='medium' and model.agent_model_choice==('gpt-6.1-sol',None)
            new=next(i for i,d in enumerate(config['dependencies']) if d['trigger_after'] is None and fns[i].fn and len(fns[i].inputs)==2 and fns[i].inputs[0] is current and fns[i].outputs[0] is current)
            await call(new,[None,False]);after=await follow(new)
            fresh=state[current._id]
            assert fresh is not model and fresh.agent_model_choice==('gpt-6.1-sol',None)
            updates=[result['data'][fns[index].outputs.index(reasoning)] for index,result in after if reasoning in fns[index].outputs]
            assert updates and updates[-1]['value']=='default',updates
            from modules.models import OpenAIAgents as agents
            calls=[]
            agents.connection_for_model=lambda **kwargs:dict(api_key='synthetic-unused',base_url='https://example.invalid/v1',proxy_env={})
            def worker(command):
                calls.append(command)
                if command['action']=='run':yield dict(type='result',session_id='fresh-session',turn_id='fresh-turn',outcome='completed',text='fresh default answer')
                elif command['action']=='download':yield dict(type='result',artifacts=[])
                else:raise AssertionError(command['action'])
            agents.worker_messages=worker
            list(fresh.predict('fresh request',[]))
            run=next(c for c in calls if c['action']=='run')
            assert run['reasoning'] is None and run['model']=='gpt-6.1-sol'
        print('native followup event chain passed:',case)
    finally:app.close()


if __name__=='__main__':
    import asyncio
    sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
    asyncio.run(exercise(sys.argv[2]))
