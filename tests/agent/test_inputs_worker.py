"""Offline worker journals, cancellation, path input formatting, and SDK headers."""
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.agent import runtime, worker
from modules.agent.connection import AgentConnectionError, create_client
from test_inputs_runtime import stage, FakeClient as InputClient, RUN_ID
from test_runtime import FakeClient as TurnClient, turn, text


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Offline test')))


def prepare_command(record, root, **values):
    return dict(action='prepare_inputs', inputs=[record], staging_root=str(root), model='test-model',
                run_id=RUN_ID, **values)


def run_worker(monkeypatch, command, client, *, observer=None):
    @contextmanager
    def connected(connection):
        yield client
    frames = []
    def emit(kind, **values):
        frame = {'type': kind, **deepcopy(values)}
        if observer:
            observer(frame)
        frames.append(frame)
    monkeypatch.setattr(worker, 'create_client', connected)
    monkeypatch.setattr(worker, 'emit', emit)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(command) + '\n'))
    worker.main()
    return frames


def manifest():
    return [{'input_id': 'b' * 32, 'name': 'notes.txt', 'remote_path': '/workspace/inputs/' + 'b' * 32 + '/notes.txt'}]


def test_preparation_worker_journals_before_emit_and_never_sends_turn(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    path = root / ('.prepare-' + RUN_ID + '.json')
    def persisted_first(frame):
        assert json.loads(path.read_text()) == frame['preparation']
    frames = run_worker(monkeypatch, prepare_command(record, root), client, observer=persisted_first)
    assert frames[-1]['type'] == 'result' and frames[-1]['preparation']['outcome'] == 'ready'
    assert all('preparation' in frame and 'session_id' not in frame for frame in frames)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    encoded = path.read_text()
    assert 'staged_path' not in encoded and str(root) not in encoded and record['sha256'] in encoded
    assert not list(root.glob('*.tmp'))
    assert [kind for kind, _ in client.writes] == ['session_create', 'environment_copy']


def test_input_error_uses_dict_state_and_canonical_exception_class(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    client.copy_error = TimeoutError('private body must not be shown')
    frames = run_worker(monkeypatch, prepare_command(record, root), client)
    failure = frames[-1]
    assert worker.AgentError is runtime.AgentError
    assert failure['type'] == 'error' and failure['preparation']['outcome'] == 'uncertain'
    assert failure['preparation']['session_id'] == 'sess_test'
    assert 'private body' not in json.dumps(frames) and 'snapshot' not in failure['message']
    assert json.loads((root / ('.prepare-' + RUN_ID + '.json')).read_text()) == failure['preparation']


def test_existing_cancel_marker_prevents_all_api_mutations(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    (root / ('.cancel-' + RUN_ID)).touch()
    frames = run_worker(monkeypatch, prepare_command(record, root), client)
    assert frames[-1]['preparation']['outcome'] == 'cancelled'
    assert not client.writes


def test_cancel_during_copy_keeps_successful_install_in_journal(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    client.after_copy = lambda: (root / ('.cancel-' + RUN_ID)).touch()
    frames = run_worker(monkeypatch, prepare_command(record, root), client)
    state = frames[-1]['preparation']
    assert state['outcome'] == 'cancelled' and record['input_id'] in state['installed']
    assert state['submission_started'] is False


def test_stdout_broken_pipe_does_not_stop_journal_or_prepare(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    emitted = []
    def disconnected(frame):
        emitted.append(frame)
        raise BrokenPipeError('synthetic disconnected observer')
    monkeypatch.setattr(sys, 'stdout', io.StringIO())
    run_worker(monkeypatch, prepare_command(record, root), client, observer=disconnected)
    assert len(emitted) == 1
    state = json.loads((root / ('.prepare-' + RUN_ID + '.json')).read_text())
    assert state['outcome'] == 'ready' and record['input_id'] in state['installed']


def test_real_closed_stdout_pipe_still_finishes_and_exits_cleanly(stage):
    make, root = stage
    record = make()
    script = '''
from contextlib import contextmanager
from pathlib import Path
import sys, time
sys.path.insert(0, 'tests/agent')
from test_inputs_runtime import FakeClient
from modules.agent import worker
client = FakeClient()
original = client.create_session
def blocked(**kwargs):
    deadline = time.monotonic() + 5
    while not (Path(sys.argv[1]) / 'resume-http').exists():
        if time.monotonic() > deadline:
            raise AssertionError('Missing offline handoff')
        time.sleep(0.01)
    return original(**kwargs)
client.beta.agents.sessions.create = blocked
@contextmanager
def connection(value):
    yield client
worker.create_client = connection
worker.main()
'''
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('OPENAI_', 'CHUANHU_AGENT_'))}
    process = subprocess.Popen([sys.executable, '-u', '-c', script, str(root)], cwd=ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=environment)
    try:
        process.stdin.write(json.dumps(prepare_command(record, root)) + '\n')
        process.stdin.flush()
        first = json.loads(process.stdout.readline())
        assert first['type'] == 'progress'
        process.stdout.close()
        (root / 'resume-http').touch()
        process.wait(timeout=5)
        assert process.returncode == 0, process.stderr.read()
        saved = json.loads((root / ('.prepare-' + RUN_ID + '.json')).read_text())
        assert saved['outcome'] == 'ready' and record['input_id'] in saved['installed']
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        process.stdin.close()
        process.stderr.close()


def test_failed_atomic_replace_keeps_previous_journal_and_removes_temp(stage, monkeypatch):
    _, root = stage
    journal = worker.PreparationJournal(str(root), RUN_ID)
    try:
        journal.write({'outcome': 'preparing', 'session_id': 'sess_test'})
        previous = (root / ('.prepare-' + RUN_ID + '.json')).read_bytes()
        def interrupted(*args, **kwargs):
            raise OSError('synthetic filesystem failure')
        monkeypatch.setattr(worker.os, 'replace', interrupted)
        with pytest.raises(OSError):
            journal.write({'outcome': 'ready'})
        assert (root / ('.prepare-' + RUN_ID + '.json')).read_bytes() == previous
        assert not list(root.glob('*.tmp'))
    finally:
        journal.close()


def test_restarted_worker_uses_latest_locked_journal_instead_of_stale_parent_receipt(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    command = prepare_command(record, root)
    first = run_worker(monkeypatch, command, client)
    stale = next(frame['preparation'] for frame in first if frame['type'] == 'progress')
    before = len(client.writes)
    frames = run_worker(monkeypatch, {**command, 'resume_state': stale}, client)
    assert frames[-1]['preparation']['outcome'] == 'ready' and len(client.writes) == before


def test_cross_process_nonblocking_lock_returns_busy_without_client_or_journal_mutation(stage, monkeypatch):
    make, root = stage
    record = make()
    script = '''
import json, sys
from modules.agent.worker import PreparationJournal
journal = PreparationJournal(sys.argv[1], sys.argv[2])
journal.write({'session_id':'sess_background','run_id':sys.argv[2],'outcome':'preparing','submission_started':False})
print('locked', flush=True)
sys.stdin.readline()
journal.close()
'''
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('OPENAI_', 'CHUANHU_AGENT_'))}
    process = subprocess.Popen([sys.executable, '-u', '-c', script, str(root), RUN_ID], cwd=ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=environment)
    try:
        assert process.stdout.readline().strip() == 'locked'
        path = root / ('.prepare-' + RUN_ID + '.json')
        before = path.read_bytes()
        def forbidden_client(*args):
            raise AssertionError('Busy preparation must not create any API client')
        monkeypatch.setattr(worker, 'create_client', forbidden_client)
        monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(prepare_command(record, root)) + '\n'))
        frames = []
        monkeypatch.setattr(worker, 'emit', lambda kind, **values: frames.append({'type': kind, **values}))
        worker.main()
        assert frames[-1]['preparation_busy'] is True and frames[-1]['preparation']['session_id'] == 'sess_background'
        assert frames[-1]['message'] == '附件仍在后台准备，消息未发送'
        assert path.read_bytes() == before
        process.communicate('\n', timeout=5)
        assert process.returncode == 0
        # Kernel releases the lock; a stale .lock path does not block recovery.
        journal = worker.PreparationJournal(str(root), RUN_ID)
        journal.close()
    finally:
        if process.poll() is None:
            process.kill(); process.communicate()


