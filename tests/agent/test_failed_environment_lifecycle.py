"""Known failed preparation is terminal locally; New never starts remote work."""
from copy import deepcopy
import gradio as gr
import pytest
from agent_fixtures import env,request,send,complete
from test_input_model import staged
from modules.agent.ui import AgentPanel
from modules.model_capabilities import CapabilityUI


def failed_model(env,tmp_path,monkeypatch,*,uncertain=False):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    def worker(command):
        calls.append(command)
        assert command['action']=='prepare_inputs'
        preparation={'run_id':command['run_id'],'session_id':'sess_failed','environment_id':'env_failed',
                     'last_request_phase':'preparation.environment_retrieve','environment_status':'failed',
                     'environment_error':{'code':'environment_connection_failed','type':'environment_error'},
                     'outcome':'uncertain' if uncertain else 'failed','submission_started':False,
                     'session_creation_started':True,'files':[],'installed':{},
                     'uncertain_operation':{'operation':'environment_file'} if uncertain else None}
        yield {'type':'error','message':'Synthetic sandbox environment failed','preparation':preparation}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    list(env.wrappers['predict'](model,'visible failure',[],files=paths,request=request()))
    return model,paths,calls


def test_confirmed_failed_preparation_blocks_reuse_without_remote_write(env,tmp_path,monkeypatch):
    model,paths,calls=failed_model(env,tmp_path,monkeypatch)
    assert model._state['outcome']=='failed' and model._failed_preparation_environment()
    before=deepcopy(model._store().get(model._owner,model.history_file_path));count=len(calls)
    with pytest.raises(gr.Error,match='主动新建'):
        model._assert_idle()
    with pytest.raises(gr.Error,match='主动新建'):
        list(model.predict('manual attempt',model.chatbot,files=paths))
    assert len(calls)==count and model._store().get(model._owner,model.history_file_path)==before
    assert not model.history and not model._draft_submitted


def test_actual_new_reset_is_clean_and_preserves_failed_history_binding(env,tmp_path,monkeypatch):
    model,paths,calls=failed_model(env,tmp_path,monkeypatch)
    old=deepcopy(model._store().get(model._owner,model.history_file_path));old_path=model.history_file_path
    with gr.Blocks(analytics_enabled=False) as app:
        cap=CapabilityUI([],gr.Dropdown(),gr.HTML(),gr.Button(),gr.Button());cap.wire(None,None)
        panel=AgentPanel()
    try:
        fresh=panel.wrap_reset(env.wrappers['reset'],cap)(model,False,request=request())[0]
        assert fresh is not model and fresh._conversation_id!=model._conversation_id
        assert fresh._state=={'outcome':'not_started'} and fresh._input_context is None and not fresh._needs_sync
        assert not fresh._failed_preparation_environment() and not fresh.history and not fresh.chatbot
        assert model._store().get(model._owner,old_path)==old and len(calls)==1
        sent,_=complete(env,monkeypatch);send(env,fresh,'new manually initiated request')
        assert sent[0]['action']=='run' and sent[0]['session_id'] is None
        assert fresh._state['outcome']=='completed'
        assert model._store().get(model._owner,old_path)==old
    finally:app.close()


def test_failed_history_restore_is_local_terminal_and_keeps_binding(env,tmp_path,monkeypatch):
    model,paths,calls=failed_model(env,tmp_path,monkeypatch)
    original=deepcopy(model._store().get(model._owner,model.history_file_path))
    restored=model.new_view();restored.history_file_path=model.history_file_path;restored._restore_binding()
    assert restored._state['outcome']=='failed' and not restored._needs_sync
    assert restored._failed_preparation_environment() and 'environment_connection_failed' in restored._notice
    assert model._store().get(model._owner,model.history_file_path)==original
    with pytest.raises(gr.Error,match='主动新建'):restored._assert_idle()
    assert len(calls)==1


def test_uncertain_preparation_is_not_turned_into_terminal_failure(env,tmp_path,monkeypatch):
    model,paths,calls=failed_model(env,tmp_path,monkeypatch,uncertain=True)
    assert model._state['outcome']=='incomplete' and model._needs_sync
    assert not model._failed_preparation_environment()
    model._input_context['resume_state']['uncertain_operation']=None
    assert not model._failed_preparation_environment()  # Uncertain outcome alone still requires confirmation.
    with pytest.raises(gr.Error,match='状态尚待确认'):model._assert_idle()

@pytest.mark.parametrize('existing_history',[False,True])
def test_real_prepare_session_failed_before_environment_get_is_terminal(env,tmp_path,monkeypatch,existing_history):
    from test_inputs_runtime import FakeClient
    from modules.agent.inputs import prepare_inputs,InputPreparationError
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    client=FakeClient();client.session_status='failed'
    if existing_history:
        model._state={'outcome':'completed','session_id':client.session_id,'turn_id':'old-turn'}
        model.history=[{'role':'user','content':'old question'},{'role':'assistant','content':'old answer'}]
        model.chatbot=model._display=[['old question','old answer']]
    previous=deepcopy(model.history)
    def worker(command):
        calls.append(command['action']);assert command['action']=='prepare_inputs'
        try:
            prepare_inputs(client,command['inputs'],command['model'],staging_root=command['staging_root'],
                session_id=command.get('session_id'),run_id=command['run_id'],reasoning=command.get('reasoning'),
                tool_settings=command['tool_settings'])
            raise AssertionError('failed session unexpectedly accepted')
        except InputPreparationError as error:
            yield {'type':'error','message':str(error),'preparation':error.state}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    list(env.wrappers['predict'](model,'copyable failed request',model.chatbot,files=paths,request=request()))
    receipt=model._input_context['resume_state']
    assert receipt['session_status']=='failed' and receipt['last_request_phase']=='preparation.session_retrieve'
    assert 'environment_status' not in receipt and 'environment_error' not in receipt and client.environment_reads==0
    assert 'code=unknown' in model._notice and 'phase=preparation.session_retrieve' in model._notice
    assert model._state['outcome']=='failed' and model._failed_preparation_environment()
    assert model.history==previous and model.chatbot[-1][0]=='copyable failed request'
    saved=deepcopy(model._store().get(model._owner,model.history_file_path))
    with pytest.raises(gr.Error,match='主动新建'):model.set_agent_model('gpt-6-sol','high')
    with pytest.raises(gr.Error,match='主动新建'):list(model.predict('manual next',model.chatbot,files=paths))
    assert calls==['prepare_inputs']
    restored=model.new_view();restored.history_file_path=model.history_file_path;restored._restore_binding()
    assert restored._state['outcome']=='failed' and not restored._needs_sync
    assert restored._failed_preparation_environment() and 'phase=preparation.session_retrieve' in restored._notice
    assert model._store().get(model._owner,model.history_file_path)==saved
    fresh=model.new_view()
    assert fresh._input_context is None and fresh._state=={'outcome':'not_started'}
    assert not fresh._failed_preparation_environment() and calls==['prepare_inputs']
