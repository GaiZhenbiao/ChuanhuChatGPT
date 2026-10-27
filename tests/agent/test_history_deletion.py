"""Local deletion lifecycle using synthetic tasks, files and durable bindings."""
from copy import deepcopy
from pathlib import Path
from threading import Event, Thread
import json
import gradio as gr
import pytest
from agent_fixtures import env, select, request, send, complete
from test_background_tasks import new_chat, finish
from modules.agent.tasks import TASKS
from modules.agent.store import BindingStore


def saved(env, outcome='completed',username=None):
    model=select(env,username=username)
    model.history_file_path='delete-me.json'
    model.history=[{'role':'user','content':'question'},{'role':'assistant','content':'answer'}]
    model.chatbot=model._display=[['question','answer']]
    model._state=dict(outcome=outcome,session_id='old-session',turn_id='old-turn',generation='old-generation')
    model.auto_save(model.chatbot)
    return model


def deleted(env, model):
    path=env.history_dir/model.user_name/Path(model.history_file_path).name
    assert not path.exists() and not path.with_suffix('.md').exists()
    assert model._store().get(model._owner, model.history_file_path) is None
    return model._store().deletion_receipt(model._owner, model.history_file_path, model._conversation_id)


@pytest.mark.parametrize('outcome',['completed','failed','cancelled','in_progress','incomplete','starting','uncertain'])
def test_restart_old_binding_and_unsynced_state_do_not_block_local_delete(env,monkeypatch,outcome):
    from test_background_tasks import open_history
    original=saved(env,outcome)
    assert TASKS.find(original) is None
    model=open_history(env,monkeypatch,original.new_view(),original.history_file_path)
    assert model._needs_sync and model._state['generation']=='old-generation'
    assert model._conversation_id==original._conversation_id
    stale=model.new_view();stale.history_file_path=model.history_file_path;stale._conversation_id=model._conversation_id
    stale._state=deepcopy(model._state);stale.history=deepcopy(model.history);stale.chatbot=deepcopy(model.chatbot)
    result=env.wrappers['delete_chat_history'](model, model.history_file_path,request=request())
    receipt=deleted(env,model)
    assert receipt['last_known_outcome']==outcome and not receipt['remote_stop_confirmed'] and receipt['remote_stop']=='not_requested'
    assert receipt['session_id']=='old-session' and receipt['turn_id']=='old-turn' and receipt['generation']=='old-generation'
    if outcome not in ('completed','failed','cancelled'):assert '云端任务停止未确认' in result[0]
    assert model._retired and model._history_deleted and model._state['outcome']==outcome
    assert BindingStore(env.agents.shared.chuanhu_path).is_history_deleted(model._owner,model.history_file_path,model._conversation_id)
    stale.auto_save(stale.chatbot);stale._remember();deleted(env,model)
    with pytest.raises(gr.Error):stale._assert_idle()