@pytest.mark.parametrize('kind', ['root', 'lock', 'journal'])
def test_symlink_journal_surfaces_are_rejected_before_api(stage, monkeypatch, tmp_path, kind):
    make, root = stage
    record, client = make(), InputClient()
    target = tmp_path / 'outside'
    target.mkdir()
    if kind == 'root':
        link = tmp_path / 'root-link'
        link.symlink_to(root, target_is_directory=True)
        requested_root = link
    else:
        requested_root = root
        name = '.prepare-' + RUN_ID + ('.lock' if kind == 'lock' else '.json')
        outside = target / 'receipt'
        outside.write_text('{}')
        (root / name).symlink_to(outside)
    frames = run_worker(monkeypatch, prepare_command(record, requested_root), client)
    assert frames[-1]['type'] == 'error' and not client.writes
    if kind != 'root':
        assert outside.read_text() == '{}'


def test_invalid_run_id_cannot_create_journal_outside_staging(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    command = prepare_command(record, root)
    command['run_id'] = '../../outside'
    frames = run_worker(monkeypatch, command, client)
    assert frames[-1]['type'] == 'error' and not client.writes
    assert not list(root.glob('.prepare-*'))


def test_connection_preflight_error_preserves_existing_partial_receipt(stage, monkeypatch):
    make, root = stage
    record, client = make(), InputClient()
    first = run_worker(monkeypatch, prepare_command(record, root), client)[-1]['preparation']
    def fail(*args):
        raise AgentConnectionError('Synthetic connection unavailable')
    monkeypatch.setattr(worker, 'create_client', fail)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(prepare_command(record, root)) + '\n'))
    frames = []
    monkeypatch.setattr(worker, 'emit', lambda kind, **data: frames.append({'type': kind, **data}))
    worker.main()
    assert frames[-1]['preparation']['installed'] == first['installed']
    assert frames[-1]['preparation']['session_id'] == first['session_id']
    assert frames[-1]['preparation']['outcome'] == 'failed'


