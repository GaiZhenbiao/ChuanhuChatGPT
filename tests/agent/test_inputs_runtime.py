"""Strictly offline Agent attachment preparation and uncertainty regressions."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.agent.input_files import AgentInputFiles
from modules.agent import inputs


RUN_ID = 'a' * 32


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Offline test')))


@pytest.fixture
def stage(tmp_path):
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    store = AgentInputFiles((uploads,), staging_parent=tmp_path)

    def prepare(content=b'synthetic attachment', name='notes.txt', *, folder='one'):
        directory = uploads / folder
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.write_bytes(content)
        return store.set_pending([path])[0].to_dict()

    yield prepare, store.staging_root
    store.close()


class Rejected(Exception):
    status_code = 400


class FakeClient:
    def __init__(self):
        self.session_id, self.environment_id = 'sess_test', 'env_test'
        self.session_status, self.environment_type = 'idle', 'openai_hosted'
        self.environment_statuses, self.turns = ['connected'], []
        self.sessions, self.remote, self.uploads, self.writes, self.reads = [], [], {}, [], []
        self.options, self.create_error, self.copy_error, self.upload_error = [], None, None, None
        self.after_copy = self.after_upload = None
        self.environment_reads = 0
        self.beta = SimpleNamespace(agents=SimpleNamespace(
            sessions=SimpleNamespace(create=self.create_session, retrieve=self.retrieve_session,
                list=self.list_sessions, turns=SimpleNamespace(list=self.list_turns),
                events=SimpleNamespace(create=self.forbidden_turn, stream=self.forbidden_turn)),
            environments=SimpleNamespace(retrieve=self.retrieve_environment,
                files=SimpleNamespace(create=self.copy_file, list=self.list_files))))
        self.files = SimpleNamespace(create=self.upload_file, delete=self.forbidden_delete)

    def with_options(self, **kwargs):
        self.options.append(kwargs)
        assert kwargs == {'max_retries': 0}
        return self

    def _write(self, operation, args):
        assert len(self.options) == len(self.writes) + 1
        self.writes.append((operation, deepcopy(args)))

    def forbidden_turn(self, *args, **kwargs):
        raise AssertionError('Preparing attachments must never send or open a turn')

    def forbidden_delete(self, *args, **kwargs):
        raise AssertionError('Uploads are retained until expiration; no deletion')

    def retrieve_session(self, identifier):
        self.reads.append(('session', identifier))
        return {'id': identifier, 'status': self.session_status,
                'environment': {'id': self.environment_id, 'type': self.environment_type}}

    def create_session(self, **kwargs):
        self._write('session_create', kwargs)
        if self.create_error:
            raise self.create_error
        result = self.retrieve_session(self.session_id)
        self.sessions.append({**result, 'metadata': kwargs['metadata']})
        return result

    def list_sessions(self, **kwargs):
        return deepcopy(self.sessions)

    def list_turns(self, identifier, **kwargs):
        self.reads.append(('turns', identifier))
        return deepcopy(self.turns)

    def retrieve_environment(self, identifier):
        self.environment_reads += 1
        status = self.environment_statuses[min(self.environment_reads - 1, len(self.environment_statuses) - 1)]
        return {'id': identifier, 'status': status}

    def list_files(self, identifier, **kwargs):
        self.reads.append(('files', kwargs))
        return deepcopy(self.remote)

    def upload_file(self, **kwargs):
        self._write('files_upload', kwargs)
        if self.upload_error:
            raise self.upload_error
        identifier = 'file_synthetic'
        self.uploads[identifier] = kwargs['file'][1]
        if self.after_upload:
            self.after_upload()
        return {'id': identifier}

    def copy_file(self, identifier, **kwargs):
        self._write('environment_copy', kwargs)
        if self.copy_error:
            raise self.copy_error
        contents = base64.b64decode(kwargs['data'], validate=True) if kwargs['type'] == 'inline' else self.uploads[kwargs['file_id']]
        result = {'environment_id': identifier, 'path': kwargs['path'], 'size_bytes': len(contents)}
        self.remote.append(result)
        if self.after_copy:
            self.after_copy()
        return result


def run(client, record, root, **kwargs):
    return inputs.prepare_inputs(client, [record], 'test-model', staging_root=root, run_id=RUN_ID,
                                 poll_interval=0, **kwargs)


def test_new_session_omits_input_reports_id_early_and_installs_standard_base64(stage):
    make, root = stage
    record = make(b'\x00\xff\xfa\r\n', name='image.png')
    client, progress = FakeClient(), []
    result = run(client, record, root, on_progress=progress.append, reasoning='high', instructions='test')
    creation, copy = client.writes
    assert creation[0] == 'session_create'
    assert creation[1]['stream'] is False and 'input' not in creation[1]
    assert creation[1]['metadata'] == {'chuanhu_run_id': RUN_ID}
    assert creation[1]['agent']['reasoning'] == {'effort': 'high'}
    assert copy[1] == {'type': 'inline', 'data': base64.b64encode(b'\x00\xff\xfa\r\n').decode(), 'path': record['remote_path']}
    assert result['outcome'] == 'ready' and result['submission_started'] is False
    assert result['environment_id'] == 'env_test' and result['baseline_turn_ids'] == []
    early = next(item for item in progress if item['session_id'])
    assert early['environment_id'] is None
    assert {'prepared', 'uploading', 'ready'} <= {item['files'][0]['status'] for item in progress}
    encoded = json.dumps(result)
    assert 'staged_path' not in encoded and str(root) not in encoded and 'data' not in result['files'][0]


def test_existing_session_keeps_prior_turns_and_never_creates_or_sends(stage):
    make, root = stage
    client = FakeClient()
    client.turns = [{'id': 'turn_previous', 'status': 'completed'}]
    result = run(client, make(), root, session_id='sess_existing')
    assert result['session_id'] == 'sess_existing'
    assert result['baseline_turn_ids'] == ['turn_previous']
    assert [kind for kind, _ in client.writes] == ['environment_copy']


def test_same_names_have_distinct_stable_paths(stage):
    make, root = stage
    records = [make(b'one', folder='one'), make(b'two', folder='two')]
    client = FakeClient()
    result = inputs.prepare_inputs(client, records, 'test-model', staging_root=root, run_id=RUN_ID)
    assert len({entry['remote_path'] for entry in result['files']}) == 2
    assert len(result['installed']) == 2


def test_confirmed_installation_reused_only_in_matching_environment(stage):
    make, root = stage
    record, client = make(), FakeClient()
    first = run(client, record, root)
    before = len(client.writes)
    again = run(client, record, root, session_id=first['session_id'], installed=first['installed'])
    assert len(client.writes) == before and again['outcome'] == 'ready'
    client.environment_id = 'env_other'
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id=first['session_id'], installed=first['installed'])
    assert caught.value.state['outcome'] == 'uncertain' and len(client.writes) == before


@pytest.mark.parametrize('same_size', [True, False])
def test_existing_unknown_path_never_proves_content_or_overwrites(stage, same_size):
    make, root = stage
    record, client = make(), FakeClient()
    client.remote = [{'path': record['remote_path'], 'size_bytes': record['size'] if same_size else 999, 'environment_id': 'env_test'}]
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id='sess_test')
    state = caught.value.state
    assert state['outcome'] == 'uncertain' and not client.writes
    assert state['files'][0]['remote_observation'] == ('path_and_size_match' if same_size else 'path_conflict')


@pytest.mark.parametrize('size,method', [(inputs.INLINE_LIMIT, 'inline'), (inputs.INLINE_LIMIT + 1, 'file_id'),
                                       (inputs.FILE_IMPORT_LIMIT, 'file_id')])
def test_official_size_boundaries_and_expiring_user_data(stage, size, method):
    make, root = stage
    record, client = make(b'x' * size), FakeClient()
    result = run(client, record, root, session_id='sess_test')
    assert client.writes[-1][1]['type'] == method
    assert result['files'][0]['status'] == 'ready'
    if method == 'file_id':
        assert client.writes[0][1]['purpose'] == 'user_data'
        assert client.writes[0][1]['expires_after'] == {'anchor': 'created_at', 'seconds': 3600}
        assert result['installed'][record['input_id']]['file_id'] == 'file_synthetic'


def test_oversize_snapshot_rejected_before_any_api_write(stage):
    make, root = stage
    record, client = make(), FakeClient()
    record['size'] = inputs.FILE_IMPORT_LIMIT + 1
    with pytest.raises(inputs.InputPreparationError, match='50 MiB'):
        run(client, record, root)
    assert not client.writes


def test_snapshot_integrity_and_root_checked_before_api_access(stage, tmp_path):
    make, root = stage
    record, client = make(), FakeClient()
    with pytest.raises(inputs.InputPreparationError):
        run(client, record, tmp_path)
    Path(record['staged_path']).chmod(0o600)
    Path(record['staged_path']).write_bytes(b'changed snapshot')
    with pytest.raises(inputs.InputPreparationError):
        run(client, record, root)
    assert not client.writes and not client.reads


@pytest.mark.parametrize('existing', [True, False])
def test_none_environment_is_explicitly_rejected(stage, existing):
    make, root = stage
    client = FakeClient()
    if existing:
        client.environment_type = 'none'
        kwargs = {'session_id': 'sess_test'}
    else:
        kwargs = {'tool_settings': {'code_execution': False, 'computer_use': False, 'programmatic_tool_calling': False}}
    with pytest.raises(inputs.InputPreparationError, match='环境'):
        run(client, make(), root, **kwargs)
    assert not client.writes


def test_pending_environment_has_no_elapsed_task_cap_and_is_cancellable(stage, monkeypatch):
    make, root = stage
    client = FakeClient()
    client.environment_statuses = ['pending'] * 370 + ['connected']
    waits = []
    monkeypatch.setattr(inputs.time, 'sleep', waits.append)
    result = inputs.prepare_inputs(client, [make()], 'test-model', staging_root=root, run_id=RUN_ID, poll_interval=0.25)
    assert sum(waits) > 90 and result['outcome'] == 'ready'


@pytest.mark.parametrize('moment', ['before_session', 'pending', 'before_copy', 'after_copy'])
def test_stop_never_submits_turn_and_preserves_known_side_effects(stage, moment):
    make, root = stage
    record, client = make(), FakeClient()
    cancelled = [moment == 'before_session']
    if moment == 'pending':
        client.environment_statuses = ['pending']
    if moment == 'after_copy':
        client.after_copy = lambda: cancelled.__setitem__(0, True)

    def progress(state):
        if moment == 'pending' and state.get('environment_status') == 'pending':
            cancelled[0] = True
        if moment == 'before_copy' and (state['uncertain_operation'] or {}).get('operation') == 'environment_copy':
            cancelled[0] = True

    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, should_cancel=lambda: cancelled[0], on_progress=progress)
    state = caught.value.state
    assert state['outcome'] == 'cancelled' and state['submission_started'] is False
    assert len(client.writes) == (0 if moment == 'before_session' else 2 if moment == 'after_copy' else 1)
    if moment == 'after_copy':
        assert record['input_id'] in state['installed']
    if moment == 'before_copy':
        assert state['uncertain_operation'] is None


def test_lost_session_create_ack_recovers_by_metadata_without_replay(stage):
    make, root = stage
    record, client = make(), FakeClient()
    client.create_error = TimeoutError('SECRET and raw response must never leak')
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root)
    state = caught.value.state
    assert state['outcome'] == 'uncertain' and 'SECRET' not in json.dumps(state)
    with pytest.raises(inputs.InputPreparationError):
        run(client, record, root, resume_state=state)
    assert len(client.writes) == 1
    client.sessions = [{'id': 'sess_test', 'metadata': {'chuanhu_run_id': RUN_ID}}]
    client.create_error = None
    result = run(client, record, root, resume_state=state)
    assert result['outcome'] == 'ready'
    assert [kind for kind, _ in client.writes].count('session_create') == 1


def test_lost_files_upload_ack_blocks_retry_even_without_remote_path(stage):
    make, root = stage
    record, client = make(b'x' * (inputs.INLINE_LIMIT + 1)), FakeClient()
    client.upload_error = TimeoutError('private content')
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id='sess_test')
    state = caught.value.state
    assert state['uncertain_operation']['operation'] == 'files_upload'
    client.upload_error = None
    with pytest.raises(inputs.InputPreparationError) as resumed:
        run(client, record, root, session_id='sess_test', resume_state=state)
    assert resumed.value.state['outcome'] == 'uncertain'
    assert [kind for kind, _ in client.writes] == ['files_upload']


def test_known_upload_id_survives_rejected_copy_and_is_not_reuploaded(stage):
    make, root = stage
    record, client = make(b'x' * (inputs.INLINE_LIMIT + 1)), FakeClient()
    client.copy_error = Rejected('raw response')
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id='sess_test')
    state = caught.value.state
    assert state['files'][0]['file_id'] == 'file_synthetic'
    assert state['outcome'] == 'failed'
    client.copy_error = None
    result = run(client, record, root, session_id='sess_test', resume_state=state)
    assert result['outcome'] == 'ready'
    assert [kind for kind, _ in client.writes] == ['files_upload', 'environment_copy', 'environment_copy']


def test_unknown_copy_ack_retains_confirmed_earlier_files_and_does_not_replay(stage):
    make, root = stage
    records, client = [make(b'first'), make(b'second', folder='two')], FakeClient()
    client.after_copy = lambda: setattr(client, 'copy_error', TimeoutError('lost ack'))
    with pytest.raises(inputs.InputPreparationError) as caught:
        inputs.prepare_inputs(client, records, 'test-model', staging_root=root, run_id=RUN_ID)
    state = caught.value.state
    assert records[0]['input_id'] in state['installed'] and records[1]['input_id'] not in state['installed']
    client.copy_error = None
    with pytest.raises(inputs.InputPreparationError):
        inputs.prepare_inputs(client, records, 'test-model', staging_root=root, run_id=RUN_ID,
                              session_id='sess_test', resume_state=state)
    assert [kind for kind, _ in client.writes].count('environment_copy') == 2


def test_new_turn_during_prepare_is_detected_with_partial_install_preserved(stage):
    make, root = stage
    record, client = make(), FakeClient()
    client.after_copy = lambda: client.turns.append({'id': 'turn_external'})
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id='sess_test')
    assert caught.value.state['outcome'] == 'uncertain'
    assert record['input_id'] in caught.value.state['installed']


def test_resuming_old_session_preserves_baseline_instead_of_accepting_new_turn(stage):
    make, root = stage
    record, client = make(), FakeClient()
    first = run(client, record, root, session_id='sess_test')
    client.turns.append({'id': 'turn_external'})
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id='sess_test', resume_state=first)
    assert caught.value.state['baseline_turn_ids'] == [] and len(client.writes) == 1


def test_progress_receipts_are_independent_copies(stage):
    make, root = stage
    client = FakeClient()
    def corrupt(state):
        state['session_id'] = 'corrupted'
        state['files'].clear()
    result = run(client, make(), root, on_progress=corrupt)
    assert result['session_id'] == 'sess_test' and result['files'][0]['status'] == 'ready'


def test_cancel_before_session_http_can_resume_without_uncertain_creation(stage):
    make, root = stage
    record, client = make(), FakeClient()
    cancelled = [False]
    def progress(state):
        if (state['uncertain_operation'] or {}).get('operation') == 'session_create':
            cancelled[0] = True
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, should_cancel=lambda: cancelled[0], on_progress=progress)
    state = caught.value.state
    assert state['outcome'] == 'cancelled' and not state['session_creation_started']
    assert state['uncertain_operation'] is None and not client.writes
    assert run(client, record, root, resume_state=state)['outcome'] == 'ready'


@pytest.mark.parametrize('moment', ['before_upload', 'after_upload'])
def test_cancel_large_file_keeps_upload_receipt_and_resumes_without_duplicates(stage, moment):
    make, root = stage
    record, client = make(b'x' * (inputs.INLINE_LIMIT + 1)), FakeClient()
    cancelled = [False]
    if moment == 'after_upload':
        client.after_upload = lambda: cancelled.__setitem__(0, True)
    def progress(state):
        if moment == 'before_upload' and (state['uncertain_operation'] or {}).get('operation') == 'files_upload':
            cancelled[0] = True
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id='sess_test', should_cancel=lambda: cancelled[0], on_progress=progress)
    state = caught.value.state
    assert state['outcome'] == 'cancelled' and state['uncertain_operation'] is None
    assert len(client.writes) == (1 if moment == 'after_upload' else 0)
    if moment == 'after_upload':
        assert state['files'][0]['file_id'] == 'file_synthetic'
    client.after_upload = None
    assert run(client, record, root, session_id='sess_test', resume_state=state)['outcome'] == 'ready'
    assert [kind for kind, _ in client.writes] == ['files_upload', 'environment_copy']


def test_copy_collision_400_rechecks_remote_and_does_not_retry(stage):
    make, root = stage
    record, client = make(), FakeClient()
    def competing_write(identifier, **kwargs):
        client._write('environment_copy', kwargs)
        client.remote.append({'environment_id': identifier, 'path': record['remote_path'], 'size_bytes': record['size']})
        raise Rejected('path already exists')
    client.beta.agents.environments.files.create = competing_write
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root, session_id='sess_test')
    assert caught.value.state['outcome'] == 'uncertain'
    assert caught.value.state['files'][0]['remote_observation'] == 'path_and_size_match'
    assert len(client.writes) == 1


@pytest.mark.parametrize('status', ['disconnected', 'expired', 'failed'])
def test_unavailable_environment_never_writes_file(stage, status):
    make, root = stage
    client = FakeClient()
    client.environment_statuses = [status]
    with pytest.raises(inputs.InputPreparationError):
        run(client, make(), root, session_id='sess_test')
    assert not client.writes


def test_metadata_recovery_refuses_existing_turns_and_duplicate_matches(stage):
    make, root = stage
    record, client = make(), FakeClient()
    client.sessions = [{'id': 'sess_test', 'metadata': {'chuanhu_run_id': RUN_ID}}]
    client.turns = [{'id': 'unexpected_turn'}]
    with pytest.raises(inputs.InputPreparationError) as caught:
        run(client, record, root)
    assert caught.value.state['outcome'] == 'uncertain' and not client.writes
    client.sessions.append({'id': 'sess_other', 'metadata': {'chuanhu_run_id': RUN_ID}})
    with pytest.raises(inputs.InputPreparationError):
        run(client, record, root)
    assert not client.writes


@pytest.mark.parametrize('failure_at', ['session_create', 'files_upload', 'environment_copy'])
def test_real_sdk_mock_transport_serialization_and_no_post_retries(stage, failure_at):
    import httpx2
    from modules.agent.connection import create_client
    make, root = stage
    content = b'x' * (inputs.INLINE_LIMIT + 1) if failure_at == 'files_upload' else b'synthetic wire bytes'
    record, requests = make(content), []
    remote = []

    def respond(request):
        requests.append(request)
        path = request.url.path
        if request.method == 'POST' and path == '/v1/agents/sessions':
            body = json.loads(request.content)
            assert 'input' not in body and body['stream'] is False
            if failure_at == 'session_create':
                return httpx2.Response(500, json={'error': {'message': 'synthetic failure', 'type': 'server_error'}})
            return httpx2.Response(200, json={'id': 'sess_sdk', 'status': 'idle', 'environment': {'id': 'env_sdk', 'type': 'openai_hosted'}})
        if request.method == 'GET' and path == '/v1/agents/sessions':
            return httpx2.Response(200, json={'data': [], 'has_more': False})
        if path == '/v1/agents/sessions/sess_sdk':
            return httpx2.Response(200, json={'id': 'sess_sdk', 'status': 'idle', 'environment': {'id': 'env_sdk', 'type': 'openai_hosted'}})
        if path.endswith('/turns'):
            return httpx2.Response(200, json={'data': [], 'has_more': False})
        if path == '/v1/agents/environments/env_sdk':
            return httpx2.Response(200, json={'id': 'env_sdk', 'status': 'connected'})
        if path == '/v1/files' and request.method == 'POST':
            assert failure_at == 'files_upload'
            body = request.content
            assert b'user_data' in body and b'created_at' in body and b'3600' in body
            return httpx2.Response(500, json={'error': {'message': 'synthetic failure', 'type': 'server_error'}})
        if path == '/v1/agents/environments/env_sdk/files':
            if request.method == 'GET':
                return httpx2.Response(200, json={'data': remote, 'has_more': False})
            body = json.loads(request.content)
            assert body == {'type': 'inline', 'path': record['remote_path'], 'data': base64.b64encode(b'synthetic wire bytes').decode()}
            return httpx2.Response(500, json={'error': {'message': 'synthetic failure', 'type': 'server_error'}})
        raise AssertionError(f'Unexpected request: {request.method} {path}')

    client = create_client({'api_key': 'synthetic-offline-key', 'base_url': 'https://example.invalid/v1'},
                           http_client=httpx2.Client(transport=httpx2.MockTransport(respond)))
    try:
        with pytest.raises(inputs.InputPreparationError) as caught:
            run(client, record, root)
    finally:
        client.close()
    assert caught.value.state['outcome'] == 'uncertain'
    posts = [request for request in requests if request.method == 'POST']
    assert len(posts) == (1 if failure_at == 'session_create' else 2)
    assert all('/events' not in request.url.path for request in requests)


def test_reattach_after_agent_edits_same_length_input_installs_original_again(tmp_path):
    upload = tmp_path / 'uploads'
    upload.mkdir()
    source = upload / 'notes.txt'
    source.write_bytes(b'ORIGINAL')
    store = AgentInputFiles((upload,), staging_parent=tmp_path)
    client = FakeClient()
    contents = {}
    copy = client.copy_file
    def copy_content(identifier, **kwargs):
        result = copy(identifier, **kwargs)
        contents[kwargs['path']] = base64.b64decode(kwargs['data'])
        return result
    client.beta.agents.environments.files.create = copy_content
    try:
        first, = store.set_pending([source])
        result = run(client, first, store.staging_root)
        store.mark_submitted([first.input_id])
        client.turns.append({'id': 'turn_previous', 'status': 'completed'})
        contents[first.remote_path] = b'MODIFIED'
        store.clear()
        second, = store.set_pending([source])
        result = run(client, second, store.staging_root, session_id='sess_test', installed=result['installed'])
        assert result['outcome'] == 'ready'
        assert second.remote_path != first.remote_path
        assert contents[second.remote_path] == source.read_bytes()
        assert contents[first.remote_path] == b'MODIFIED'
    finally:
        store.close()
