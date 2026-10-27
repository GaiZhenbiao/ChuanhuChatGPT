"""Offline model compatibility and sanitized SDK rejection regressions."""
import asyncio
import json
import logging
import subprocess

import gradio as gr
import httpx2
import pytest

from agent_fixtures import complete, env, request, select, send
from agent_sdk_contract import check
from modules.agent import inputs, runtime
from modules.agent.connection import create_client
from modules.agent.reasoning import compatible_reasoning, reasoning_options
from test_inputs_runtime import stage, RUN_ID
from test_runtime import FakeClient, turn


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket
    def fail(*args, **kwargs): raise AssertionError('Real network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', fail)
    monkeypatch.setattr(socket.socket, 'connect_ex', fail)
    monkeypatch.setattr(socket, 'create_connection', fail)


def rejection(request):
    return httpx2.Response(400, headers={'x-request-id': 'req_'+'d'*32},
        json={'error': {'code': 'invalid_request_error', 'type': 'invalid_request_error',
            'param': 'agent.reasoning.effort', 'message': 'Bearer synthetic-private-body'}}, request=request)


def sdk(route):
    return create_client({'api_key': 'offline-only', 'base_url': 'https://offline.invalid/v1',
        'organization': '', 'project': ''}, http_client=httpx2.Client(transport=httpx2.MockTransport(route)))


@pytest.mark.parametrize('model', ['gpt-6-astra', 'gpt-6-sol', 'gpt-6.1-sol'])
@pytest.mark.parametrize('effort', ['minimal', 'low', 'medium', 'high', 'xhigh', 'max', None])
def test_new_run_sdk_payload_never_sends_known_unsupported_effort(model, effort):
    requests = []
    def route(request):
        requests.append(request)
        return rejection(request)
    with sdk(route) as client, pytest.raises(runtime.AgentError) as caught:
        runtime.run_task(client, 'synthetic input', model, reasoning=effort)
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    check(payload)
    assert payload['agent'].get('reasoning', {}).get('effort') == ('low' if effort == 'minimal' else effort)
    assert caught.value.diagnostics['phase'] == 'run.session_create'
    assert caught.value.diagnostics['type'] == 'invalid_request_error'
    assert 'synthetic-private-body' not in str(caught.value)
    assert 'API 地址' not in str(caught.value) and '支持 Agents API' not in str(caught.value)
    assert caught.value.state.outcome == 'not_started'


@pytest.mark.parametrize('failure_phase', ['list', 'create'])
def test_attachment_rejection_retains_phase_after_submission_marker_clears(stage, failure_phase):
    make, root = stage
    record = make()
    requests = []
    def route(request):
        requests.append(request)
        if request.method == 'GET' and failure_phase == 'create':
            return httpx2.Response(200, json={'object': 'list', 'data': [], 'has_more': False})
        return rejection(request)
    with sdk(route) as client, pytest.raises(inputs.InputPreparationError) as caught:
        inputs.prepare_inputs(client, [record], 'gpt-6.1-sol', reasoning='minimal',
            staging_root=root, run_id=RUN_ID)
    error = caught.value
    expected = 'preparation.session_' + failure_phase
    assert error.diagnostics['phase'] == expected
    assert error.state['last_request_phase'] == expected
    assert error.state['diagnostics'] == error.diagnostics
    assert not error.state['submission_started'] and not error.state['session_creation_started']
    assert error.state['uncertain_operation'] is None and error.state['session_id'] is None
    if failure_phase == 'create':
        body = json.loads(requests[-1].content)
        assert body['agent']['reasoning']['effort'] == 'low' and body['stream'] is False
        assert 'input' not in body
    assert 'synthetic-private-body' not in json.dumps(error.state)


def test_update_sdk_payload_migrates_minimal_and_keeps_safe_diagnostics():
    requests = []
    def route(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx2.Response(200, json={'id': 'sess_test', 'status': 'idle',
                'agent': {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'minimal'}}})
        return rejection(request)
    with sdk(route) as client, pytest.raises(runtime.AgentError) as caught:
        runtime.update_settings(client, 'sess_test', 'gpt-6.1-sol', 'minimal')
    body = json.loads(requests[-1].content)
    check(body, 'update')
    assert body['agent']['reasoning']['effort'] == 'low'
    assert caught.value.diagnostics['phase'] == 'update.session_update'
    assert caught.value.diagnostics['request_id'] == 'req_'+'d'*32
    assert 'synthetic-private-body' not in str(caught.value)


