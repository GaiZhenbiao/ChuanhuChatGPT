"""Durable background file jobs through real model/history paths and barriers."""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
from threading import Event, Thread
import time
from types import SimpleNamespace
import pytest
from agent_fixtures import env, select, request
from test_finalization_boundary import complete_state, wait_main, wait_files
from modules.agent import file_jobs, runtime


def seed(env, monkeypatch, worker):
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model=select(env)
    stream=env.wrappers['predict'](model,'first',[],request=request());next(stream);wait_main(model)
    stream.close()
    return model

def artifact(tmp_path, identifier='file', session='sess_one', turn='turn_one'):
    folder=Path(__import__('tempfile').mkdtemp(prefix='chuanhu-agent-artifacts-'))
    file=folder/(identifier+'.txt');file.write_text('bytes')
    return dict(id=identifier,session_id=session,turn_id=turn,name=file.name,path=str(file),status='ready',size=5)

def run_result():
    state=complete_state();state.submission_started=True
    return dict(type='result',**state.snapshot())


def test_rename_follows_job_alias_without_recreating_old_json(env,monkeypatch,tmp_path):
    ready,release=Event(),Event();record=artifact(tmp_path)
    def worker(command):
        if command['action']=='run': yield run_result()
        else:
            ready.set();assert release.wait(5)
            yield dict(type='result',artifacts=[record])
    model=seed(env,monkeypatch,worker);assert ready.wait(3)
    old=model.history_file_path;model.rename_chat_history('Renamed.json')
    release.set();wait_files(model)
    assert not (env.history_dir/old).exists()
    document=json.loads((env.history_dir/'Renamed.json').read_text())
    assert document['agent_transcript']['files'][0]['source_id']=='file'
    assert model._store().get(model._owner,'Renamed.json')['artifacts'][0]['status']=='ready'
    assert file_jobs.jobs_for(model._store(),model._owner,model._conversation_id)[0]['history']=='Renamed'


def test_deleted_job_cannot_recreate_history_or_contaminate_same_filename(env,monkeypatch,tmp_path):
    ready,release=Event(),Event();record=artifact(tmp_path)
    def worker(command):
        if command['action']=='run': yield run_result()
        else:
            ready.set();assert release.wait(5)
            yield dict(type='result',artifacts=[record])
    old=seed(env,monkeypatch,worker);assert ready.wait(3)
    filename=old.history_file_path;conversation=old._conversation_id
    old.delete_chat_history(filename)
    fresh=select(env);fresh.history_file_path=filename
    fresh.history=[dict(role='user',content='fresh'),dict(role='assistant',content='fresh answer')]
    fresh.chatbot=fresh._display=[['fresh','fresh answer']]
    fresh._state=dict(session_id='sess_fresh',turn_id='turn_fresh',outcome='completed',generation='fresh')
    fresh.auto_save(fresh.chatbot)
    release.set();wait_files(fresh)
    document=json.loads((env.history_dir/filename).read_text())
    assert document['history']==fresh.history and not document['agent_transcript']['files']
    assert fresh._store().get(fresh._owner,filename)['conversation_id']==fresh._conversation_id
    assert fresh._store().is_history_deleted(fresh._owner,filename,conversation)
    assert file_jobs.jobs_for(fresh._store(),fresh._owner,conversation)[0]['status']=='deleted'


def test_restart_pending_job_resumes_only_matching_authorized_binding(env,monkeypatch,tmp_path):
    record=artifact(tmp_path);calls=[]
    registry=file_jobs.FileJobRegistry()
    monkeypatch.setattr(file_jobs,'FILE_JOBS',registry)
    submit=registry.submit;monkeypatch.setattr(registry,'submit',lambda *a,**k:False)
    def worker(command):
        calls.append(command['action'])
        yield run_result() if command['action']=='run' else dict(type='result',artifacts=[record])
    model=seed(env,monkeypatch,worker)
    jobs=file_jobs.jobs_for(model._store(),model._owner,model._conversation_id)
    assert jobs[0]['status']=='pending' and calls==['run']
    monkeypatch.setattr(registry,'submit',submit)
    restored=select(env);restored.load_chat_history(model.history_file_path)
    restored._connection_mismatch=True;restored.refresh_files();assert calls==['run']
    restored._connection_mismatch=False;restored.refresh_files();wait_files(restored)
    assert calls==['run','download'] and restored._artifacts[0]['status']=='ready'
    assert restored._needs_sync  # File resume cannot manufacture cloud idle.