@pytest.mark.parametrize('phase',['running','completed_download'])
def test_active_task_delete_retires_readers_and_late_output_cannot_restore_history(env,monkeypatch,tmp_path,phase):
    ready,release=Event(),Event();commands=[]
    file=tmp_path/'result.txt';file.write_text('synthetic')
    def worker(command):
        commands.append(command['action'])
        if command['action']=='run':
            yield dict(type='progress',session_id='s',turn_id='t',outcome='in_progress',text='partial',submission_started=True)
            if phase=='running':
                ready.set();assert release.wait(5)
                assert command['_observe_cancel']()
            yield dict(type='result',session_id='s',turn_id='t',outcome='completed',text='late final',sync_complete=True)
        elif command['action']=='download':
            if phase=='completed_download':
                ready.set();assert release.wait(5)
                assert command['_observe_cancel']()
            yield dict(type='result',artifacts=[dict(id='f',session_id='s',turn_id='t',name='result.txt',size=9,status='ready',path=str(file))])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model=select(env);stream=env.wrappers['predict'](model,'question',[],request=request());next(stream)
    assert ready.wait(3);task=model._background_task;fresh=new_chat(env,model)
    try:
        result=env.wrappers['delete_chat_history'](fresh,model.history_file_path,request=request())
        receipt=deleted(env,model)
        assert TASKS.find(model) is None
        if phase == 'completed_download':
            task.thread.join(3)
            assert task.done
        else:
            assert task.deleted and task in TASKS.retiring
        expected = '该轮任务已结束，未停止后续任务' if phase == 'completed_download' else '本地历史已删除，云端任务停止未确认'
        assert task.stop()==expected and 'cancel' not in commands
        assert model._local_history_deleted() and not fresh._retired and fresh.chatbot==[]
        assert list(task.subscribe(fresh))==[]
        assert receipt['remote_stop_confirmed'] is False
        release.set();finish(task);assert task not in TASKS.retiring
        deleted(env,model);assert list(stream)==[]
    finally:release.set();task.thread.join(5);stream.close()


def test_old_history_read_only_observation_can_be_deleted_without_waiting_remote(env,monkeypatch):
    model=saved(env);model._needs_sync=True;ready,release=Event(),Event()
    def worker(command):
        assert command['action']=='observe'
        ready.set();assert release.wait(5)
        assert command['_observe_cancel']()
        yield dict(type='result',session_id='old-session',turn_id='old-turn',outcome='completed',text='late recovered')
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    task=TASKS.start(model,lambda:model.observe_history(),read_only=True);assert ready.wait(3)
    try:
        result=env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
        assert task.deleted and model._retired and TASKS.find(model) is None
        release.set();finish(task);deleted(env,model)
        assert model._state['outcome']=='completed'
    finally:release.set();task.thread.join(5)


def test_file_write_started_before_delete_finishes_before_unlink(env,monkeypatch):
    model=saved(env);started,release,deleted_done=Event(),Event(),Event();errors=[]
    parent=env.agents.BaseLLMModel.auto_save
    def blocked(self,chatbot=None):
        started.set();assert release.wait(5);return parent(self,chatbot)
    monkeypatch.setattr(env.agents.BaseLLMModel,'auto_save',blocked)
    writer=Thread(target=lambda:model.auto_save(model.chatbot));writer.start();assert started.wait(3)
    def delete():
        try:env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
        except Exception as error:errors.append(error)
        finally:deleted_done.set()
    deleter=Thread(target=delete);deleter.start()
    assert not deleted_done.wait(.1)
    release.set();writer.join(5);deleter.join(5)
    assert not writer.is_alive() and not deleter.is_alive() and not errors
    deleted(env,model);model.auto_save(model.chatbot);deleted(env,model)


def test_same_filename_new_conversation_survives_old_deleted_task_cleanup(env,monkeypatch):
    ready,release=Event(),Event();calls=[]
    def worker(command):
        calls.append(command['action'])
        if command['action']=='run':
            yield dict(type='progress',session_id='old-session',turn_id='old-turn',outcome='in_progress',submission_started=True)
            ready.set();assert release.wait(5)
            yield dict(type='result',session_id='old-session',turn_id='old-turn',outcome='completed',text='OLD')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    old=select(env);stream=env.wrappers['predict'](old,'old',[],request=request());next(stream);assert ready.wait(3)
    task=old._background_task
    try:
        env.wrappers['delete_chat_history'](old,old.history_file_path,request=request())
        new=old.new_view();new.history_file_path=old.history_file_path
        new.history=[{'role':'user','content':'NEW'},{'role':'assistant','content':'new answer'}];new.chatbot=new._display=[['NEW','new answer']]
        new._state=dict(outcome='completed',session_id='NEW-session',turn_id='NEW-turn',generation='NEW-generation')
        new.auto_save(new.chatbot)
        binding=deepcopy(new._store().get(new._owner,new.history_file_path));path=env.history_dir/Path(new.history_file_path).name;wire=path.read_bytes()
        assert binding['conversation_id']==new._conversation_id and new._conversation_id!=old._conversation_id
        assert not new._local_history_deleted()
        assert task.stop()=='本地历史已删除，云端任务停止未确认'
        release.set();finish(task)
        old._remember();old.auto_save(old.chatbot)
        assert new._store().get(new._owner,new.history_file_path)==binding and path.read_bytes()==wire
        assert 'cancel' not in calls
    finally:release.set();task.thread.join(5);stream.close()


