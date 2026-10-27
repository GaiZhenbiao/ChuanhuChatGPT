"""JSON-lines worker using the main application's interpreter and configuration."""
import json
import hashlib
from copy import deepcopy
import os
import re
import sys
from pathlib import Path
from threading import Lock
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from modules.agent.connection import AgentConnectionError
from modules.agent.tools import ToolConfigurationError
from modules.agent.inputs import prepare_inputs
from modules.agent.runtime import (AgentError, create_client, run_task, inspect_saved, recover_stream,
                     cancel_session, download_artifacts, find_uncertain_session, update_settings,
                     submit_browser_response, safe_request_error, TERMINAL)


_output_lock = Lock()


def emit(kind, **data):
    with _output_lock:
        print(json.dumps({'type': kind, **data}, ensure_ascii=False), flush=True)


class PreparationBusy(AgentError):
    preparation_busy = True


class PreparationJournal:
    """在服务端拥有的目录中使用跨平台安全句柄保存准备记录。"""
    def __init__(self, staging_root, run_id):
        from modules.agent.secure_io import SecureDirectory
        self.directory, self.lock = None, None
        if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise AgentError('附件准备任务标识无效')
        self.name, self.cancel_name = '.prepare-' + run_id + '.json', '.cancel-' + run_id
        try:
            self.directory = SecureDirectory(staging_root)
            try:
                self.lock = self.directory.lock('.prepare-' + run_id + '.lock')
            except BlockingIOError:
                try:
                    previous = self.read()
                except Exception:
                    previous = None
                raise PreparationBusy('附件仍在后台准备，消息未发送', previous) from None
        except BaseException:
            self.close()
            raise

    def read(self):
        try:
            value = self.directory.read_json(self.name)
        except FileNotFoundError:
            return None
        if not isinstance(value, dict):
            raise AgentError('附件准备记录无效')
        return value

    def write(self, value):
        self.directory.write_json(self.name, value)

    def cancelled(self):
        return self.directory.exists(self.cancel_name)

    def close(self):
        if self.lock is not None:
            self.lock.close()
            self.lock = None
        if self.directory is not None:
            self.directory.close()
            self.directory = None


def _empty_preparation(command):
    if isinstance(command.get('resume_state'), dict):
        return deepcopy(command['resume_state'])
    return {'session_id': command.get('session_id'), 'environment_id': None,
            'run_id': command.get('run_id'), 'outcome': 'failed', 'submission_started': False,
            'baseline_turn_ids': [], 'baseline_verified': False, 'files': [],
            'installed': deepcopy(command.get('installed') or {}),
            'uncertain_operation': None, 'session_creation_started': False}


