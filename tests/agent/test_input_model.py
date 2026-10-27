import threading
from copy import deepcopy
from pathlib import Path

import gradio as gr
import pytest
from modules.agent.input_files import AgentInputFiles
from agent_fixtures import env, select, send, request
from main_chat_mock import MainChatMock


def staged(env, tmp_path, monkeypatch, names=('one.txt',)):
    model=select(env);root=tmp_path/'uploads';root.mkdir()
    paths=[]
    for index,name in enumerate(names):
        folder=root/str(index);folder.mkdir();path=folder/name;path.write_text('Synthetic '+str(index));paths.append(str(path))
    model._input_stager=AgentInputFiles(upload_roots=[root])
    model.stage_input_files(paths)
    service=MainChatMock();calls=[]
    def worker(command):
        calls.append(deepcopy(command));yield from service.worker(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    return model,paths,service,calls


def submit(env,model,text,paths):
    envelope=env.wrappers['transfer_input'](text,model,None,'default',None,paths,request=request())[0]
    return list(env.wrappers['predict'](model,envelope,model.chatbot,files=paths,request=request()))


def test_first_file_only_and_existing_session_file_inputs(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    submit(env,model,'',paths)
    session=model._state['session_id']
    assert [c['action'] for c in calls]==['prepare_inputs','run','download']
    assert calls[1]['session_id']==session and calls[1]['input_files'][0]['name']=='one.txt'
    assert len(model.history)==2 and '/workspace/' not in model.chatbot[0][0]
    assert model.chatbot[0][0] == '请查看上传的附件。' and not model._pending_upload_paths
    from modules.agent.ui import message_file_projection
    assert message_file_projection(model).user_files[0][0]['name'] == 'one.txt'
    model.stage_input_files(paths);submit(env,model,'read again',paths)
    assert model._state['session_id']==session
    assert len(service.sessions[session]['inputs'])==2
    assert calls[0]['inputs'][0]['input_id'] != calls[3]['inputs'][0]['input_id']
    assert calls[0]['inputs'][0]['remote_path'] != calls[3]['inputs'][0]['remote_path']
    assert calls[3]['installed'] and len(model.history)==4


def test_same_names_distinct_files_and_frozen_send_snapshot(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,('same.txt','same.txt'))
    envelope=env.wrappers['transfer_input']('both',model,None,'default',None,paths,request=request())[0]
    with pytest.raises(gr.Error):model.stage_input_files(paths[:1])
    list(env.wrappers['predict'](model,envelope,model.chatbot,files=[],request=request()))
    records=calls[0]['inputs']
    assert len({record['remote_path'] for record in records})==2
    assert len(calls[1]['input_files'])==2


def test_upload_failure_creates_no_turn_and_preserves_empty_session(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,('upload-fail.txt',))
    result=submit(env,model,'must not run',paths)
    assert [c['action'] for c in calls]==['prepare_inputs']
    assert model._state['session_id'] in service.sessions
    assert model._state['outcome']=='not_started' and model.history==[]
    assert not service.sessions[model._state['session_id']]['items']
    assert '消息未发送' in result[-1][1]


def test_stop_during_upload_never_runs_message(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,('slow-upload.txt',))
    ready,release=threading.Event(),threading.Event()
    original=env.agents.worker_messages
    def worker(command):
        for message in original(command):
            yield message
            preparation=message.get('preparation') or {}
            if command['action']=='prepare_inputs' and preparation.get('session_id') and preparation.get('outcome')=='preparing':
                ready.set();assert release.wait(5)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    iterator=env.wrappers['predict'](model,'cancel',[],files=paths,request=request())
    next(iterator);assert ready.wait(3)
    session=model._state['session_id']
    try:
        model.interrupt();release.set();list(iterator)
        assert [c['action'] for c in calls]==['prepare_inputs']
        assert model._state['session_id']==session and model.history==[]
        assert model._state['outcome']=='not_started'
    finally:release.set();model._background_task.thread.join(5);iterator.close()


def test_no_environment_rejects_before_any_upload_or_turn(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    model.save_agent_tools(dict(model._tool_settings,code_execution=False,computer_use=False,programmatic_tool_calling=False))
    with pytest.raises(gr.Error):submit(env,model,'no sandbox',paths)
    assert not calls


def test_unregistered_path_or_other_owner_cannot_submit_input(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    with pytest.raises(gr.Error):submit(env,model,'wrong file',[str(tmp_path/'private.txt')])
    with pytest.raises(gr.Error):env.wrappers['transfer_input']('wrong owner',model,agent_files=paths,request=request(username='other'))
    assert not calls


def test_model_switch_clears_pending_inputs_and_does_not_copy_them(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    ordinary=select(env,model,name='GPT3.5 Turbo')
    assert not model._pending_upload_paths and not hasattr(ordinary,'_input_stager')
    assert not calls


def test_history_reference_survives_precreated_file_session(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    model.history=[{'role':'user','content':'old question'},{'role':'assistant','content':'old answer'}]
    model.chatbot=model._display=[['old question','old answer']]
    submit(env,model,'use context',paths)
    assert calls[1]['history_reference']==[{'role':'user','content':'old question'},{'role':'assistant','content':'old answer'}]
    assert 'old answer' in service.sessions[model._state['session_id']]['items'][0]['content'][0]['text']
    assert model.chatbot[0][0]=='use context'
    from modules.agent.ui import message_file_projection
    assert message_file_projection(model).user_files[0][0]['name'] == 'one.txt'


def test_late_upload_completion_cannot_attach_to_a_reset_conversation(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    target=model._conversation_id;model.reset()
    with pytest.raises(gr.Error):model.add_input_files(paths,target)
    assert not model._pending_upload_paths and not calls


def test_failure_reconnect_preserves_unsent_history_seed_and_same_empty_session(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,('upload-fail.txt',))
    reference=[{'role':'user','content':'prior question'},{'role':'assistant','content':'prior answer'}]
    model.history=deepcopy(reference);model.chatbot=model._display=[['prior question','prior answer']]
    submit(env,model,'not submitted',paths)
    session=model._state['session_id'];list(model.reconnect())
    assert model.history==reference and model._input_seed_reference==reference
    model.stage_input_files([])
    good=Path(paths[0]).with_name('good.txt');good.write_text('Synthetic retry')
    model.stage_input_files([str(good)]);submit(env,model,'retry with valid file',[str(good)])
    assert len(service.sessions)==1 and model._state['session_id']==session
    assert [call for call in calls if call['action']=='run'][0]['history_reference']==reference


def test_persistent_binding_keeps_installed_inputs_but_export_does_not_grant_them(env,tmp_path,monkeypatch):
    import json
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    submit(env,model,'read',paths)
    saved=model.history_file_path
    restored=select(env,browser='another-browser')
    restored.load_chat_history(saved.removesuffix('.json'))
    assert restored._installed_inputs==model._installed_inputs and not restored._pending_upload_paths
    payload=json.loads((env.history_dir/saved).read_text())
    assert 'installed_inputs' not in payload and 'input_context' not in payload
    imported=env.history_dir/'imported.json';imported.write_text(json.dumps(payload))
    clone=select(env);clone.load_chat_history('imported')
    assert not clone._installed_inputs and not clone._state.get('session_id')


def test_new_prepared_session_has_same_cross_browser_send_reservation(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    iterator=env.wrappers['predict'](model,'one',[],files=paths,request=request())
    next(iterator);next(iterator);next(iterator)
    session=model._state['session_id']
    other=select(env,browser='other-browser')
    other._state={'session_id':session,'outcome':'not_started'};other._session_settings=model._current_settings()
    with pytest.raises(gr.Error):send(env,other,'competing',browser='other-browser')
    model.interrupt();list(iterator)


def test_ordinary_upload_keeps_existing_handler_and_late_rag_event_cannot_stage_agent(env,tmp_path,monkeypatch):
    ordinary=select(env,name='GPT3.5 Turbo');seen=[]
    monkeypatch.setattr(ordinary,'handle_file_upload',lambda *args:seen.append(args) or ('files','chat','status'))
    result=env.wrappers['handle_file_upload'](ordinary,['synthetic.txt'],[],'English',request=request())
    assert result==('files','chat','status') and seen==[(['synthetic.txt'],[],'English')]
    agent=select(env,ordinary)
    with pytest.raises(gr.Error):env.wrappers['handle_file_upload'](agent,['synthetic.txt'],[],'English',request=request())
    assert not agent._pending_upload_paths


def test_input_picker_routes_and_repeat_paste_dom_contract():
    import subprocess,shutil
    result=subprocess.run([shutil.which('node') or 'node','tests/javascript/agent-inputs.test.cjs'],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_uncertain_file_write_is_not_presented_as_ready_or_resubmitted(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    operations=[]
    def worker(command):
        operations.append(command['action'])
        assert command['action']=='prepare_inputs'
        yield {'type':'error','message':'文件写入结果未确认','preparation':{
            'run_id':command['run_id'],'session_id':'sess_uncertain','environment_id':'env_uncertain',
            'outcome':'uncertain','session_creation_started':True,'installed':{},'files':[],
            'uncertain_operation':{'operation':'environment_file','input_id':command['inputs'][0]['input_id']}}}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    result=submit(env,model,'not sent',paths)
    assert operations==['prepare_inputs'] and model._state['outcome']=='incomplete' and model._needs_sync
    assert '消息未发送' in result[-1][1] and not model.history


def test_idle_reconnect_preserves_newly_staged_unsent_files(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,('notes.txt',))
    submit(env,model,'First turn',paths)
    assert model._draft_acknowledged and model._state['outcome']=='completed'
    model.stage_input_files(paths)
    pending_ids=[record.input_id for record in model._input_stager.snapshot()]
    original=env.agents.worker_messages
    def worker(command):
        if command['action']=='recover':
            # Real recover_stream constructs TurnState without a new submission;
            # its public snapshot therefore has submission_started=False.
            saved=deepcopy(service.snapshot(command['session_id']))
            saved['submission_started']=False
            yield dict(type='result',**saved)
        else: yield from original(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    list(model.reconnect())
    assert model._pending_upload_paths==tuple(paths)
    assert [record.input_id for record in model._input_stager.snapshot()]==pending_ids


def test_direct_next_predict_confirms_and_clears_its_own_files(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch,('notes.txt',))
    submit(env,model,'First turn',paths)
    assert model._draft_acknowledged
    model.stage_input_files(paths)
    list(env.wrappers['predict'](model,'Direct second turn',model.chatbot,files=paths,request=request()))
    assert model._draft_acknowledged and not model._pending_upload_paths
    assert len([call for call in calls if call['action']=='run'])==2
