"""Session-bound configuration, using synthetic workers and local storage only."""
from copy import deepcopy

import gradio as gr
import pytest

from modules.agent.settings import load_settings, save_settings
from modules.agent.store import owner_identity
from modules.model_capabilities import reserve_submission
from agent_fixtures import complete, env, request, select, send, settle_files
from test_input_model import staged, submit


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    import socket

    def fail(*args, **kwargs):
        raise AssertionError('Session configuration tests must remain offline')

    monkeypatch.setattr(socket, 'create_connection', fail)
    monkeypatch.setattr(socket.socket, 'connect', fail)
    monkeypatch.setattr(socket.socket, 'connect_ex', fail)


def test_new_chat_settings_apply_when_session_is_created(env, monkeypatch):
    calls, _ = complete(env, monkeypatch)
    model = select(env)
    defaults = load_settings(env.agents.shared.chuanhu_path, model._owner)
    settings = dict(model._tool_settings, network=False, web_search=False)
    model.save_agent_tools(settings)
    env.wrappers['set_system_prompt'](model, 'Instructions for this session', request=request())
    settings['network'] = True
    assert model._tool_settings['network'] is False
    assert load_settings(env.agents.shared.chuanhu_path, model._owner) == defaults
    assert load_settings(env.agents.shared.chuanhu_path, owner_identity('other'))['network'] is True

    send(env, model)
    command = next(call for call in calls if call['action'] == 'run')
    assert command['tool_settings']['network'] is False
    assert command['tool_settings']['web_search'] is False
    assert command['instructions'] == 'Instructions for this session'
    assert model._session_settings == model._current_settings()


@pytest.mark.parametrize('change', [
    {'network': False}, {'web_search': False}, {'search_mode': 'cached'},
    {'search_domains': ['example.com']}, {'computer_use': False},
    {'include_screenshots': True}, {'tool_search': True},
    {'programmatic_tool_calling': True}, {'functions': ['text_statistics']},
    {'mcp_servers': [{'server_label': 'reader', 'server_url': 'https://mcp.example.com',
                      'allowed_tools': ['read_issue']}]},
    {'code_execution': False, 'computer_use': False, 'programmatic_tool_calling': False},
])
def test_existing_session_rejects_every_tool_configuration_change(env, monkeypatch, change):
    complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    snapshot = deepcopy(model._session_settings)
    defaults = load_settings(env.agents.shared.chuanhu_path, model._owner)

    with pytest.raises(gr.Error, match='会话创建后'):
        model.save_agent_tools(dict(model._tool_settings, **change))

    assert model._session_settings == snapshot
    assert model._current_settings() == snapshot
    assert model._tool_settings == snapshot['tools']
    assert load_settings(env.agents.shared.chuanhu_path, model._owner) == defaults


def test_existing_instructions_reject_direct_and_wrapped_setters(env, monkeypatch):
    complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    snapshot = deepcopy(model._session_settings)
    for setter in (
        lambda: model.set_system_prompt('Changed instructions'),
        lambda: env.wrappers['set_system_prompt'](model, 'Changed instructions', request=request()),
    ):
        with pytest.raises(gr.Error, match='会话创建后'):
            setter()
    assert model.system_prompt == snapshot['instructions']
    model.auto_save(model.chatbot)
    assert model._store().get(model._owner, model.history_file_path)['settings'] == snapshot


def test_first_send_preparation_failure_locks_configuration_after_submission(env, tmp_path, monkeypatch):
    model, paths, service, calls = staged(env, tmp_path, monkeypatch, ('upload-fail.txt',))
    model.set_system_prompt('Prepared session instructions')
    model.save_agent_tools(dict(model._tool_settings, network=False))
    submit(env, model, 'Not submitted', paths)
    session = model._state['session_id']
    snapshot = deepcopy(model._session_settings)
    assert model._state['outcome'] == 'not_started'
    assert not model.history and not service.sessions[session]['items']
    assert [call['action'] for call in calls] == ['prepare_inputs']

    with pytest.raises(gr.Error, match='会话创建后'):
        model.save_agent_tools(dict(model._tool_settings, network=True))
    with pytest.raises(gr.Error, match='会话创建后'):
        model.set_system_prompt('A different instruction')
    with pytest.raises(gr.Error, match='会话创建后'):
        model.stage_agent_tools(dict(model._tool_settings, network=True), 1, model._conversation_id)
    with pytest.raises(gr.Error, match='会话创建后'):
        model.freeze_agent_configuration(snapshot['tools'], 'Different instructions', 1, model._conversation_id)
    with pytest.raises(gr.Error, match='会话创建后'):
        model._network_request('开启联网')
    assert model._pending_network is None
    assert model._session_settings == snapshot
    assert model._store().get(model._owner, model.history_file_path)['settings'] == snapshot
    assert service.sessions[session]['instructions'] == snapshot['instructions']
    assert service.sessions[session]['tools'] == snapshot['tools']


