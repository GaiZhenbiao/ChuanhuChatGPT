"""Offline recovery of expired Files API sources, never ambiguous write replay."""
import json
from pathlib import Path

import pytest

from modules.agent import inputs
from modules.agent.connection import create_client
from test_inputs_runtime import FakeClient, RUN_ID, stage


class HTTPFailure(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__('synthetic private body')


class ExpiringClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.expired_ids, self.source_reads, self.copy_attempts = set(), [], []
        self.copy_failures, self.source_failure, self.environment_failure = [], None, None
        self.on_source_read = None
        self.files.retrieve = self.retrieve_source

    def upload_file(self, **kwargs):
        self._write('files_upload', kwargs)
        if self.upload_error:
            raise self.upload_error
        identifier = 'file_synthetic_' + str(len(self.uploads) + 1)
        self.uploads[identifier] = kwargs['file'][1]
        return {'id': identifier}

    def retrieve_source(self, identifier):
        self.source_reads.append(identifier)
        if self.on_source_read:
            self.on_source_read()
        if self.source_failure:
            raise self.source_failure
        if identifier in self.expired_ids:
            raise HTTPFailure(404)
        return {'id': identifier}

    def retrieve_environment(self, identifier):
        if self.copy_attempts and self.environment_failure:
            raise self.environment_failure
        return super().retrieve_environment(identifier)

    def copy_file(self, identifier, **kwargs):
        self._write('environment_copy', kwargs)
        self.copy_attempts.append(kwargs['file_id'])
        if self.copy_failures:
            raise self.copy_failures.pop(0)
        if kwargs['file_id'] in self.expired_ids:
            raise HTTPFailure(404)
        copied = {'environment_id': identifier, 'path': kwargs['path'],
                  'size_bytes': len(self.uploads[kwargs['file_id']])}
        self.remote.append(copied)
        return copied


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Offline test')))


def prepare(client, record, root, **kwargs):
    return inputs.prepare_inputs(client, [record], 'synthetic-model', staging_root=root,
                                 session_id='sess_test', run_id=RUN_ID, poll_interval=0, **kwargs)


def stopped_after_upload(stage):
    make, root = stage
    record = make(b'x' * (inputs.INLINE_LIMIT + 1))
    client, cancelled = ExpiringClient(), [False]
    def progress(state):
        if (state['uncertain_operation'] or {}).get('operation') == 'environment_copy':
            cancelled[0] = True
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root, on_progress=progress, should_cancel=lambda: cancelled[0])
    state = caught.value.state
    assert state['outcome'] == 'cancelled' and state['files'][0]['file_id'] == 'file_synthetic_1'
    assert not client.copy_attempts
    return client, record, root, state


def test_confirmed_source_404_refreshes_once_from_verified_snapshot(stage):
    client, record, root, state = stopped_after_upload(stage)
    client.expired_ids.add('file_synthetic_1')
    progress = []
    result = prepare(client, record, root, resume_state=state, on_progress=progress.append)
    assert result['outcome'] == 'ready' and result['submission_started'] is False
    assert client.source_reads == ['file_synthetic_1']
    assert client.copy_attempts == ['file_synthetic_1', 'file_synthetic_2']
    assert len(client.uploads) == 2
    assert result['installed'][record['input_id']]['file_id'] == 'file_synthetic_2'
    retired = next(frame for frame in progress if frame['files'][0].get('source_status') == 'missing_confirmed')
    assert retired['files'][0]['expired_file_id'] == 'file_synthetic_1'
    assert 'file_id' not in retired['files'][0] and retired['uncertain_operation'] is None
    assert result['files'][0]['source_status'] == 'uploaded'
    assert 'synthetic private body' not in json.dumps(result)


