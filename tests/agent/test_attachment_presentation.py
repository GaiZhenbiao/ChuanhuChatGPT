"""Attachment presentation through production Gradio Send/Enter and File callbacks."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]

def test_production_attachment_send_enter_and_cross_turn_receipts():
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--exercise'],cwd=ROOT,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr

async def exercise():
    import asyncio,html,json,re,threading
    from copy import deepcopy
    from uuid import uuid4
    import gradio as gr
    from gradio.state_holder import SessionState
    from main_chat_preview import build
    app=build()
    from modules.models import OpenAIAgents as agents
    from modules.agent.runtime import format_input_text
    from modules.agent.input_files import read_snapshot_file
    from modules.agent.ui import AgentPanel
    from main_chat_mock import MainChatMock
    config=app.get_config_file();fns=app.fns
    initial=next(i for i,f in enumerate(fns) if f.fn and f.fn.__name__=='initial')
    current=fns[initial].outputs[0]
    state=SessionState(app);request=gr.Request(session_hash='attachment-presentation-offline')
    upload=next(i for i,f in enumerate(fns) if f.fn and f.fn.__name__=='upload_files')
    functions={f.fn.__name__:i for i,f in enumerate(fns) if f.fn}
    from modules.utils import convert_user_before_marked,convert_bot_before_marked
    actual_panel=AgentPanel(convert_user_before_marked,convert_bot_before_marked)
    upload_root=Path(gr.utils.get_upload_folder())/('attachment-test-'+uuid4().hex);upload_root.mkdir(parents=True)
    def file_data(path):return {'path':str(path),'orig_name':path.name,'meta':{'_type':'gradio.FileData'}}
    def descendants(index):
        while True:
            children=[i for i,d in enumerate(config['dependencies']) if d['trigger_after']==index and fns[i].fn]
            if not children:return
            assert len(children)==1,children
            index=children[0];yield index
    async def exhaust(index,inputs,first=None):
        result=first or await app.process_api(index,inputs,state=state,request=request)
        last=result
        while result['is_generating']:
            result=await app.process_api(index,inputs,state=state,request=request,iterator=result['iterator'])
            if any(value is not None for value in result['data']): last=result
        return last
    cases=[]
    try:
      for event in ('click','submit'):
       entry=next(i for i,d in enumerate(config['dependencies']) if fns[i].fn and fns[i].fn.__name__=='transfer_input' and any(t[1]==event for t in d['targets']))
       predict=next(i for i in descendants(entry) if fns[i].fn.__name__=='predict_with_ui')
       for outcome in ('slow-success','prepare-failed','file-only'):
        service=MainChatMock();calls=[];items=[];entered=threading.Event();release=threading.Event()
        session='synthetic-'+uuid4().hex
        # Seed a real view-only output receipt: the old row-count check misses
        # this ordinary producer output on the next actual submission.
        def worker(command):
            calls.append(deepcopy(command))
            action=command['action']
            if action=='prepare_inputs':
                entered.set();assert release.wait(5)
                for record in command['inputs']:
                    assert read_snapshot_file(record,staging_root=command['staging_root']).startswith(b'Synthetic')
                yield from service.worker(command)
            elif action=='run':
                turn='turn-'+str(len(items));sid=command.get('session_id') or session
                wire=format_input_text(command['prompt'],command.get('history_reference'),command.get('input_files'))
                user={'id':'u-'+str(len(items)),'type':'message','role':'user','turn_id':turn,'content':[{'type':'input_text','text':wire}]}
                items.extend([user,{'id':'a-'+str(len(items)),'type':'message','role':'assistant','turn_id':turn,'content':[{'type':'output_text','text':'Synthetic reply '+command['prompt']}]}])
                artifact={'id':'output-'+turn,'session_id':sid,'turn_id':turn,'name':'output.txt','size':3}
                if command.get('input_files'):
                    provisional=deepcopy(items);provisional[-2]['id']=None
                    yield dict(type='progress',session_id=sid,turn_id=turn,outcome='in_progress',submission_started=True,items=provisional,
                               item_occurrences={len(provisional)-2:'upload-user-occurrence'},capture={'items':'partial'})
                yield dict(type='result',session_id=sid,turn_id=turn,outcome='completed',submission_started=True,items=deepcopy(items),
                           text='Synthetic reply '+command['prompt'],sync_complete=True,history_authoritative=True,
                           transcript_artifacts=[artifact],capture={'items':'complete','artifacts':'partial'})
            elif action=='download':yield {'type':'result','artifacts':[]}
            elif action=='title':yield {'type':'result','title':'Synthetic title'}
            else:raise AssertionError(action)
        agents.worker_messages=worker
        model=agents.OpenAIAgentsClient('OpenAI Agent',api_key='offline-fixture-only');model.bind_owner(request);state[current._id]=model
        # Seed through actual production wrapper/background generator.
        from modules.utils import predict as real_predict
        list(real_predict(model,'seed',[],request=request))
        rendered=actual_panel.render_chat(model,model.chatbot)
        assert len(rendered)>len(model._display)
        # The synthetic service's preparation endpoint must know this session.
        service.sessions[model._state['session_id']]={'items':[],'artifacts':[],'tools':deepcopy(model._tool_settings),'model':model.model_name,'reasoning':model._reasoning,
              'instructions':model.system_prompt,'turn_id':None,'outcome':'not_started','text':'','cards':[],'submitted':False}
        filename='upload-fail.txt' if outcome=='prepare-failed' else 'notes.txt'
        path=upload_root/(uuid4().hex+'-'+filename);path.write_text('Synthetic attachment payload')
        uploaded=await exhaust(upload,[None,[file_data(path)],model._conversation_id])
        pending=uploaded['data'][2]['value'];old_ids=tuple(record.input_id for record in model._input_stager.snapshot())
        text='' if outcome=='file-only' else 'Read the attached file'
        tools=model._current_settings()['tools']
        transfer_inputs=[text,None,*model.agent_model_choice[:1],model.agent_model_choice[1] or 'default',model._choice_revision,pending,
           tools['network'],tools['code_execution'],tools['web_search'],tools['search_mode'],'\n'.join(tools['search_domains']),
           tools['computer_use'],tools['include_screenshots'],tools['tool_search'],tools['programmatic_tool_calling'],tools['functions'],json.dumps(tools['mcp_servers']),
           model.system_prompt,model._conversation_id,model._tool_revision]
        await app.process_api(entry,transfer_inputs,state=state,request=request)
        for index in descendants(entry):
            if index==predict:break
            await exhaust(index,[None]*len(fns[index].inputs))
        predict_inputs=[None,None,rendered,False,[],None,pending]
        result=await app.process_api(predict,predict_inputs,state=state,request=request)
        first_data=result['data']
        marker=next(value for component,value in zip(fns[predict].outputs,first_data) if component.elem_id=='model-capability-state')
        if isinstance(marker,dict):marker=marker['value']
        caps=json.loads(html.unescape(re.search(r'data-model-capabilities="([^"]+)"',marker).group(1)))
        assert caps.get('submitted_draft',{}).get('text')==text, {'caps_keys':sorted(caps),'presented':getattr(model,'_draft_presented',None),'pending_token':getattr(model,'_pending_send',None),'draft_token':getattr(model,'_draft_token',None),'display_count':len(model._display),'incoming_count':len(rendered),'notice':model._notice,'errors':[e.get('message') for e in model._ui_errors]}
        file_update=next(value for component,value in zip(fns[predict].outputs,first_data) if component.elem_id=='agent-pending-files')
        assert file_update['value']==[] and json.loads(file_update['label'])['files']==[]
        assert not model._pending_upload_paths and not model._draft_acknowledged
        assert entered.wait(3)
        # Actual Send/Enter preprocessor + actual clear JS, including edits back
        # to the same bytes and a newer ready attachment's visible metadata.
        js={'entry':config['dependencies'][entry]['js'],'draft':caps['submitted_draft'],'file_update':file_update,'before_label':uploaded['data'][2]['label']}
        node=subprocess.run(['node','tests/javascript/attachment-presentation.test.cjs'],input=json.dumps(js),capture_output=True,text=True)
        assert node.returncode==0,node.stderr
        release.set();await exhaust(predict,predict_inputs,result)
        if outcome=='prepare-failed':
            assert len([c for c in calls if c['action']=='run'])==1
            assert text in str(model.chatbot) and not model._pending_upload_paths
            try:await app.process_api(functions['emit_ui_error'],[None],state=state,request=request)
            except gr.Error as error:assert '消息未发送' in str(error)
            else:raise AssertionError('Missing global error')
        else:
            run=next(c for c in calls if c['action']=='run' and c.get('input_files'))
            assert run['input_files'][0]['input_id']==old_ids[0]
            for next_text in ('Second text-only turn','Third text-only turn'):
                list(real_predict(model,next_text,actual_panel.render_chat(model,model.chatbot),files=[],request=request))
                document=model.history_document({'history':model.history,'chatbot':model.chatbot})['agent_transcript']
                input_files=[f for f in document['files'] if f['kind']=='input']
                assert len(input_files)==1 and input_files[0]['source_id']==old_ids[0]
                projection=__import__('modules.agent.ui',fromlist=['message_file_projection']).message_file_projection(model)
                assert len(projection.user_files)==1
                attached_row=next(iter(projection.user_files))
                assert projection._original_rows[attached_row][0]==model._display[1][0]
                assert '未关联消息的文件' not in str(actual_panel.render_chat(model,model.chatbot))
            fresh=model.new_view();fresh.history_file_path=model.history_file_path;fresh.load_chat_history(model.history_file_path)
            assert '未关联消息的文件' not in str(actual_panel.render_chat(fresh,fresh.chatbot))
        newer=upload_root/(uuid4().hex+'-new.txt');newer.write_text('Synthetic newer draft')
        await exhaust(upload,[None,[file_data(newer)],model._conversation_id])
        new_ids=tuple(r.input_id for r in model._input_stager.snapshot())
        model._remove_input_selection(old_ids)
        assert model._pending_upload_paths and tuple(r.input_id for r in model._input_stager.snapshot())==new_ids
        cases.append({'event':event,'outcome':outcome,'same_frame_text_receipt_and_files_clear':True,'worker_snapshot_retained':True,'newer_file_retained':True})
        model._reset_inputs()
      print(json.dumps({'production_attachment_cases':cases,'new_real_API_calls':0},ensure_ascii=False))
    finally:app.close()

if __name__=='__main__':
    import asyncio
    sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
    asyncio.run(exercise())
