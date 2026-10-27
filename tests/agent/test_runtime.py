"""No-network session lifecycle regressions, including restore and stop races."""
from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.agent import runtime
from modules.agent.tools import ToolConfigurationError


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    import socket
    from modules.agent import tools
    monkeypatch.setattr(tools, 'CONTROL_ROOT', tmp_path / 'function-controls')
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Real network forbidden')))


def event(kind, turn_id='t1', session='sess_test', **kw):
    return {'type': 'agent.session.turn.' + kind, 'session_id': session, 'turn_id': turn_id, **kw}


def turn(kind, turn='t1', subagent=None):
    return event(kind, turn, turn={'id': turn, 'subagent_id': subagent, 'status': kind})


def text(kind, value, turn_id='t1', item='msg1', **kw):
    return event('output_text.' + kind, turn_id, item_id=item, output_index=0, content_index=0,
                 **{('delta' if kind == 'delta' else 'text'): value}, **kw)


def message(identifier, value, turn_id='t1', status='completed', role='assistant'):
    return {'id': identifier, 'type': 'message', 'role': role, 'turn_id': turn_id, 'status': status,
            'content': [{'type': 'output_text' if role == 'assistant' else 'input_text', 'text': value}]}


class Stream:
    def __init__(self, events, trace): self.events, self.trace = events, trace
    def __enter__(self): self.trace.append('stream_open'); return iter(self.events)
    def __exit__(self, *args): self.trace.append('stream_close')


class FakePages:
    """An auto-paginating SDK iterator, recording whether every page was read."""
    def __init__(self, pages): self.pages, self.visited = pages, []
    def __iter__(self):
        for number, page in enumerate(self.pages):
            self.visited.append(number)
            yield from page


class FakeClient:
    def __init__(self, events=(), session_status='idle', saved_turn='completed'):
        self.trace, self.payloads, self.submitted, self.updated = [], [], [], []
        self.events, self.session_status, self.saved_turn = events, session_status, saved_turn
        self.required_actions, self.saved_items, self.saved_artifacts, self.roots = [], [], [], []
        self.agent = {'model': 'model', 'reasoning': {'effort': 'medium'}}
        self.environment = {'type': 'openai_hosted', 'network': {'access': 'enabled'}}
        sessions = SimpleNamespace(create=self.create, retrieve=self.retrieve, update=self.update,
            events=SimpleNamespace(create=self.send, stream=self.stream),
            turns=SimpleNamespace(retrieve=lambda identifier, **kw: {'id': identifier, 'session_id': kw.get('session_id', 'sess_test'), 'agent_id': 'agent_one', 'status': self.saved_turn},
                                  list=lambda *a, **kw: self.roots),
            items=SimpleNamespace(list=lambda *a, **kw: self.saved_items),
            artifacts=SimpleNamespace(list=lambda *a, **kw: self.saved_artifacts))
        self.beta = SimpleNamespace(agents=SimpleNamespace(sessions=sessions))
    def create(self, **kw): self.payloads.append(kw); return Stream(self.events, self.trace)
    def stream(self, *a, **kw): return Stream(self.events, self.trace)
    def send(self, *a, **kw): self.trace.append('submit'); self.submitted.append(kw)
    def retrieve(self, identifier):
        self.trace.append('retrieve')
        return {'id': identifier, 'status': self.session_status, 'required_actions': deepcopy(self.required_actions),
                'agent': deepcopy(self.agent), 'environment': deepcopy(self.environment)}
    def update(self, identifier, **kw):
        self.updated.append((identifier, kw)); self.agent.update(kw['agent']); return {'agent': deepcopy(self.agent)}


def test_delta_done_replacement_dedupe_and_other_turns():
    state = runtime.TurnState()
    for value in [turn('created'), text('delta', 'he', event_id='e1'), text('delta', 'he', event_id='e1'),
                  text('delta', 'llo'), text('done', 'hello'), text('done', 'wrong', turn_id='other'),
                  turn('completed', turn='child', subagent='sub')]: state.accept(value)
    assert state.outcome == 'in_progress'
    state.accept(turn('completed'))
    assert state.text == 'hello' and state.outcome == 'completed'


def test_only_done_and_session_isolation():
    a, b = runtime.TurnState(), runtime.TurnState()
    a.accept(turn('created')); b.accept(turn('created'))
    a.accept(text('done', 'one')); b.accept(text('done', 'two'))
    a.accept(dict(text('done', 'alien'), session_id='sess_other'))
    assert a.text == 'one' and b.text == 'two'


