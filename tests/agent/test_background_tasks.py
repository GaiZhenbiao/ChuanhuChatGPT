"""Deterministic background lifecycle tests: temporary history, no API calls."""
from copy import deepcopy
import json
from threading import Event
from types import SimpleNamespace

import gradio as gr
import pytest
from agent_fixtures import env, request, select, send


def finish(task):
    task.thread.join(5)
    assert not task.thread.is_alive()
    assert task.error is None
    from agent_fixtures import settle_files
    settle_files(task.model)


def new_chat(env, model):
    from modules.agent.ui import AgentPanel
    caps = SimpleNamespace(stream_values=lambda model: [])
    return AgentPanel().wrap_reset(env.wrappers['reset'], caps)(model, False, request())[0]


def open_history(env, monkeypatch, model, filename):
    from modules.history_selection import load_history_model
    monkeypatch.setattr(env.presets, 'HISTORY_DIR', str(env.history_dir), raising=False)
    return load_history_model(model, filename, request())[0]


def test_close_new_switch_back_reuses_worker_and_saves_old_answer(env, monkeypatch):
    ready, release = Event(), Event()
    calls = []
    def worker(command):
        calls.append(command['action'])
        if command['action'] == 'run':
            yield dict(type='progress', session_id='session_A', turn_id='turn_A', outcome='in_progress', text='partial', submission_started=True)
            ready.set(); assert release.wait(5)
            yield dict(type='result', session_id='session_A', turn_id='turn_A', outcome='completed', text='final A', sync_complete=True)
        elif command['action'] == 'download': yield dict(type='result', artifacts=[])
        else: raise AssertionError(command)
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    model = select(env)
    stream = env.wrappers['predict'](model, 'A', [], request=request())
    next(stream); assert ready.wait(3)
    task = model._background_task
    stream.close()
    try:
        fresh = new_chat(env, model)
        assert fresh is not model and fresh.chatbot == []
        view = open_history(env, monkeypatch, fresh, model.history_file_path)
        assert view is not task.model and view._background_task is task
        assert view.chatbot[-1][1] == 'partial'
        subscription = task.subscribe(view)
        next(subscription); subscription.close()
        assert calls == ['run']
        release.set(); finish(task)
        assert json.loads((env.history_dir / model.history_file_path).read_text())['history'][-1]['content'] == 'final A'
        assert fresh.chatbot == []
        assert calls == ['run', 'download']
        assert view._store().get(view._owner, view.history_file_path)['state']['outcome'] == 'completed'
    finally:
        release.set(); task.thread.join(5)


def test_distinct_conversations_run_concurrently_stop_targets_original(env, monkeypatch):
    ready = {'A': Event(), 'B': Event()}; release = Event(); cancelled = []
    def worker(command):
        if command['action'] == 'run':
            name = command['prompt']
            yield dict(type='progress', session_id='session_'+name, turn_id='turn_'+name, outcome='in_progress', submission_started=True)
            ready[name].set(); assert release.wait(5)
            yield dict(type='result', session_id='session_'+name, turn_id='turn_'+name,
                       outcome='cancelled' if name == 'A' else 'completed', text='answer '+name)
        elif command['action'] == 'cancel':
            cancelled.append((command['session_id'], command['turn_id']))
            yield dict(type='result', outcome='cancel_requested')
        elif command['action'] == 'download': yield dict(type='result', artifacts=[])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    a = select(env); sa = env.wrappers['predict'](a, 'A', [], request=request()); next(sa)
    assert ready['A'].wait(3)
    b = new_chat(env, a); sb = env.wrappers['predict'](b, 'B', [], request=request()); next(sb)
    assert ready['B'].wait(3)
    try:
        assert a.history_file_path != b.history_file_path
        view = open_history(env, monkeypatch, b, a.history_file_path)
        env.wrappers['interrupt'](view, request=request())
        assert cancelled == [('session_A', 'turn_A')]
        assert not b._cancel_requested
        release.set(); finish(a._background_task); finish(b._background_task)
        assert a.history[-1]['content'] == 'answer A'
        assert b.history[-1]['content'] == 'answer B'
    finally:
        release.set(); sa.close(); sb.close()
        a._background_task.thread.join(5); b._background_task.thread.join(5)