def test_worker_file_filter_uses_actual_provider_turn_before_bytes(tmp_path):
    opened=[];metadata=[]
    values=[dict(id='old',session_id='sess_one',turn_id='turn_one',filename='old.txt',size_bytes=5),
            dict(id='future',session_id='sess_one',turn_id='turn_two',filename='future.txt',size_bytes=5),
            dict(id='missing',session_id='sess_one',filename='missing.txt'),
            dict(id='conflict',session_id='sess_other',turn_id='turn_one',filename='conflict.txt')]
    @contextmanager
    def content(identifier,**kwargs):
        opened.append(identifier);yield SimpleNamespace(iter_bytes=lambda:iter([b'bytes']))
    client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(artifacts=SimpleNamespace(
        list=lambda *a,**k:values,with_streaming_response=SimpleNamespace(content=content))))))
    records=runtime.download_artifacts(client,'sess_one',turn_id='turn_one',cache_root=tmp_path/'cache',on_metadata=metadata.extend)
    assert opened==['old']
    assert {record['id'] for record in records}=={'old','missing','conflict'}
    assert next(record for record in records if record['id']=='old')['turn_id']=='turn_one'
    assert all(record.get('turn_id') is None and 'path' not in record for record in records if record['id']!='old')
    assert 'future' not in {record['id'] for record in metadata}


def test_stale_retry_attempt_cannot_overwrite_newer_file_receipt(env,monkeypatch,tmp_path):
    monkeypatch.setattr(file_jobs.FILE_JOBS,'submit',lambda *a,**k:False)
    model=seed(env,monkeypatch,lambda command:iter([run_result()]))
    store=model._store();first=file_jobs.jobs_for(store,model._owner,model._conversation_id)[0]
    record=artifact(tmp_path)
    assert file_jobs.apply_receipts(store,first['id'],[dict(record,status='failed',error='first failure')],env.history_dir)
    with store.history_guard(model._owner,model.history_file_path):
        newer=file_jobs.create_job(store,owner=model._owner,conversation=model._conversation_id,history=model.history_file_path,
            session='sess_one',turn='turn_one',generation='later',connection_ref=model._connection_reference(),artifact_ids=['file'])
    assert file_jobs.apply_receipts(store,newer['id'],[record],env.history_dir)
    assert file_jobs.apply_receipts(store,first['id'],[dict(record,status='failed',error='late old failure')],env.history_dir)
    saved=store.get(model._owner,model.history_file_path)
    assert saved['artifacts'][0]['status']=='ready' and not saved['artifacts'][0].get('error')


def test_same_file_retry_during_next_turn_keeps_file_target_not_run_generation(env,monkeypatch,tmp_path):
    record=artifact(tmp_path);ready,release=Event(),Event();commands=[]
    def worker(command):
        commands.append(deepcopy({k:v for k,v in command.items() if k not in ('connection','_observe_cancel')}))
        if command['action']=='run':yield run_result()
        elif command.get('artifact_ids'):
            ready.set();assert release.wait(5);yield dict(type='result',artifacts=[record])
        else:yield dict(type='result',artifacts=[dict(record,status='failed',error='retry')])
    model=seed(env,monkeypatch,worker);wait_files(model)
    list(model.retry_artifact('file'));assert ready.wait(3)
    model._state.update(generation='next-generation',turn_id='turn_two',outcome='in_progress')
    model.auto_save(model.chatbot)
    release.set();wait_files(model)
    retry=next(command for command in commands if command.get('artifact_ids'))
    assert retry['turn_id']=='turn_one' and model._state['turn_id']=='turn_two'
    assert model._store().get(model._owner,model.history_file_path)['state']['generation']=='next-generation'
    assert model._artifacts[0]['turn_id']=='turn_one' and model._artifacts[0]['status']=='ready'


def test_file_queue_is_bounded_with_overflow_left_durable_pending(env,monkeypatch):
    monkeypatch.setattr(file_jobs.FILE_JOBS,'submit',lambda *a,**k:False)
    model=seed(env,monkeypatch,lambda command:iter([run_result()]))
    store=model._store();registry=file_jobs.FileJobRegistry(workers=1,capacity=1)
    ready,release=Event(),Event();count=[0]
    def runner(command):
        count[0]+=1;ready.set();assert release.wait(5);yield dict(type='result',artifacts=[])
    jobs=[]
    for turn in ('one','two','three'):
        with store.history_guard(model._owner,model.history_file_path):
            jobs.append(file_jobs.create_job(store,owner=model._owner,conversation=model._conversation_id,
                history=model.history_file_path,session='sess_one',turn=turn,generation=turn,connection_ref=model._connection_reference()))
    assert registry.submit(store,jobs[0],runner,env.history_dir);assert ready.wait(3)
    assert registry.submit(store,jobs[1],runner,env.history_dir)
    assert not registry.submit(store,jobs[2],runner,env.history_dir)
    assert file_jobs.get_job(store,jobs[2]['id'])['status']=='pending' and len(registry.active)==2
    release.set();registry.queue.join();assert count[0]==2


