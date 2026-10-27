"""Gradio component and callback integration; no browser or live API claimed."""
import asyncio
import json
import xml.etree.ElementTree as ET
from types import SimpleNamespace
import gradio as gr
import pytest
from gradio.state_holder import SessionState
from modules.agent.ui import AgentPanel, ArtifactPanel, browser_form
from agent_fixtures import env, select, send, complete, request, settle_files


def artifact_rows(markup):
    return [[''.join(card.find('.//span[@class="model-file-name"]').itertext()), '', card.find('.//span[@class="model-file-size"]').text or '', (card.findtext('.//span[@class="model-file-state"]') or '') + (card.find('.//span[@class="model-file-error"]').text or '')] for card in ET.fromstring(markup).findall('button')]


def panel_app(model):
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State()
        chatbot=gr.Chatbot()
        status=gr.Markdown()
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components();panel.wire(current,chatbot,status)
    state=SessionState(app);state[current._id]=model
    return app,panel,state


def test_actual_component_output_shapes_and_no_input_file_bubbles(env,monkeypatch):
    complete(env,monkeypatch,True);model=select(env);send(env,model)
    app,panel,state=panel_app(model)
    assert len(panel.values(model))==len(panel.outputs)
    assert len(panel.values(None))==len(panel.outputs)
    assert len(panel.values(model,include_config=False))==len(panel.outputs)
    files=ArtifactPanel.values(model)
    assert len(files[2]['value'])==1 and model.chatbot==[['hello','Agent synthetic answer']]
    assert panel.artifacts.files.interactive is False
    assert isinstance(panel.artifacts.list, gr.HTML)
    assert panel.payload.type=='password' and panel.payload.visible is False
    app.close()


def test_login_form_escapes_external_labels_and_masks_every_field(env):
    model=select(env);model._pending_actions=[{'request_id':'request_one','turn_id':'turn_one','request':{
        'type':'browser_authentication','credential_origin':'https://example.com','reason':'<script>unsafe()</script>',
        'fields':[{'id':'email','type':'text','label':'<img src=x onerror=bad()>','required':True},{'id':'password','type':'password','label':'Password','required':True}],
        'options':[{'id':'password_method','label':'Password','field_ids':['email','password']}]}}]
    form,*buttons=browser_form(model,'request_one')
    assert '<script>' not in form and '<img src=' not in form and '&lt;script&gt;' in form
    assert form.count('type="password"')==2 and 'value="secret' not in form
    assert buttons[-1]['visible'] is True


def test_file_status_markup_escapes_names_types_and_errors(env):
    model=select(env)
    model._artifacts=[{'id':'one','name':'<img src=x onerror="bad()">&.txt',
                       'type':'<script>bad()</script>','status':'failed',
                       'error':'<svg onload="bad()"> & error','size':8}]
    markup=ArtifactPanel.values(model)[1]['value']
    assert '<img' not in markup and '<script' not in markup and '<svg onload' not in markup
    rows=artifact_rows(markup)
    assert rows[0][0]==model._artifacts[0]['name'][:-4]
    assert 'data-artifact-id="one"' in markup and 'data-file-action="retry"' in markup
    assert rows[0][3]=='下载失败，点击重试：'+model._artifacts[0]['error']