@pytest.mark.parametrize('kind', ['failed', 'cancelled'])
def test_target_terminal_outcome_not_misreported_as_completed(kind):
    client = FakeClient([turn('created'), turn(kind)], saved_turn=kind)
    result = runtime.run_task(client, 'test', 'model')
    assert result.outcome == kind and len(client.payloads) == 1


@pytest.mark.parametrize('events', [[], [turn('created'), {'type': 'agent.session.idle'}],
    [turn('created'), turn('completed', turn='child', subagent='sub')]])
def test_eof_idle_and_subagent_completion_do_not_mean_success(events):
    client = FakeClient(events)
    with pytest.raises(runtime.AgentError, match='连接已中断') as caught:
        runtime.run_task(client, 'test', 'model')
    assert len(client.payloads) == 1 and caught.value.state.outcome not in runtime.TERMINAL


def test_default_tools_and_network_enabled_with_no_legacy_plugin_import():
    client = FakeClient([turn('created'), text('done', 'result'), turn('completed')])
    result = runtime.run_task(client, 'test', 'explicit-model')
    assert result.text == 'result'
    payload = client.payloads[0]
    assert payload['environment'] == {'type': 'openai_hosted', 'network': {'access': 'enabled'}, 'desktop': {'enabled': True}}
    assert {tool['type'] for tool in payload['agent']['tools']} == {'computer_use', 'web_search'}
    assert payload['agent']['model'] == 'explicit-model'