@pytest.mark.parametrize('command', ['开网', '请开启联网！', '关闭联网', '关闭云端联网'])
def test_network_commands_only_explain_locked_session_without_fork_state(env, monkeypatch, command):
    calls, _ = complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    previous = (deepcopy(model.history), deepcopy(model._state), deepcopy(model._session_settings))
    count = len(calls)
    model._pending_network = False  # Clear obsolete pending state from the earlier workflow.
    with pytest.raises(gr.Error, match='会话创建后'):
        send(env, model, command)
    assert len(calls) == count
    assert (model.history, model._state, model._session_settings) == previous
    assert model._pending_network is None and model._fork_previous is None
    assert model._notice == env.agents.SESSION_CONFIG_LOCKED


def test_network_commands_configure_new_chat_without_creating_session(env):
    model = select(env)
    send(env, model, '请关闭联网。')
    assert model._tool_settings['network'] is False
    assert model._tool_settings['web_search'] is True
    assert not model._state.get('session_id') and not model.history
    assert load_settings(env.agents.shared.chuanhu_path, model._owner)['network'] is True
    send(env, model, '开启联网')
    assert model._tool_settings['network'] is True and model._pending_network is None


def test_idempotent_existing_setters_do_not_overwrite_new_chat_defaults(env, monkeypatch):
    complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    snapshot = deepcopy(model._session_settings)
    new_defaults = dict(snapshot['tools'], network=False, web_search=False)
    save_settings(env.agents.shared.chuanhu_path, model._owner, new_defaults)

    def fail_save(*args, **kwargs):
        raise AssertionError('An unchanged existing session must not rewrite saved settings')

    monkeypatch.setattr('modules.agent.settings.save_settings', fail_save)
    model.save_agent_tools(deepcopy(snapshot['tools']))
    model.set_system_prompt(snapshot['instructions'])
    assert load_settings(env.agents.shared.chuanhu_path, model._owner) == new_defaults
    assert model._session_settings == snapshot


def test_restore_displays_effective_snapshot_even_when_account_defaults_changed(env, monkeypatch):
    complete(env, monkeypatch)
    model = select(env)
    model.set_system_prompt('Session-owned instruction')
    send(env, model)
    snapshot = deepcopy(model._session_settings)
    new_defaults = dict(snapshot['tools'], network=False, web_search=False)
    save_settings(env.agents.shared.chuanhu_path, model._owner, new_defaults)
    restored = select(env, browser='another-browser')
    assert restored._tool_settings == new_defaults
    restored.load_chat_history(model.history_file_path)
    assert restored._current_settings() == snapshot
    assert restored._tool_settings == snapshot['tools']
    assert restored.system_prompt == snapshot['instructions']
    # Recovery status does not make immutable fields editable; same-value
    # callbacks remain harmless even before cloud history is synchronized.
    restored.save_agent_tools(deepcopy(snapshot['tools']))
    restored.set_system_prompt(snapshot['instructions'])
    with pytest.raises(gr.Error, match='会话创建后'):
        restored.save_agent_tools(new_defaults)
    assert load_settings(env.agents.shared.chuanhu_path, model._owner) == new_defaults
    restored.auto_save(restored.chatbot)
    assert restored._store().get(restored._owner, restored.history_file_path)['settings'] == snapshot


@pytest.mark.parametrize('pending', ['running', 'queued'])
def test_first_submission_freezes_configuration_before_session_id_is_known(env, pending):
    model = select(env)
    snapshot = model._current_settings()
    generator = None
    if pending == 'running':
        generator = model.predict('Pending first message', [])
        next(generator)
    else:
        reserve_submission(model, 'Pending first message')
    assert not model._state.get('session_id')
    try:
        with pytest.raises(gr.Error):
            model.save_agent_tools(dict(model._tool_settings, network=False))
        with pytest.raises(gr.Error):
            model.set_system_prompt('Late instructions')
        with pytest.raises(gr.Error):
            model._network_request('关闭联网')
        assert model._current_settings() == snapshot
    finally:
        if generator is not None:
            generator.close()