def test_card_native_download_and_retry_dom_contract():
    import subprocess, shutil
    from pathlib import Path
    result=subprocess.run([shutil.which('node') or 'node','tests/javascript/artifact-cards.test.cjs'],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_dropdown_revision_ignores_late_callback_and_send_freezes_visible_pair(env,monkeypatch):
    import threading
    complete(env,monkeypatch);model=select(env);send(env,model)
    app,panel,state=panel_app(model)
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='choose_settings')
    entered=threading.Event();release=threading.Event();original=model.set_agent_model
    def delayed(name,effort,revision=None,target=None):
        if revision==1:entered.set();assert release.wait(3)
        return original(name,effort,revision,target=target)
    monkeypatch.setattr(model,'set_agent_model',delayed)
    async def exercise():
        req=gr.Request(session_hash='choice-race')
        early=asyncio.create_task(app.process_api(index,[None,'gpt-6-sol','default',1,model.agent_choice_target],state=state,request=req))
        assert await asyncio.to_thread(entered.wait,3)
        await app.process_api(index,[None,'gpt-6-sol','high',2,model.agent_choice_target],state=state,request=req)
        release.set();stale=await early
        assert all(isinstance(value,dict) and value.get('__type__')=='update' and 'value' not in value for value in stale['data'])
        assert model.agent_model_choice==('gpt-6-sol','high')
        envelope=env.wrappers['transfer_input']('send current',model,'gpt-6.1-sol','medium',3,request=req)[0]
        assert original('gpt-6-sol','default',2) is None
        list(env.wrappers['predict'](model,envelope,model.chatbot,request=req))
        assert (model.model_name,model._reasoning)==('gpt-6.1-sol','medium')
    try:asyncio.run(exercise())
    finally:release.set();app.close()


def test_retry_listing_failure_returns_clickable_failed_card_then_can_retry(env,monkeypatch,tmp_path):
    from pathlib import Path
    import tempfile
    complete(env,monkeypatch);model=select(env);send(env,model)
    model._artifacts=[dict(id='file',name='same.txt',status='failed',size=1,session_id=model._state['session_id'],turn_id=model._state['turn_id'])]
    model._remember()
    path=Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-'))/'same.txt';path.write_text('x')
    calls=[]
    def worker(command):
        calls.append(command)
        if len(calls)==1:yield dict(type='error',message='listing unavailable')
        else:yield dict(type='result',artifacts=[dict(model._artifacts[0],status='ready',path=str(path),error=None)])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    app,panel,state=panel_app(model)
    indices={fn.fn.__name__:i for i,fn in enumerate(app.fns) if fn.fn}
    async def retry():
        result=await app.process_api(indices['retry_file'],[None,'file'],state=state,request=gr.Request(session_hash='ui'))
        while result['is_generating']:
            result=await app.process_api(indices['retry_file'],[None,'file'],state=state,request=gr.Request(session_hash='ui'),iterator=result['iterator'])
    try:
        asyncio.run(retry());settle_files(model)
        markup=ArtifactPanel.values(model)[1]['value']
        assert 'data-file-action="retry"' in markup and 'listing unavailable' in markup
        asyncio.run(retry());settle_files(model)
        assert model._artifacts[0]['status']=='ready' and len(calls)==2
    finally:app.close()


def test_older_completed_choice_response_cannot_overwrite_widgets_or_same_revision_send(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    app,panel,state=panel_app(model)
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='choose_settings')
    req=gr.Request(session_hash='late-response')
    early=asyncio.run(app.process_api(index,[None,'gpt-6-sol','default',1,model.agent_choice_target],state=state,request=req))
    later=asyncio.run(app.process_api(index,[None,'gpt-6-sol','high',2,model.agent_choice_target],state=state,request=req))
    assert panel.model not in app.fns[index].outputs and panel.reasoning not in app.fns[index].outputs
    assert len(early['data'])==len(later['data'])==2  # status + guarded selector receipt
    # Even a stale visible value submitted with an already-confirmed revision
    # cannot silently replace the latest pair stored by that revision.
    envelope=env.wrappers['transfer_input']('send',model,'gpt-6-sol','default',2,request=req)[0]
    list(env.wrappers['predict'](model,envelope,model.chatbot,request=req))
    assert (model.model_name,model._reasoning)==('gpt-6-sol','high')
    app.close()