def test_followup_stream_open_before_submit_and_no_new_session():
    client = FakeClient([turn('created'), turn('completed')])
    runtime.run_task(client, 'follow up', 'model', session_id='sess_test')
    assert client.trace.index('stream_open') < client.trace.index('submit')
    assert not client.payloads
    assert client.submitted[0]['events'] == [{'type': 'agent.session.input.message', 'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'follow up'}]}]}]


def test_followup_busy_does_not_send():
    client = FakeClient([], session_status='in_progress')
    with pytest.raises(runtime.AgentError, match='仍在运行') as caught:
        runtime.run_task(client, 'follow up', 'model', session_id='sess_test')
    assert not client.submitted and not client.payloads and caught.value.state.outcome == 'not_started'


def test_function_allowlist_validates_parameters_and_dedupes_results():
    client = FakeClient(); state = runtime.TurnState('sess_test', 't1'); handled = set()
    action = {'type': 'function_call', 'turn_id': 't1', 'call_id': 'call1', 'name': 'text_statistics', 'arguments': {'text': 'hello world'}}
    runtime.handle_function_actions(client, state, {'required_actions': [action]}, {'functions': ['text_statistics']}, handled)
    result = client.submitted[0]['events'][0]
    assert result['success'] and json.loads(result['output'])['words'] == 2
    runtime.handle_function_actions(client, state, {'required_actions': [action]}, {'functions': ['text_statistics']}, handled)
    assert len(client.submitted) == 1
    action = dict(action, call_id='call2', arguments={'text': 'hello', 'path': '/private'})
    runtime.handle_function_actions(client, state, {'required_actions': [action]}, {'functions': ['text_statistics']}, handled)
    assert not client.submitted[1]['events'][0]['success']
    with pytest.raises(ToolConfigurationError, match='未启用'):
        runtime.handle_function_actions(client, state, {'required_actions': [dict(action, name='shell', call_id='call3')]}, {'functions': ['text_statistics']}, handled)


def test_recovery_reads_authoritative_turn_without_resubmitting():
    client = FakeClient(saved_turn='cancelled'); client.saved_items = [message('msg1', 'saved')]
    result = runtime.inspect_saved(client, 'sess_test', 't1')
    assert result['outcome'] == 'cancelled' and result['text'] == 'saved'
    assert not client.submitted and not client.payloads


def test_restore_paginates_all_items_and_merges_by_id():
    client = FakeClient()
    pages = FakePages([[message('m' + str(n), str(n)) for n in range(300)],
                      [message('m' + str(n), str(n)) for n in range(300, 650)],
                      [message('m2', 'authoritative replacement')]])
    client.saved_items = pages
    result = runtime.inspect_saved(client, 'sess_test', 't1')
    assert len(result['items']) == 650 and pages.visited == [0, 1, 2]
    assert result['items'][2]['content'][0]['text'] == 'authoritative replacement'


def test_followup_history_over_500_is_complete_and_submitted_once():
    client = FakeClient([turn('created'), turn('completed')])
    pages = FakePages([[{'id': 'old_' + str(i)} for i in range(500)], [{'id': 'old_' + str(i)} for i in range(500, 1100)]])
    client.roots = pages
    result = runtime.run_task(client, 'follow up', 'model', session_id='sess_test')
    assert len(result.ignored_turn_ids) == 1100 and pages.visited == [0, 1] and len(client.submitted) == 1


def test_reconnect_stream_is_open_before_snapshot_and_buffered_updates_win():
    item = message('current', 'new authoritative output')
    client = FakeClient([event('item.done', item=item), turn('completed')], session_status='in_progress', saved_turn='in_progress')
    client.saved_items = [message('current', 'older partial', status='in_progress')]
    result = runtime.recover_stream(client, 'sess_test', 't1')
    assert client.trace[0] == 'stream_open' and client.trace.index('retrieve') > 0
    assert result.outcome == 'completed' and result.text == 'new authoritative output'
    assert len(result.items) == 1 and not client.submitted


def test_completed_restore_does_not_replay_past_function_actions():
    client = FakeClient([{'type': 'agent.session.requires_action', 'session_id': 'sess_test', 'turn_id': 't1'}])
    client.saved_items = [message('saved', 'completed result')]
    result = runtime.recover_stream(client, 'sess_test', 't1', tool_settings={'functions': ['text_statistics']})
    assert result.outcome == 'completed' and not client.submitted


def test_cancel_targets_current_turn_and_waits_for_remote_confirmation():
    client = FakeClient(session_status='in_progress', saved_turn='in_progress')
    client.roots = [{'id': 't1', 'status': 'in_progress', 'subagent_id': None}]
    result = runtime.cancel_session(client, 'sess_test', 't1')
    assert client.submitted[0]['events'] == [{'type': 'agent.session.input.cancel'}]
    assert result['outcome'] == 'cancel_requested'


@pytest.mark.parametrize('status', ['completed', 'failed', 'cancelled'])
def test_cancel_natural_completion_race_preserves_actual_terminal_outcome(status):
    client = FakeClient(saved_turn=status)
    assert runtime.cancel_session(client, 'sess_test', 't1')['outcome'] == status
    assert not client.submitted


def test_cancel_stale_turn_cannot_cancel_a_new_turn():
    client = FakeClient(session_status='in_progress', saved_turn='in_progress')
    client.roots = [{'id': 'newer', 'status': 'in_progress', 'subagent_id': None}]
    with pytest.raises(runtime.AgentError, match='运行任务已变化'):
        runtime.cancel_session(client, 'sess_test', 't1')
    assert not client.submitted


def test_cancel_failure_does_not_claim_stopped_or_retry():
    client = FakeClient(session_status='in_progress', saved_turn='in_progress')
    client.roots = [{'id': 't1', 'status': 'in_progress', 'subagent_id': None}]
    attempts = []
    def fail(*a, **kw): attempts.append(kw); raise OSError('secret details')
    client.beta.agents.sessions.events.create = fail
    with pytest.raises(runtime.AgentError, match='尚待确认'):
        runtime.cancel_session(client, 'sess_test', 't1')
    assert len(attempts) == 1


def test_settings_update_returns_only_confirmed_actual_values():
    client = FakeClient()
    assert runtime.update_settings(client, 'sess_test', 'gpt-6-sol', 'high') == {'model': 'gpt-6-sol', 'reasoning': 'high'}
    assert len(client.updated) == 1 and not client.payloads and not client.submitted


def test_settings_update_busy_or_unconfirmed_does_not_succeed():
    client = FakeClient(session_status='in_progress')
    with pytest.raises(runtime.AgentError, match='仍在执行'): runtime.update_settings(client, 'sess_test', 'gpt-6-sol', 'high')
    assert not client.updated
    client.session_status = 'idle'
    client.beta.agents.sessions.update = lambda *a, **kw: {'agent': {'model': 'old', 'reasoning': {'effort': 'low'}}}
    with pytest.raises(runtime.AgentError, match='尚未确认'): runtime.update_settings(client, 'sess_test', 'gpt-6-sol', 'high')


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500])
def test_errors_do_not_expose_body_or_secret(status):
    class Failure(Exception): status_code = status
    client = FakeClient()
    def fail(**kw): raise Failure('private prompt fake-secret-value')
    client.beta.agents.sessions.create = fail
    with pytest.raises(runtime.AgentError) as caught: runtime.run_task(client, 'private prompt', 'model')
    assert str(status) in str(caught.value)
    assert 'private prompt' not in str(caught.value) and 'fake-secret-value' not in str(caught.value)
    assert caught.value.state.outcome == ('uncertain' if status == 500 else 'not_started')


