from copy import deepcopy
from collections import OrderedDict
import asyncio
import gradio as gr
from gradio.state_holder import SessionState
from modules.agent.ui import AgentPanel
from agent_fixtures import env,select,send,complete
from test_runtime import FakeClient,message,event,text,turn
from modules.agent import runtime


def test_recovery_buffer_overlap_does_not_duplicate_partial_text(env):
    model=select(env)
    model._state={'generation':'g','session_id':'sess_test','turn_id':'t1','outcome':'in_progress'}
    model._session_settings=model._current_settings()
    # During snapshot GET, the already-open stream buffers the same bc that GET returns.
    client=FakeClient([text('delta','bc',item='a'),event('item.done',item=message('a','abcdef')),turn('completed')],session_status='in_progress',saved_turn='in_progress')
    client.saved_items=[message('u','q',role='user'),message('a','abc',status='in_progress')]
    displayed=[]
    def progress(state):
        model._accept(state.snapshot(),'g',restoring=True)
        displayed.append(model.history[-1]['content'])
    runtime.recover_stream(client,'sess_test','t1',on_progress=progress)
    print('RECOVERY_OVERLAP_DISPLAY',displayed)
    assert 'abcbc' not in displayed, 'Snapshot and already buffered delta must not duplicate text'


def test_terminal_reconcile_keeps_stream_order_for_snapshot_lag():
    client=FakeClient()
    client.saved_items=[message('u','q',role='user')]
    state=runtime.TurnState('sess_test','t1',outcome='completed')
    expected=['msg'+str(i) for i in range(10)]
    for identifier in expected:
        state.accept(event('item.done',item=message(identifier,identifier)))
    runtime._reconcile_terminal(client,state)
    actual=[i['id'] for i in state.snapshot()['items'] if i['role']=='assistant']
    print('RECONCILED_ORDER',actual)
    assert actual==expected


def test_fork_then_new_chat_does_not_restore_old_session_on_failure(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    old_session=model._state['session_id']
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chatbot=gr.Chatbot();status=gr.Markdown();prompt=gr.Textbox();retain=gr.Checkbox(value=False)
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components();panel.wire(current,chatbot,status)
        outputs=[chatbot,status,gr.Radio(),gr.Textbox(),gr.Checkbox(),gr.Number(),gr.Number(),gr.Number(),gr.JSON(),gr.Number(),gr.Number(),gr.Number(),gr.Number(),gr.JSON(),gr.Textbox(),gr.Checkbox()]
        gr.Button('New chat').click(env.wrappers['reset'],[current,retain],outputs)
        gr.Button('Send').click(env.wrappers['predict'],[current,prompt,chatbot],[chatbot,status])
    state=SessionState(app);state[current._id]=model
    indexes={fn.fn.__name__:i for i,fn in enumerate(app.fns) if fn.fn}
    async def exercise():
        request=gr.Request(session_hash='review-ui')
        await app.process_api(indexes['fork'],[None],state=state,request=request)
        await app.process_api(indexes['reset'],[None,False],state=state,request=request)
        assert model.history==[] and not model._state.get('session_id')
        monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([dict(type='error',outcome='not_started',message='synthetic create rejected')]))
        result=await app.process_api(indexes['predict'],[None,'unrelated new question',[]],state=state,request=request)
        while result['is_generating']:
            result=await app.process_api(indexes['predict'],[None,'unrelated new question',[]],state=state,request=request,iterator=result['iterator'])
    try: asyncio.run(exercise())
    finally: app.close()
    print('RESET_FAILURE_TARGET',model._state,model.chatbot)
    assert model._state.get('session_id')!=old_session, 'Reset must discard the prior fork rollback target'


def test_main_auto_title_callback_rejects_another_owner(env,monkeypatch):
    import pytest
    complete(env,monkeypatch);model=select(env,username='alice');send(env,model,username='alice')
    original_path=model.history_file_path
    calls=[]
    def worker(command):
        calls.append(command['action'])
        yield {'type':'result','title':'Unauthorized title'}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();method=gr.Textbox();question=gr.Textbox();single=gr.Checkbox();history=gr.Radio()
        gr.Button('Auto title').click(env.wrappers['auto_name_chat_history'],[current,method,question,single],[history])
    state=SessionState(app);state[current._id]=model
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='auto_name_chat_history')
    try:
        try:
            asyncio.run(app.process_api(index,[None,env.locale('naming.by_model_summary'),'x',False],state=state,request=gr.Request(username='bob',session_hash='review-ui')))
        except gr.Error:
            assert calls==[] and model.history_file_path==original_path
        else:
            print('OWNER_BYPASS_TITLE',calls,original_path,'->',model.history_file_path)
            pytest.fail('Actual auto_name_chat_history callback accepted Bob for Alice model state')
    finally: app.close()


def test_login_error_callback_clears_payload_and_command(env,monkeypatch):
    import json
    from test_ui import panel_app
    model=select(env);model._state={'session_id':'sess_test','turn_id':'t1','outcome':'requires_action'}
    model._pending_actions=[{'request_id':'r','turn_id':'t1','request':{'type':'browser_authentication','credential_origin':'https://example.test','fields':[{'id':'secret','label':'Password','type':'password','required':True}]}}]
    captured=[]
    def worker(command):
        captured.append(command)
        yield {'type':'error','message':'Synthetic acknowledgement lost'}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    app,panel,state=panel_app(model)
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='login')
    payload=json.dumps({'type':'browser_authentication','action':'submit','fields':[{'field_id':'secret','value':'dummy-secret-review'}]})
    try:
        result=asyncio.run(app.process_api(index,[None,'r',payload],state=state,request=gr.Request(session_hash='review-ui')))
        assert result['data'][0]==''
        assert 'dummy-secret-review' not in repr(result['data'])+repr(model.history)+repr(model._state)
        assert 'response' not in captured[0] and model._pending_actions
    finally: app.close()
