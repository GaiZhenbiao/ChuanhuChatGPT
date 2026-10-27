import base64
import json
from copy import deepcopy
import pytest

from modules.agent import inputs, runtime
from modules.agent.input_files import AgentInputFiles
from test_inputs_runtime import FakeClient as InputClient
from test_runtime import FakeClient as TurnClient, turn, text, message
from agent_fixtures import env, select, request, send
from test_input_model import submit


class ContentClient(InputClient):
    def __init__(self):
        super().__init__()
        self.remote_contents = {}

    def copy_file(self, identifier, **kwargs):
        result = super().copy_file(identifier, **kwargs)
        self.remote_contents[kwargs['path']] = (base64.b64decode(kwargs['data'])
            if kwargs['type'] == 'inline' else self.uploads[kwargs['file_id']])
        return result


def wired_model(env, tmp_path, monkeypatch):
    model = select(env)
    upload = tmp_path / 'uploads'
    upload.mkdir()
    original = upload / 'notes.txt'
    original.write_bytes(b'ORIGINAL')
    second = upload / 'second.txt'
    second.write_bytes(b'B_ORIGIN')
    model._input_stager = AgentInputFiles((upload,), staging_parent=tmp_path)
    client, commands, file_reads, saved_items = ContentClient(), [], [], []

    def worker(command):
        commands.append(deepcopy(command))
        if command['action'] == 'prepare_inputs':
            frames = []
            result = inputs.prepare_inputs(client, command['inputs'], command['model'],
                staging_root=command['staging_root'], session_id=command['session_id'],
                run_id=command['run_id'], instructions=command['instructions'],
                reasoning=command['reasoning'], tool_settings=command['tool_settings'],
                installed=command['installed'], resume_state=command['resume_state'],
                on_progress=lambda value: frames.append({'type': 'progress', 'preparation': value}),
                poll_interval=0)
            yield from frames
            yield {'type': 'result', 'preparation': result}
        elif command['action'] == 'run':
            index = len(client.turns) + 1
            turn_id = 't' + str(index)
            turn_client = TurnClient([turn('created', turn_id), text('done', 'answer', turn_id, item='a'+str(index)), turn('completed', turn_id)])
            turn_client.roots = deepcopy(client.turns)
            wire = runtime.format_input_text(command['prompt'], command.get('history_reference'), command.get('input_files'))
            saved_items.extend([message('u'+str(index), wire, turn_id, role='user'),
                                message('a'+str(index), 'answer', turn_id)])
            turn_client.saved_items = deepcopy(saved_items)
            file_reads.append({item['name']: client.remote_contents[item['remote_path']]
                for item in command.get('input_files', [])})
            frames = []
            result = runtime.run_task(turn_client, command['prompt'], command['model'],
                session_id=command['session_id'], run_id=command['run_id'],
                instructions=command['instructions'], reasoning=command['reasoning'],
                tool_settings=command['tool_settings'], history_reference=command.get('history_reference'),
                input_files=command.get('input_files'),
                on_progress=lambda value: frames.append({'type': 'progress', **value.snapshot()}))
            assert turn_client.submitted and result.submission_started
            client.turns.append({'id': turn_id, 'status': 'completed'})
            if command['prompt'] == 'mutate all sandbox inputs':
                for path in client.remote_contents:
                    client.remote_contents[path] = b'MODIFIED'
            yield from frames
            yield {'type': 'result', **result.snapshot()}
        elif command['action'] == 'download':
            yield {'type': 'result', 'artifacts': []}
        else:
            raise AssertionError(command)
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    return model, original, second, client, commands, file_reads


def test_original_reattach_content_regression_through_real_model_and_runtime(env, tmp_path, monkeypatch):
    model, original, _, client, commands, reads = wired_model(env, tmp_path, monkeypatch)
    model.stage_input_files([str(original)])
    submit(env, model, 'mutate all sandbox inputs', [str(original)])
    assert reads[-1]['notes.txt'] == b'ORIGINAL'
    original_path = [c for c in commands if c['action'] == 'run'][0]['input_files'][0]['remote_path']
    assert client.remote_contents[original_path] == b'MODIFIED'
    model.stage_input_files([str(original)])
    submit(env, model, 'read original again', [str(original)])
    assert reads[-1]['notes.txt'] == original.read_bytes() == b'ORIGINAL'
    new_path = [c for c in commands if c['action'] == 'run'][-1]['input_files'][0]['remote_path']
    assert new_path != original_path


@pytest.mark.parametrize('with_second_file', [True, False])
def test_prepared_cancelled_file_is_also_fresh_after_different_attachment_turn(env, tmp_path, monkeypatch, with_second_file):
    model, original, second, client, commands, reads = wired_model(env, tmp_path, monkeypatch)
    model.stage_input_files([str(original)])
    # Exercise the preparation executor directly so cancellation is placed at
    # the exact installed-file boundary, independent of UI snapshot coalescing.
    iterator = model.predict('stop before sending', [], files=[str(original)])
    for _ in iterator:
        if model._installed_inputs:
            model.interrupt()
            break
    list(iterator)
    assert not [c for c in commands if c['action'] == 'run']
    assert model._state['outcome'] == 'not_started'
    old_path = next(iter(model._installed_inputs.values()))['remote_path']
    assert client.remote_contents[old_path] == b'ORIGINAL'
    later_files = [str(second)] if with_second_file else []
    model.stage_input_files(later_files)
    submit(env, model, 'mutate all sandbox inputs', later_files)
    assert client.remote_contents[old_path] == b'MODIFIED'
    model.stage_input_files([str(original)])
    submit(env, model, 'read original again', [str(original)])
    assert reads[-1]['notes.txt'] == original.read_bytes() == b'ORIGINAL'