def test_actual_gradio_diff_stream_removes_provisional_reference_rows(env,monkeypatch):
    from copy import deepcopy
    from pathlib import Path
    import shutil
    import subprocess
    from modules.model_capabilities import CapabilityUI
    ordinary=select(env,name='GPT3.5 Turbo')
    send(env,ordinary,'old one');send(env,ordinary,'old two')
    model=select(env,ordinary)
    user={'id':'u','type':'message','role':'user','content':[{'type':'input_text','text':'reference and new request'}]}
    answer={'id':'a','type':'message','role':'assistant','content':[{'type':'output_text','text':'completed answer'}]}
    def worker(command):
        if command['action']=='run':
            assert len(command['history_reference'])==4
            yield {'type':'progress','session_id':'s','turn_id':'t','outcome':'in_progress','history_authoritative':True,'items':[user]}
            yield {'type':'result','session_id':'s','turn_id':'t','outcome':'completed','sync_complete':True,'items':[user,answer]}
        elif command['action']=='download':yield {'type':'result','artifacts':[]}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    frames=[];expected=[]
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();prompt=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();selector=gr.Dropdown();marker=gr.HTML();button=gr.Button()
        caps=CapabilityUI([],selector,marker)
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components()
        projected = panel.wrap_predict(env.wrappers['predict'],caps)
        def capture(current_model, inputs, chatbot, request: gr.Request):
            from modules.agent.message_files import decode_rows
            for values in projected(current_model, inputs, chatbot, request=request):
                chat_value = values[0].get('value') if isinstance(values[0], dict) else values[0]
                expected.append(decode_rows(chat_value, model._conversation_id))
                yield values
        button.click(capture,[current,prompt,chat],[chat,status,*panel.outputs,*caps.outputs])
    state=SessionState(app);state[current._id]=model
    async def exercise():
        iterator=None
        while True:
            result=await app.process_api(0,[None,'new request',ordinary.chatbot],state=state,
                request=gr.Request(session_hash='real-stream'),session_hash='real-stream',iterator=iterator)
            frames.append({'generating':result['is_generating'],'data':deepcopy(result['data'])})
            if not result['is_generating']:
                expected.append(deepcopy(expected[-1]))
                break
            iterator=result['iterator']
    try:asyncio.run(exercise())
    finally:app.close()
    # Execute the installed Gradio browser client's actual splice-based decoder.
    client_source=None
    for path in (Path(gr.__file__).parent/'templates/frontend/assets').glob('index-*.js.map'):
        source_map=json.loads(path.read_text())
        for source in source_map.get('sourcesContent',[]):
            if source and 'function apply_diff_stream(' in source:
                client_source=source[source.index('function apply_diff_stream('):source.index('function submit(',source.index('function apply_diff_stream('))]
                break
        if client_source:break
    assert client_source,'Installed Gradio client source map is required for the streaming regression'
    script=client_source+'''
const frames=JSON.parse(require('fs').readFileSync(0,'utf8'));
const pending={};const visible=[];let chat=[];
for(const frame of frames){
  const data={data:frame.data};
  if(frame.generating)apply_diff_stream(pending,'event',data);
  const value=data.data[0];
  if(Array.isArray(value))chat=value;
  else if(value && Object.hasOwn(value,'value'))chat=value.value;
  visible.push(JSON.parse(JSON.stringify(chat)));
}
process.stdout.write(JSON.stringify(visible));
'''
    result=subprocess.run([shutil.which('node') or 'node','-e',script],input=json.dumps(frames),text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    from modules.agent.message_files import decode_rows
    assert [decode_rows(rows,model._conversation_id) for rows in json.loads(result.stdout)]==expected
    assert expected[-1]==[['reference and new request','completed answer']]


def test_no_login_submit_without_known_origin(env):
    model=select(env);model._pending_actions=[{'request_id':'request_one','request':{'type':'browser_authentication','fields':[]}}]
    form,*buttons=browser_form(model)
    assert buttons[-1]['visible'] is False


def test_gradio_callback_updates_same_session_and_restores_on_failure(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    app,panel,state=panel_app(model)
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='choose_settings')
    result=asyncio.run(app.process_api(index,[None,'gpt-6-sol','high',1,model.agent_choice_target],state=state,request=gr.Request(session_hash='ui-test')))
    assert app.fns[index].outputs == [panel.activity,panel.choice_result]
    assert not result['data'][0]['visible'] and result['data'][0]['value']=='' and model.agent_model_choice==('gpt-6-sol','high') and model._state['session_id']=='sess_test'
    assert model.model_name!='gpt-6-sol'
    send(env,model,'apply on send')
    assert model.model_name=='gpt-6-sol'
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([{'type':'error','message':'rejected'}]))
    result=asyncio.run(app.process_api(index,[None,'bad','low',2,model.agent_choice_target],state=state,request=gr.Request(session_hash='ui-test')))
    assert not result['data'][0]['visible'] and model.model_name=='gpt-6-sol'
    output=send(env,model,'must not submit')
    assert '消息未发送' in output[-1][1] and model.model_name=='gpt-6-sol'
    app.close()


