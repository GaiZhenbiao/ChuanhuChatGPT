"""No-network checks for quiet UI, suffixes and read-only history observation."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import gradio as gr
import pytest
from modules.agent.ui import AgentPanel, ArtifactPanel, REASONING_CHOICES, split_filename, i18n
from modules.agent.file_icons import file_type_label
from agent_fixtures import env, select, send, complete, request, settle_files


@pytest.mark.parametrize('name,stem,suffix', [
    ('很长的文件名😊.txt', '很长的文件名😊', '.txt'),
    ('archive.TAR.GZ', 'archive', '.TAR.GZ'),
    ('definition.d.ts', 'definition', '.d.ts'),
    ('report.final.v2.pdf','report.final.v2','.pdf'),
    ('.env', '.env', ''), ('.config.json', '.config', '.json'),
    ('无后缀', '无后缀', ''), ('trailing.', 'trailing.', ''),
])
def test_single_line_basename_and_extension_size_metadata_preserve_download_identity(env,name,stem,suffix):
    assert split_filename(name)==(stem,suffix)
    model=select(env);model._artifacts=[dict(id='stable-file',name=name,status='ready',path='/tmp/synthetic',size=1)]
    card=ET.fromstring(ArtifactPanel.values(model)[1]['value']).find('button')
    assert card.get('data-artifact-id')=='stable-file' and name in card.get('aria-label')
    label=card.find('.//span[@class="model-file-name"]')
    assert label.get('title')==name and ''.join(label.itertext())==stem
    assert label.find('span[@class="model-file-basename"]').text==stem
    assert label.find('span[@class="model-file-extension"]') is None
    meta=card.find('.//span[@class="model-file-meta"]')
    assert ''.join(meta.itertext())==file_type_label(name)+' · 0.00 KB'
    assert ArtifactPanel.values(model)[2]['value']==['/tmp/synthetic']


def test_supported_none_restored_and_send_snapshot_preserves_explicit_effort(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env)
    model.set_agent_model('gpt-6-sol','none',1)
    assert model.agent_model_choice==('gpt-6-sol','none')
    envelope=env.wrappers['transfer_input']('first',model,'gpt-6-sol','none',2,request=request())[0]
    list(env.wrappers['predict'](model,envelope,[],request=request()))
    assert next(c for c in calls if c['action']=='run')['reasoning'] == 'none'
    model._session_settings['reasoning']='none'
    model._pending_model_settings=('gpt-6-sol','none');model._remember()
    model._restore_binding()
    assert model._reasoning == 'none' and model._session_settings['reasoning'] == 'none'
    assert model.agent_model_choice==('gpt-6-sol','none')


def test_history_observer_only_reads_and_old_stream_cannot_overwrite_new_history(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    saved=model.history_file_path;model.load_chat_history(saved)
    calls=[];closed=[]
    def worker(command):
        calls.append(command['action'])
        assert command['action']=='observe'
        try:
            yield dict(type='progress',session_id='sess_test',turn_id='old',outcome='in_progress',sync_complete=True,items=[])
            assert command['_observe_cancel']()
            yield dict(type='result',session_id='sess_test',turn_id='old',outcome='completed',sync_complete=True,
                       items=[dict(id='old-answer',type='message',role='assistant',content=[dict(type='output_text',text='stale answer')])])
        finally:closed.append(True)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    observer=model.observe_history();next(observer)
    # Navigation is allowed while merely observing; a new epoch cancels even
    # selection of the same trusted history, before its next SSE response.
    model.load_chat_history(saved)
    preserved=deepcopy((model.chatbot,model.history,model._conversation_id))
    assert list(observer)==[] and closed and calls==['observe']
    assert (model.chatbot,model.history,model._conversation_id)==preserved
    assert not model._running


def test_unbound_history_does_not_adopt_cloud_session(env,monkeypatch):
    model=select(env);calls=[]
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:calls.append(command) or iter(()))
    assert list(model.observe_history())==[] and calls==[]


def test_error_dedup_cancellation_and_cleanup_before_gradio_error(env):
    model=select(env);panel=AgentPanel();events=[]
    def operation(current):
        current._running=True
        try:
            current._record_message_error(dict(type='error',message='cancelled preparation',preparation={'outcome':'cancelled'}))
            assert not current.take_ui_error()
            current._record_message_error(dict(type='result',outcome='failed',message='real failure'))
            current._record_message_error(dict(type='result',outcome='failed',message='real failure'))
        finally:
            current._running=False
            events.append('unlocked')
        yield current.chatbot, 'ignored status'
    iterator=panel.status_callback(operation,1)(model)
    final=next(iterator)
    assert events==['unlocked'] and not model._running and not final[1]['visible']
    assert list(iterator)==[]
    model.complete_error_operation(model._state.get('generation'))
    with pytest.raises(gr.Error,match='real failure'):
        panel.emit_ui_error(model,gr.Request(session_hash='synthetic-error'))
    assert model.take_ui_error()==''


def test_login_failure_clears_payload_before_error_and_preserves_request(env,monkeypatch):
    import asyncio,json
    from gradio.state_holder import SessionState
    model=select(env);model._state={'session_id':'session','turn_id':'turn','outcome':'requires_action'}
    model._pending_actions=[dict(request_id='request',turn_id='turn',request=dict(type='browser_authentication',fields=[]))]
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([dict(type='error',message='synthetic login failure')]))
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chat=gr.Chatbot();status=gr.Markdown()
        panel=AgentPanel();panel.selectors();panel.settings_components();panel.output_components();panel.wire(current,chat,status)
    state=SessionState(app);state[current._id]=model
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='login')
    async def exercise():
        inputs=[None,'request',json.dumps({'type':'browser_authentication','action':'submit','fields':[{'field_id':'test','value':'synthetic-secret'}]})]
        frame=await app.process_api(index,inputs,state=state,request=gr.Request(session_hash='synthetic-login'))
        assert frame['data'][0]=='' and not frame['data'][1]['visible']
        assert model._pending_actions and 'synthetic-secret' not in repr(model._state)+repr(model.history)
        complete=await app.process_api(index,inputs,state=state,request=gr.Request(session_hash='synthetic-login'),iterator=frame['iterator'])
        assert not complete['is_generating']
        with pytest.raises(gr.Error,match='synthetic login failure'):
            panel.emit_ui_error(model,gr.Request(session_hash='synthetic-login'))
        assert not model.take_ui_error()
    try:asyncio.run(exercise())
    finally:app.close()


def test_failed_stop_reports_error_after_pending_actions_cleanup(env,monkeypatch):
    model=select(env);panel=AgentPanel()
    model._state=dict(session_id='s',turn_id='t',generation='g',outcome='requires_action')
    model._pending_actions=[{'request_id':'synthetic'}]
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([dict(type='error',message='synthetic stop failure')]))
    first=panel.status_callback(lambda current:current.interrupt(),header=True)(model)
    assert first[0]=='' and not first[1]['visible'] and not model._pending_actions
    assert not model._cancel_sent
    with pytest.raises(gr.Error,match='synthetic stop failure'):
        panel.emit_stop_error(model,gr.Request(session_hash='synthetic-stop'))


def test_real_gradio_client_contract_routes_multiframe_events_through_streaming_queue():
    """4.29 skip_queue completes after one POST response regardless of is_generating."""
    import json
    from pathlib import Path
    source=None
    for path in (Path(gr.__file__).parent/'templates/frontend/assets').glob('index-*.js.map'):
        for candidate in json.loads(path.read_text()).get('sourcesContent',[]):
            if candidate and 'skip_queue' in candidate and 'function submit(' in candidate:
                source=candidate;break
        if source:break
    assert source and 'skip_queue' in source
    # Execute the exact shipped JS client with deterministic mock transport.
    # No browser substitute or backend iterator pumping is involved here.
    import re,subprocess,shutil
    client_source=re.sub(r'export \{[\s\S]*?\};\s*$', '', source)
    harness=client_source+r"""