def test_duplicate_before_session_exists_is_atomic_and_owner_scoped(env, monkeypatch):
    ready, release = Event(), Event(); runs = []
    def worker(command):
        if command['action'] == 'run':
            runs.append(command); ready.set(); assert release.wait(5)
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='done')
        elif command['action'] == 'download': yield dict(type='result', artifacts=[])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    model = select(env); stream = env.wrappers['predict'](model, 'one', [], request=request()); next(stream)
    assert ready.wait(3)
    try:
        view = open_history(env, monkeypatch, new_chat(env, model), model.history_file_path)
        with pytest.raises(gr.Error): send(env, view, 'duplicate')
        assert len(runs) == 1
        from modules.agent.tasks import TASKS
        other = model.new_view(); other._owner = 'another-owner'; other._conversation_id = model._conversation_id
        assert TASKS.find(other) is None
        assert TASKS.find(other, model.history_file_path) is None
    finally:
        release.set(); finish(model._background_task); stream.close()


def test_terminal_download_releases_task_and_follows_rename_after_ui_detach(env, monkeypatch, tmp_path):
    ready, release = Event(), Event()
    import tempfile
    from pathlib import Path
    file = Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-'))/'result.txt'; file.write_text('saved')
    def worker(command):
        if command['action'] == 'run':
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='answer', sync_complete=True, items=[dict(id='u',type='message',role='user',turn_id='t',status='completed',content=[dict(type='input_text',text='file task')]), dict(id='a',type='message',role='assistant',turn_id='t',status='completed',content=[dict(type='output_text',text='answer')])])
        elif command['action'] == 'download':
            ready.set(); assert release.wait(5)
            yield dict(type='result', artifacts=[dict(id='file', session_id='s', turn_id='t', name='result.txt', type='text/plain', status='ready', path=str(file), size=5)])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    model = select(env); stream = env.wrappers['predict'](model, 'file task', [], request=request()); next(stream)
    assert ready.wait(3)
    try:
        model._background_task.thread.join(3)
        assert model._background_task.done
        model._assert_idle()
        fresh = new_chat(env, model)
        old = model.history_file_path
        model.rename_chat_history('renamed')
        stream.close(); release.set(); finish(model._background_task)
        binding = model._store().get(model._owner, model.history_file_path)
        assert binding['artifacts'][0]['path'] == str(file)
        assert not (env.history_dir/old).exists()
        assert fresh._artifacts == [] and fresh.chatbot == []
        from modules.agent.tasks import TASKS
        assert TASKS.find(model) is None
    finally:
        release.set(); model._background_task.thread.join(5); stream.close()


def test_stale_view_cannot_roll_back_background_binding_or_json(env, monkeypatch):
    ready, advance, advanced, release = Event(), Event(), Event(), Event()
    def worker(command):
        if command['action'] == 'run':
            yield dict(type='progress', session_id='s', turn_id='t', outcome='in_progress', text='old', submission_started=True)
            ready.set(); assert advance.wait(5)
            yield dict(type='progress', session_id='s', turn_id='t', outcome='in_progress', text='new',
                       artifacts=[dict(id='latest', session_id='s', turn_id='t', name='latest.txt', status='preparing')])
            advanced.set(); assert release.wait(5)
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='final')
        elif command['action'] == 'download': yield dict(type='result', artifacts=[])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    model = select(env); stream = env.wrappers['predict'](model, 'A', [], request=request()); next(stream)
    assert ready.wait(3)
    try:
        view = open_history(env, monkeypatch, new_chat(env, model), model.history_file_path)
        assert view.chatbot[-1][1] == 'old'
        advance.set(); assert advanced.wait(3)
        before = deepcopy(model._store().get(model._owner, model.history_file_path))
        view._remember(); view.auto_save(view.chatbot)
        new_chat(env, view)
        after = model._store().get(model._owner, model.history_file_path)
        assert after == before and after['artifacts'][0]['id'] == 'latest'
        release.set(); finish(model._background_task)
    finally:
        advance.set(); release.set(); model._background_task.thread.join(5); stream.close()


@pytest.mark.parametrize('submission_started', [False, True])
def test_restart_intent_without_session_recovers_unknown_without_post(env, monkeypatch, submission_started):
    model = select(env)
    model._task_backend = True
    model._state = dict(outcome='starting', generation='durable-intent', submission_started=submission_started)
    model.history = [{'role':'user','content':'question'}, {'role':'assistant','content':''}]
    model.chatbot = model._display = [['question','']]
    model.auto_save(model.chatbot)
    calls = []
    def worker(command):
        calls.append(command['action'])
        assert command['action'] in ('observe_unknown', 'recover_unknown', 'download')
        yield dict(type='result', outcome='incomplete', session_id=None)
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    restored = select(env); restored.load_chat_history(model.history_file_path)
    assert restored._state['outcome'] == 'uncertain'
    list(restored.observe_history())
    assert calls == ['observe_unknown']
    with pytest.raises(gr.Error): restored._assert_idle()
    assert restored.history[0]['content'] == 'question'