def test_delete_one_conversation_keeps_other_conversation_binding_and_file(env):
    target=saved(env);other=target.new_view();other.history_file_path='other.json'
    other.history=deepcopy(target.history);other.chatbot=deepcopy(target.chatbot);other._state=deepcopy(target._state)
    other._state.update(session_id='other-session',turn_id='other-turn',generation='other-generation');other.auto_save(other.chatbot)
    binding=deepcopy(other._store().get(other._owner,other.history_file_path));path=env.history_dir/'other.json';wire=path.read_bytes()
    env.wrappers['delete_chat_history'](other,target.history_file_path,request=request())
    assert not other._retired and not other._local_history_deleted()
    assert other._store().get(other._owner,other.history_file_path)==binding and path.read_bytes()==wire
    deleted(env,target)


def test_cancelled_confirmation_does_not_retire_or_delete(env):
    model=saved(env);before=model._store().get(model._owner,model.history_file_path)
    env.wrappers['delete_chat_history'](model,'CANCELED',request=request())
    assert not model._retired and not model._history_deleted and model._store().get(model._owner,model.history_file_path)==before
    assert (env.history_dir/model.history_file_path).exists()


def test_ordinary_delete_still_removes_ordinary_json_and_markdown(env):
    model=select(env,name='GPT3.5 Turbo');model.history_file_path='ordinary.json';model.history=[{'role':'user','content':'q'},{'role':'assistant','content':'a'}];model.chatbot=[['q','a']]
    model.auto_save(model.chatbot)
    result=env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
    assert result[-1]==[] and not (env.history_dir/'ordinary.json').exists() and not (env.history_dir/'ordinary.md').exists()


def test_delete_current_busy_history_then_ui_new_chat_can_send(env,monkeypatch):
    ready,release=Event(),Event()
    def worker(command):
        if command['action']=='run':
            if command['prompt']=='old':
                yield dict(type='progress',session_id='old-s',turn_id='old-t',outcome='in_progress',submission_started=True)
                ready.set();assert release.wait(5)
            yield dict(type='result',session_id='fresh-s',turn_id='fresh-t',outcome='completed',text='fresh answer')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    old=select(env);stream=env.wrappers['predict'](old,'old',[],request=request());next(stream);assert ready.wait(3);task=old._background_task
    try:
        env.wrappers['delete_chat_history'](old,old.history_file_path,request=request())
        fresh=new_chat(env,old)
        assert not fresh._retired and fresh._state['outcome']=='not_started' and fresh._conversation_id!=old._conversation_id
        send(env,fresh,'new');assert fresh.chatbot==[['new','fresh answer']] and not fresh._running
        release.set();finish(task);deleted(env,old)
    finally:release.set();task.thread.join(5);stream.close()


def test_waiting_subscriber_wakes_on_delete_without_waiting_worker(env):
    model=saved(env);release=Event();started=Event()
    def execute():
        yield None
        started.set();assert release.wait(5)
        yield None
    task=TASKS.start(model,execute);assert started.wait(3)
    view=model.new_view();view._background_task=task;task.project(view)
    subscription=task.subscribe(view);next(subscription)
    waiting,returned=Event(),Event();frames=[]
    def read():
        waiting.set();frames.extend(subscription);returned.set()
    reader=Thread(target=read);reader.start();assert waiting.wait(1)
    try:
        env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
        assert returned.wait(1) and not frames and not task.done
        assert task.deleted and task in TASKS.retiring
    finally:release.set();task.thread.join(5);reader.join(3);subscription.close()