def test_file_persistence_barrier_preserves_new_save_in_both_orders(env,monkeypatch,tmp_path):
    monkeypatch.setattr(file_jobs.FILE_JOBS,'submit',lambda *a,**k:False)
    model=seed(env,monkeypatch,lambda command:iter([run_result()]))
    store=model._store();job=file_jobs.jobs_for(store,model._owner,model._conversation_id)[0];record=artifact(tmp_path)
    entered,release=Event(),Event();write=file_jobs._atomic_document
    def delayed(path,document):
        entered.set();assert release.wait(5);return write(path,document)
    monkeypatch.setattr(file_jobs,'_atomic_document',delayed)
    receiver=Thread(target=lambda:file_jobs.apply_receipts(store,job['id'],[record],env.history_dir));receiver.start();assert entered.wait(3)
    model._state.update(generation='new',turn_id='turn_two',outcome='in_progress')
    model.history[-1]['content']='newest';model._display[-1][1]='newest'
    # Save blocks at history_guard and then overlays the newly durable file.
    saver=Thread(target=lambda:model.auto_save(model.chatbot));saver.start()
    assert saver.is_alive();release.set();receiver.join(5);saver.join(5)
    assert not receiver.is_alive() and not saver.is_alive()
    binding=store.get(model._owner,model.history_file_path)
    assert binding['state']['generation']=='new' and binding['artifacts'][0]['status']=='ready'
    document=json.loads((env.history_dir/model.history_file_path).read_text())
    assert document['agent_transcript']['files'][0]['source_id']=='file'


def test_late_file_controls_carry_turn_placement_without_claiming_api_message(env,monkeypatch,tmp_path):
    record=artifact(tmp_path)
    def worker(command):
        yield run_result() if command['action']=='run' else dict(type='result',artifacts=[record])
    model=seed(env,monkeypatch,worker);wait_files(model)
    from modules.agent.ui import ArtifactPanel, message_file_projection
    from modules.agent.message_files import _anchor
    import xml.etree.ElementTree as ET
    card=ET.fromstring(ArtifactPanel.values(model)[1]['value']).find('button')
    assert card.get('data-file-after-key') and card.get('data-file-after-key') != card.get('data-message-key')
    assert model._transcript['files'][0]['attachment']['basis']=='turn_only'
    assert model._transcript['files'][0]['attachment']['message_ref'] is None
    projection=message_file_projection(model)
    assert card.get('data-file-after-key') in projection.row_anchors.values()


def test_file_json_failure_settles_failed_job_and_explicit_retry_repairs(env,monkeypatch,tmp_path):
    record=artifact(tmp_path)
    def worker(command):
        yield run_result() if command['action']=='run' else dict(type='result',artifacts=[dict(record,status='preparing')] if not command.get('artifact_ids') else [record])
    atomic=file_jobs._atomic_document
    def failure(*args):raise OSError('synthetic file JSON failure')
    monkeypatch.setattr(file_jobs,'_atomic_document',failure)
    model=seed(env,monkeypatch,worker);wait_files(model)
    job=file_jobs.jobs_for(model._store(),model._owner,model._conversation_id)[0]
    assert job['status']=='failed' and job['error']
    assert model._store().get(model._owner,model.history_file_path)['local_phase']=='settled'
    model._assert_idle()
    monkeypatch.setattr(file_jobs,'_atomic_document',atomic)
    list(model.retry_artifact('file'));wait_files(model)
    jobs=file_jobs.jobs_for(model._store(),model._owner,model._conversation_id)
    assert jobs[-1]['status']=='done' and model._artifacts[0]['status']=='ready'
    document=json.loads((env.history_dir/model.history_file_path).read_text())
    assert document['agent_transcript']['files'][0]['source_id']=='file'


def test_rename_job_alias_failure_rolls_back_history_and_binding(env,monkeypatch):
    monkeypatch.setattr(file_jobs.FILE_JOBS,'submit',lambda *a,**k:False)
    model=seed(env,monkeypatch,lambda command:iter([run_result()]))
    before=model.history_file_path
    def fail(*args):raise OSError('synthetic alias migration failure')
    monkeypatch.setattr(file_jobs,'move_jobs',fail)
    with pytest.raises(OSError):model.rename_chat_history('failed-rename.json')
    assert model.history_file_path==before and (env.history_dir/before).is_file()
    assert not (env.history_dir/'failed-rename.json').exists()
    assert model._store().get(model._owner,before)['conversation_id']==model._conversation_id
    assert model._store().get(model._owner,'failed-rename.json') is None
    assert file_jobs.jobs_for(model._store(),model._owner,model._conversation_id)[0]['history']==before.removesuffix('.json')


def test_stale_pending_snapshot_cannot_reactivate_finished_job(env,monkeypatch):
    monkeypatch.setattr(file_jobs.FILE_JOBS,'submit',lambda *a,**k:False)
    model=seed(env,monkeypatch,lambda command:iter([run_result()]))
    store=model._store();old=file_jobs.jobs_for(store,model._owner,model._conversation_id)[0]
    finished=dict(old,status='done');file_jobs._put_job(store,finished)
    calls=[]
    def runner(command):calls.append(command);yield dict(type='result',artifacts=[])
    registry=file_jobs.FileJobRegistry()
    assert registry.submit(store,old,runner,env.history_dir)
    registry.queue.join()
    assert not calls and file_jobs.get_job(store,old['id'])['status']=='done'
