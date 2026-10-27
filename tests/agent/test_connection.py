"""Offline connection inheritance, SDK HTTP and same-interpreter transport tests."""
import importlib.util
import json
from pathlib import Path
import ssl
import sys
from types import SimpleNamespace

import httpx2
import openai
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.agent import connection


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Real network forbidden')))


def settings(tmp_path, **kwargs):
    return connection.resolve_connection(credential_path=tmp_path / 'missing-key-file', **kwargs)


def test_inherit_existing_key_base_scope_and_environment_proxies(tmp_path):
    source = {'OPENAI_API_KEY': 'ordinary-key', 'OPENAI_API_BASE': 'https://proxy.example/relay/v1/',
              'OPENAI_BASE_URL': 'https://ignored.example/v1', 'OPENAI_ORG_ID': 'org-one',
              'OPENAI_PROJECT_ID': 'proj-one', 'HTTP_PROXY': 'http://local:8080',
              'HTTPS_PROXY': 'http://local:8443', 'NO_PROXY': 'localhost'}
    actual = settings(tmp_path, environ=source)
    assert actual == {'api_key': 'ordinary-key', 'base_url': 'https://proxy.example/relay/v1',
                      'organization': 'org-one', 'project': 'proj-one',
                      'proxy_env': {k: source[k] for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY')}}
    assert source['OPENAI_API_BASE'].endswith('/')


def test_explicit_user_scope_and_optional_key_precedence(tmp_path):
    env = {'OPENAI_API_KEY': 'global-key', 'CHUANHU_AGENT_API_KEY': 'agent-env',
           'OPENAI_ORG_ID': 'global-org', 'OPENAI_PROJECT_ID': 'global-project'}
    resolved = settings(tmp_path, api_key='user-key', api_base='https://private.example/v1',
                        organization='', project='user-project', environ=env)
    assert resolved['api_key'] == 'agent-env'
    assert resolved['base_url'] == 'https://private.example/v1'
    assert resolved['organization'] == '' and resolved['project'] == 'user-project'
    assert settings(tmp_path, api_key='user-key', environ={})['api_key'] == 'user-key'
    assert settings(tmp_path, api_key='user-key', dedicated_key='explicit-agent', environ=env)['api_key'] == 'explicit-agent'


def test_optional_file_absent_or_empty_reuses_existing_key(tmp_path):
    path = tmp_path / '.env.agents'
    path.write_text('CHUANHU_AGENT_API_KEY=\n')
    assert connection.resolve_connection('ordinary', credential_path=path, environ={})['api_key'] == 'ordinary'
    path.write_text('CHUANHU_AGENT_API_KEY="file-override"\n')
    assert connection.resolve_connection('ordinary', credential_path=path, environ={})['api_key'] == 'file-override'


def test_missing_or_invalid_connection_never_silently_uses_official(tmp_path):
    with pytest.raises(connection.AgentConnectionError, match='未配置'):
        settings(tmp_path, environ={})
    for base in ('not a url', 'ftp://wrong.example', 'https://user:secret@example.test/v1', 'https://example.test?secret=x'):
        with pytest.raises(connection.AgentConnectionError):
            settings(tmp_path, api_key='ordinary', api_base=base, environ={})


def test_child_environment_keeps_proxy_tls_but_key_only_in_stdin(tmp_path):
    config = settings(tmp_path, api_key='secret', environ={'HTTPS_PROXY': 'http://scope:80', 'SSL_CERT_FILE': '/scope/ca.pem'})
    source = {'OPENAI_API_KEY': 'old', 'CHUANHU_AGENT_API_KEY': 'old', 'OPENAI_BASE_URL': 'old',
              'HTTPS_PROXY': 'http://wrong:80', 'HTTP_PROXY': 'http://wrong:80', 'PATH': '/usr/bin'}
    actual = connection.worker_environment(config, source)
    assert actual == {'HTTPS_PROXY': 'http://scope:80', 'SSL_CERT_FILE': '/scope/ca.pem', 'PATH': '/usr/bin'}
    assert source['OPENAI_API_KEY'] == 'old'


def mock_client(tmp_path, handler):
    config = settings(tmp_path, api_key='offline-key', api_base='https://custom.example/relay/v1',
                      organization='org-test', project='proj-test', environ={})
    return connection.create_client(config, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_actual_sdk_headers_custom_endpoint_and_ordinary_completion(tmp_path):
    calls = []
    def route(request):
        calls.append(request)
        return httpx2.Response(200, json={'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 0,
                                         'model': 'ordinary-model', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}]})
    with mock_client(tmp_path, route) as client:
        response = client.chat.completions.create(model='ordinary-model', messages=[{'role': 'user', 'content': 'offline'}])
    assert response.choices[0].message.content == 'ok'
    assert str(calls[0].url) == 'https://custom.example/relay/v1/chat/completions'
    assert calls[0].headers['authorization'] == 'Bearer offline-key'
    assert calls[0].headers['openai-organization'] == 'org-test'
    assert calls[0].headers['openai-project'] == 'proj-test'


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500])
@pytest.mark.parametrize('operation', ['create', 'input', 'update', 'delete'])
def test_mutations_not_retried_or_redirected_to_another_base(tmp_path, status, operation):
    calls = []
    def route(request):
        calls.append(request)
        return httpx2.Response(status, json={'error': {'message': 'synthetic error', 'type': 'invalid_request_error'}})
    with mock_client(tmp_path, route) as client:
        sessions = client.beta.agents.sessions
        actions = {'create': lambda: sessions.create(agent={'model': 'gpt-6-astra'}, environment={'type': 'none'}, input='x'),
                   'input': lambda: sessions.events.create('sess_test', events=[{'type': 'agent.session.input.message', 'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'x'}]}]}]),
                   'update': lambda: sessions.update('sess_test', agent={'model': 'gpt-6-sol'}),
                   'delete': lambda: sessions.delete('sess_test')}
        with pytest.raises(openai.APIStatusError):
            actions[operation]()
    assert len(calls) == 1 and calls[0].url.host == 'custom.example'


def test_mutation_connection_failure_not_retried(tmp_path):
    calls = []
    def route(request):
        calls.append(request)
        raise httpx2.ConnectError('synthetic', request=request)
    with mock_client(tmp_path, route) as client:
        with pytest.raises(openai.APIConnectionError):
            client.beta.agents.sessions.create(agent={'model': 'gpt-6-astra'}, environment={'type': 'none'}, input='x')
    assert len(calls) == 1


def test_reads_retry_bounded_and_preserve_beta_header(tmp_path, monkeypatch):
    monkeypatch.setattr(openai._base_client.time, 'sleep', lambda *a: None)
    calls = []
    def route(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx2.Response(503, json={'error': {'message': 'busy'}})
        return httpx2.Response(200, json={'id': 'sess_test', 'object': 'agent.session', 'status': 'idle'})
    with mock_client(tmp_path, route) as client:
        assert client.beta.agents.sessions.retrieve('sess_test').status == 'idle'
    assert len(calls) == 3
    assert all(request.headers['OpenAI-Beta'] == 'agents=v1' for request in calls)


def test_artifact_observer_disables_sdk_read_retries(tmp_path, monkeypatch):
    from modules.agent.artifacts import ArtifactObserver
    monkeypatch.setattr(openai._base_client.time, 'sleep', lambda *a: None)
    calls = []
    def route(request):
        calls.append(request)
        return httpx2.Response(503, json={'error': {'message': 'busy'}})
    with mock_client(tmp_path, route) as client:
        observer = ArtifactObserver(client, lambda *args, **kwargs: None)
        with pytest.raises(openai.APIStatusError):
            observer.client.beta.agents.sessions.retrieve('sess_test')
    assert len(calls) == 1


def load_transport(tmp_path, monkeypatch):
    import modules
    monkeypatch.setattr(modules, 'shared', SimpleNamespace(chuanhu_path=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, 'modules.presets', SimpleNamespace(i18n=lambda key: key))
    spec = importlib.util.spec_from_file_location('test_transport_private', ROOT / 'modules/agent/transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transport_same_python_complete_large_stdin_and_stdout(tmp_path, monkeypatch):
    bridge = load_transport(tmp_path, monkeypatch)
    worker = tmp_path / 'modules/agent/worker.py'
    worker.parent.mkdir(parents=True)
    worker.write_text('import json,sys,os\nc=json.loads(sys.stdin.readline())\nassert c["connection"]["api_key"]=="offline"\nassert "OPENAI_API_KEY" not in os.environ\nprint(json.dumps({"type":"result","text":c["prompt"],"python":sys.executable}))\n')
    monkeypatch.setenv('CHUANHU_AGENT_PYTHON', '/intentionally-invalid-interpreter')
    text = '长内容' * 500000
    config = settings(tmp_path, api_key='offline', environ={})
    result = list(bridge.worker_messages({'action': 'run', 'prompt': text}, connection=config))
    assert len(result) == 1 and result[0]['text'] == text
    assert result[0]['python'] == sys.executable


def test_transport_preserves_ids_when_worker_dies(tmp_path, monkeypatch):
    bridge = load_transport(tmp_path, monkeypatch)
    worker = tmp_path / 'modules/agent/worker.py'
    worker.parent.mkdir(parents=True)
    worker.write_text('import json,sys\nsys.stdin.readline()\nprint(json.dumps({"type":"progress","session_id":"sess_saved","turn_id":"turn_saved"}))\n')
    result = list(bridge.worker_messages({'action': 'inspect'}, connection=settings(tmp_path, api_key='offline', environ={})))
    assert result[-1]['type'] == 'error' and result[-1]['outcome'] == 'incomplete'
    assert result[-1]['session_id'] == 'sess_saved' and result[-1]['turn_id'] == 'turn_saved'


def test_host_connection_uses_existing_proxy_context_and_user_model_scope(tmp_path, monkeypatch):
    from contextlib import contextmanager
    bridge = load_transport(tmp_path, monkeypatch)
    bridge.shared.state = SimpleNamespace(openai_api_base='https://configured.example/v1')
    bridge.shared.format_openai_host = lambda host: (None, None, host.rstrip('/') + '/v1')
    calls = []
    @contextmanager
    def retrieve_proxy():
        calls.append('proxy')
        with monkeypatch.context() as patch:
            patch.setenv('HTTPS_PROXY', 'http://existing-proxy:88')
            yield ('', 'http://existing-proxy:88')
    monkeypatch.setitem(sys.modules, 'modules.config', SimpleNamespace(config={'openai_project_id': 'project-config'}, my_api_key='app-key', retrieve_proxy=retrieve_proxy))
    monkeypatch.delenv('CHUANHU_AGENT_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_PROJECT_ID', raising=False)
    actual = bridge.connection_for_model(api_key='user-key', api_host='https://user.example')
    assert calls == ['proxy']
    assert actual['api_key'] == 'user-key' and actual['base_url'] == 'https://user.example/v1'
    assert actual['proxy_env']['HTTPS_PROXY'] == 'http://existing-proxy:88'
    assert actual['project'] == 'project-config'


def test_default_client_retains_normal_tls_certificate_checks(tmp_path, monkeypatch):
    # Construct only, without sending a request or touching any real account.
    for name in connection.PROXY_ENV:
        monkeypatch.delenv(name, raising=False)
    with connection.create_client(settings(tmp_path, api_key='offline', environ={})) as client:
        context = client._client._transport._pool._ssl_context
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        assert client._client.follow_redirects is True
