"""Offline contracts against the same pinned SDK used for ordinary chat."""
import copy
import json
from pathlib import Path
import sys

import httpx2
import openai
import pytest
from agent_sdk_contract import check


@pytest.fixture
def payload():
    return {'agent': {'model': 'gpt-6-astra', 'reasoning': {'effort': 'medium'},
                      'tools': [{'type': 'computer_use'}, {'type': 'web_search'}, {'type': 'tool_search'}, {'type': 'programmatic_tool_calling', 'enabled': True}],
                      'multi_agent': {'enabled': False}},
            'environment': {'type': 'openai_hosted', 'network': {'access': 'enabled'}, 'desktop': {'enabled': True}},
            'input': 'offline synthetic prompt', 'stream': True}


def test_all_requested_builtin_tools_and_desktop_match_sdk(payload):
    report = check(payload)
    assert report['sdk_version'] == '3.22.0' and report['serialized'] == payload


def test_update_current_session_model_and_effort_contract():
    payload = {'agent': {'model': 'gpt-6-sol', 'reasoning': {'effort': 'high'}}}
    assert check(payload, 'update')['serialized'] == payload
    assert check({'agent': {'reasoning': {'effort': None}}}, 'update')['serialized']['agent']['reasoning']['effort'] is None


def test_reject_old_network_mode_and_invented_tools(payload):
    payload['environment']['network'] = {'mode': 'disabled'}
    with pytest.raises(AssertionError, match='SDK'):
        check(payload)
    payload['environment']['network'] = {'access': 'disabled'}
    payload['agent']['tools'] = [{'type': 'shell'}]
    with pytest.raises(AssertionError, match='SDK'):
        check(payload)