def test_original_expiry_recovery_after_cancel_has_verified_original_bytes(tmp_path):
    class Missing(Exception):
        status_code = 404
    upload = tmp_path / 'uploads'
    upload.mkdir()
    original = upload / 'large.bin'
    original.write_bytes(b'x' * (inputs.INLINE_LIMIT + 1))
    store = AgentInputFiles((upload,), staging_parent=tmp_path)
    record = store.set_pending([original])[0]
    client, cancelled, source_reads = ContentClient(), [False], []
    client.after_upload = lambda: cancelled.__setitem__(0, True)
    def prepare(**kwargs):
        return inputs.prepare_inputs(client, [record], 'model', staging_root=store.staging_root,
            session_id='sess_test', run_id='a' * 32, poll_interval=0, **kwargs)
    with pytest.raises(inputs.InputPreparationError) as initial:
        prepare(should_cancel=lambda: cancelled[0])
    assert initial.value.state['outcome'] == 'cancelled'
    assert initial.value.state['files'][0]['file_id'] == 'file_synthetic'
    client.uploads.clear()
    client.after_upload = None
    def retrieve(identifier):
        source_reads.append(identifier)
        if identifier not in client.uploads:
            raise Missing()
        return {'id': identifier}
    client.files.retrieve = retrieve
    copy = client.copy_file
    def expired_copy(identifier, **kwargs):
        if kwargs.get('file_id') not in client.uploads:
            client._write('environment_copy', kwargs)
            raise Missing()
        return copy(identifier, **kwargs)
    client.beta.agents.environments.files.create = expired_copy
    result = prepare(resume_state=initial.value.state)
    assert result['outcome'] == 'ready'
    assert client.remote_contents[record.remote_path] == original.read_bytes()
    assert [kind for kind, _ in client.writes] == [
        'files_upload', 'environment_copy', 'files_upload', 'environment_copy']
    assert source_reads == ['file_synthetic']
    store.close()


def test_original_wrong_actual_copy_path_is_not_accepted(tmp_path):
    upload = tmp_path / 'uploads'
    upload.mkdir()
    original = upload / 'notes.txt'
    original.write_bytes(b'ORIGINAL')
    store = AgentInputFiles((upload,), staging_parent=tmp_path)
    record = store.set_pending([original])[0]
    client = ContentClient()
    copy = client.copy_file
    def wrong_path(identifier, **kwargs):
        kwargs['path'] = '/workspace/unrelated.txt'
        return copy(identifier, **kwargs)
    client.beta.agents.environments.files.create = wrong_path
    with pytest.raises(inputs.InputPreparationError) as caught:
        inputs.prepare_inputs(client, [record], 'model', staging_root=store.staging_root,
            run_id='a' * 32, poll_interval=0)
    assert record.remote_path not in client.remote_contents
    assert caught.value.state['outcome'] == 'uncertain'
    assert not caught.value.state['installed']
    store.close()


@pytest.mark.parametrize('source', ['switch', 'import'])
def test_history_reference_without_files_keeps_plain_user_bubble_after_restore(env, tmp_path, monkeypatch, source):
    model, _, _, _, commands, _ = wired_model(env, tmp_path, monkeypatch)
    def no_file_worker(command):
        commands.append(deepcopy(command))
        if command['action'] == 'run':
            wire = runtime.format_input_text(command['prompt'], command.get('history_reference'), command.get('input_files'))
            yield dict(type='result', session_id='sess_test', turn_id='t1', outcome='completed',
                       sync_complete=True, items=[message('u1', wire, 't1', role='user'), message('a1', 'answer', 't1')])
        elif command['action'] == 'download':
            yield dict(type='result', artifacts=[])
        else:
            raise AssertionError(command)
    monkeypatch.setattr(env.agents, 'worker_messages', no_file_worker)
    reference = [{'role': 'user', 'content': 'old question'},
                 {'role': 'assistant', 'content': 'old answer'}]
    if source == 'switch':
        ordinary = select(env, name='GPT3.5 Turbo')
        send(env, ordinary, 'old question')
        reference = deepcopy(ordinary.history)
        model = select(env, original=ordinary)
    else:
        imported = env.history_dir / 'imported.json'
        imported.write_text(json.dumps({'system': 'ordinary prompt', 'history': reference, 'chatbot': [['old question', 'old answer']]}))
        imported.with_suffix('.md').write_text('synthetic history')
        model.load_chat_history(imported.name)
    send(env, model, 'new question')
    command = next(c for c in commands if c['action'] == 'run')
    wire = runtime.format_input_text('new question', reference, [])
    assert command['history_reference'] == reference and not command.get('input_files')
    assert wire != 'new question'
    assert model.history[-2]['content'] == 'new question'
    assert model.chatbot[-1][0] == 'new question'
    assert model._project_input_text(wire) == 'new question'
    model.rename_chat_history('history-seed-display.json')
    filename = model.history_file_path
    cloud_items = [message('u1', wire, 't1', role='user'), message('a1', 'answer', 't1')]
    def recover(command):
        if command['action'] == 'recover':
            yield dict(type='result', session_id='sess_test', turn_id='t1', outcome='completed',
                       sync_complete=True, history_authoritative=True, items=cloud_items, required_actions=[])
        elif command['action'] == 'download':
            yield dict(type='result', artifacts=[])
        else:
            raise AssertionError(command)
    monkeypatch.setattr(env.agents, 'worker_messages', recover)
    restored = select(env)
    restored.load_chat_history(filename)
    assert restored.history[-2]['content'] == 'new question'
    assert restored._input_messages == model._input_messages
    list(restored.reconnect())
    assert restored.history[-2]['content'] == 'new question'
    assert restored.chatbot[-1][0] == 'new question'