def test_gradio_login_callback_clears_payload_and_no_saved_secret(env,monkeypatch):
    model=select(env);model._state={'session_id':'sess_one','turn_id':'turn_one','outcome':'requires_action'}
    model._pending_actions=[{'request_id':'request_one','turn_id':'turn_one','request':{'type':'browser_authentication','credential_origin':'https://example.com','fields':[{'id':'email','label':'Email','required':True,'type':'text'}]}}]
    commands=[]
    def worker(command):
        commands.append(command)
        assert command['action']=='browser_response'
        yield {'type':'result','accepted':True}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    app,panel,state=panel_app(model)
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='login')
    payload=json.dumps({'type':'browser_authentication','action':'submit','fields':[{'field_id':'email','value':'private@example.com'}]})
    result=asyncio.run(app.process_api(index,[None,'request_one',payload],state=state,request=gr.Request(session_hash='ui-test')))
    assert result['data'][0]=='' and model._pending_actions==[]
    assert 'private@example.com' not in repr(model.history) and 'private@example.com' not in repr(model._state)
    assert 'response' not in commands[0]  # The same command dict is cleared after submission.
    app.close()


def test_live_updates_do_not_overwrite_unsaved_tool_form(env):
    model=select(env)
    app,panel,state=panel_app(model)
    values=panel.values(model,include_config=False)
    for component in panel.config_inputs:
        assert 'value' not in values[panel.outputs.index(component)]
        assert values[panel.outputs.index(component)]['interactive'] is (component not in (panel.discovery, panel.programmatic))
    app.close()


def test_callback_owner_validation_is_gradio_injected(env,monkeypatch):
    complete(env,monkeypatch);model=select(env,username='alice')
    app,panel,state=panel_app(model)
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='choose_settings')
    with pytest.raises(gr.Error):
        asyncio.run(app.process_api(index,[None,'gpt-6-sol','high',1,model.agent_choice_target],state=state,request=gr.Request(username='bob',session_hash='ui-test')))
    app.close()


def test_history_observer_waiting_permission_exposes_same_main_stop(env,monkeypatch):
    from modules.model_capabilities import CapabilityUI
    model=select(env);model._state={'session_id':'sess_test','turn_id':'turn_one','generation':'g','outcome':'incomplete'}
    model._session_settings=model._current_settings();model._needs_sync=True
    from threading import Event
    release = Event()
    calls=[]
    def worker(command):
        calls.append(command['action'])
        if command['action']=='observe':
            yield {'type':'progress','session_id':'sess_test','turn_id':'turn_one','outcome':'requires_action','required_actions':[{'request_id':'req','turn_id':'turn_one','request':{'type':'browser_origin_access','origin':'https://example.com'}}]}
            assert release.wait(5)
            yield {'type':'result','session_id':'sess_test','turn_id':'turn_one','outcome':'cancelled','required_actions':[]}
        elif command['action']=='cancel':
            release.set()
            yield {'type':'result','outcome':'cancel_requested'}
        elif command['action']=='download':yield {'type':'result','artifacts':[]}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chat=gr.Chatbot();status=gr.Markdown();main_send=gr.Button();main_stop=gr.Button(visible=False);selector=gr.Dropdown();marker=gr.HTML()
        caps=CapabilityUI([],selector,marker,main_send,main_stop);caps.wire(current,chat)
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components();panel.wire(current,chat,status,caps)
        gr.Button().click(panel.observe_history, [current], panel.history_outputs, queue=False)
        main_stop.click(env.wrappers['interrupt'],[current],[status],queue=False)
    state=SessionState(app);state[current._id]=model
    indices={fn.fn.__name__:i for i,fn in enumerate(app.fns) if fn.fn}
    async def exercise():
        req=gr.Request(session_hash='ui')
        result=await app.process_api(indices['observe_history'],[None],state=state,request=req)
        assert all(value == gr.update() for value in result['data'])
        result=await app.process_api(indices['observe_history'],[None],state=state,request=req,iterator=result['iterator'])
        assert result['data'][2+caps.stream_outputs.index(main_stop)]['visible']
        assert model._pending_actions
        await app.process_api(indices['interrupt'],[None],state=state,request=req)
        assert 'cancel' in calls
        results=[]
        while result['is_generating']:
            result=await app.process_api(indices['observe_history'],[None],state=state,request=req,iterator=result['iterator'])
            results.append(result)
        updates=[entry['data'][2+caps.stream_outputs.index(main_stop)] for entry in results if isinstance(entry['data'][2+caps.stream_outputs.index(main_stop)],dict)]
        assert any(update.get('visible') is False for update in updates)
    try:asyncio.run(exercise())
    finally:release.set();app.close()


