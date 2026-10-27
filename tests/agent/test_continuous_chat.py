"""连续新建/提交/历史切换使用独立合成数据，不请求供应商。"""
from copy import deepcopy
import json
import pytest
import gradio as gr
from agent_fixtures import env, select, request, send, settle_files


@pytest.mark.parametrize('name', ['GPT3.5 Turbo', 'OpenAI Agent'])
def test_reserved_draft_is_neither_listed_nor_selected(env, name):
    from modules.models.base_model import init_history_list
    model = select(env, name=name)
    draft = model.history_file_path.removesuffix('.json')
    radio = init_history_list(model.user_name, prepend=draft)
    assert radio.value is None and draft not in [value for _, value in radio.choices]
    assert not list(env.history_dir.glob('*.json'))


def test_actual_submission_saves_before_terminal_and_selects_existing_file(env, monkeypatch):
    from modules.agent.ui import AgentPanel
    model = select(env)
    def worker(command):
        if command['action'] == 'run':
            yield dict(type='progress', session_id='s', turn_id='t', outcome='in_progress', submission_started=True)
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='answer')
        elif command['action'] == 'download':
            yield dict(type='result', artifacts=[])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    frames = env.wrappers['predict'](model, 'hello', [], request=request())
    next(frames)
    # Accepting an actual submission persists intent before network work.
    saved = json.loads((env.history_dir / model.history_file_path).read_text())
    assert saved['history'][0]['content'] == 'hello'
    assert saved['chatbot'][0][0] == 'hello'
    selected = AgentPanel.history_value(None, model)
    assert selected['value'] == model.history_file_path.removesuffix('.json')
    list(frames)


def test_new_chat_detaches_unreconciled_terminal_but_preserves_old_binding(env, monkeypatch):
    from modules.agent.operations import OperationScope
    model = select(env)
    def worker(command):
        if command['action'] == 'run':
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='answer', sync_complete=False, submission_started=True)
        elif command['action'] == 'download':
            yield dict(type='result', artifacts=[])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    send(env, model)
    scope = OperationScope.capture(model)
    old_path = model.history_file_path
    old_state = deepcopy(model._state)
    with pytest.raises(gr.Error): model._assert_idle()
    model.reset()
    assert not scope.current(model)
    assert model._state == {'outcome': 'not_started'}
    assert model.history == [] and not model._needs_sync
    old = model._store().get(model._owner, old_path)
    assert old['state'] == old_state
    assert (env.history_dir / old_path).is_file()


def test_new_chat_still_rejects_local_running_or_reserved_submission(env):
    model = select(env)
    for attribute, value in [('_running', True), ('_pending_send', 'queued')]:
        setattr(model, attribute, value)
        with pytest.raises(gr.Error): model.reset()
        setattr(model, attribute, False if attribute == '_running' else None)


def test_terminal_download_detaches_without_saving_into_new_chat(env, monkeypatch):
    model = select(env)
    download_cancelled = []
    def worker(command):
        if command['action'] == 'run':
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='final', submission_started=True)
        elif command['action'] == 'download':
            old_path = model.history_file_path
            model.reset()
            new_path = model.history_file_path
            download_cancelled.append(command['_observe_cancel']())
            yield dict(type='result', artifacts=[])
            assert model.history_file_path == new_path and model.chatbot == []
            assert (env.history_dir / old_path).is_file()
            assert not (env.history_dir / new_path).is_file()
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    list(model.predict('hello', []))
    settle_files(model)
    assert download_cancelled == [False]
    assert model.chatbot == [] and model._state == {'outcome': 'not_started'}


def test_stale_title_envelope_cannot_name_reset_chat_even_same_reserved_path(env):
    model = select(env, name='GPT3.5 Turbo')
    envelope = env.wrappers['transfer_input']('old title', model)[0]
    model._pending_send = None
    old_path = model.history_file_path
    model.reset()
    model.history_file_path = old_path
    model.history = [{'role': 'user', 'content': 'new title'}, {'role': 'assistant', 'content': 'new answer'}]
    result = env.wrappers['auto_name_chat_history'](model, 'unused', envelope, False)
    assert result == {'__type__': 'update'} and model.history_file_path == old_path


