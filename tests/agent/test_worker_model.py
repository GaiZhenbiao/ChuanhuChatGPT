"""Real worker/runtime result shapes through the main model, without a service."""
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import sys
import pytest
import gradio as gr
from agent_fixtures import env, select, send, complete, ROOT
from test_runtime import runtime, FakeClient, turn, text, load_worker
from modules.agent.connection import AgentConnectionError


@pytest.fixture(autouse=True)
def isolate_controls(tmp_path, monkeypatch):
    from modules.agent import tools
    import socket
    monkeypatch.setattr(tools, "CONTROL_ROOT", tmp_path / "controls")
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Real network forbidden")))


def install_bridge(env, monkeypatch, fake, failure=None):
    worker = load_worker(monkeypatch, 'worker_model_bridge')
    failing = [failure]
    @contextmanager
    def client(connection):
        if failing[0] in ('missing_key', 'missing_sdk'):
            raise AgentConnectionError('未配置密钥' if failing[0] == 'missing_key' else '请升级 SDK')
        yield fake
    monkeypatch.setattr(worker, 'create_client', client)
    commands = []
    def bridge(command):
        commands.append(deepcopy(command))
        emitted = []
        wire = {key: value for key, value in command.items() if key != '_observe_cancel'}
        monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(wire) + '\n'))
        monkeypatch.setattr(worker, 'emit', lambda kind, **data: emitted.append(dict(type=kind, **data)))
        worker.main()
        yield from emitted
    monkeypatch.setattr(env.agents, 'worker_messages', bridge)
    return commands, failing


@pytest.mark.parametrize('failure', ['busy', 'missing_key', 'missing_sdk'])
def test_unsent_worker_failure_can_reset_and_explicitly_submit(env, monkeypatch, failure):
    complete(env, monkeypatch); model = select(env); send(env, model, 'completed previous turn')
    fake = FakeClient([turn('created'), text('done', 'new result'), turn('completed')],
                      session_status='in_progress' if failure == 'busy' else 'idle')
    commands, failing = install_bridge(env, monkeypatch, fake, failure)
    send(env, model, 'unsent followup')
    assert model._state['outcome'] == 'not_started'
    assert fake.submitted == [] and fake.payloads == []
    with pytest.raises(gr.Error, match='不支持重新生成'):
        list(model.retry(model.chatbot))
    assert len(commands) == 1
    model.reset()
    assert model._state['outcome'] == 'not_started' and model._state.get('session_id') is None
    failing[0] = None; fake.session_status = 'idle'
    output = send(env, model, 'explicit fresh submission')
    assert model._state['outcome'] == 'completed'
    assert model.history[-1]['content'] == 'new result'
    assert len(fake.payloads) == 1 and fake.submitted == []
    assert output[-1][0][-1] == ['explicit fresh submission', 'new result']


def test_more_than_500_prior_turns_remains_same_session(env, monkeypatch):
    complete(env, monkeypatch); model = select(env); send(env, model, 'first')
    fake = FakeClient([turn('created'), text('done', 'followup result'), turn('completed')])
    fake.roots = [{'id': 'old_' + str(n)} for n in range(701)]
    commands, _ = install_bridge(env, monkeypatch, fake)
    send(env, model, 'follow up')
    assert model._state['outcome'] == 'completed' and model._state['session_id'] == 'sess_test'
    assert len(fake.submitted) == 1 and not fake.payloads
    assert model.history[-1]['content'] == 'followup result'


def test_worker_unknown_creation_failure_does_not_resubmit(env, monkeypatch):
    fake = FakeClient()
    attempts = []
    def fail(**kw): attempts.append(kw); raise OSError('private task and secret')
    fake.beta.agents.sessions.create = fail
    install_bridge(env, monkeypatch, fake)
    model = select(env); send(env, model, 'test')
    assert model._state['outcome'] == 'uncertain' and len(attempts) == 1
    assert model._state['submission_started'] is True
    assert 'private task and secret' not in model._notice