def test_independent_file_refresh_exposes_progress_after_predict_queue_ends(env,monkeypatch):
    from threading import Event
    from pathlib import Path
    import tempfile, time
    from modules.model_capabilities import CapabilityUI
    prepared_seen, first_ready_seen = Event(), Event()
    model=select(env);path=Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-'))/'one.txt';path.write_text('1')
    def worker(command):
        if command['action']=='run':yield dict(type='result',session_id='sess_test',turn_id='turn_one',outcome='completed',text='answer')
        elif command['action']=='download':
            records=[dict(id='a',session_id='sess_test',turn_id='turn_one',name='one.txt',size=1,status='preparing'),dict(id='b',session_id='sess_test',turn_id='turn_one',name='two.txt',size=2,status='preparing')]
            yield dict(type='progress',artifacts=records);assert prepared_seen.wait(5)
            records=[dict(records[0],status='ready',path=str(path)),records[1]]
            yield dict(type='progress',artifacts=records);assert first_ready_seen.wait(5)
            yield dict(type='result',artifacts=[records[0],dict(records[1],status='failed',error='unavailable')])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();prompt=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();send_button=gr.Button();stop=gr.Button();selector=gr.Dropdown();marker=gr.HTML()
        caps=CapabilityUI([],selector,marker,send_button,stop);caps.wire(current,chat)
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components();panel.wire(current,chat,status,caps)
        send_button.click(panel.wrap_predict(env.wrappers['predict'],caps),[current,prompt,chat],[chat,status,*panel.outputs,*caps.outputs])
    state=SessionState(app);state[current._id]=model
    indices={fn.fn.__name__:i for i,fn in enumerate(app.fns) if fn.fn}
    async def exercise():
        req=gr.Request(session_hash='ui');result=await app.process_api(indices['predict_with_ui'],[None,'files',[]],state=state,request=req)
        while result['is_generating']:
            result=await app.process_api(indices['predict_with_ui'],[None,'files',[]],state=state,request=req,iterator=result['iterator'])
        assert not prepared_seen.is_set() and not model._background_busy
        assert state.blocks_config.blocks[send_button._id].interactive
        async def read_files(expect):
            deadline=time.monotonic()+3
            while True:
                frame=await app.process_api(indices['refresh_files'],[None],state=state,request=req)
                wire=json.loads(frame['data'][0]);assert len(wire['updates'])==4
                rows=artifact_rows(wire['updates'][1]['value'])
                if expect(rows):return wire,rows
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
        wire,rows=await read_files(lambda rows:len(rows)==2 and all(row[3]=='准备中' for row in rows))
        assert wire['generation']==model._state['generation'];prepared_seen.set()
        wire,rows=await read_files(lambda rows:len(rows)==2 and rows[0][3]=='' and rows[1][3]=='准备中')
        assert len(wire['updates'][2]['value'])==1 and wire['updates'][2]['value'][0]['url'].startswith('/file=')
        first_ready_seen.set()
        await read_files(lambda rows:len(rows)==2 and rows[1][3].startswith('下载失败'))
    try:asyncio.run(exercise())
    finally:prepared_seen.set();first_ready_seen.set();settle_files(model);app.close()