def test_copy_reply_for_wrong_path_must_not_be_ready(stage):
    make, root = stage
    record, client = make(b'synthetic bytes'), FakeClient()
    original = client.beta.agents.environments.files.create
    def wrong_path(environment_id, **kwargs):
        copied = original(environment_id, **kwargs)
        return {**copied, 'path': record['remote_path'] + '.unexpected'}
    client.beta.agents.environments.files.create = wrong_path
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root)
    assert caught.value.state['outcome'] == 'uncertain'
    assert caught.value.state['installed'] == {}
    assert caught.value.state['files'][0]['status'] == 'failed'
    assert len(client.writes) == 1


@pytest.mark.parametrize('source', ['still_exists', '500', '403', 'timeout'])
def test_source_not_definitively_missing_never_reuploads(stage, source):
    client, record, root, state = stopped_after_upload(stage)
    client.copy_failures = [HTTPFailure(404)]
    if source != 'still_exists':
        client.source_failure = TimeoutError('private') if source == 'timeout' else HTTPFailure(int(source))
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root, resume_state=state)
    assert caught.value.state['outcome'] == 'failed'
    assert len(client.uploads) == 1 and client.copy_attempts == ['file_synthetic_1']
    assert client.source_reads == ['file_synthetic_1']


@pytest.mark.parametrize('failure', [HTTPFailure(500), TimeoutError('private')])
def test_unknown_copy_outcome_does_not_probe_source_or_refresh(stage, failure):
    client, record, root, state = stopped_after_upload(stage)
    client.copy_failures = [failure]
    client.expired_ids.add('file_synthetic_1')
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root, resume_state=state)
    assert caught.value.state['outcome'] == 'uncertain'
    assert caught.value.state['uncertain_operation']['operation'] == 'environment_copy'
    assert not client.source_reads and len(client.uploads) == 1


@pytest.mark.parametrize('condition', ['404', '500', 'disconnected', 'changed_session', 'destination_exists'])
def test_source_404_is_insufficient_without_same_live_environment_and_empty_path(stage, condition):
    client, record, root, state = stopped_after_upload(stage)
    client.expired_ids.add('file_synthetic_1')
    if condition in ('404', '500'):
        client.environment_failure = HTTPFailure(int(condition))
    elif condition == 'disconnected':
        client.on_source_read = lambda: setattr(client, 'environment_statuses', ['disconnected'])
    elif condition == 'changed_session':
        client.on_source_read = lambda: client.turns.append({'id': 'unexpected_turn'})
    else:
        client.on_source_read = lambda: client.remote.append({'environment_id': 'env_test',
            'path': record['remote_path'], 'size_bytes': record['size']})
    with pytest.raises(inputs.InputPreparationError):
        prepare(client, record, root, resume_state=state)
    assert len(client.uploads) == 1 and client.copy_attempts == ['file_synthetic_1']


def test_cancel_during_source_verification_never_refreshes(stage):
    client, record, root, state = stopped_after_upload(stage)
    client.expired_ids.add('file_synthetic_1')
    cancelled = [False]
    client.on_source_read = lambda: cancelled.__setitem__(0, True)
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root, resume_state=state, should_cancel=lambda: cancelled[0])
    assert caught.value.state['outcome'] == 'cancelled' and len(client.uploads) == 1
    assert caught.value.state['files'][0]['file_id'] == 'file_synthetic_1'
    assert caught.value.state['uncertain_operation'] is None


def test_cancel_after_retiring_source_can_resume_without_reusing_expired_id(stage):
    client, record, root, state = stopped_after_upload(stage)
    client.expired_ids.add('file_synthetic_1')
    cancelled = [False]
    def progress(value):
        if value['files'][0].get('source_status') == 'missing_confirmed':
            cancelled[0] = True
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root, resume_state=state, should_cancel=lambda: cancelled[0], on_progress=progress)
    recovery = caught.value.state
    assert recovery['outcome'] == 'cancelled' and 'file_id' not in recovery['files'][0]
    assert len(client.uploads) == 1
    result = prepare(client, record, root, resume_state=recovery)
    assert result['outcome'] == 'ready' and len(client.uploads) == 2
    assert client.copy_attempts == ['file_synthetic_1', 'file_synthetic_2']