def test_thread_start_failure_rolls_back_all_reservations(env, monkeypatch):
    from modules.agent.tasks import TaskRegistry
    registry = TaskRegistry(); model = select(env)
    model._state.update(session_id='existing')
    def failed(*args): raise RuntimeError('thread unavailable')
    monkeypatch.setattr('modules.agent.tasks.Thread.start', failed)
    with pytest.raises(RuntimeError, match='thread unavailable'): registry.start(model, lambda: iter(()))
    assert registry.tasks == registry.sessions == {}
    assert not getattr(model, '_background_busy', False)
    assert not getattr(model, '_task_backend', False)


def test_capacity_rejects_before_execute_and_completed_tasks_are_reclaimed(env, monkeypatch):
    from modules.agent.tasks import TaskRegistry
    registry = TaskRegistry(limit=1, owner_limit=1)
    a, b = select(env), select(env); ready, release = Event(), Event()
    def execute():
        ready.set(); assert release.wait(5)
        yield [], 'done'
    task = registry.start(a, execute); assert ready.wait(3)
    try:
        with pytest.raises(gr.Error, match='尚未提交'): registry.start(b, lambda: (_ for _ in ()).throw(AssertionError('must not execute')))
    finally: release.set(); finish(task)
    assert registry.tasks == registry.sessions == {}


def test_final_snapshot_is_frozen_before_new_generation_can_start(env, monkeypatch):
    from modules.agent.tasks import TaskRegistry
    registry = TaskRegistry()
    model = select(env); model._state = dict(outcome='completed', generation='first')
    model._display = model.chatbot = [['one', 'answer one']]
    entered, release = Event(), Event()
    original_finish = registry.finish
    def blocked_finish(task):
        entered.set(); assert release.wait(5)
        original_finish(task)
    monkeypatch.setattr(registry, 'finish', blocked_finish)
    first = registry.start(model, lambda: iter(())); assert entered.wait(3)
    try:
        with pytest.raises(gr.Error): registry.start(model, lambda: iter(()))
        assert first.snapshot[0]['_state']['generation'] == 'first'
    finally: release.set(); finish(first)
    model._state = dict(outcome='completed', generation='second')
    model._display = model.chatbot = [['two', 'answer two']]
    second = registry.start(model, lambda: iter(())); finish(second)
    assert first.snapshot[0]['_display'] == [['one', 'answer one']]
    assert first.snapshot[0]['_state']['generation'] == 'first'
    assert list(first.subscribe(model)) == []  # stale subscriber cannot project onto second
    assert second.snapshot[0]['_state']['generation'] == 'second'


def test_completed_projection_rename_preserves_trusted_session(env, monkeypatch):
    from test_runtime import message
    ready, release = Event(), Event()
    def worker(command):
        if command['action'] == 'run':
            yield dict(type='progress', session_id='trusted', turn_id='original', outcome='in_progress', submission_started=True)
            ready.set(); assert release.wait(5)
            yield dict(type='result', session_id='trusted', turn_id='original', outcome='completed', text='final', sync_complete=True,
                       items=[message('u','question','original',role='user'),message('a','final','original')])
        elif command['action'] == 'download': yield dict(type='result', artifacts=[])
        else: raise AssertionError('rename must not call API')
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    model = select(env); stream = env.wrappers['predict'](model, 'question', [], request=request()); next(stream)
    assert ready.wait(3)
    try:
        view = open_history(env, monkeypatch, new_chat(env, model), model.history_file_path)
        old = view.history_file_path
        release.set(); finish(model._background_task)
        view.rename_chat_history('renamed trusted')
        binding = view._store().get(view._owner, view.history_file_path)
        assert binding['state']['session_id'] == 'trusted' and binding['state']['turn_id'] == 'original'
        assert view._store().get(view._owner, old) is None
        restored = select(env); restored.load_chat_history(view.history_file_path)
        assert restored._state['session_id'] == 'trusted' and restored.chatbot[-1][1] == 'final'
    finally: release.set(); model._background_task.thread.join(5); stream.close()