def test_existing_cloud_session_repairs_effort_before_input():
    client = FakeClient([turn('created'), turn('completed')])
    client.agent = {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'minimal'}}
    runtime.run_task(client, 'synthetic followup', 'gpt-6.1-sol', reasoning='minimal', session_id='sess_test')
    assert client.updated[0][1]['agent']['reasoning']['effort'] == 'low'
    assert client.agent['reasoning']['effort'] == 'low' and len(client.submitted) == 1


def test_existing_cloud_low_is_not_overwritten():
    client = FakeClient([turn('created'), turn('completed')])
    client.agent = {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'low'}}
    runtime.run_task(client, 'synthetic followup', 'gpt-6.1-sol', reasoning='low', session_id='sess_test')
    assert not client.updated and client.agent['reasoning']['effort'] == 'low'


@pytest.mark.parametrize('model,effort,expected', [
    ('gpt-6-sol', 'none', 'none'), ('gpt-6.1-sol', 'none', 'low'),
    ('custom-model', 'minimal', 'minimal'), ('custom-model', 'none', 'none'),
])
def test_explicit_none_and_unknown_model_reach_sdk_without_inventing_support(model, effort, expected):
    requests = []
    def route(request):
        requests.append(request)
        return rejection(request)
    with sdk(route) as client, pytest.raises(runtime.AgentError):
        runtime.run_task(client, 'synthetic input', model, reasoning=effort)
    assert len(requests) == 1
    assert json.loads(requests[0].content)['agent']['reasoning']['effort'] == expected


@pytest.mark.parametrize('entry', ['run', 'update', 'prepare'])
def test_invalid_sdk_effort_is_rejected_before_any_http_request(stage, entry):
    make, root = stage
    record = make()
    def route(request): raise AssertionError('Invalid effort reached SDK transport')
    with sdk(route) as client, pytest.raises(runtime.AgentError):
        if entry == 'run': runtime.run_task(client, 'synthetic', 'gpt-6.1-sol', reasoning='ultra')
        elif entry == 'update': runtime.update_settings(client, 'sess_test', 'gpt-6.1-sol', 'ultra')
        else: inputs.prepare_inputs(client, [record], 'gpt-6.1-sol', reasoning='ultra', staging_root=root, run_id=RUN_ID)


def test_new_view_and_reset_migrate_inherited_minimal_and_ui_matches(env):
    from modules.agent.ui import AgentPanel
    model = select(env)
    model._reasoning = 'minimal'
    fresh = model.new_view()
    assert fresh.agent_model_choice == ('gpt-6.1-sol', 'low')
    fresh.reset()
    assert fresh.agent_model_choice == ('gpt-6.1-sol', 'low') and '已调整' in fresh._status()
    with gr.Blocks(analytics_enabled=False) as app:
        panel = AgentPanel(); panel.selectors(); panel.settings_components(); panel.output_components()
    values = dict(zip(panel.outputs, panel.values(fresh)))
    assert values[panel.reasoning]['value'] == 'low'
    assert 'minimal' not in [value for label, value in values[panel.reasoning]['choices']]
    app.close()


def test_history_migration_queues_cloud_update_and_preserves_legal_low(env, monkeypatch):
    calls, _ = complete(env, monkeypatch)
    model = select(env); send(env, model)
    model._reasoning = model._session_settings['reasoning'] = 'minimal'
    model._remember(); model._restore_binding()
    assert model._reasoning == 'minimal'  # effective value until confirmation
    assert model.agent_model_choice == ('gpt-6.1-sol', 'low')
    model._apply_next_model(model._state['generation'])
    assert calls[-1]['action'] == 'update' and calls[-1]['reasoning'] == 'low'
    assert model._reasoning == model._session_settings['reasoning'] == 'low'
    model._remember(); model._restore_binding()
    assert model.agent_model_choice == ('gpt-6.1-sol', 'low')
    assert model.new_view()._reasoning == 'low'