def test_key_reuses_existing_config_with_optional_override(tmp_path, monkeypatch):
    monkeypatch.delenv('CHUANHU_AGENT_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'ordinary-key')
    path = tmp_path / '.env.agents'; path.write_text('CHUANHU_AGENT_API_KEY=\n')
    assert runtime.read_dedicated_key(path) == 'ordinary-key'
    path.write_text('CHUANHU_AGENT_API_KEY="optional-key"\n')
    assert runtime.read_dedicated_key(path) == 'optional-key'


def test_followup_ignores_replayed_prior_root_turn():
    client = FakeClient([turn('created', turn='old'), text('done', 'OLD', turn_id='old'), turn('completed', turn='old'),
                         turn('created', turn='new'), text('done', 'NEW', turn_id='new'), turn('completed', turn='new')])
    client.roots = [{'id': 'old'}]
    result = runtime.run_task(client, 'follow up', 'model', session_id='sess_test')
    assert result.turn_id == 'new' and result.text == 'NEW' and len(client.submitted) == 1


def test_uncertain_creation_lookup_uses_exact_run_id_over_all_pages():
    client = FakeClient(); run_id = 'a' * 32
    pages = FakePages([[{'id': 'sess_other' + str(n), 'metadata': {}} for n in range(600)], [{'id': 'sess_match', 'metadata': {'chuanhu_run_id': run_id}}]])
    client.beta.agents.sessions.list = lambda **kw: pages
    client.roots = [{'id': 't1', 'subagent_id': None}]
    assert runtime.find_uncertain_session(client, run_id) == ('sess_match', 't1')
    assert pages.visited == [0, 1] and not client.submitted and not client.payloads


@pytest.mark.parametrize('baseline', [[], ['old']])
def test_missing_turn_recovers_unique_new_root(baseline):
    client = FakeClient(saved_turn='cancelled')
    client.roots = [{'id': identifier, 'subagent_id': None} for identifier in baseline] + [{'id': 'new', 'subagent_id': None}, {'id': 'child', 'subagent_id': 'sub'}]
    result = runtime.inspect_saved(client, 'sess_test', baseline_turn_ids=baseline, submission_started=True)
    assert result['turn_id'] == 'new' and result['outcome'] == 'cancelled' and not client.submitted


@pytest.mark.parametrize('roots', [[], ['old'], ['old', 'new', 'other']])
def test_missing_turn_never_chooses_previous_or_ambiguous_root(roots):
    client = FakeClient(); client.roots = [{'id': identifier, 'subagent_id': None} for identifier in roots]
    result = runtime.inspect_saved(client, 'sess_test', baseline_turn_ids=['old'], submission_started=True)
    assert result['turn_id'] is None and result['outcome'] == 'incomplete'


def test_followup_exports_baseline_before_submission_without_new_turn_event():
    client = FakeClient([{'type': 'agent.session.ready', 'session_id': 'sess_test'}]); client.roots = [{'id': 'old'}]
    states = []
    with pytest.raises(runtime.AgentError):
        runtime.run_task(client, 'new', 'model', session_id='sess_test', on_progress=lambda state: states.append((state.session_id, set(state.ignored_turn_ids), state.submission_started)))
    assert states[:2] == [('sess_test', {'old'}, False), ('sess_test', {'old'}, True)]
    assert len(client.submitted) == 1


def load_worker(monkeypatch, name='agent_worker'):
    monkeypatch.setitem(sys.modules, 'runtime', runtime)
    spec = importlib.util.spec_from_file_location(name, ROOT / 'modules/agent/worker.py')
    worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
    return worker


@pytest.mark.parametrize('failure', ['key', 'sdk'])
def test_real_worker_preflight_failure_not_started(failure, monkeypatch, capsys):
    worker = load_worker(monkeypatch)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'action': 'run', 'prompt': 'test', 'model': 'model'}) + '\n'))
    def fail(*a): raise runtime.AgentError('Synthetic ' + failure + ' unavailable')
    monkeypatch.setattr(worker, 'create_client', fail)
    worker.main(); output = json.loads(capsys.readouterr().out)
    assert output['type'] == 'error' and output['outcome'] == 'not_started' and output.get('session_id') is None