@pytest.mark.parametrize('unavailable', ['unbound', 'retired'])
def test_configuration_setters_require_current_owned_model(env, unavailable):
    model = select(env)
    snapshot = model._current_settings()
    if unavailable == 'unbound':
        model._owner = None
    else:
        model.retire()
    for action in (
        lambda: model.save_agent_tools(dict(model._tool_settings, network=False)),
        lambda: model.set_system_prompt('Not authorized'),
        lambda: model._network_request('关闭联网'),
        lambda: model.stage_agent_tools(model._tool_settings, 1, model._conversation_id),
        lambda: model.freeze_agent_configuration(model._tool_settings, 'Not authorized', 1, model._conversation_id),
    ):
        with pytest.raises(gr.Error):
            action()
    assert model._current_settings() == snapshot


def test_wrong_owner_cannot_change_new_chat_instructions(env):
    model = select(env)
    snapshot = model._current_settings()
    with pytest.raises(gr.Error, match='不属于'):
        env.wrappers['set_system_prompt'](model, 'Wrong owner', request=request(username='other'))
    assert model._current_settings() == snapshot


def test_model_effort_still_updates_on_next_turn_in_same_locked_session(env, monkeypatch):
    calls, _ = complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    session = model._state['session_id']
    snapshot = deepcopy(model._session_settings)
    start = len(calls)
    model.set_agent_model('gpt-6-sol', 'high')
    assert len(calls) == start
    send(env, model, 'Continue with the next model')
    assert [call['action'] for call in calls[start:]] == ['update', 'run', 'download']
    assert model._state['session_id'] == session
    assert model._session_settings['tools'] == snapshot['tools']
    assert model._session_settings['instructions'] == snapshot['instructions']
    assert model.agent_model_choice == ('gpt-6-sol', 'high')


def test_reset_enables_new_chat_configuration_and_preserves_old_binding(env, monkeypatch):
    complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    old_path = model.history_file_path
    snapshot = deepcopy(model._session_settings)
    model.reset()
    model.save_agent_tools(dict(model._tool_settings, network=False))
    model.set_system_prompt('Instructions for the next chat')
    assert not model._state.get('session_id')
    assert model._tool_settings['network'] is False
    assert model.system_prompt == 'Instructions for the next chat'
    assert model._store().get(model._owner, old_path)['settings'] == snapshot


def test_legacy_fork_does_not_apply_obsolete_pending_configuration(env, monkeypatch):
    complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    snapshot = deepcopy(model._session_settings)
    model._pending_network = False
    model.new_session_from_history()
    assert not model._state.get('session_id') and model._pending_network is None
    assert model._tool_settings == snapshot['tools']
    assert load_settings(env.agents.shared.chuanhu_path, model._owner) == snapshot['tools']
    # Internal compatibility callers can still create a fresh session first,
    # then choose its configuration. A failed fork restores the old snapshot.
    model.save_agent_tools(dict(model._tool_settings, network=False))
    model.set_system_prompt('New fork instructions')
    monkeypatch.setattr(env.agents, 'worker_messages', lambda command: iter([
        {'type': 'error', 'outcome': 'not_started', 'message': 'Synthetic creation failure'}]))
    send(env, model, 'New attempt')
    assert model._state.get('session_id') and model._current_settings() == snapshot
    assert model._tool_settings == snapshot['tools']
    assert model.system_prompt == snapshot['instructions']


def test_tool_inputs_apply_locally_and_ignore_older_callbacks(env):
    model = select(env)
    target = model._conversation_id
    settings = dict(model._tool_settings, network=False)
    model.stage_agent_tools(settings, 2, target)
    latest = dict(settings, web_search=False)
    model.stage_agent_tools(latest, 4, target)
    assert model.stage_agent_tools(settings, 3, target) is None
    assert model.stage_agent_tools(settings, 4, target) is None
    assert model._tool_settings == latest and model._tool_revision == 4
    settings['search_domains'].append('late-edit.example.com')
    latest['search_domains'].append('also-late.example.com')
    assert model._tool_settings['search_domains'] == []
    assert load_settings(env.agents.shared.chuanhu_path, model._owner)['network'] is True