def test_completed_wrapped_send_explicitly_unlocks_agent_selectors(env,monkeypatch):
    from test_runtime import message
    from modules.model_capabilities import CapabilityUI
    from threading import Event
    release = Event()
    model=select(env);downloads=[]
    def worker(command):
        if command['action']=='run':
            yield dict(type='progress',session_id='s',turn_id='t',outcome='in_progress')
            yield dict(type='result',session_id='s',turn_id='t',outcome='completed',text='answer',sync_complete=True,
                       items=[message('u','hello','t',role='user'),message('a','answer','t')])
        elif command['action']=='download':
            downloads.append('started')
            yield dict(type='progress',artifacts=[])
            assert release.wait(5)
            yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();text=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();selector=gr.Dropdown();marker=gr.HTML()
        caps=CapabilityUI([],selector,marker);caps.wire(current,chat)
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components()
        event=gr.Button().click(panel.wrap_predict(env.wrappers['predict'],caps,compact=True),
            [current,text,chat],[chat,status,*panel.stream_outputs,*caps.stream_outputs],queue=True)
    state=SessionState(app);state[current._id]=model
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='predict_with_ui')
    async def exercise():
        inputs=[None,'hello',[]];req=gr.Request(session_hash='ui')
        result=await app.process_api(index,inputs,state=state,request=req)
        # File work no longer reserves the completed main conversation.
        while result['is_generating']:
            result=await app.process_api(index,inputs,state=state,request=req,iterator=result['iterator'])
        assert not model._background_busy
        assert all(state.blocks_config.blocks[c._id].interactive is True for c in (panel.model,panel.reasoning))
        assert not release.is_set(); release.set()
    try:asyncio.run(exercise())
    finally:release.set();app.close()