def test_safe_error_preserves_allowlisted_diagnostics_without_body_or_message():
    class Failure(Exception):
        status_code=400;code='invalid_value';param='environment.network.access';request_id='req_'+'a'*32
        @property
        def body(self):raise AssertionError('Body must never be inspected')
        @property
        def response(self):raise AssertionError('Headers must never be inspected')
    error=runtime.safe_request_error(Failure('sk-proj-do-not-display private prompt'))
    assert error.diagnostics=={'status_code':400,'code':'invalid_value','param':'environment.network.access','request_id':'req_'+'a'*32}
    assert 'environment.network.access' in str(error) and 'req_'+'a'*32 in str(error)
    assert 'sk-proj' not in str(error) and 'private prompt' not in str(error)


@pytest.mark.parametrize('value',['sk-proj-secret-value','Bearer credential-value','Authorization: secret',
    'https://private.example/key','private prompt','invalid_value secret', 'x'*10000,
    'req_'+'a'*32+'secret','environment.network.access\nsecret','环境.秘密'])
def test_untrusted_diagnostic_values_are_dropped_not_truncated(value):
    error=runtime.safe_request_error(SimpleNamespace(status_code=400,code=value,param=value,request_id=value))
    assert error.diagnostics=={'status_code':400} and value not in str(error)


def test_error_metadata_accessors_cannot_leak_exception_text():
    class Failure(Exception):
        status_code=400
        @property
        def code(self):raise RuntimeError('secret key must not escape')
    error=runtime.safe_request_error(Failure('private message'))
    assert error.diagnostics=={'status_code':400} and 'secret' not in str(error)


def test_manual_agent_error_diagnostics_are_filtered():
    error=runtime.AgentError('Safe fixed message',diagnostics={'code':'sk-proj-secret','param':'input',
                            'request_id':'Authorization: secret','status_code':'400 secret','body':'secret'})
    assert error.diagnostics=={'param':'input'}


def test_real_worker_emits_filtered_diagnostics_not_exception_body(monkeypatch,capsys):
    import io,json
    from contextlib import contextmanager
    monkeypatch.setitem(sys.modules,'runtime',runtime)
    spec=importlib.util.spec_from_file_location('worker_error_diagnostics',ROOT/'modules/agent/worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    class Failure(Exception):
        status_code=400;code='invalid_value';param='environment.network.access';request_id='req_'+'b'*32
    fake=FakeClient([])
    def fail(**kwargs):raise Failure('sk-proj-secret-value private task; never surface this')
    fake.beta.agents.sessions.create=fail
    @contextmanager
    def client(key):yield fake
    monkeypatch.setattr(worker,'create_client',client)
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps({'action':'run','model':'gpt-6-astra','prompt':'offline'})+'\n'))
    worker.main()
    output=capsys.readouterr().out
    message=json.loads(output.splitlines()[-1])
    assert message['outcome']=='not_started'
    assert message['diagnostics']=={'status_code':400,'code':'invalid_value','param':'environment.network.access','request_id':'req_'+'b'*32,'phase':'run.session_create'}
    assert 'sk-proj' not in output and 'private task' not in output


def approval_client(request=None):
    client = FakeClient(session_status='requires_action', saved_turn='in_progress')
    client.required_actions = [{'type': 'computer_use_approval_request', 'turn_id': 't1', 'request_id': 'approval1',
                                'request': request or {'type': 'browser_origin_access', 'origin': 'https://example.test', 'reason': 'Read requested site'}}]
    return client


@pytest.mark.parametrize('decision', ['approve', 'deny', 'cancel'])
def test_current_site_response_is_scoped_to_original_request(decision):
    client = approval_client()
    result = runtime.submit_browser_response(client, 'sess_test', 't1', 'approval1', {'type': 'browser_origin_access', 'decision': decision})
    assert result['accepted'] is True and len(client.submitted) == 1
    assert client.submitted[0]['events'][0] == {'type': 'agent.session.input.computer_use_approval_request_result',
        'request_id': 'approval1', 'response': {'type': 'browser_origin_access', 'decision': decision}}