def test_tool_inputs_preserve_existing_account_defaults(env):
    model = select(env)
    existing = dict(model._tool_settings, network=False, web_search=False)
    save_settings(env.agents.shared.chuanhu_path, model._owner, existing)
    preferences_path = model._store().path.parent / model._owner / 'settings.json'
    before = preferences_path.read_bytes()
    model.stage_agent_tools(dict(model._tool_settings, include_screenshots=True), 1, model._conversation_id)
    model.save_agent_tools(dict(model._tool_settings, search_mode='cached'))
    model._network_request('关闭联网')
    model.freeze_agent_configuration(model._tool_settings, 'Local instructions', 1, model._conversation_id)
    assert preferences_path.read_bytes() == before
    assert load_settings(env.agents.shared.chuanhu_path, model._owner) == existing


@pytest.mark.parametrize('revision', [None, -1, 0.5, '2', True, float('nan'), float('inf')])
def test_tool_events_require_valid_integer_revision(env, revision):
    model = select(env)
    snapshot = model._current_settings()
    for action in (
        lambda: model.stage_agent_tools(dict(model._tool_settings, network=False), revision, model._conversation_id),
        lambda: model.freeze_agent_configuration(model._tool_settings, 'Changed', revision, model._conversation_id),
    ):
        with pytest.raises(gr.Error, match='版本'):
            action()
    assert model._current_settings() == snapshot


def test_old_conversation_tool_events_cannot_modify_reset_chat(env):
    model = select(env)
    target = model._conversation_id
    model.stage_agent_tools(dict(model._tool_settings, network=False), 10, target)
    model.reset()
    snapshot = model._current_settings()
    for action in (
        lambda: model.stage_agent_tools(dict(model._tool_settings, network=True), 11, target),
        lambda: model.freeze_agent_configuration(model._tool_settings, 'Old instructions', 11, target),
    ):
        with pytest.raises(gr.Error, match='聊天已切换'):
            action()
    assert model._current_settings() == snapshot and model._tool_revision == 0
    model.stage_agent_tools(dict(model._tool_settings, network=True), 1, model._conversation_id)
    assert model._tool_settings['network'] is True


@pytest.mark.parametrize('callback_before_send', [False, True])
def test_send_snapshot_wins_over_same_revision_input_callback(env, monkeypatch, callback_before_send):
    calls, _ = complete(env, monkeypatch)
    model = select(env)
    target = model._conversation_id
    earlier = dict(model._tool_settings, network=False)
    latest = dict(earlier, web_search=False, search_domains=['example.com'])
    if callback_before_send:
        model.stage_agent_tools(earlier, 1, target)
    with model._lock:
        model.freeze_agent_configuration(latest, 'Send-time instructions', 1, target)
        envelope = reserve_submission(model, 'Use exactly these settings')
    assert model.stage_agent_tools(earlier, 1, target) is None
    with pytest.raises(gr.Error):
        model.stage_agent_tools(earlier, 2, target)
    with pytest.raises(gr.Error):
        model.set_system_prompt('Late instructions')
    with pytest.raises(gr.Error):
        model.freeze_agent_configuration(earlier, 'Late send', 2, target)
    assert model._tool_revision == 1
    list(env.wrappers['predict'](model, envelope, [], request=request()))
    command = next(call for call in calls if call['action'] == 'run')
    assert command['tool_settings'] == latest
    assert command['instructions'] == 'Send-time instructions'
    assert model._session_settings['tools'] == latest
    assert model._session_settings['instructions'] == 'Send-time instructions'
    with pytest.raises(gr.Error, match='会话创建后'):
        model.stage_agent_tools(earlier, 2, target)
    with pytest.raises(gr.Error, match='会话创建后'):
        model.freeze_agent_configuration(earlier, 'Send-time instructions', 2, target)


def test_freeze_rejects_stale_send_and_validates_atomically(env):
    model = select(env)
    target = model._conversation_id
    model.stage_agent_tools(dict(model._tool_settings, network=False), 5, target)
    snapshot = model._current_settings()
    for tools, instructions, revision in (
        (dict(model._tool_settings, network=True), 'Old snapshot', 4),
        (dict(model._tool_settings, network='invalid'), 'Invalid tools', 6),
        (dict(model._tool_settings, network=True), None, 6),
    ):
        with pytest.raises((gr.Error, ValueError)):
            model.freeze_agent_configuration(tools, instructions, revision, target)
        assert model._current_settings() == snapshot and model._tool_revision == 5