@pytest.mark.parametrize('action', ['run', 'recover'])
def test_same_history_revisit_rejects_old_result_and_finalizer(env, monkeypatch, action):
    from uuid import uuid4
    model = select(env)
    if action == 'recover':
        model._state.update(session_id='s', turn_id='t', generation=uuid4().hex, outcome='incomplete')
        model._needs_sync = True
    revisited = []
    def worker(command):
        if command['action'] == action:
            yield dict(type='progress', session_id='s', turn_id='t', outcome='completed', text='preserved', submission_started=True)
            old_generation = model._state['generation']
            model.load_chat_history(model.history_file_path)
            assert model._state['generation'] == old_generation
            model._running = True
            model._notice = 'new visit owns this state'
            revisited.append(model.agent_choice_target)
            yield dict(type='result', session_id='s', turn_id='t', outcome='completed', text='STALE OLD RESULT')
        elif command['action'] == 'download':
            raise AssertionError('Old visit must not start download')
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    if action == 'run': list(model.predict('hello', []))
    else: list(model.reconnect())
    assert revisited and model._running
    assert model._notice == 'new visit owns this state'
    assert 'STALE OLD RESULT' not in str(model.history)


def test_real_model_worker_merges_caller_cancel_with_visit_scope(env, monkeypatch):
    from uuid import uuid4
    model = select(env)
    model._state.update(session_id='s', generation='g', outcome='completed')
    cancelled = []
    def worker(command):
        assert not command['_observe_cancel']()
        model._choice_epoch = uuid4().hex
        cancelled.append(command['_observe_cancel']())
        yield dict(type='result', artifacts=[])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    # No file operation is admitted until its exact turn has been captured.
    list(model._download('g'))
    assert cancelled == []
    monkeypatch.setattr(env.agents, 'worker_messages', lambda command: iter([{'type':'result', 'cancelled':command['_observe_cancel']()}]))
    result = list(model._worker({'action':'download', 'session_id':'s', '_observe_cancel':lambda:True}))
    assert result[0]['cancelled'] is True


def test_stale_history_click_scope_is_a_noop(env):
    from modules.history_selection import load_history_model
    model = select(env)
    assert load_history_model(model, {'filename':'missing.json', 'visit':'old visit'}, request())[0] is model


def test_history_visit_is_checked_after_acquiring_switch_lock(env):
    from modules.history_selection import load_history_model
    from uuid import uuid4
    model = select(env)
    visit = model.agent_choice_target
    actual_lock = model._lock
    class ConcurrentSwitch:
        def __enter__(self):
            actual_lock.acquire()
            # The earlier switch wins immediately before this waiter owns lock.
            model._choice_epoch = uuid4().hex
            return self
        def __exit__(self, *args): actual_lock.release()
    model._lock = ConcurrentSwitch()
    result = load_history_model(model, {'filename':'missing.json','visit':visit}, request())
    assert result[0] is model and all(item == {'__type__':'update'} for item in result[1:])


def test_stale_history_click_restores_authoritative_empty_selection(env):
    from modules.history_selection import load_history_model
    from modules.agent.ui import AgentPanel
    model = select(env, name='GPT3.5 Turbo')
    stale = {'filename':'missing.json', 'visit':'old visit'}
    result = AgentPanel().wrap_history_load(load_history_model)(model, stale, request())
    assert len(result) == 25 and result[0] is model
    assert result[-1]['value'] is None and model.chatbot == []


def test_reset_publishes_new_visit_before_cleared_chat_and_radio(env):
    from types import SimpleNamespace
    from modules.agent.ui import AgentPanel
    model = select(env, name='GPT3.5 Turbo')
    old_visit = model._history_visit
    caps = SimpleNamespace(stream_values=lambda current:[current._history_visit])
    result = AgentPanel().wrap_reset(env.wrappers['reset'], caps)(model, False, request())
    assert result[0] is model
    assert result[1] == model._history_visit != old_visit
    assert result[2] == [] and result[4].value is None