def test_prompt_change_after_session_is_rejected_and_effective_value_kept(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();prompt=gr.Textbox();status=gr.Markdown()
        prompt.change(env.wrappers['set_system_prompt'],[current,prompt],[status])
    state=SessionState(app);state[current._id]=model
    before=model.system_prompt
    with pytest.raises(gr.Error,match='已固定'):
        asyncio.run(app.process_api(0,[None,'new instructions'],state=state,request=gr.Request(session_hash='ui')))
    assert model.system_prompt==before
    app.close()


@pytest.mark.parametrize('final_status',['ready','failed'])
def test_single_file_retry_finishes_independently_without_losing_other_files(env,monkeypatch,final_status):
    from pathlib import Path
    from threading import Event
    import tempfile
    complete(env,monkeypatch);model=select(env);send(env,model)
    path=Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-'))/'retry.txt';path.write_text('x')
    identity=dict(session_id=model._state['session_id'],turn_id=model._state['turn_id'])
    existing=dict(id='other',name='other.txt',status='ready',path=str(path),size=1,**identity)
    model._artifacts=[existing,dict(id='retry',name='retry.txt',status='failed',error='unavailable',**identity)];model._remember()
    release=Event();calls=[]
    def worker(command):
        calls.append(command);assert command['action']=='download' and command['artifact_ids']==['retry']
        record=dict(id='retry',name='retry.txt',status='preparing',size=1,**identity)
        yield dict(type='progress',artifacts=[record]);assert release.wait(5)
        final=dict(record,status=final_status)
        if final_status=='ready':final['path']=str(path)
        else:final['error']='still unavailable'
        yield dict(type='result',artifacts=[final])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    app,panel,state=panel_app(model)
    indices={fn.fn.__name__:i for i,fn in enumerate(app.fns) if fn.fn}
    async def exercise():
        req=gr.Request(session_hash='ui');result=await app.process_api(indices['retry_file'],[None,'retry'],state=state,request=req)
        while result['is_generating']:
            result=await app.process_api(indices['retry_file'],[None,'retry'],state=state,request=req,iterator=result['iterator'])
        rows=artifact_rows(ArtifactPanel.values(model)[1]['value'])
        assert rows[0][0]=='other' and rows[0][3]=='' and rows[1][3]=='准备中'
        assert not release.is_set();release.set();settle_files(model)
        frame=await app.process_api(indices['refresh_files'],[None],state=state,request=req)
        rows=artifact_rows(json.loads(frame['data'][0])['updates'][1]['value'])
        assert rows[0][0]=='other' and rows[0][3]==''
        assert rows[1][3]=='' if final_status=='ready' else 'still unavailable' in rows[1][3]
    try:asyncio.run(exercise())
    finally:release.set();settle_files(model);app.close()
    assert len(calls)==1 and model._state['session_id']==identity['session_id']


def test_predict_final_frame_then_switch_then_eof_is_noop(env):
    model=select(env)
    app,panel,state=panel_app(model)
    caps=SimpleNamespace(outputs=[],stream_outputs=[],values=lambda model:[],stream_values=lambda model:[])
    def source(*args,**kwargs):
        yield model.chatbot,'final'
    stream=panel.wrap_predict(source,caps)(model,'input',[],request=request())
    next(stream)
    next(stream)  # final frame has been delivered; iterator not resumed to EOF
    model.retire()
    tail=next(stream)
    assert all(value==gr.update() for value in tail)
    with pytest.raises(StopIteration):next(stream)


def test_header_wrapper_preserves_noop_when_old_agent_view_retires(env):
    model=select(env)
    panel=AgentPanel()
    result=panel.status_callback(lambda model:gr.update(),header=True)(model)
    assert result==(gr.update(),gr.update())


def test_ui_generators_never_yield_while_holding_model_lock():
    import ast
    from pathlib import Path
    tree=ast.parse((Path(__file__).parents[2]/'modules/agent/ui.py').read_text())
    for node in ast.walk(tree):
        if isinstance(node,ast.With) and any('_lock' in ast.unparse(item.context_expr) for item in node.items):
            assert not any(isinstance(child,(ast.Yield,ast.YieldFrom)) for child in ast.walk(node))


def test_history_final_frame_then_switch_then_eof_is_noop(env,monkeypatch):
    from modules.agent.tasks import TASKS
    model=select(env);app,panel,state=panel_app(model)
    task=SimpleNamespace(subscribe=lambda view:iter([(view.chatbot,'done')]))
    monkeypatch.setattr(TASKS,'find',lambda *args:task)
    stream=panel.observe_history(model,request=request())
    next(stream);next(stream);next(stream)
    model.retire()
    assert all(value==gr.update() for value in next(stream))
    with pytest.raises(StopIteration):next(stream)


def test_retry_first_frame_stale_is_noop(env,monkeypatch):
    model=select(env);app,panel,state=panel_app(model)
    def retry(*args,**kwargs):
        model.retire()
        yield model.chatbot,'obsolete'
    monkeypatch.setattr(model,'retry_artifact',retry)
    callback=next(fn.fn for fn in app.fns if fn.fn and fn.fn.__name__=='retry_file')
    stream=callback(model,'artifact',request=request())
    assert all(value==gr.update() for value in next(stream))
    with pytest.raises(StopIteration):next(stream)


def test_predict_final_frame_then_new_operation_cannot_replay_old_final(env):
    model=select(env);app,panel,state=panel_app(model)
    caps=SimpleNamespace(outputs=[],stream_outputs=[],values=lambda model:[],stream_values=lambda model:[])
    def source(*args,**kwargs):yield model.chatbot,'final'
    stream=panel.wrap_predict(source,caps)(model,'input',[],request=request())
    next(stream);next(stream)
    model._predict_error_operation='next operation'
    model._state['generation']='next generation'
    assert all(value==gr.update() for value in next(stream))
    with pytest.raises(StopIteration):next(stream)
    assert model._predict_error_operation=='next operation'