def test_stop_receipt_from_finished_task_never_cancels_next_generation(env, monkeypatch):
    from modules.agent.tasks import TaskRegistry
    registry = TaskRegistry(); model = select(env); commands = []
    monkeypatch.setattr(env.agents, 'worker_messages', lambda command: commands.append(command) or iter([]))
    model._state = dict(outcome='completed', generation='first', session_id='s', turn_id='t1')
    first = registry.start(model, lambda: iter(())); finish(first)
    ready, release = Event(), Event()
    model._state = dict(outcome='in_progress', generation='second', session_id='s', turn_id='t2')
    def execute():
        yield [], 'running'
        ready.set(); assert release.wait(5)
    second = registry.start(model, execute); assert ready.wait(3)
    try:
        assert '未停止后续任务' in first.stop()
        assert model._state['generation'] == 'second' and not model._cancel_requested
        assert commands == []
    finally: release.set(); finish(second)


def test_waiting_authorization_survives_switch_and_never_auto_approves(env, monkeypatch):
    ready, approved = Event(), Event(); calls = []
    card = dict(request_id='approval', turn_id='t', request=dict(type='browser_origin_access', origin='https://example.com'))
    def worker(command):
        calls.append(command['action'])
        if command['action'] == 'run':
            yield dict(type='progress', session_id='s', turn_id='t', outcome='requires_action', required_actions=[card], submission_started=True)
            ready.set(); assert approved.wait(5)
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='approved explicitly')
        elif command['action'] == 'browser_response':
            assert command['session_id'] == 's' and command['turn_id'] == 't' and command['request_id'] == 'approval'
            assert command['response']['decision'] == 'approve'
            approved.set(); yield dict(type='result', accepted=True)
        elif command['action'] == 'download': yield dict(type='result', artifacts=[])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    model = select(env); stream = env.wrappers['predict'](model, 'permission', [], request=request()); next(stream)
    assert ready.wait(3)
    try:
        view = open_history(env, monkeypatch, new_chat(env, model), model.history_file_path)
        assert view._pending_actions[0]['request_id'] == 'approval'
        assert calls == ['run'] and not approved.is_set()
        view.respond_browser('approval', dict(type='browser_origin_access', decision='approve'))
        finish(model._background_task)
        assert calls == ['run', 'browser_response', 'download']
        assert model.history[-1]['content'] == 'approved explicitly'
    finally: approved.set(); model._background_task.thread.join(5); stream.close()


def test_background_attachment_preparation_can_stop_before_post(env, monkeypatch, tmp_path):
    import types
    from modules.agent.tools import validate_settings
    model = select(env); model._tool_settings = validate_settings(dict(code_execution=True))
    file = tmp_path/'attachment.txt'; file.write_text('synthetic')
    model._input_upload_roots=(str(tmp_path),)
    model.stage_input_files([str(file)])
    ready, release = Event(), Event(); runs=[]
    def prepare(self, records, generation, settings, reference):
        yield deepcopy(self._display), 'preparing'
        ready.set(); assert release.wait(5)
        return [dict(remote_path='/mnt/data/attachment.txt', name='attachment.txt')]
    monkeypatch.setattr(model, '_prepare_input_frames', types.MethodType(prepare, model))
    monkeypatch.setattr(env.agents, 'worker_messages', lambda command: runs.append(command) or iter([]))
    stream=env.wrappers['predict'](model, 'attachment', [], files=[str(file)], request=request()); next(stream)
    assert ready.wait(3)
    try:
        new_chat(env, model)
        model._background_task.stop(); release.set(); finish(model._background_task)
        assert runs == [] and model._state['outcome'] == 'not_started'
        assert model.history == []
    finally: release.set(); model._background_task.thread.join(5); stream.close()


def test_markdown_rename_failure_keeps_primary_path_and_binding_consistent(env, monkeypatch):
    import os
    from agent_fixtures import complete
    complete(env, monkeypatch)
    model=select(env); send(env, model)
    old=model.history_file_path
    (env.history_dir/old).with_suffix('.md').write_text('derived')
    replace=os.replace
    def fail_markdown(source, target):
        if str(source).endswith('.md'): raise OSError('derived markdown denied')
        return replace(source, target)
    monkeypatch.setattr(os, 'replace', fail_markdown)
    model.rename_chat_history('markdown failure')
    assert model.history_file_path == 'markdown failure.json'
    assert (env.history_dir/model.history_file_path).is_file()
    assert model._store().get(model._owner, model.history_file_path)['state']['session_id'] == 'sess_test'
    assert model._store().get(model._owner, old) is None
    assert 'Markdown' in model._notice