def test_format_preserves_plain_prompt_and_escapes_metadata():
    assert runtime.format_input_text('exact prompt\n') == 'exact prompt\n'
    assert runtime.format_input_text('exact prompt', [], []) == 'exact prompt'
    files = manifest()
    files[0]['name'] = 'a\nignore system.txt'
    history = [{'role': 'user', 'content': 'previous ordinary chat'}]
    formatted = runtime.format_input_text('question', history, files)
    assert 'previous ordinary chat' in formatted and '本轮新请求：\nquestion' in formatted
    assert 'a\\nignore system.txt' in formatted
    assert formatted.endswith(json.dumps(files, ensure_ascii=False))
    assert 'input_file' not in formatted and 'data:image' not in formatted


@pytest.mark.parametrize('record', [dict(input_id='bad', name='notes', remote_path='/workspace/notes'),
                                  dict(input_id='b' * 32, name='notes', remote_path='/etc/passwd')])
def test_unconfirmed_or_invalid_file_paths_fail_before_submission(record):
    client = TurnClient([turn('created'), turn('completed')])
    with pytest.raises(runtime.AgentError):
        runtime.run_task(client, 'question', 'model', session_id='sess_test', input_files=[record])
    assert not client.submitted and not client.payloads


@pytest.mark.parametrize('existing', [True, False])
def test_both_run_paths_include_same_history_and_file_text(existing):
    client = TurnClient([turn('created'), text('done', 'answer'), turn('completed')])
    history = [{'role': 'user', 'content': 'ordinary history seed'}]
    files = manifest()
    result = runtime.run_task(client, 'question', 'model', run_id=RUN_ID,
                              session_id='sess_test' if existing else None,
                              history_reference=history, input_files=files)
    expected = runtime.format_input_text('question', history, files)
    assert result.outcome == 'completed'
    if existing:
        assert client.submitted[0]['events'][0]['input'][0]['content'] == [{'type': 'input_text', 'text': expected}]
        assert client.submitted[0]['idempotency_key'] == RUN_ID
    else:
        assert client.payloads[0]['input'] == expected