@pytest.mark.parametrize('change', ['wrong_turn', 'old_id', 'completed', 'consumed', 'widen_origin'])
def test_stale_or_widened_origin_response_is_rejected(change):
    client = approval_client(); turn_id, request_id = 't1', 'approval1'
    response = {'type': 'browser_origin_access', 'decision': 'approve'}
    if change == 'wrong_turn': turn_id = 'old'
    elif change == 'old_id': request_id = 'old'
    elif change == 'completed': client.session_status = 'idle'
    elif change == 'consumed': client.required_actions = []
    elif change == 'widen_origin': response['origin'] = 'https://other.example'
    with pytest.raises(ToolConfigurationError): runtime.submit_browser_response(client, 'sess_test', turn_id, request_id, response)
    assert not client.submitted


@pytest.mark.parametrize('fields', [[{'field_id': 'other', 'value': 'synthetic'}], [],
                                  [{'field_id': 'password', 'value': 'one'}, {'field_id': 'password', 'value': 'two'}]])
def test_login_only_accepts_current_required_fields(fields):
    client = approval_client({'type': 'browser_authentication', 'credential_origin': 'https://example.test',
                              'fields': [{'id': 'password', 'required': True}]})
    with pytest.raises(ToolConfigurationError):
        runtime.submit_browser_response(client, 'sess_test', 't1', 'approval1', {'type': 'browser_authentication', 'action': 'submit', 'fields': fields})
    assert not client.submitted


def test_login_cancel_contains_no_fields_or_credentials():
    client = approval_client({'type': 'browser_authentication', 'credential_origin': 'https://example.test', 'fields': []})
    response = {'type': 'browser_authentication', 'action': 'cancel'}
    assert runtime.submit_browser_response(client, 'sess_test', 't1', 'approval1', response)['accepted']
    assert client.submitted[0]['events'][0]['response'] == response


def test_all_artifacts_download_with_duplicate_names_and_individual_failure(tmp_path):
    client = FakeClient()
    client.saved_artifacts = FakePages([
        [{'id': 'a' + str(n), 'path': '../../same.txt', 'turn_id': 't1'} for n in range(20)],
        [{'id': 'a' + str(n), 'path': '../../same.txt', 'turn_id': 't1'} for n in range(20, 35)],
    ])
    class Content:
        def __init__(self, identifier): self.identifier = identifier
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_bytes(self):
            if self.identifier == 'a1':
                yield b'partial'
                raise OSError('synthetic failure with private details')
            if self.identifier == 'a0':
                # The former 10MiB cap must not silently drop an output.
                for _ in range(176): yield b'x' * 65536
            else: yield b'whole artifact'
    client.beta.agents.sessions.artifacts.with_streaming_response = SimpleNamespace(content=lambda identifier, **kw: Content(identifier))
    result = runtime.download_artifacts(client, 'sess_test')
    assert len(result) == 35 and client.saved_artifacts.visited == [0, 1]
    assert result[0]['size'] > 10 * 1024 * 1024 and result[0]['status'] == 'ready'
    assert result[1]['status'] == 'failed' and 'path' not in result[1]
    assert all(item['status'] == 'ready' for item in result[2:])
    assert len({item['path'] for item in result if item['status'] == 'ready'}) == 34
    assert all(item['name'] == 'same.txt' and item['turn_id'] == 't1' for item in result)
    assert 'private details' not in result[1]['error']
    # Clean temporary downloaded fixtures after inspecting real bytes.
    import shutil
    for folder in {str(Path(item['path']).parents[1]) for item in result if item['status'] == 'ready'}:
        shutil.rmtree(folder)


def test_artifact_listing_failure_does_not_block_text_restore():
    client=FakeClient();client.saved_items=[message('u','question',role='user'),message('a','complete answer')]
    def fail(*a,**k):raise OSError('artifact-only failure')
    client.beta.agents.sessions.artifacts.list=fail
    result=runtime.recover_stream(client,'sess_test','t1')
    assert result.text=='complete answer' and result.outcome=='completed'


def test_incomplete_artifact_is_individual_failure():
    client=FakeClient();client.saved_artifacts=[{'id':'art_one','path':'file.txt','turn_id':'t1','size_bytes':100}]
    class Content:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_bytes(self):yield b'short'
    client.beta.agents.sessions.artifacts.with_streaming_response=SimpleNamespace(content=lambda *a,**k:Content())
    result=runtime.download_artifacts(client,'sess_test')
    assert result[0]['status']=='failed' and 'path' not in result[0]
    assert '长度' in result[0]['error']