def test_client_stop_envelope_targets_A_even_if_current_server_state_is_B(env, monkeypatch):
    ready={'A':Event(),'B':Event()}; release=Event(); cancelled=[]
    def worker(command):
        if command['action']=='run':
            name=command['prompt']
            yield dict(type='progress',session_id='s'+name,turn_id='t'+name,outcome='in_progress',submission_started=True)
            ready[name].set(); assert release.wait(5)
            yield dict(type='result',session_id='s'+name,turn_id='t'+name,outcome='cancelled' if name=='A' else 'completed',text=name)
        elif command['action']=='cancel':
            cancelled.append((command['session_id'],command['turn_id']))
            yield dict(type='result',outcome='cancel_requested')
        elif command['action']=='download': yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    a=select(env); sa=env.wrappers['predict'](a,'A',[],request=request());next(sa);assert ready['A'].wait(3)
    envelope=dict(conversation=a._conversation_id,generation=a._state['generation'])
    b=new_chat(env,a); sb=env.wrappers['predict'](b,'B',[],request=request());next(sb);assert ready['B'].wait(3)
    try:
        env.wrappers['interrupt'](b,envelope,request=request())
        assert cancelled==[('sA','tA')] and not b._cancel_requested
        stale=dict(envelope,generation='obsolete')
        env.wrappers['interrupt'](b,stale,request=request())
        assert cancelled==[('sA','tA')]
    finally:release.set();finish(a._background_task);finish(b._background_task);sa.close();sb.close()


def test_reserved_ordinary_filename_does_not_reuse_existing_minute_history(env):
    import datetime
    from offline_models import definitions
    scope=dict(HISTORY_DIR=str(env.history_dir),os=__import__('os'),i18n=lambda key:'New ',
               datetime=SimpleNamespace(datetime=SimpleNamespace(now=lambda:datetime.datetime(2026,10,4,10,0))))
    definitions(env.root/'modules/utils.py',{'new_auto_history_filename'},scope)
    first=scope['new_auto_history_filename']('')
    (env.history_dir/first).write_text('existing history')
    second=scope['new_auto_history_filename']('')
    assert second != first and second=='New 10-04 10-00 (2).json'
    assert not (env.history_dir/second).exists()
    assert (env.history_dir/first).read_text()=='existing history'


def test_stale_stop_fallback_rechecks_generation_before_pending_cancel(env, monkeypatch):
    from modules.agent.tasks import TASKS
    model=select(env)
    model._state['generation']='old'
    target=dict(conversation=model._conversation_id,generation='old')
    def race(*args):
        model._state['generation']='new'
        model._pending_send='new reservation'
        return None
    monkeypatch.setattr(TASKS,'find_conversation',race)
    env.wrappers['interrupt'](model,target,request=request())
    assert model._pending_send=='new reservation' and not model._cancel_requested


def test_direct_stop_generation_guard_preserves_new_round(env):
    model=select(env)
    model._state['generation']='new'
    model._pending_send='new reservation'
    model.interrupt(expected_generation='old')
    assert model._pending_send=='new reservation' and not model._cancel_requested


def test_direct_stop_none_generation_guard_preserves_new_round(env):
    model=select(env)
    model._state['generation']='new'
    model.interrupt(expected_generation=None)
    assert not model._cancel_requested


def test_fork_must_reject_while_task_downloads(env,monkeypatch):
    ready,release=Event(),Event()
    def worker(command):
        if command['action']=='run':
            yield dict(type='result',session_id='s',turn_id='t',outcome='completed',text='answer',sync_complete=True)
        elif command['action']=='download':
            ready.set();assert release.wait(5)
            yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model=select(env)
    stream=env.wrappers['predict'](model,'task',[],request=request());next(stream)
    task=model._background_task
    assert ready.wait(3)
    try:
        with pytest.raises(gr.Error):model.new_session_from_history()
    finally:
        release.set();task.thread.join(5);stream.close()


def test_stream_saves_keep_recency_until_new_user_turn(env,monkeypatch):
    import os
    from agent_fixtures import complete
    complete(env,monkeypatch)
    model=select(env);send(env,model)
    path=env.history_dir/model.history_file_path
    os.utime(path,ns=(1_000_000_000,1_000_000_000))
    model.auto_save(model.chatbot)
    assert path.stat().st_mtime_ns==1_000_000_000
    model.history.extend([{'role':'user','content':'next'},{'role':'assistant','content':'answer'}])
    model.auto_save(model.chatbot)
    assert path.stat().st_mtime_ns>1_000_000_000