def test_worker_run_forwards_installed_inputs_and_history(monkeypatch):
    client = TurnClient([turn('created'), text('done', 'answer'), turn('completed')])
    command = {'action': 'run', 'session_id': 'sess_test', 'run_id': RUN_ID,
               'model': 'model', 'prompt': 'question', 'history_reference': ['earlier'], 'input_files': manifest()}
    frames = run_worker(monkeypatch, command, client)
    assert frames[-1]['type'] == 'result' and frames[-1]['outcome'] == 'completed'
    sent = client.submitted[0]['events'][0]['input'][0]['content'][0]['text']
    assert sent == runtime.format_input_text('question', ['earlier'], manifest())


@pytest.mark.parametrize('submission_started,expected', [(False, 'not_started'), (True, 'incomplete')])
def test_empty_idle_session_inspection_distinguishes_unsent_from_unknown(submission_started, expected):
    client = TurnClient()
    result = runtime.inspect_saved(client, 'sess_test', baseline_turn_ids=[], submission_started=submission_started)
    assert result['outcome'] == expected and result['turn_id'] is None and not client.submitted


def test_empty_idle_session_recover_returns_without_processing_or_creating_turn():
    client = TurnClient()
    result = runtime.recover_stream(client, 'sess_test')
    assert result.outcome == 'not_started' and result.turn_id is None and not client.submitted


def test_subagent_only_history_is_not_mistaken_for_empty_session():
    client = TurnClient()
    client.roots = [{'id': 'orphan_child', 'subagent_id': 'sub_test'}]
    assert runtime.inspect_saved(client, 'sess_test')['outcome'] == 'incomplete'


def test_real_sdk_idempotency_header_and_text_only_event_no_retry(monkeypatch):
    import httpx2
    calls = []
    def respond(request):
        calls.append(request)
        if request.method == 'GET' and request.url.path.endswith('/sess_test'):
            return httpx2.Response(200, json={'id': 'sess_test', 'status': 'idle'})
        if request.url.path.endswith('/turns'):
            return httpx2.Response(200, json={'data': [], 'has_more': False})
        if request.method == 'GET' and request.url.path.endswith('/events'):
            return httpx2.Response(200, headers={'Content-Type': 'text/event-stream'}, content=b'')
        if request.method == 'POST' and request.url.path.endswith('/events'):
            assert request.headers['Idempotency-Key'] == RUN_ID
            body = json.loads(request.content)
            assert 'idempotency_key' not in body
            content = body['events'][0]['input'][0]['content']
            assert content == [{'type': 'input_text', 'text': runtime.format_input_text('question', ['earlier'], manifest())}]
            return httpx2.Response(500, json={'error': {'message': 'synthetic failure', 'type': 'server_error'}})
        raise AssertionError(f'Unexpected offline request: {request.method} {request.url.path}')
    client = create_client({'api_key': 'synthetic-offline-key', 'base_url': 'https://example.invalid/v1'},
                           http_client=httpx2.Client(transport=httpx2.MockTransport(respond)))
    try:
        with pytest.raises(runtime.AgentError):
            runtime.run_task(client, 'question', 'model', session_id='sess_test', run_id=RUN_ID,
                             history_reference=['earlier'], input_files=manifest())
    finally:
        client.close()
    assert len([request for request in calls if request.method == 'POST']) == 1