def test_draining_deleted_threads_still_count_against_capacity(env,monkeypatch):
    model=saved(env);release=Event();started=Event()
    monkeypatch.setattr(TASKS,'limit',1);monkeypatch.setattr(TASKS,'owner_limit',1)
    def execute():
        started.set();assert release.wait(5)
        yield None
    task=TASKS.start(model,execute);assert started.wait(3)
    try:
        env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
        fresh=model.new_view()
        with pytest.raises(gr.Error,match='后台任务数量已达上限'):TASKS.start(fresh,lambda:iter(()))
        release.set();finish(task)
        next_task=TASKS.start(fresh,lambda:iter(()));finish(next_task)
    finally:release.set();task.thread.join(5)


def test_pending_first_submission_cannot_dispatch_after_local_delete(env):
    model=saved(env,'starting');model._pending_send={'token':'pending'}
    env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
    assert model._pending_send is None and model._retired
    with pytest.raises(gr.Error,match='此本地历史已删除'):TASKS.start(model,lambda:iter(()))
    deleted(env,model)


def test_same_filename_for_two_legitimate_owners_is_isolated(env):
    alice=saved(env,username='alice');bob=saved(env,username='bob')
    binding=deepcopy(bob._store().get(bob._owner,bob.history_file_path))
    path=env.history_dir/'bob'/bob.history_file_path;wire=path.read_bytes()
    env.wrappers['delete_chat_history'](alice,alice.history_file_path,request=request(username='alice'))
    deleted(env,alice)
    assert bob._store().get(bob._owner,bob.history_file_path)==binding and path.read_bytes()==wire
    assert not bob._local_history_deleted() and not bob._retired


def test_old_title_rename_after_delete_cannot_create_a_new_binding(env):
    model=saved(env);stale=model.new_view();stale.history_file_path=model.history_file_path
    stale._conversation_id=model._conversation_id;stale._state=deepcopy(model._state)
    stale.history=deepcopy(model.history);stale.chatbot=deepcopy(model.chatbot);stale._display=deepcopy(model.chatbot)
    env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
    with pytest.raises(gr.Error,match='此本地历史已删除'):stale.rename_chat_history('late title')
    assert stale._store().get(stale._owner,'late title.json') is None and not (env.history_dir/'late title.json').exists()
    deleted(env,model)


def test_ordinary_current_model_can_delete_another_agent_binding(env):
    agent=saved(env,'incomplete');ordinary=select(env,name='GPT3.5 Turbo')
    ordinary._chat_running=True
    env.wrappers['delete_chat_history'](ordinary,agent.history_file_path,request=request())
    deleted(env,agent);assert ordinary._chat_running is True


def test_missing_derived_markdown_does_not_block_agent_delete(env):
    model=saved(env);(env.history_dir/Path(model.history_file_path).with_suffix('.md')).unlink()
    env.wrappers['delete_chat_history'](model,model.history_file_path,request=request());deleted(env,model)


def test_delete_before_observer_first_snapshot_keeps_durable_generation(env,monkeypatch):
    model=saved(env,'in_progress');fresh=model.new_view();entered,release=Event(),Event()
    def execute():
        entered.set();assert release.wait(5)
        yield None
    task=TASKS.start(model,execute);assert entered.wait(3) and task.snapshot is None
    reservation=(model._owner,'old-session');monkeypatch.setitem(env.agents._session_locks,reservation,model)
    try:
        env.wrappers['delete_chat_history'](fresh,model.history_file_path,request=request())
        receipt=deleted(env,model)
        assert receipt['generation']=='old-generation' and receipt['session_id']=='old-session' and receipt['turn_id']=='old-turn'
        release.set();finish(task);assert reservation not in env.agents._session_locks
    finally:release.set();task.thread.join(5)