@pytest.mark.parametrize('state', ['running', 'queued', 'uncertain', 'needs_sync'])
def test_tool_callbacks_and_freeze_reject_unsettled_new_session(env, state):
    model = select(env)
    snapshot = model._current_settings()
    if state == 'running': model._running = True
    elif state == 'queued': reserve_submission(model, 'Queued')
    elif state == 'uncertain': model._state['outcome'] = 'uncertain'
    else: model._needs_sync = True
    for action in (
        lambda: model.stage_agent_tools(dict(model._tool_settings, network=False), 1, model._conversation_id),
        lambda: model.freeze_agent_configuration(model._tool_settings, 'Late change', 1, model._conversation_id),
    ):
        with pytest.raises(gr.Error):
            action()
    assert model._current_settings() == snapshot and model._tool_revision == 0


def test_existing_snapshot_is_idempotent_and_still_allows_next_model(env, monkeypatch):
    calls, _ = complete(env, monkeypatch)
    model = select(env)
    send(env, model)
    snapshot = deepcopy(model._session_settings)
    session = model._state['session_id']
    model.stage_agent_tools(snapshot['tools'], 1, model._conversation_id)
    model._needs_sync = True
    model.freeze_agent_configuration(snapshot['tools'], snapshot['instructions'], 1, model._conversation_id)
    model._needs_sync = False
    model.set_agent_model('gpt-6-sol', 'high')
    model._state['public_text_streaming'] = True  # A prior generation must not suppress new waiting state.
    with model._lock:
        model.freeze_agent_configuration(snapshot['tools'], snapshot['instructions'], 1, model._conversation_id)
        envelope = reserve_submission(model, 'Next model')
    from threading import Event
    entered, release, finished = Event(), Event(), Event()
    worker = env.agents.worker_messages
    def hold_download(command):
        try:
            for frame in worker(command):
                if command['action'] == 'download':
                    entered.set()
                    assert release.wait(5), 'Test did not release independent download'
                yield frame
        finally:
            if command['action'] == 'download': finished.set()
    monkeypatch.setattr(env.agents, 'worker_messages', hold_download)
    try:
        list(env.wrappers['predict'](model, envelope, model.chatbot, request=request()))
        assert entered.wait(3), 'Independent download job did not start'
        assert not finished.is_set() and not release.is_set()
        model._assert_idle()  # UI completion must not wait for the held file job.
        assert model._state['public_text_streaming'] is False
        assert model._state['session_id'] == session
        assert model._session_settings['tools'] == snapshot['tools']
        assert model._session_settings['instructions'] == snapshot['instructions']
        assert model.agent_model_choice == ('gpt-6-sol', 'high')
        assert [call['action'] for call in calls][-3:] == ['update', 'run', 'download']
    finally:
        release.set()
        settle_files(model)

def test_attachment_selection_keeps_configuration_editable_until_first_send(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    assert calls==[] and service.sessions=={} and model._state.get('session_id') is None
    records=model.freeze_input_files(paths)
    chosen=dict(model._tool_settings,network=False,include_screenshots=True)
    model.stage_agent_tools(chosen,1,model._conversation_id)
    model.set_system_prompt('Instructions chosen after selecting attachments')
    assert model.freeze_input_files(paths)==records and not calls
    submit(env,model,'First send after configuration change',paths)
    settle_files(model)  # Verify download calls only after their independent job settles.
    assert [call['action'] for call in calls]==['prepare_inputs','run','download']
    for call in calls[:2]:
        assert call['tool_settings']==chosen
        assert call['instructions']=='Instructions chosen after selecting attachments'
    assert calls[0]['inputs'][0]['input_id']==records[0].input_id
    assert calls[1]['input_files'][0]['input_id']==records[0].input_id
    session=model._state['session_id']
    assert service.sessions[session]['tools']==chosen
    with pytest.raises(gr.Error):
        model.stage_agent_tools(dict(chosen,network=True),2,model._conversation_id)


def test_remove_selected_upload_before_first_send_leaves_no_remote_session(env,tmp_path,monkeypatch):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    records=model.freeze_input_files(paths)
    model.remove_input_ids([records[0].input_id],model._conversation_id)
    model.stage_agent_tools(dict(model._tool_settings,network=False),1,model._conversation_id)
    assert not model._pending_upload_paths and not model.freeze_input_files([])
    assert not calls and not service.sessions and model._state.get('session_id') is None