async function exercise(queue) {
  const events=[],posts=[];
  const self={options:{},app_reference:'offline',session_hash:'synthetic',
    config:{root:'http://synthetic.invalid',version:'4.29.0',protocol:'sse_v2',enable_queue:true,dependencies:[{queue,zerogpu:false}]},
    api_info:{unnamed_endpoints:{0:{}}},api_map:{},stream_status:{open:false},pending_stream_messages:{},pending_diff_streams:{},event_callbacks:{},unclosed_events:new Set(),
    handle_blob:async (root,data)=>data,
    post_data:async (url,payload)=>{posts.push(url);return url.includes('/run/') ? [{data:['initial'],is_generating:true},200] : [{event_id:'synthetic-event'},200]},
    open_stream(){this.stream_status.open=true;}
  };
  submit.call(self,0,[]).on('data',e=>events.push(['data',e.data])).on('status',e=>events.push(['status',e.stage,e.message]));
  await new Promise(resolve=>setImmediate(resolve));
  if(queue){
    const callback=self.event_callbacks['synthetic-event'];
    if(!callback)throw Error('No queued event callback');
    await callback({msg:'process_generating',success:true,output:{data:['initial']}});
    await callback({msg:'process_generating',success:true,output:{data:[[['replace',[],'cleanup']]]}});
    await callback({msg:'process_completed',success:false,output:{error:'synthetic failure after cleanup'}});
  }
  return {events,posts};
}
(async()=>{process.stdout.write(JSON.stringify({single:await exercise(false),stream:await exercise(true)}));})().catch(e=>{console.error(e);process.exit(1);});
"""
    run=subprocess.run([shutil.which('node') or 'node','-e',harness],capture_output=True,text=True,timeout=15)
    assert run.returncode==0,run.stderr
    evidence=json.loads(run.stdout)
    assert [e[1] for e in evidence['single']['events'] if e[0]=='data']==[['initial']]
    assert evidence['single']['events'][-1][1]=='complete'
    assert [e[1] for e in evidence['stream']['events'] if e[0]=='data']==[['initial'],['cleanup']]
    assert evidence['stream']['events'][-1]==['status','error','synthetic failure after cleanup']
    assert '/queue/join' in evidence['stream']['posts'][0]

    import ast
    tree=ast.parse((Path(__file__).resolve().parents[2]/'ChuanhuChatbot.py').read_text())
    observer_chains=[ast.unparse(node) for node in ast.walk(tree) if isinstance(node,ast.Expr) and 'agent_panel.observe_history' in ast.unparse(node)]
    assert any(text.startswith('demo.load(') for text in observer_chains)
    assert any(text.startswith('model_select_dropdown.input(') for text in observer_chains)
    assert any(text.startswith('historyIntentBtn.click(') for text in observer_chains)


def test_each_user_artifact_retry_persists_its_own_failure(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    model._artifacts=[dict(id='file',session_id=model._state['session_id'],turn_id=model._state['turn_id'],name='synthetic.txt',status='failed')]
    model._remember()
    def worker(command):
        yield dict(type='progress',artifacts=[dict(model._artifacts[0],status='preparing')])
        yield dict(type='error',message='same timeout')
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    from modules.agent.file_jobs import jobs_for
    for index in range(2):
        list(model.retry_artifact('file', error_operation=f'retry-{index}'))
        settle_files(model)
        assert model._artifacts[0]['status']=='failed' and model._artifacts[0]['error']=='same timeout'
    attempts=[job for job in jobs_for(model._store(),model._owner,model._conversation_id) if job['artifact_ids']==['file']]
    assert len(attempts)==2 and all(job['error']=='same timeout' for job in attempts)


def test_stop_before_snapshot_waits_for_exact_turn_then_submits_cancel(env,monkeypatch):
    model=select(env);model._state=dict(session_id='s',generation='g',outcome='incomplete');model._needs_sync=True
    model.interrupt();calls=[]
    def worker(command):
        calls.append(command)
        if command['action']=='observe':
            yield dict(type='progress',session_id='s',turn_id='found-turn',outcome='in_progress',sync_complete=True,items=[])
            yield dict(type='result',session_id='s',turn_id='found-turn',outcome='cancelled',sync_complete=True,items=[])
        elif command['action']=='cancel':yield dict(type='result',outcome='cancel_requested')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    list(model.observe_history())
    cancel=next(c for c in calls if c['action']=='cancel')
    assert cancel['session_id']=='s' and cancel['turn_id']=='found-turn'
    assert model._state['outcome']=='cancelled' and not model.take_ui_error()


def test_retired_observer_never_emits_final_agent_ui_frame(env,monkeypatch):
    from modules.model_capabilities import CapabilityUI
    model=select(env);model._state=dict(session_id='s',turn_id='t',generation='g',outcome='incomplete');model._needs_sync=True
    model._session_settings=model._current_settings()
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([dict(type='result',session_id='s',turn_id='t',outcome='completed',sync_complete=True,items=[])]))
    with gr.Blocks(analytics_enabled=False) as app:
        state=gr.State();chat=gr.Chatbot();status=gr.Markdown();caps=CapabilityUI([],gr.Dropdown(),gr.HTML())
        panel=AgentPanel();panel.selectors();panel.settings_components();panel.output_components();panel.wire(state,chat,status,caps)
    try:
        iterator=panel.observe_history(model,gr.Request(session_hash='synthetic-history'))
        assert all(isinstance(value,dict) and value==gr.update() for value in next(iterator))
        next(iterator);model._retired=True
        tail=list(iterator)
        assert len(tail)==1 and all(value==gr.update() for value in tail[0])
    finally:app.close()


def test_error_outbox_cannot_drain_unfinished_operation(env):
    model=select(env);model._state=dict(generation='g')
    model.record_ui_error('retry failure',operation='active-retry')
    model.complete_error_operation('successful-send')
    assert model.take_completed_ui_errors()==''
    assert model.has_ui_error('active-retry')
    model.complete_error_operation('active-retry')
    assert model.take_completed_ui_errors()=='retry failure'
    assert model.take_completed_ui_errors()==''


def test_agent_placeholder_uses_original_supplied_avatar_and_precedes_chuanhu(env):
    models=env.presets.ONLINE_MODELS
    assert models.index('OpenAI Agent')==models.index('川虎助理')-1
    placeholder=env.presets.MODEL_METADATA['OpenAI Agent']['placeholder']
    assert placeholder['logo']=='file=web_assets/model_logos/codex-color.png'
    import hashlib
    assert hashlib.sha256((Path(__file__).resolve().parents[2]/'web_assets/model_logos/codex-color.png').read_bytes()).hexdigest()=='325bd64b65331712cdfcceaf0b6f8d678952257ad3f131290fa2ac434009e5cf'


def test_tool_input_javascript_ignores_appended_gradio_output_values(env):
    import subprocess,json
    with gr.Blocks(analytics_enabled=False) as app:
        model=gr.State();chat=gr.Chatbot();status=gr.Markdown();panel=AgentPanel()
        panel.selectors();panel.settings_components();panel.output_components();panel.wire(model,chat,status)
    script=next(fn.js for fn in app.fns if fn.fn and fn.fn.__name__=='choose_tools')
    values=[None,True,True,True,'live','',True,False,True,True,[],'[]',0,'conversation','previous-status-output']
    run=subprocess.run(['node','-e','global.window={}; const fn='+script+'; console.log(JSON.stringify(fn(...'+json.dumps(values)+')));'],capture_output=True,text=True,check=True)
    returned=json.loads(run.stdout)
    assert returned[-2:]==[1,'conversation'] and len(returned)==14
    app.close()


def test_send_javascript_ignores_appended_outputs_and_keeps_tool_revision():
    import ast,subprocess,json
    tree=ast.parse((Path(__file__).resolve().parents[2]/'ChuanhuChatbot.py').read_text())
    assignment=next(node for node in ast.walk(tree) if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='transfer_input_args' for t in node.targets))
    script=next(k.value.value for k in assignment.value.keywords if k.arg=='js')
    values=['task',None,'gpt-6-astra','default',0,[],True,True,True,'live','',True,False,True,True,[],'[]','instructions','conversation',0,None,'previous-draft',True,False]
    code='global.window={chuanhuAgentToolRevision:3}; global.document={querySelector:()=>null}; const fn='+script+'; console.log(JSON.stringify(fn(...'+json.dumps(values)+')));'
    run=subprocess.run(['node','-e',code],capture_output=True,text=True,check=True)
    returned=json.loads(run.stdout)
    assert returned[-3:]==['instructions','conversation',3] and len(returned)==20
    chains=[ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Expr)]
    assert any('submit(**transfer_input_args).success(**submission_ui_args).success(**chatgpt_predict_args)' in text for text in chains)
    assert any('click(**transfer_input_args).success(**submission_ui_args).success(**chatgpt_predict_args' in text for text in chains)


def wrapped_send(env,model,text):
    from modules.model_capabilities import CapabilityUI
    panel=AgentPanel();panel.values=lambda *a,**kw:[]
    capabilities=SimpleNamespace(values=lambda *a,**kw:[])
    envelope=env.wrappers['transfer_input'](text,model,request=request())[0]
    list(panel.wrap_predict(env.wrappers['predict'],capabilities)(model,envelope,model.chatbot,request=request()))
    return panel


def test_model_update_rejection_rolls_back_draft_and_reports_once(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    previous=deepcopy((model._state,model.history,model.chatbot));calls=[]
    def worker(command):
        calls.append(command['action']);assert command['action']=='update'
        yield dict(type='error',message='update rejected')
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model.set_agent_model('gpt-6-sol','high')
    panel=wrapped_send(env,model,'preserve this draft')
    assert calls==['update'] and (model._state,model.history)==previous[:2]
    assert model.chatbot==previous[2]+[['preserve this draft','']]  # Keep the displayed local message copyable.
    assert not model._draft_submitted and not model._running
    with pytest.raises(gr.Error,match='update rejected'):panel.emit_ui_error(model,request())
    panel.emit_ui_error(model,request())
    assert not model._ui_errors and not model._ui_error_outbox


def test_recovery_then_new_run_failure_uses_one_ui_operation(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model);model._needs_sync=True
    old_generation=model._state['generation'];calls=[]
    def worker(command):
        calls.append(command['action'])
        if command['action']=='recover':
            yield dict(type='result',session_id='sess_test',turn_id=model._state['turn_id'],outcome='completed',sync_complete=True,items=[dict(id='u',type='message',role='user',content=[dict(type='input_text',text='hello')]),dict(id='a',type='message',role='assistant',content=[dict(type='output_text',text='Agent synthetic answer')])])
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        elif command['action']=='run':yield dict(type='error',message='new run failed',outcome='failed')
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    panel=wrapped_send(env,model,'next task')
    assert 'recover' in calls and 'run' in calls and model._state['generation']!=old_generation
    with pytest.raises(gr.Error,match='new run failed'):panel.emit_ui_error(model,request())
    panel.emit_ui_error(model,request())
    assert not model._ui_errors and not model._ui_error_outbox


def test_connection_mismatch_observer_early_error_receipt(env):
    from modules.model_capabilities import CapabilityUI
    model=select(env);model._needs_sync=True;model._connection_mismatch=True
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chat=gr.Chatbot();status=gr.Markdown();panel=AgentPanel()
        panel.selectors();panel.settings_components();panel.output_components();cap=SimpleNamespace(outputs=[],values=lambda *a:[],stream_outputs=[],stream_values=lambda *a:[])
        panel.wire(current,chat,status,cap)
    panel.values=lambda *a,**kw:[]
    panel.stream_values=lambda *a,**kw:[]
    list(panel.observe_history(model,request()))
    with pytest.raises(gr.Error,match='连接配置'):panel.emit_ui_error(model,request())
    panel.emit_ui_error(model,request());app.close()


def test_real_queue_duplicate_predict_completes_noop_and_never_runs_twice(env,monkeypatch):
    import asyncio,threading,time,httpx
    from gradio.routes import App
    from modules.model_capabilities import CapabilityUI
    model=select(env);entered=threading.Event();release=threading.Event();calls=[]
    def worker(command):
        calls.append(command['action'])
        if command['action']=='run':
            yield dict(type='progress',session_id='s',turn_id='t',outcome='in_progress')
            entered.set();assert release.wait(8)
            yield dict(type='result',session_id='s',turn_id='t',outcome='completed',text='done')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    apps=[]
    async def exercise():
        with gr.Blocks(analytics_enabled=False) as app:
            current=gr.State();text=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();button=gr.Button()
            panel=AgentPanel();panel.selectors();panel.settings_components();panel.output_components()
            cap=CapabilityUI([],gr.Dropdown(),gr.HTML());cap._visible={}
            button.click(panel.wrap_predict(env.wrappers['predict'],cap),[current,text,chat],[chat,status,*panel.outputs,*cap.outputs],queue=True,concurrency_limit=None)
        app.queue();api=App.create_app(app);index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='predict_with_ui')
        api.state_holder['browser-one'][current._id]=model
        apps.append(app)
        app._queue.start()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api),base_url='http://synthetic') as client:
            payload={'fn_index':index,'data':[None,'synthetic task',[]],'session_hash':'browser-one'}
            first=(await client.post('/queue/join',json=payload)).json()['event_id']
            assert await asyncio.to_thread(entered.wait,5)
            second=(await client.post('/queue/join',json=payload)).json()['event_id']
            messages=app._queue.pending_messages_per_session['browser-one'];seen=[]
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                while not messages.empty():seen.append(messages.get_nowait())
                completed=next((msg for msg in seen if msg.event_id==second and msg.msg=='process_completed'),None)
                if completed:break
                await asyncio.sleep(.02)
            assert completed.success and all(value==gr.update() for value in completed.output['data'])
            assert calls==['run'] and model._running
            with pytest.raises(gr.Error,match='当前任务仍在运行'):panel.emit_ui_error(model,request())
            panel.emit_ui_error(model,request())
            release.set()
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                while not messages.empty():seen.append(messages.get_nowait())
                if any(msg.event_id==first and msg.msg=='process_completed' for msg in seen):break
                await asyncio.sleep(.02)
            assert all(msg.success for msg in seen if msg.msg=='process_completed')
            assert calls.count('run')==1 and not model._running and not model._predict_error_operation
    try:asyncio.run(exercise())
    finally:
        release.set()
        if apps: apps[-1].close()


@pytest.mark.parametrize('decision',['approve','deny','cancel'])
@pytest.mark.parametrize('stale',[False,True])
def test_direct_browser_decision_failure_preserves_form_and_reports_once(env,monkeypatch,decision,stale):
    import asyncio
    from gradio.state_holder import SessionState
    model=select(env);model._state=dict(session_id='s',turn_id='t',generation='g',outcome='requires_action')
    model._pending_actions=[dict(request_id='r',turn_id='t',request=dict(type='browser_access',origin='https://synthetic.invalid'))]
    original=deepcopy(model._pending_actions);calls=[]
    def worker(command):
        calls.append(command)
        yield dict(type='error',message='synthetic decision failure')
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chat=gr.Chatbot();status=gr.Markdown();panel=AgentPanel()
        panel.selectors();panel.settings_components();panel.output_components();panel.wire(current,chat,status)
    state=SessionState(app);state[current._id]=model
    button={'approve':panel.approve,'deny':panel.deny,'cancel':panel.cancel_request}[decision]
    dependency=next(dep for dep in app.get_config_file()['dependencies'] if dep['targets']==[(button._id,'click')])
    index=app.get_config_file()['dependencies'].index(dependency)
    assert dependency['queue'] is False
    async def exercise():
        result=await app.process_api(index,[None,'expired' if stale else 'r'],state=state,request=request())
        assert all(value==gr.update() for value in result['data'])
        assert model._pending_actions==original
        assert calls==[] if stale else calls[0]['action']=='browser_response'
        with pytest.raises(gr.Error,match='网站请求已失效' if stale else 'synthetic decision failure'):panel.emit_ui_error(model,request())
        panel.emit_ui_error(model,request())
    try:asyncio.run(exercise())
    finally:app.close()


@pytest.mark.parametrize('active',[False,True])
def test_artifact_retry_preconditions_preserve_all_outputs_and_emit_once(env,active):
    model=select(env);model._state=dict(session_id='s',turn_id='t',generation='g',outcome='completed')
    model._artifacts=[dict(id='f',status='failed',name='synthetic.txt')]
    if active:model._active_file_retries.add(('s','f'))
    with gr.Blocks(analytics_enabled=False) as app:
        state=gr.State();chat=gr.Chatbot();status=gr.Markdown();panel=AgentPanel()
        panel.selectors();panel.settings_components();panel.output_components();panel.wire(state,chat,status)
    callback=next(fn.fn for fn in app.fns if fn.fn and fn.fn.__name__=='retry_file')
    frames=list(callback(model,'f' if active else 'stale',request()))
    assert len(frames)==1 and all(value==gr.update() for value in frames[0])
    with pytest.raises(gr.Error,match='文件正在重新获取' if active else '文件不属于当前会话'):panel.emit_ui_error(model,request())
    panel.emit_ui_error(model,request());app.close()


def test_agent_fork_precondition_preserves_chat_and_error_is_posted_once(env):
    model=select(env);model._running=True
    with gr.Blocks(analytics_enabled=False) as app:
        state=gr.State();chat=gr.Chatbot();status=gr.Markdown();panel=AgentPanel()
        panel.selectors();panel.settings_components();panel.output_components();panel.wire(state,chat,status)
    callback=next(fn.fn for fn in app.fns if fn.fn and fn.fn.__name__=='fork')
    assert callback(model,request())==(gr.update(),gr.update())
    with pytest.raises(gr.Error,match='请先停止或确认当前任务状态'):panel.emit_ui_error(model,request())
    panel.emit_ui_error(model,request());assert model._running
    app.close()


def test_deferred_ui_tools_are_closed_for_new_sessions_but_keep_direct_mcp():
    from modules.agent.tools import build_tool_config, validate_settings
    server={'server_label':'synthetic','server_url':'https://example.invalid/mcp','allowed_tools':['read_document']}
    value=validate_settings({'mcp_servers':[server],'tool_search':True,'programmatic_tool_calling':True})
    new=SimpleNamespace(_state={'session_id':None})
    config=AgentPanel.user_tool_config(new,value)
    assert config['tool_search'] is False and config['programmatic_tool_calling'] is False
    assert config['mcp_servers']==[server]
    built=build_tool_config(config,verify_connections=False)
    assert {'tool_search','programmatic_tool_calling'}.isdisjoint(t['type'] for t in built['tools'])
    mcp=next(t for t in built['tools'] if t['type']=='mcp')
    assert mcp['allowed_tools']==['read_document']
    frozen=SimpleNamespace(_state={'session_id':'existing-synthetic'})
    assert AgentPanel.user_tool_config(frozen,value)==value
    with gr.Blocks():
        panel=AgentPanel();panel.selectors();panel.settings_components()
        assert panel.discovery.visible is False and panel.discovery.value is False
        assert panel.programmatic.visible is False and panel.programmatic.value is False
        assert panel.browser.label==i18n('ui.toolbox.agent.browser')


def test_agent_welcome_slogan_uses_local_language_spacing():
    import json
    root=Path(__file__).resolve().parents[2]
    assert json.loads((root/'locale/zh_CN.json').read_text())['model']['openai_agent']['slogan']=='把任务交给 Agent 完成'
    assert json.loads((root/'locale/en_US.json').read_text())['model']['openai_agent']['slogan']=='Let Agent complete the task.'


def test_empty_local_chat_can_configure_tools_before_first_submission(env,monkeypatch):
    model=select(env)
    assert model._state.get('session_id') is None
    def forbidden(command):
        raise AssertionError('Empty local chat configuration must not create a remote session')
    monkeypatch.setattr(env.agents,'worker_messages',forbidden)
    settings=dict(model._tool_settings,network=False)
    model.stage_agent_tools(settings,1,model._conversation_id)
    assert model._tool_settings['network'] is False
    model.freeze_agent_configuration(settings,'First-round instructions',1,model._conversation_id)
    assert model._state.get('session_id') is None
    assert model.system_prompt=='First-round instructions'


def test_old_choice_target_cannot_change_new_visit_even_same_conversation(env):
    model=select(env);old=model.agent_choice_target
    model._choice_epoch='new-visit'
    before=(model.agent_model_choice,model._choice_revision)
    assert model.set_agent_model('gpt-6-astra','high',99,target=old) is None
    assert (model.agent_model_choice,model._choice_revision)==before
    model.set_agent_model('gpt-6-sol','low',100,target=model.agent_choice_target)
    assert model.agent_model_choice==('gpt-6-sol','low')


@pytest.mark.parametrize('response',[{'type':'error','message':'old failure'},
    {'type':'result','artifacts':[{'id':'old','name':'old.txt','status':'failed','error':'old failure'}]},
    {'type':'progress','artifact_metadata':[{'id':'old','session_id':'s','turn_id':'t','remote_path':'/workspace/old.txt'}]}])
def test_download_response_cannot_mutate_same_generation_new_visit(env,monkeypatch,response):
    model=select(env);model._state=dict(session_id='s',turn_id='t',generation='g',outcome='completed')
    model._artifacts=[dict(id='old',name='old.txt',status='failed',turn_id='t')]
    before=deepcopy(model._artifacts)
    def worker(command):
        model._choice_epoch='new-visit';model._notice='current notice'
        yield deepcopy(response)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    list(model._download('g'))
    settle_files(model)
    assert model._artifacts==before and not model._needs_sync


def test_late_title_does_not_rename_or_consume_new_chat(env,monkeypatch):
    def initial(command):
        if command['action']=='run':
            yield dict(type='result',session_id='s',turn_id='t',outcome='completed',text='first answer')
        elif command['action']=='download': yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',initial)
    model=select(env);send(env,model)
    assert not model._needs_sync and not model._auto_named
    def worker(command):
        assert command['action']=='title'
        model.reset();model._notice='current notice'
        yield dict(type='result',title='old chat title')
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    result=model.auto_name_chat_history(env.agents.i18n('naming.by_model_summary'),'old question',False)
    assert result==gr.update() and not model._auto_named
    assert 'old chat title' not in model.history_file_path and model._notice=='current notice'


def test_hot_events_exclude_sidebar_and_no_chatbot_change_refresh():
    import ast
    root=Path(__file__).resolve().parents[2]
    tree=ast.parse((root/'ChuanhuChatbot.py').read_text())
    def assignment(name):
        return next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
    predict=assignment('chatgpt_predict_args')
    outputs=next(k.value for k in predict.keywords if k.arg=='outputs')
    assert 'stream_outputs' in ast.unparse(outputs) and 'agent_panel.outputs' not in ast.unparse(outputs)
    for name in ('chatgpt_predict_args','transfer_input_args','submission_ui_args','finish_submission_args'):
        assert next(k.value.value for k in assignment(name).keywords if k.arg=='show_progress')=='hidden'
    ui=ast.parse((root/'modules/model_capabilities.py').read_text())
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='change' and isinstance(n.func.value,ast.Name) and n.func.value.id=='chatbot' for n in ast.walk(ui))


def test_same_chat_rename_during_retry_finishes_instead_of_staying_preparing(env,monkeypatch,tmp_path):
    complete(env,monkeypatch);model=select(env);send(env,model)
    model._artifacts=[dict(id='file',name='synthetic.txt',status='failed',session_id=model._state['session_id'],turn_id=model._state['turn_id'])]
    model._remember()
    folder=Path(__import__('tempfile').mkdtemp(prefix='chuanhu-agent-artifacts-'))
    file=folder/'synthetic.txt';file.write_text('synthetic')
    def worker(command):
        assert command['action']=='download'
        yield dict(type='result',artifacts=[dict(id='file',name='synthetic.txt',status='ready',path=str(file),session_id=model._state['session_id'],turn_id=model._state['turn_id'])])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    retry=model.retry_artifact('file');next(retry)
    model.rename_chat_history('Renamed chat.json')
    list(retry);settle_files(model)
    assert model._artifacts[0]['status']=='ready' and not model._active_file_retries
    assert model.history_file_path=='Renamed chat.json'


def test_history_terminal_boundary_rejects_completed_old_visit(env):
    from modules.agent.operations import OperationScope
    model=select(env)
    panel=AgentPanel()
    scope=OperationScope.capture(model);model._history_ui_complete_scope=scope
    model._choice_epoch='new-visit'
    with gr.Blocks(analytics_enabled=False) as app:
        panel.selectors();panel.settings_components();panel.output_components()
    cap=SimpleNamespace(outputs=[])
    values=panel.history_boundary_values(cap)(model,request())
    assert values and all(value==gr.update() for value in values)
    app.close()


def test_artifact_refresh_does_not_clear_click_transport_before_retry(env):
    model=select(env)
    model._artifacts=[dict(id='file',name='synthetic.txt',status='failed')]
    # 失败卡到达与发送终态边界都可能紧跟用户点击；不覆盖用户写入的传输值。
    assert ArtifactPanel.values(model)[-1]==gr.update()
    assert ArtifactPanel.values(SimpleNamespace())[-1]==gr.update(value='')


def sync_warning_model(env):
    model=select(env);model._state.update(generation='sync-generation',session_id='sess_test',turn_id='t1',outcome='completed')
    return model


def sync_warning_snapshot(complete):
    from test_runtime import message
    return dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=complete,
                items=[message('u1','question',role='user'),message('a1','preserved answer')])


def test_complete_sync_resolves_only_own_pending_warning_and_notice(env):
    model=sync_warning_model(env)
    model._accept(sync_warning_snapshot(False),'sync-generation',restoring=True,error_operation='observe')
    assert model._needs_sync and '历史尚未完整同步' in model._notice
    model.record_ui_error('file retry failed',operation='observe')
    model.record_ui_error('different callback failed',operation='retry')
    model._accept(sync_warning_snapshot(True),'sync-generation',restoring=True,error_operation='observe')
    assert not model._needs_sync and model._notice==''
    model.complete_error_operation('observe')
    assert model.take_completed_ui_errors()=='file retry failed'
    assert model.has_ui_error('retry')
    assert model.history[-1]['content']=='preserved answer'
    # If another partial result arrives, it must warn again rather than remain deduped.
    model._accept(sync_warning_snapshot(False),'sync-generation',restoring=True,error_operation='observe')
    model.complete_error_operation('observe')
    assert '历史尚未完整同步' in model.take_completed_ui_errors()


@pytest.mark.parametrize('invalid',['stale-generation','no-items','no-items-with-artifacts','partial','unsafe-items'])
def test_unconfirmed_sync_does_not_clear_pending_warning(env,invalid):
    model=sync_warning_model(env)
    model._accept(sync_warning_snapshot(False),'sync-generation',restoring=True,error_operation='observe')
    snapshot=sync_warning_snapshot(True)
    generation='sync-generation'
    if invalid=='stale-generation':generation='old-generation'
    elif invalid in ('no-items','no-items-with-artifacts'):
        snapshot.pop('items')
        if invalid=='no-items-with-artifacts':snapshot['artifacts']=[]
    elif invalid=='partial':snapshot['sync_complete']=False
    else:
        from test_runtime import message
        snapshot['items'].append(message(None,'unknown final identity'))
    if invalid=='unsafe-items':
        with pytest.raises(gr.Error):model._accept(snapshot,generation,restoring=True,error_operation='observe')
    else:model._accept(snapshot,generation,restoring=True,error_operation='observe')
    assert model._needs_sync
    assert '历史尚未完整同步' in model._notice or (invalid=='unsafe-items' and '缺少稳定消息身份' in model._notice)
    model.complete_error_operation('observe')
    assert '历史尚未完整同步' in model.take_completed_ui_errors()


def test_successful_sync_keeps_unrelated_notice_and_other_operation_warning(env):
    model=sync_warning_model(env)
    model._accept(sync_warning_snapshot(False),'sync-generation',restoring=True,error_operation='old-observer')
    model._notice='文件获取失败，可重试'
    model._accept(sync_warning_snapshot(True),'sync-generation',restoring=True,error_operation='new-observer')
    assert not model._needs_sync and model._notice=='文件获取失败，可重试'
    model.complete_error_operation('old-observer')
    assert '历史尚未完整同步' in model.take_completed_ui_errors()


@pytest.mark.parametrize('capture',[{'items':'partial'},{'items':'not_collected'},{}])
def test_incomplete_capture_overrides_claimed_complete_sync(env,capture):
    model=sync_warning_model(env)
    model._accept(sync_warning_snapshot(False),'sync-generation',restoring=True,error_operation='observe')
    snapshot=sync_warning_snapshot(True);snapshot['capture']=capture
    model._accept(snapshot,'sync-generation',restoring=True,error_operation='observe')
    assert model._needs_sync and model._notice
    assert model.has_ui_error('observe')
    assert 'log_reconciled' not in model._state


def test_other_operation_complete_items_do_not_resolve_owned_sync_notice(env):
    model=sync_warning_model(env)
    model._accept(sync_warning_snapshot(False),'sync-generation',restoring=True,error_operation='new-observer')
    before=model._notice
    model._accept(sync_warning_snapshot(True),'sync-generation',restoring=True,error_operation='old-observer')
    assert model._notice==before and model.has_ui_error('new-observer')
    model._accept(sync_warning_snapshot(True),'sync-generation',restoring=True,error_operation='new-observer')
    assert model._notice=='' and not model.has_ui_error('new-observer')