def test_actual_sdk_serializes_create_and_update_without_network(payload, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Network forbidden')))
    from modules.agent.connection import create_client
    requests = []
    def route(request):
        requests.append(request)
        return httpx2.Response(200, json={'id': 'sess_test', 'object': 'agent.session', 'status': 'idle'})
    with create_client({'api_key': 'offline', 'base_url': 'https://test.example/v1'},
                       http_client=httpx2.Client(transport=httpx2.MockTransport(route))) as client:
        request = copy.deepcopy(payload)
        request['stream'] = False
        client.beta.agents.sessions.create(**request)
        client.beta.agents.sessions.update('sess_test', agent={'model': 'gpt-6-sol', 'reasoning': {'effort': 'high'}})
    assert json.loads(requests[0].content) == request
    assert json.loads(requests[1].content) == {'agent': {'model': 'gpt-6-sol', 'reasoning': {'effort': 'high'}}}
    assert str(requests[1].url).endswith('/agents/sessions/sess_test')


def test_same_sdk_preserves_legacy_completion_resource():
    with openai.OpenAI(api_key='offline') as client:
        assert callable(client.completions.create)
        assert callable(client.chat.completions.create)
        assert callable(client.embeddings.create)
        assert callable(client.beta.agents.sessions.create)
        assert callable(client.beta.agents.sessions.update)


def test_requirements_do_not_request_a_second_agent_environment():
    root = Path(__file__).resolve().parents[2]
    for file in (root / 'requirements.txt', root / 'requirements_tests.txt'):
        assert 'openai==3.22.0' in file.read_text()
    source = (root / 'modules/agent/transport.py').read_text()
    assert '.agents-runtime' not in source and 'CHUANHU_AGENT_PYTHON' not in source


def test_function_mcp_and_web_search_parameter_contracts(payload):
    payload['agent']['tools'] += [
        {'type': 'function', 'name': 'text_statistics', 'description': 'Offline test',
         'defer_loading': True, 'parameters': {'type': 'object', 'properties': {'text': {'type': 'string'}}}},
        {'type': 'mcp', 'server_label': 'configured', 'transport': {'type': 'http', 'server_url': 'https://configured.example/mcp'}, 'allowed_tools': ['read']},
        {'type': 'web_search', 'allowed_domains': ['example.com'], 'context_size': 'medium', 'mode': 'live'},
    ]
    assert check(payload)['serialized'] == payload


def test_browser_approval_response_and_followup_event_contracts():
    # Explicit event types prevent a UI-only approval switch from counting as a backend path.
    body = {'events': [{'type': 'agent.session.input.message', 'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'followup'}]}]}]}
    assert check(body, 'events')['serialized'] == body
    for decision in ('approve', 'deny', 'cancel'):
        body = {'events': [{'type': 'agent.session.input.computer_use_approval_request_result',
                            'request_id': 'approval_test', 'response': {'type': 'browser_origin_access', 'decision': decision}}]}
        assert check(body, 'events')['serialized'] == body


def test_langchain_ordinary_chat_uses_shared_sdk_offline(monkeypatch):
    langchain = pytest.importorskip('langchain_openai')
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Network forbidden')))
    requests = []
    def route(request):
        requests.append(request)
        return httpx2.Response(200, json={'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 0,
                                         'model': 'ordinary-model', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ordinary reply'}, 'finish_reason': 'stop'}],
                                         'usage': {'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3}})
    with httpx2.Client(transport=httpx2.MockTransport(route)) as client:
        model = langchain.ChatOpenAI(api_key='offline', base_url='https://example.test/v1', model='ordinary-model',
                                    http_client=client, http_socket_options=())
        answer = model.invoke('offline question')
    assert answer.content == 'ordinary reply' and answer.usage_metadata['total_tokens'] == 3
    assert str(requests[0].url) == 'https://example.test/v1/chat/completions'


@pytest.mark.parametrize('network', [True, False])
def test_actual_runtime_create_payload_through_real_sdk(network, monkeypatch):
    import socket
    from modules.agent import runtime
    from modules.agent.connection import create_client
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Network forbidden')))
    requests = []
    def route(request):
        requests.append(request)
        if request.method == 'POST':
            event = lambda kind: {'type': 'agent.session.turn.' + kind, 'session_id': 'sess_test', 'turn_id': 'turn_test',
                                  'turn': {'id': 'turn_test', 'status': kind, 'subagent_id': None}}
            data = ''.join('data: ' + json.dumps(event(kind)) + '\n\n' for kind in ('created', 'completed'))
            return httpx2.Response(200, text=data, headers={'content-type': 'text/event-stream'})
        if '/turns/' in str(request.url):
            data = {'id': 'turn_test', 'status': 'completed'}
        elif str(request.url).endswith('/sess_test'):
            data = {'id': 'sess_test', 'status': 'idle', 'required_actions': []}
        else:
            data = {'object': 'list', 'data': [], 'has_more': False}
        return httpx2.Response(200, json=data)
    with create_client({'api_key': 'offline', 'base_url': 'https://example.test/v1'},
                       http_client=httpx2.Client(transport=httpx2.MockTransport(route))) as client:
        state = runtime.run_task(client, '长输入' * 10000, 'gpt-6-astra', reasoning='medium',
                                 tool_settings={'network': network, 'functions': ['text_statistics']})
    assert state.outcome == 'completed'
    body = json.loads(requests[0].content)
    assert check(body)['serialized'] == body
    assert body['environment']['network']['access'] == ('enabled' if network else 'disabled')
    assert len(body['input']) == 30000
    assert {tool['type'] for tool in body['agent']['tools']} >= {'computer_use', 'web_search', 'function'}
    assert not ({tool['type'] for tool in body['agent']['tools']} & {'tool_search', 'programmatic_tool_calling'})


def test_langchain_ordinary_stream_survives_sdk_upgrade(monkeypatch):
    langchain = pytest.importorskip('langchain_openai')
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Network forbidden')))
    def route(request):
        chunks = [{'id': 'chatcmpl-test', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'ordinary-model',
                   'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': text}, 'finish_reason': None}]}
                  for text in ('ordinary ', 'stream')]
        end = {'id': 'chatcmpl-test', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'ordinary-model',
               'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}
        data = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in [*chunks, end]) + 'data: [DONE]\n\n'
        return httpx2.Response(200, text=data, headers={'content-type': 'text/event-stream'})
    with httpx2.Client(transport=httpx2.MockTransport(route)) as client:
        model = langchain.ChatOpenAI(api_key='offline', base_url='https://example.test/v1', model='ordinary-model',
                                    http_client=client, http_socket_options=())
        assert ''.join(chunk.content for chunk in model.stream('offline question')) == 'ordinary stream'


def test_legacy_completions_and_embeddings_keep_expected_result_shape(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Network forbidden')))
    def route(request):
        if request.url.path.endswith('/embeddings'):
            body = {'object': 'list', 'model': 'embedding-model', 'data': [{'object': 'embedding', 'index': 0, 'embedding': [0.1, 0.2]}], 'usage': {'prompt_tokens': 2, 'total_tokens': 2}}
        else:
            body = {'id': 'cmpl-test', 'object': 'text_completion', 'created': 0, 'model': 'instruct-model',
                    'choices': [{'index': 0, 'text': ' legacy reply ', 'finish_reason': 'stop', 'logprobs': None}],
                    'usage': {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5}}
        return httpx2.Response(200, json=body)
    with openai.OpenAI(api_key='offline', base_url='https://example.test/v1',
                       http_client=httpx2.Client(transport=httpx2.MockTransport(route))) as client:
        result = client.completions.create(model='instruct-model', prompt='offline')
        assert result.choices[0].text.strip() == 'legacy reply' and result.usage.total_tokens == 5
        assert client.embeddings.create(model='embedding-model', input='offline').data[0].embedding == [0.1, 0.2]