def test_refresh_revalidates_staged_bytes_after_remote_reads(stage):
    client, record, root, state = stopped_after_upload(stage)
    client.expired_ids.add('file_synthetic_1')
    def changed():
        path = Path(record['staged_path'])
        path.chmod(0o600)
        path.write_bytes(b'z' * record['size'])
    client.on_source_read = changed
    with pytest.raises(inputs.InputPreparationError):
        prepare(client, record, root, resume_state=state)
    assert len(client.uploads) == 1


def test_lost_refreshed_upload_ack_remains_uncertain_and_is_never_replayed(stage):
    client, record, root, state = stopped_after_upload(stage)
    client.expired_ids.add('file_synthetic_1')
    client.upload_error = TimeoutError('private')
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root, resume_state=state)
    recovery = caught.value.state
    assert recovery['outcome'] == 'uncertain'
    assert recovery['uncertain_operation']['operation'] == 'files_upload'
    before = len(client.writes)
    client.upload_error = None
    with pytest.raises(inputs.InputPreparationError):
        prepare(client, record, root, resume_state=recovery)
    assert len(client.writes) == before


def test_second_copy_404_does_not_start_a_refresh_loop(stage):
    client, record, root, state = stopped_after_upload(stage)
    client.expired_ids.add('file_synthetic_1')
    client.copy_failures = [HTTPFailure(404), HTTPFailure(404)]
    with pytest.raises(inputs.InputPreparationError) as caught:
        prepare(client, record, root, resume_state=state)
    assert caught.value.state['outcome'] == 'failed'
    assert len(client.uploads) == 2 and len(client.copy_attempts) == 2
    assert client.source_reads == ['file_synthetic_1']
    assert caught.value.state['files'][0]['file_id'] == 'file_synthetic_2'


def test_official_sdk_source_retrieve_path_and_single_refreshed_upload(stage):
    import httpx2
    _, record, root, resume = stopped_after_upload(stage)
    calls, remote = [], []
    def respond(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if request.method == 'GET' and path == '/v1/agents/sessions/sess_test':
            return httpx2.Response(200, json={'id': 'sess_test', 'status': 'idle',
                'environment': {'id': 'env_test', 'type': 'openai_hosted'}})
        if path.endswith('/turns'):
            return httpx2.Response(200, json={'data': [], 'has_more': False})
        if path == '/v1/agents/environments/env_test':
            return httpx2.Response(200, json={'id': 'env_test', 'status': 'connected'})
        if path == '/v1/files/file_synthetic_1':
            assert request.method == 'GET'
            return httpx2.Response(404, json={'error': {'message': 'synthetic missing source', 'type': 'invalid_request_error'}})
        if path == '/v1/files':
            assert request.method == 'POST' and b'user_data' in request.content
            return httpx2.Response(200, json={'id': 'file_refreshed'})
        if path == '/v1/agents/environments/env_test/files':
            if request.method == 'GET':
                return httpx2.Response(200, json={'data': remote, 'has_more': False})
            body = json.loads(request.content)
            if body['file_id'] == 'file_synthetic_1':
                return httpx2.Response(404, json={'error': {'message': 'synthetic missing source', 'type': 'invalid_request_error'}})
            assert body['file_id'] == 'file_refreshed'
            copied = {'environment_id': 'env_test', 'path': record['remote_path'], 'size_bytes': record['size']}
            remote.append(copied)
            return httpx2.Response(200, json=copied)
        raise AssertionError(f'Unexpected request: {request.method} {path}')
    client = create_client({'api_key': 'synthetic-offline-key', 'base_url': 'https://example.invalid/v1'},
                           http_client=httpx2.Client(transport=httpx2.MockTransport(respond)))
    try:
        result = prepare(client, record, root, resume_state=resume)
    finally:
        client.close()
    assert result['outcome'] == 'ready'
    assert calls.count(('GET', '/v1/files/file_synthetic_1')) == 1
    assert calls.count(('POST', '/v1/files')) == 1
    assert calls.count(('POST', '/v1/agents/environments/env_test/files')) == 2
    assert all('/events' not in path for _, path in calls)