def test_worker_current_browser_login_response_is_not_echoed(monkeypatch):
    worker = load_worker(monkeypatch, 'browser_worker')
    fake = FakeClient(session_status='requires_action', saved_turn='in_progress')
    fake.required_actions = [{'type': 'computer_use_approval_request', 'turn_id': 't1', 'request_id': 'auth1',
                              'request': {'type': 'browser_authentication', 'credential_origin': 'https://example.test',
                                          'fields': [{'id': 'password', 'required': True, 'label': 'Password'}]}}]
    @contextmanager
    def client(connection): yield fake
    monkeypatch.setattr(worker, 'create_client', client)
    emitted = []
    monkeypatch.setattr(worker, 'emit', lambda kind, **data: emitted.append(dict(type=kind, **data)))
    command = {'action': 'browser_response', 'session_id': 'sess_test', 'turn_id': 't1', 'request_id': 'auth1',
               'response': {'type': 'browser_authentication', 'action': 'submit', 'fields': [{'field_id': 'password', 'value': 'SYNTHETIC-NOT-A-REAL-PASSWORD'}]}}
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(command) + '\n'))
    worker.main()
    assert emitted[-1]['type'] == 'result' and emitted[-1]['accepted'] is True
    assert 'SYNTHETIC-NOT-A-REAL-PASSWORD' not in json.dumps(emitted)
    assert len(fake.submitted) == 1


def test_worker_stale_browser_action_is_not_submitted(monkeypatch):
    worker = load_worker(monkeypatch, 'stale_browser_worker'); fake = FakeClient(session_status='idle')
    @contextmanager
    def client(connection): yield fake
    monkeypatch.setattr(worker, 'create_client', client)
    emitted = []
    monkeypatch.setattr(worker, 'emit', lambda kind, **data: emitted.append(dict(type=kind, **data)))
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'action': 'browser_response', 'session_id': 'sess_test',
        'turn_id': 'old', 'request_id': 'old-approval', 'response': {'type': 'browser_origin_access', 'decision': 'approve'}}) + '\n'))
    worker.main()
    assert emitted[-1]['type'] == 'error' and not fake.submitted


def test_cancel_reaches_application_function_in_another_worker(tmp_path, monkeypatch):
    """The real subprocess boundary must not hide a process-local Event bug."""
    import os
    import subprocess
    from modules.agent import tools
    control = tmp_path / 'shared-controls'
    monkeypatch.setattr(tools, 'CONTROL_ROOT', control)
    script = r'''
import json,sys,socket,time
from pathlib import Path
from types import SimpleNamespace
from modules.agent import tools
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('Network forbidden'))
tools.CONTROL_ROOT=Path(sys.argv[1])
def execute(arguments, stop):
    print('ready', flush=True)
    if not stop.wait(8): raise RuntimeError('Cancel did not cross worker boundary')
    deadline=time.monotonic()+5
    while not (tools.CONTROL_ROOT/'finish-allowed').exists():
        if time.monotonic()>deadline: raise RuntimeError('Missing test completion handshake')
        time.sleep(0.01)
    return {'observed_stop': True}
def cancel():
    (tools.CONTROL_ROOT/'callback-observed').write_text('yes')
tools.register_function('cooperative_test','Offline cooperative function', {'type':'object','properties':{},'additionalProperties':False},execute,cancel=cancel)
client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(events=SimpleNamespace(create=lambda *a,**k:print(json.dumps(k),flush=True))))))
state=SimpleNamespace(session_id='sess_subprocess',turn_id='turn_subprocess')
action={'type':'function_call','turn_id':state.turn_id,'call_id':'call_worker','name':'cooperative_test','arguments':{}}
tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['cooperative_test']},set())
'''
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('OPENAI_', 'CHUANHU_AGENT_'))}
    process = subprocess.Popen([sys.executable, '-u', '-c', script, str(control)], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    try:
        assert process.stdout.readline().strip() == 'ready'
        assert not tools._running  # The running function lives in a different interpreter.
        receipt = tools.cancel_application_tasks('sess_subprocess', 'turn_subprocess')
        assert receipt and receipt[0]['confirmed'] is False
        (control / 'finish-allowed').write_text('yes')
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr
        event = json.loads(stdout)['events'][0]
        assert event['success'] is False and event['call_id'] == 'call_worker'
        assert (control / 'callback-observed').read_text() == 'yes'
        outcome = tools.cancel_application_tasks('sess_subprocess', 'turn_subprocess')
        assert outcome[0]['status'] == 'stopped' and outcome[0]['confirmed'] is True
    finally:
        if process.poll() is None:
            process.kill(); process.communicate()