def test_effective_settings_snapshot_excludes_mcp_secrets():
    snapshot=runtime._public_settings({'agent':{'model':'model','tools':[{'type':'mcp','server_label':'explicit','allowed_tools':['read'],'transport':{'authorization':'secret','headers':{'X-Key':'secret'}}}]},'environment':{'type':'openai_hosted','env':{'SECRET':'secret'},'network':{'access':'enabled'}}})
    assert 'secret' not in repr(snapshot).lower()
    assert snapshot['agent']['tools'][0]['allowed_tools']==['read']


def test_read_only_recovery_never_executes_or_submits_function_actions(monkeypatch):
    client=FakeClient([{'type':'agent.session.requires_action','session_id':'sess_test'},turn('completed')],
                      session_status='requires_action',saved_turn='in_progress')
    client.required_actions=[{'type':'function_call','call_id':'function1','name':'text_statistics','arguments':'{}'}]
    monkeypatch.setattr(runtime,'handle_function_actions',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('Observer must never execute functions')))
    result=runtime.recover_stream(client,'sess_test','t1',read_only=True)
    assert result.outcome=='completed' and not client.submitted and not client.payloads and not client.updated
    assert client.trace[0]=='stream_open' and client.trace[-1]=='stream_close'


@pytest.mark.parametrize('action',['observe','observe_unknown'])
def test_real_worker_entry_accepts_read_only_observation_actions(action,monkeypatch,capsys):
    worker=load_worker(monkeypatch,'readonly_worker_entry')
    fake=FakeClient(saved_turn='completed');called=[]
    @contextmanager
    def client(connection):
        called.append('client');yield fake
    monkeypatch.setattr(worker,'create_client',client)
    monkeypatch.setattr(worker,'find_uncertain_session',lambda client,run_id:('sess_test','t1'))
    command={'action':action,'run_id':'a'*32}
    if action=='observe':command.update(session_id='sess_test',turn_id='t1')
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps(command)+'\n'))
    worker.main()
    messages=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert called==['client'] and messages[-1]['type']=='result'
    assert messages[-1]['session_id']=='sess_test' and not fake.submitted and not fake.payloads


def test_repeated_uncertain_recovery_preserves_baseline_and_submission_receipt():
    client = FakeClient(events=[], session_status='idle', saved_turn='completed')
    client.roots = [{'id': 'old', 'subagent_id': None, 'status': 'completed'}]
    client.saved_items = [message('old_answer', 'Previous answer', turn_id='old')]
    receipts = []
    with pytest.raises(runtime.AgentError) as first:
        runtime.recover_stream(client, 'sess_test', baseline_turn_ids=['old'], submission_started=True,
                               on_progress=lambda state: receipts.append(state.snapshot()), read_only=True)
    receipt = first.value.state.snapshot()
    assert receipt['baseline_turn_ids'] == ['old'] and receipt['submission_started'] is True
    assert receipts[-1]['baseline_turn_ids'] == ['old'] and receipts[-1]['submission_started'] is True
    with pytest.raises(runtime.AgentError) as second:
        runtime.recover_stream(client, receipt['session_id'], receipt['turn_id'],
                               baseline_turn_ids=receipt['baseline_turn_ids'], submission_started=receipt['submission_started'], read_only=True)
    again = second.value.state.snapshot()
    assert again['turn_id'] is None and again['outcome'] == 'incomplete' and again['text'] == ''
    assert again['baseline_turn_ids'] == ['old'] and again['submission_started'] is True
    assert not client.submitted


def test_terminal_reconciliation_does_not_request_artifact_listing():
    client = FakeClient(saved_turn='completed')
    client.saved_items = [{'id': 'a', 'type': 'message', 'role': 'assistant', 'turn_id': 't1',
                           'status': 'completed', 'content': [{'type': 'output_text', 'text': 'final'}]}]
    def forbidden(*args, **kwargs):
        raise AssertionError('File listing must not block terminal text reconciliation')
    client.beta.agents.sessions.artifacts.list = forbidden
    state = runtime.TurnState(session_id='sess_test', turn_id='t1', outcome='completed')
    runtime._reconcile_terminal(client, state)
    assert state.sync_complete is True and state.outcome == 'completed'