def test_switch_model_migrates_only_incompatible_value_and_custom_model_is_preserved(env):
    from modules.agent.ui import reasoning_info
    model = select(env)
    model.set_agent_model('gpt-6-sol', 'none', 1)
    assert model.agent_model_choice == ('gpt-6-sol', 'none')
    notice = model.set_agent_model('gpt-6-astra', 'none', 2)
    assert model.agent_model_choice == ('gpt-6-astra', 'low') and '已调整' in notice
    model.set_agent_model('custom-model', 'minimal', 3)
    assert model.agent_model_choice == ('custom-model', 'minimal')
    assert reasoning_options('custom-model', 'minimal') == ['default', 'minimal']
    assert compatible_reasoning('custom-model', 'none') == ('none', '')
    assert '尚无已核实' in reasoning_info('custom-model')
    assert reasoning_info('gpt-6.1-sol') is None


@pytest.mark.parametrize('param,retained', [
    ('agent.tools[0].type', True), ('agent.tools[12]', True),
    ('agent.tools[0].synthetic_secret', False), ('agent.tools[0].type?token=secret', False),
])
def test_indexed_schema_error_field_retains_only_closed_names(param, retained):
    diagnostic = runtime._safe_diagnostics({'param': param})
    assert ('param' in diagnostic) is retained


def test_choice_receipt_updates_native_dropdown_only_for_latest_visit(env):
    from modules.agent.ui import AgentPanel
    model = select(env)
    with gr.Blocks(analytics_enabled=False) as app:
        current = gr.State(); chat = gr.Chatbot(); status = gr.Markdown()
        panel = AgentPanel(); panel.selectors(); panel.settings_components(); panel.output_components(); panel.wire(current, chat, status)
    fn = next(fn.fn for fn in app.fns if fn.fn and fn.fn.__name__ == 'choose_settings')
    result = fn(model, 'gpt-6.1-sol', 'minimal', 1, model.agent_choice_target, request=request())
    receipt = json.loads(result[1]); assert receipt['value'] == 'low'
    js = next(item['js'] for item in app.get_config_file()['dependencies'] if item.get('js') and 'JSON.parse(wire)' in item['js'])
    script = 'const fs=require("fs"),v=JSON.parse(fs.readFileSync(0,"utf8"));global.window={chuanhuAgentChoiceRevision:v.revision};const f='+js+';process.stdout.write(JSON.stringify(f(v.wire,v.target)));'
    def invoke(revision, target):
        value = {'wire': result[1], 'revision': revision, 'target': target}
        output = subprocess.run(['node', '-e', script], input=json.dumps(value), text=True, capture_output=True, check=True)
        return json.loads(output.stdout)[0]
    assert invoke(1, model.agent_choice_target)['value'] == 'low'
    assert invoke(2, model.agent_choice_target) == {'__type__': 'update'}
    assert invoke(1, 'different-visit') == {'__type__': 'update'}
    app.close()


def test_filtered_error_persists_to_private_binding_without_body_or_prompt(env, monkeypatch, caplog):
    model = select(env)
    diagnostic = {'status_code': 400, 'type': 'invalid_request_error', 'code': 'invalid_request_error',
        'param': 'agent.reasoning.effort', 'request_id': 'req_'+'e'*32, 'phase': 'run.session_create',
        'body': 'Bearer synthetic-private-body', 'prompt': 'synthetic-private-prompt'}
    def worker(command):
        yield {'type': 'error', 'outcome': 'not_started', 'message': 'Synthetic rejection', 'diagnostics': diagnostic}
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    with caplog.at_level(logging.WARNING): send(env, model, 'synthetic ordinary input')
    stored = model._store().get(model._owner, model.history_file_path)['last_request_error']
    assert stored['phase'] == 'run.session_create' and stored['request_id'] == 'req_'+'e'*32
    assert 'body' not in stored and 'prompt' not in stored
    messages = '\n'.join(record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING)
    assert 'synthetic-private-body' not in messages and 'synthetic-private-prompt' not in messages
    assert 'synthetic ordinary input' not in messages