def main():
    state, action, journal = None, None, None
    terminal_emitted = False
    command, output_closed = {}, False
    def preparation_emit(kind, **data):
        nonlocal output_closed
        if output_closed:
            return
        try:
            emit(kind, **data)
        except BrokenPipeError:
            # The parent/browser may disconnect; keep recording remote results.
            output_closed = True
            try:
                descriptor = os.open(os.devnull, os.O_WRONLY)
                try:
                    os.dup2(descriptor, sys.stdout.fileno())
                finally:
                    os.close(descriptor)
            except (AttributeError, OSError, ValueError):
                pass

    try:
        command = json.loads(sys.stdin.readline())
        action = command.get('action')
        allowed = {'run', 'prepare_inputs', 'inspect', 'recover', 'recover_unknown', 'observe', 'observe_unknown', 'cancel', 'download', 'update', 'browser_response', 'capabilities', 'title'}
        if action not in allowed: raise AgentError('未知 Agent 操作')
        session_id = command.get('session_id')
        if session_id and not re.fullmatch(r'sess_[A-Za-z0-9_-]+', session_id): raise AgentError('无效会话标识')
        if action not in ('run', 'prepare_inputs', 'recover_unknown', 'observe_unknown', 'capabilities', 'title') and not session_id: raise AgentError('当前没有可管理的会话')
        if action == 'prepare_inputs':
            journal = PreparationJournal(command.get('staging_root'), command.get('run_id'))
            # Read after acquiring the lock: another worker may have advanced
            # beyond the parent's last observed receipt before it exited.
            latest = journal.read()
            if latest is not None:
                command['resume_state'] = latest
            state = latest if latest is not None else _empty_preparation(command)
        cache_root = Path(__file__).resolve().parents[2] / 'agent_data' / 'artifacts' / hashlib.sha256(str(command.get('owner') or '').encode()).hexdigest()
        from modules.agent.artifacts import ArtifactObserver
        with create_client(command.get('connection')) as client, ArtifactObserver(
                client, emit, enabled=action in ('run', 'recover', 'recover_unknown', 'observe', 'observe_unknown'),
                skip_artifact_ids=command.get('skip_artifact_ids', ()), cache_root=cache_root) as artifacts:
            if action == 'capabilities':
                import openai
                emit('result', sdk_version=openai.__version__, available=hasattr(client.beta, 'agents'))
                return
            def terminal_snapshot(value):
                snapshot = value.snapshot()
                known = artifacts.snapshot(value.session_id, value.turn_id)
                if known: snapshot['artifacts'] = known
                return snapshot
            def progress(value):
                nonlocal state, terminal_emitted
                if terminal_emitted: return
                state = value
                if (value.outcome in TERMINAL
                        and (action == 'run' and value.turn_complete or value.sync_complete is True)):
                    # Publish before stream/context teardown. The parent transport
                    # finishes on result and reaps this worker asynchronously.
                    emit('result', **terminal_snapshot(value))
                    terminal_emitted = True
                else:
                    emit('progress', **value.snapshot())
                    artifacts.observe_session(value.session_id, value.turn_id)
            if action == 'prepare_inputs':
                def preparation_progress(value):
                    nonlocal state
                    state = value
                    journal.write(value)
                    preparation_emit('progress', preparation=value)
                state = prepare_inputs(client, command.get('inputs'), command.get('model'),
                    staging_root=command.get('staging_root'), session_id=session_id,
                    run_id=command.get('run_id'), instructions=command.get('instructions'),
                    reasoning=command.get('reasoning'), tool_settings=command.get('tool_settings'),
                    installed=command.get('installed'), resume_state=command.get('resume_state'),
                    on_progress=preparation_progress, should_cancel=journal.cancelled, owner=command.get('owner'))
                journal.write(state)
                preparation_emit('result', preparation=state)
            elif action == 'title':
                result = client.chat.completions.create(model=command['model'], messages=[
                    {'role': 'system', 'content': 'Write a short title for this conversation. Return only the title.'},
                    {'role': 'user', 'content': json.dumps(command.get('history', []), ensure_ascii=False)}])
                emit('result', title=result.choices[0].message.content or '')
            elif action == 'run':
                state = run_task(client, command.get('prompt'), command.get('model'), session_id=session_id,
                                 run_id=command.get('run_id'), on_progress=progress, instructions=command.get('instructions'),
                                 reasoning=command.get('reasoning'), tool_settings=command.get('tool_settings'),
                                 history_reference=command.get('history_reference'), input_files=command.get('input_files'), owner=command.get('owner'), observation=command.get('observation'))
                if not terminal_emitted: emit('result', **terminal_snapshot(state))
            elif action in ('recover', 'recover_unknown', 'observe', 'observe_unknown'):
                turn_id = command.get('turn_id')
                if action in ('recover_unknown', 'observe_unknown'): session_id, turn_id = find_uncertain_session(client, command.get('run_id'))
                state = recover_stream(client, session_id, turn_id, baseline_turn_ids=command.get('baseline_turn_ids'),
                       submission_started=command.get('submission_started') is True, tool_settings=command.get('tool_settings'), on_progress=progress, read_only=action in ('observe', 'observe_unknown'), observation=command.get('observation'))
                if not terminal_emitted: emit('result', **terminal_snapshot(state))
            elif action == 'inspect':
                emit('result', **inspect_saved(client, session_id, command.get('turn_id'), command.get('baseline_turn_ids'), command.get('submission_started') is True))
            elif action == 'cancel': emit('result', session_id=session_id, turn_id=command.get('turn_id'), **cancel_session(client, session_id, command.get('turn_id')))
            elif action == 'download': emit('result', session_id=session_id, artifacts=download_artifacts(client, session_id, turn_id=command.get('turn_id'), artifact_ids=command.get('artifact_ids'), skip_artifact_ids=command.get('skip_artifact_ids', ()), cache_root=cache_root, on_metadata=lambda records: emit('progress', session_id=session_id, artifact_metadata=records), on_progress=lambda records: emit('progress', session_id=session_id, artifacts=records)))
            elif action == 'update': emit('result', session_id=session_id, settings=update_settings(client, session_id, command.get('model'), command.get('reasoning')))
            elif action == 'browser_response':
                # Never echo submitted fields, including in errors or diagnostics.
                result = submit_browser_response(client, session_id, command.get('turn_id'), command.get('request_id'), command.get('response'))
                emit('result', session_id=session_id, **result)
                command.pop('response', None)
    except Exception as error:
        # A verified final receipt was already delivered. Teardown cannot
        # revoke it or append a contradictory error/progress message.
        if terminal_emitted: return
        snapshot = getattr(error, 'state', None) or state
        sanitized = error if isinstance(error, (AgentError, AgentConnectionError, ToolConfigurationError)) else safe_request_error(error)
        if action == 'prepare_inputs':
            preparation = snapshot if isinstance(snapshot, dict) else _empty_preparation(command)
            preparation['error'] = str(sanitized)
            if not isinstance(error, PreparationBusy) and preparation.get('outcome') in ('preparing', 'ready'):
                preparation['outcome'] = 'failed'
            if journal:
                try:
                    journal.write(preparation)
                except Exception:
                    # Report failure without pretending a receipt was durable.
                    preparation['journal_saved'] = False
            preparation_emit('error', message=str(sanitized), diagnostics=getattr(sanitized, 'diagnostics', {}),
                             preparation=preparation, **({'preparation_busy': True} if isinstance(error, PreparationBusy) else {}))
        else:
            emit('error', message=str(sanitized), diagnostics=getattr(sanitized, 'diagnostics', {}),
                 **(snapshot.snapshot() if snapshot else {'outcome': 'not_started' if action == 'run' else 'incomplete'}))
    finally:
        if journal:
            journal.close()


if __name__ == '__main__': main()
