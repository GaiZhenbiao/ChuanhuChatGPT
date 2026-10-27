import asyncio
import threading
import gradio as gr
import pytest
from gradio.state_holder import SessionState
from modules.agent.ui import AgentPanel
from agent_fixtures import env, request
from test_input_model import staged


@pytest.mark.parametrize('outcome',['failed','cancelled','submitted'])
def test_actual_finish_callback_keeps_unsent_draft_and_feedback(env,tmp_path,monkeypatch,outcome):
    name='upload-fail.txt' if outcome=='failed' else 'slow-upload.txt' if outcome=='cancelled' else 'notes.txt'
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,(name,))
    text='Keep this unsent attachment request'
    panel=AgentPanel()
    transferred=panel.wrap_transfer(env.wrappers['transfer_input'])(text,model,agent_files=paths,request=request())
    assert 'value' not in transferred[1]  # Browser draft is retained until acknowledgement.
    envelope=transferred[0]
    ready,release=threading.Event(),threading.Event()
    if outcome=='cancelled':
        original=env.agents.worker_messages
        def paused_upload(command):
            for message in original(command):
                yield message
                preparation=message.get('preparation') or {}
                if command['action']=='prepare_inputs' and preparation.get('session_id') and preparation.get('outcome')=='preparing':
                    ready.set();assert release.wait(5)
        monkeypatch.setattr(env.agents,'worker_messages',paused_upload)
    iterator=env.wrappers['predict'](model,envelope,[],files=paths,request=request())
    try:
        if outcome=='cancelled':
            next(iterator);assert ready.wait(3)
            assert model._input_context and not model._draft_submitted
            model.interrupt();release.set()
        list(iterator)
        if outcome=='cancelled': assert [call['action'] for call in calls]==['prepare_inputs']
    finally:
        release.set()
        if outcome=='cancelled' and getattr(model,'_background_task',None): model._background_task.thread.join(5)
        iterator.close()
    panel=AgentPanel()
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();question=gr.State();draft=gr.Textbox();status=gr.Markdown();finish=gr.Button()
        finish.click(panel.finish_submission,[current,question,draft],[draft,status])
    state=SessionState(app);state[current._id]=model;state[question._id]=envelope
    async def exercise():
        result=await app.process_api(0,[None,None,''],state=state,request=request())
        if outcome=='submitted': assert 'value' not in result['data'][0]
        else:
            assert 'value' not in result['data'][0]
            assert '消息未发送' in result['data'][1] if outcome=='failed' else '已取消' in result['data'][1]
            assert not model.history and model._pending_upload_paths
        edited=await app.process_api(0,[None,None,'A newer draft'],state=state,request=request())
        assert 'value' not in edited['data'][0]
        model.reset()
        stale_chat=await app.process_api(0,[None,None,''],state=state,request=request())
        assert all('value' not in item for item in stale_chat['data'])
        model._draft_token='new-attempt'
        stale=await app.process_api(0,[None,None,''],state=state,request=request())
        assert all('value' not in item for item in stale['data'])
        with pytest.raises(gr.Error):
            await app.process_api(0,[None,None,''],state=state,request=request(username='other'))
    try:asyncio.run(exercise())
    finally:app.close()


def test_hidden_rag_updates_cannot_clear_agent_status():
    import subprocess
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');let callback,clears=0,knowledge=false;
const uploader={observe(){}};const source=fs.readFileSync('web_assets/javascript/fake-gradio.js','utf8');
const context={window:{chuanhuSupports:()=>knowledge},gradioApp:()=>({querySelector:()=>({innerText:'',addEventListener(){},removeEventListener(){}})}),
 chatbotArea:{classList:{remove(){}}},uploaderIndicator:{},uploaderIndicator2:{},statusDisplayMessage:()=>clears++,MutationObserver:class{constructor(fn){callback=fn;}observe(){}}};
vm.createContext(context);vm.runInContext(source,context);
context.transUpload=()=>{};context.gradioApp=()=>({querySelector:s=>s.includes('table.file-preview')?null:{innerText:''}});
context.setUploader();callback();assert.strictEqual(clears,0);knowledge=true;callback();assert.strictEqual(clears,1);
'''
    result=subprocess.run(['node','-e',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_browser_only_clears_the_unchanged_acknowledged_draft():
    import subprocess
    result=subprocess.run(['node','tests/javascript/agent-draft-guard.test.cjs'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_starting_input_request_keeps_draft_and_files_until_a_turn_is_seen(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,('notes.txt',))
    panel=AgentPanel()
    envelope=panel.wrap_transfer(env.wrappers['transfer_input'])('Keep until accepted',model,agent_files=paths,request=request())[0]
    model._pending_send=None
    model._state={'generation':'g','session_id':'session','outcome':'starting','turn_id':None}
    identifiers=[item.input_id for item in model._input_stager.snapshot()]
    model._input_context={'input_ids':identifiers,'run_id':'g'}
    model._accept({'session_id':'session','submission_started':True,'outcome':'starting'},'g')
    assert not model._draft_acknowledged and model._pending_upload_paths==tuple(paths)
    assert model._input_context is not None
    model._accept({'session_id':'session','submission_started':True,'turn_id':'new-turn','outcome':'in_progress'},'g')
    assert model._draft_acknowledged and not model._pending_upload_paths
    assert model._input_context is None


def test_locked_network_command_preserves_draft_and_emits_visible_error(env, monkeypatch):
    from agent_fixtures import complete, select, send
    from modules.model_capabilities import CapabilityUI
    calls, _ = complete(env, monkeypatch)
    model = select(env)
    send(env, model, 'Start synthetic session')
    count = len(calls)
    before = [dict(item) for item in model.history]
    with gr.Blocks(analytics_enabled=False) as app:
        panel = AgentPanel(); panel.selectors(); panel.output_components(); panel.settings_components(); panel.input_components()
        cap = CapabilityUI([], gr.Dropdown(), gr.HTML(), gr.Button(), gr.Button()); cap.wire(None, None)
    try:
        envelope = panel.wrap_transfer(env.wrappers['transfer_input'])('关闭联网', model, request=request())[0]
        wrapped = panel.status_callback(panel.wrap_predict(env.wrappers['predict'], cap, compact=True), 1, header=True)
        list(wrapped(model, envelope, model.chatbot, request=request()))
        assert not model._draft_submitted and not model._draft_acknowledged
        assert len(calls) == count and model.history == before
        assert model._tool_settings['network'] is True
        assert 'value' not in panel.finish_submission(model, envelope, '关闭联网', request())[0]
        with pytest.raises(gr.Error, match='会话创建后'):
            panel.emit_ui_error(model, request())
    finally:
        app.close()