def test_deleted_task_actual_exit_releases_only_its_owned_memory_reservations(env,monkeypatch):
    model=saved(env,'in_progress');entered,release=Event(),Event()
    def execute():
        yield None
        entered.set();assert release.wait(5)
        yield None
    task=TASKS.start(model,execute);assert entered.wait(3)
    other=model.new_view();old_key=(model._owner,'old-session');new_key=(model._owner,'new-session')
    monkeypatch.setitem(env.agents._session_locks,old_key,model)
    monkeypatch.setitem(env.agents._session_locks,new_key,other)
    try:
        env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
        assert env.agents._session_locks[old_key] is model
        release.set();finish(task)
        assert old_key not in env.agents._session_locks and env.agents._session_locks[new_key] is other
    finally:release.set();task.thread.join(5)


def test_direct_save_and_export_from_stale_deleted_view_do_not_recreate_files(env):
    model=saved(env);stale=model.new_view();stale.history_file_path=model.history_file_path;stale._conversation_id=model._conversation_id
    stale.history=deepcopy(model.history);stale.chatbot=deepcopy(model.chatbot);stale._state=deepcopy(model._state)
    old_binding=deepcopy(model._store().get(model._owner,model.history_file_path))
    env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
    env.wrappers['save_file'](stale.history_file_path,stale)
    stale.export_markdown('late export',stale.chatbot)
    stale._store().put(stale._owner,stale.history_file_path,old_binding)
    deleted(env,model)
    assert not (env.history_dir/'late export.json').exists() and not (env.history_dir/'late export.md').exists()


@pytest.mark.parametrize('failed_suffix',['.json','.md'])
def test_local_unlink_failure_is_reported_without_claiming_remote_stop(env,monkeypatch,failed_suffix):
    model=saved(env,'in_progress');unlink=Path.unlink
    def fail(self,*args,**kwargs):
        if self.parent==env.history_dir and self.suffix==failed_suffix:raise PermissionError('synthetic unavailable file')
        return unlink(self,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',fail)
    if failed_suffix=='.json':
        with pytest.raises(gr.Error,match='本地历史文件删除失败'):env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
        assert (env.history_dir/model.history_file_path).exists()
    else:
        result=env.wrappers['delete_chat_history'](model,model.history_file_path,request=request())
        assert 'Markdown 导出未能移除' in result[0] and '云端任务停止未确认' in result[0]
        assert not (env.history_dir/model.history_file_path).exists()
    assert model._store().get(model._owner,model.history_file_path) is None and model._history_deleted
    assert not model._store().deletion_receipt(model._owner,model.history_file_path,model._conversation_id)['remote_stop_confirmed']


def test_delete_rename_destination_serializes_with_late_title_move(env,monkeypatch):
    model=saved(env);fresh=model.new_view();copied,release,deleted_done=Event(),Event(),Event();errors=[]
    copy=BindingStore.copy_binding
    def wait(self,*args,**kwargs):
        result=copy(self,*args,**kwargs);copied.set();assert release.wait(5);return result
    monkeypatch.setattr(BindingStore,'copy_binding',wait)
    def rename():
        try:model.rename_chat_history('renamed')
        except Exception as error:errors.append(error)
    def delete():
        try:env.wrappers['delete_chat_history'](fresh,'renamed',request=request())
        except Exception as error:errors.append(error)
        finally:deleted_done.set()
    renamer=Thread(target=rename);renamer.start();assert copied.wait(3)
    deleter=Thread(target=delete);deleter.start();assert not deleted_done.wait(.1)
    release.set();renamer.join(5);deleter.join(5)
    assert not renamer.is_alive() and not deleter.is_alive() and not errors
    assert model.history_file_path=='renamed.json';deleted(env,model)
    assert not (env.history_dir/'delete-me.json').exists()
