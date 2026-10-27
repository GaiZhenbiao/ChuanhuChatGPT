"""Install trusted staged attachments without ever starting an Agent turn.

Progress/result dictionaries are JSON-safe recovery receipts. Persist each one,
including ``uncertain_operation``, before starting another worker. An ambiguous
write is never replayed: environment listings expose sizes, not content hashes.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from pathlib import Path, PurePosixPath
import re
import time

from modules.agent.input_files import InputFile, InputFileError, read_snapshot_file
from .runtime import AgentError, as_dict, all_records, safe_request_error
from .reasoning import compatible_reasoning, ReasoningConfigurationError
from .tools import build_tool_config, ToolConfigurationError

INLINE_LIMIT = 5 * 1024 * 1024
FILE_IMPORT_LIMIT = 50 * 1024 * 1024
FILE_TTL_SECONDS = 3600
_REJECTED = frozenset((400, 401, 403, 404, 409, 413, 415, 422, 429))
_IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,128}')


class InputPreparationError(AgentError):
    """Safe error with a dictionary ``state`` preserving partial installations."""


def _fail(message, state, item=None, *, uncertain=False, diagnostics=None):
    state['outcome'] = 'uncertain' if uncertain else 'failed'
    state['error'] = message
    if item is not None:
        item['status'] = 'failed'
        item['error'] = message
        if uncertain:
            item['write_state'] = 'uncertain'
    raise InputPreparationError(message, deepcopy(state), diagnostics) from None


def _emit(state, callback):
    if callback:
        callback(deepcopy(state))


def _cancel(state, callback):
    if callback and callback():
        state['outcome'] = 'cancelled'
        state['error'] = '附件准备已停止；未提交聊天轮次，已发生的上传不会回滚'
        raise InputPreparationError(state['error'], deepcopy(state))


def _record(record, state):
    if not isinstance(record, dict):
        _fail('附件快照记录无效；未提交聊天轮次', state)
    identifier, name = record.get('input_id'), record.get('name')
    size, digest = record.get('size'), record.get('sha256')
    remote, staged = record.get('remote_path'), record.get('staged_path')
    if (not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier)
            or not isinstance(name, str) or not name or len(name) > 512
            or type(size) is not int or size < 0 or size > FILE_IMPORT_LIMIT
            or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)
            or not isinstance(remote, str) or not isinstance(staged, str)):
        _fail('附件快照无效或超过单文件 50 MiB 限制；未提交聊天轮次', state)
    parts = PurePosixPath(remote).parts
    if (len(parts) != 5 or parts[:4] != ('/', 'workspace', 'inputs', identifier)
            or parts[-1] in ('.', '..') or '\\' in remote
            or str(PurePosixPath(remote)) != remote
            or any(ord(char) < 32 or ord(char) == 127 for char in remote)
            or not Path(staged).is_absolute()):
        _fail('附件目标路径或本地快照路径无效；未提交聊天轮次', state)
    return {key: record[key] for key in ('input_id', 'name', 'size', 'sha256', 'remote_path')}


def _turns(client, session_id):
    turns = all_records(client.beta.agents.sessions.turns.list(session_id, limit=100, order='asc'))
    identifiers = [turn.get('id') for turn in turns]
    if any(not isinstance(value, str) for value in identifiers):
        raise ValueError('无法确认会话轮次记录')
    return sorted(set(identifiers))


def _verify_session(client, state, *, initial=False, empty=False):
    state['last_request_phase'] = 'preparation.session_retrieve'
    session = as_dict(client.beta.agents.sessions.retrieve(state['session_id']))
    environment = session.get('environment') or {}
    if session.get('id') != state['session_id']:
        _fail('返回的会话标识不一致；未提交聊天轮次', state, uncertain=True)
    status = session.get('status')
    state['session_status'] = status if status in ('idle', 'in_progress', 'requires_action', 'failed') else 'unknown'
    if status == 'failed':
        _fail('会话准备失败（code=unknown；phase=preparation.session_retrieve）；该会话无法继续，请主动新建聊天；未提交聊天轮次', state)
    if environment.get('type') not in ('openai_hosted', 'self_hosted'):
        _fail('当前会话没有文件执行环境，请使用已启用代码与文件执行的会话', state)
    environment_id = environment.get('id')
    if not isinstance(environment_id, str) or not environment_id:
        _fail('当前会话尚未提供执行环境标识；未提交聊天轮次', state)
    if state['environment_id'] and state['environment_id'] != environment_id:
        _fail('会话执行环境已变化，不能复用旧附件安装记录', state, uncertain=True)
    state['environment_id'] = environment_id
    if session.get('status') != 'idle':
        _fail('当前会话仍在运行、等待授权或已失败；未提交聊天轮次', state)
    state['last_request_phase'] = 'preparation.turns_list'
    turns = _turns(client, state['session_id'])
    if empty and turns:
        _fail('附件准备会话已出现聊天轮次；未提交或重发任何聊天轮次', state, uncertain=True)
    if initial:
        state['baseline_turn_ids'] = turns
        state['baseline_verified'] = True
    elif turns != state['baseline_turn_ids']:
        _fail('附件准备期间会话轮次已变化；未提交或重发聊天轮次', state, uncertain=True)
    return session


def _write(client, state, operation, action, on_progress, should_cancel, item=None):
    _cancel(state, should_cancel)
    state['last_request_phase'] = 'preparation.' + operation
    if operation == 'session_create':
        state['session_creation_started'] = True
    marker = {'operation': operation}
    if item:
        marker.update(input_id=item['input_id'], remote_path=item['remote_path'])
        item.update(status='uploading', write_state='started')
        if operation == 'files_upload':
            item['upload_state'] = 'started'
    state['uncertain_operation'] = marker
    _emit(state, on_progress)
    try:
        _cancel(state, should_cancel)
    except InputPreparationError:
        state['uncertain_operation'] = None  # The HTTP request has not started.
        if operation == 'session_create':
            state['session_creation_started'] = False
        if item:
            item.update(status='prepared', write_state='none')
            if operation == 'files_upload':
                item['upload_state'] = 'none'
        raise InputPreparationError(state['error'], deepcopy(state)) from None
    try:
        # Never accept a client which cannot suppress automatic write retries.
        return action(client.with_options(max_retries=0))
    except Exception as error:
        rejected = getattr(error, 'status_code', None) in _REJECTED
        if rejected:
            state['uncertain_operation'] = None
            if operation == 'session_create':
                state['session_creation_started'] = False
            if item:
                item['write_state'] = 'none'
                if operation == 'files_upload':
                    item['upload_state'] = 'none'
        safe = safe_request_error(error, phase=state.get('last_request_phase'))
        state['diagnostics'] = safe.diagnostics
        message = str(safe) + '；未提交聊天轮次'
        if rejected and operation == 'environment_copy' and getattr(error, 'status_code', None) in (400, 409):
            # A competing write can appear after the preflight listing. A 400
            # "already exists" still does not prove these were our bytes.
            try:
                existing = _remote_files(client, state, item)
            except Exception:
                existing = []
            if existing:
                item['remote_observation'] = 'path_and_size_match' if _matching_remote(existing, state, item) else 'path_conflict'
                _fail('远端目标路径已存在，但无法验证内容；未覆盖或重传附件',
                      state, item, uncertain=True, diagnostics=safe.diagnostics)
        _fail(message, state, item, uncertain=not rejected, diagnostics=safe.diagnostics)


def _remote_files(client, state, item):
    state['last_request_phase'] = 'preparation.files_list'
    records = all_records(client.beta.agents.environments.files.list(
        state['environment_id'], path=str(PurePosixPath(item['remote_path']).parent), limit=100))
    return [entry for entry in records if entry.get('path') == item['remote_path']]


def _matching_remote(entries, state, item):
    return (len(entries) == 1 and entries[0].get('environment_id') == state['environment_id']
            and entries[0].get('path') == item['remote_path']
            and entries[0].get('size_bytes') == item['size'])


def _trusted_install(mapping, state, item):
    return (isinstance(mapping, dict) and mapping.get('environment_id') == state['environment_id']
            and all(mapping.get(key) == item[key] for key in ('remote_path', 'size', 'sha256')))


def _upload_source(client, state, item, contents, on_progress, should_cancel):
    uploaded = as_dict(_write(client, state, 'files_upload',
        lambda writer: writer.files.create(
            file=(PurePosixPath(item['remote_path']).name, contents), purpose='user_data',
            expires_after={'anchor': 'created_at', 'seconds': FILE_TTL_SECONDS}),
        on_progress, should_cancel, item))
    if not isinstance(uploaded.get('id'), str) or not uploaded['id']:
        _fail('Files API 上传结果缺少标识，状态待确认；未再次上传', state, item, uncertain=True)
    item.update(file_id=uploaded['id'], upload_state='confirmed', write_state='none', source_status='uploaded')
    state['uncertain_operation'] = None
    _emit(state, on_progress)  # Retain the file ID before any environment copy.


def _confirm_missing_source(client, state, item, on_progress, should_cancel):
    """A copy 404 alone cannot distinguish a missing source from a missing env.

    This function only reads remote state. It retires a previously acknowledged
    upload ID only after the Files API also returns 404, the same idle session
    and connected environment are verified, and the target path remains absent.
    """
    _cancel(state, should_cancel)
    # Persist the definitive rejection before further reads; interruption here
    # must not revive the already-resolved environment-write uncertainty.
    state['outcome'] = 'preparing'
    state.pop('error', None)
    item.update(status='prepared', source_status='checking')
    item.pop('error', None)
    _emit(state, on_progress)
    try:
        state['last_request_phase'] = 'preparation.file_retrieve'
        client.files.retrieve(item['file_id'])
    except Exception as error:
        if getattr(error, 'status_code', None) != 404:
            return False
    else:
        return False
    _cancel(state, should_cancel)
    _verify_session(client, state)
    state['last_request_phase'] = 'preparation.environment_retrieve'
    environment = as_dict(client.beta.agents.environments.retrieve(state['environment_id']))
    if environment.get('id') != state['environment_id'] or environment.get('status') != 'connected':
        _fail('上传源文件已不可用，但执行环境尚未确认可用；未重新上传，请重新连接后恢复', state, item)
    existing = _remote_files(client, state, item)
    if existing:
        item['remote_observation'] = 'path_and_size_match' if _matching_remote(existing, state, item) else 'path_conflict'
        _fail('远端目标路径已存在，但无法验证内容；未覆盖或重新上传附件', state, item, uncertain=True)
    _cancel(state, should_cancel)
    item.update(expired_file_id=item.pop('file_id'), source_status='missing_confirmed',
                upload_state='none', write_state='none')
    _emit(state, on_progress)
    return True


def prepare_inputs(client, inputs, model, *, staging_root, session_id=None, run_id=None,
                   instructions=None, reasoning=None, tool_settings=None, installed=None,
                   resume_state=None, on_progress=None, should_cancel=None, poll_interval=0.25, owner=None):
    """Prepare an empty session/environment and install staged files, never a turn.

    ``inputs`` must come from the application's trusted staging store, not raw
    UI/history paths. ``installed`` and ``resume_state`` are trusted local receipts.
    The caller must persist progress and separately check its Stop/generation
    token before submitting a message. Cancellation cannot abort an active HTTP
    request or remove already copied environment files.
    """
    state = {'session_id': session_id, 'environment_id': None, 'run_id': run_id,
             'outcome': 'preparing', 'submission_started': False, 'baseline_turn_ids': [],
             'files': [], 'installed': {}, 'uncertain_operation': None,
             'session_creation_started': False, 'baseline_verified': False}
    current = None
    try:
        reasoning, notice = compatible_reasoning(model, reasoning)
        if notice: state['reasoning_notice'] = notice
        if not callable(getattr(client, 'with_options', None)):
            _fail('SDK 客户端不支持关闭写入重试；未提交聊天轮次', state)
        if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]+', model):
            _fail('请选择有效的 Agent 模型', state)
        if instructions is not None and not isinstance(instructions, str):
            _fail('系统提示词必须为文字', state)
        if run_id is not None and (not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id)):
            _fail('本地任务标识无效', state)
        if not session_id and not run_id:
            _fail('新附件会话需要可恢复的本地任务标识', state)
        if not isinstance(inputs, (list, tuple)) or not inputs:
            _fail('请先添加附件', state)
        if type(poll_interval) not in (int, float) or not 0 <= poll_interval <= 60:
            _fail('环境轮询间隔无效', state)
        if resume_state is not None and not isinstance(resume_state, dict):
            _fail('附件恢复记录无效', state)
        previous = resume_state or {}
        if (previous.get('run_id') not in (None, run_id)
                or (session_id and previous.get('session_id') not in (None, session_id))):
            _fail('附件恢复记录不属于当前任务或会话', state)
        state['session_id'] = session_id or previous.get('session_id')
        state['environment_id'] = previous.get('environment_id')
        state['session_creation_started'] = bool(previous.get('session_creation_started'))
        state['baseline_verified'] = bool(previous.get('baseline_verified'))
        state['baseline_turn_ids'] = deepcopy(previous.get('baseline_turn_ids') or [])
        state['uncertain_operation'] = deepcopy(previous.get('uncertain_operation'))
        state['installed'] = deepcopy(previous.get('installed') or {})
        state['installed'].update(deepcopy(installed or {}))
        old_files = {item.get('input_id'): item for item in previous.get('files', []) if isinstance(item, dict)}
        paths, identifiers = set(), set()
        inputs = [record.to_dict() if isinstance(record, InputFile) else record for record in inputs]
        for record in inputs:
            item = _record(record, state)
            if item['input_id'] in identifiers or item['remote_path'] in paths:
                _fail('附件快照标识或目标路径重复', state)
            identifiers.add(item['input_id']); paths.add(item['remote_path'])
            item.update(status='prepared', write_state='none')
            old = old_files.get(item['input_id'], {})
            if old:
                if any(old.get(key) != item[key] for key in ('remote_path', 'size', 'sha256')):
                    _fail('恢复的附件内容或路径已变化，不能复用旧上传状态', state)
                for key in ('file_id', 'upload_state', 'write_state', 'expired_file_id'):
                    if key in old:
                        item[key] = old[key]
            state['files'].append(item)
            current = item
            # Check all attachments before creating any remote resources.
            read_snapshot_file(record, staging_root=staging_root)
        current = None
        _cancel(state, should_cancel)
        config = build_tool_config(tool_settings or {}, owner=owner)
        if config['environment']['type'] == 'none':
            _fail('附件需要代码与文件执行环境；请先明确开启该选项', state)
        _emit(state, on_progress)

        if not state['session_id']:
            state['last_request_phase'] = 'preparation.session_list'
            matches = [session for session in all_records(client.beta.agents.sessions.list(limit=100, order='desc'))
                       if (session.get('metadata') or {}).get('chuanhu_run_id') == run_id]
            if len(matches) > 1 or (not matches and state['session_creation_started']):
                _fail('尚未找到唯一的附件会话，创建结果待确认；没有重复创建或提交聊天轮次', state, uncertain=True)
            if matches:
                state['session_id'] = matches[0]['id']
                state['session_creation_started'] = True
                if (state['uncertain_operation'] or {}).get('operation') == 'session_create':
                    state['uncertain_operation'] = None
                _emit(state, on_progress)
            else:
                agent = {'model': model, 'instructions': instructions or '', 'tools': config['tools']}
                if reasoning is not None:
                    agent['reasoning'] = {'effort': reasoning}
                created = as_dict(_write(client, state, 'session_create',
                    lambda writer: writer.beta.agents.sessions.create(
                        agent=agent, environment=config['environment'], stream=False,
                        metadata={'chuanhu_run_id': run_id}), on_progress, should_cancel))
                if not isinstance(created.get('id'), str) or not created['id']:
                    _fail('附件会话创建结果未包含会话标识，状态待确认', state, uncertain=True)
                state['session_id'] = created['id']
                state['uncertain_operation'] = None
                _emit(state, on_progress)  # Report the ID before any further read.

        _cancel(state, should_cancel)
        _verify_session(client, state, initial=not state['baseline_verified'],
                        empty=state['session_creation_started'])
        if (state['uncertain_operation'] or {}).get('operation') == 'session_create':
            state['uncertain_operation'] = None
        _emit(state, on_progress)
        while True:
            _cancel(state, should_cancel)
            state['last_request_phase'] = 'preparation.environment_retrieve'
            environment = as_dict(client.beta.agents.environments.retrieve(state['environment_id']))
            if environment.get('id') != state['environment_id']:
                _fail('返回的执行环境标识不一致', state, uncertain=True)
            status = environment.get('status')
            state['environment_status'] = status if status in ('pending', 'provisioning', 'connected', 'disconnected', 'expired', 'failed') else 'unknown'
            _emit(state, on_progress)
            if status == 'connected':
                break
            if status == 'failed':
                details = environment.get('error') or {}
                known_codes = {'environment_connection_failed', 'environment_connection_timeout',
                               'sandbox_error', 'executor_version_incompatible', 'internal_error', 'idle_timeout'}
                code = details.get('code') if isinstance(details, dict) else None
                state['environment_error'] = {'code': code if code in known_codes else 'unknown',
                    'type': 'environment_error' if isinstance(details, dict) and details.get('type') == 'environment_error' else 'unknown'}
                _fail('执行环境准备失败（code=' + state['environment_error']['code']
                      + '；phase=preparation.environment_retrieve）；该会话无法继续，请主动新建聊天；未提交聊天轮次', state)
            if status not in ('pending', 'provisioning'):
                _fail('执行环境未连接、已过期或失败；未提交聊天轮次', state)
            # No task deadline: provisioning remains cancellable between polls.
            time.sleep(poll_interval)

        for record, current in zip(inputs, state['files']):
            _cancel(state, should_cancel)
            _verify_session(client, state)
            existing = _remote_files(client, state, current)
            trusted = state['installed'].get(current['input_id'])
            if trusted is not None:
                if not _trusted_install(trusted, state, current) or not _matching_remote(existing, state, current):
                    _fail('已安装附件的执行环境、路径或内容记录不一致，未重传或覆盖', state, current, uncertain=True)
                current.update(status='ready', write_state='confirmed')
                _emit(state, on_progress)
                continue
            if existing:
                current['remote_observation'] = 'path_and_size_match' if _matching_remote(existing, state, current) else 'path_conflict'
                _fail('远端目标路径已存在，但无法验证内容；未覆盖或重传附件', state, current, uncertain=True)
            pending = state['uncertain_operation']
            if pending or current.get('write_state') in ('started', 'uncertain') or current.get('upload_state') in ('started', 'uncertain'):
                _fail('此前附件上传或复制结果待确认；没有重传或提交聊天轮次', state, current, uncertain=True)

            # Keep verified contents only for this individual write, never in a
            # progress receipt, returned state, chat history, or log.
            contents = read_snapshot_file(record, staging_root=staging_root)
            try:
                if current['size'] <= INLINE_LIMIT:
                    encoded = base64.b64encode(contents).decode('ascii')
                    try:
                        copied = as_dict(_write(client, state, 'environment_copy',
                            lambda writer: writer.beta.agents.environments.files.create(
                                state['environment_id'], type='inline', data=encoded, path=current['remote_path']),
                            on_progress, should_cancel, current))
                    finally:
                        del encoded
                else:
                    if not current.get('file_id'):
                        _upload_source(client, state, current, contents, on_progress, should_cancel)
                    _cancel(state, should_cancel)
                    _verify_session(client, state)
                    try:
                        copied = as_dict(_write(client, state, 'environment_copy',
                            lambda writer: writer.beta.agents.environments.files.create(
                                state['environment_id'], type='file_id', file_id=current['file_id'], path=current['remote_path']),
                            on_progress, should_cancel, current))
                    except InputPreparationError as error:
                        if (error.diagnostics.get('status_code') != 404
                                or state['uncertain_operation'] or current.get('upload_state') != 'confirmed'
                                or not _confirm_missing_source(client, state, current, on_progress, should_cancel)):
                            raise
                        # Refresh once in this invocation, only after definitive
                        # source-404 and environment checks. Unknown upload/copy
                        # outcomes and a second copy failure never enter a loop.
                        contents = read_snapshot_file(record, staging_root=staging_root)
                        _upload_source(client, state, current, contents, on_progress, should_cancel)
                        _cancel(state, should_cancel)
                        _verify_session(client, state)
                        copied = as_dict(_write(client, state, 'environment_copy',
                            lambda writer: writer.beta.agents.environments.files.create(
                                state['environment_id'], type='file_id', file_id=current['file_id'], path=current['remote_path']),
                            on_progress, should_cancel, current))
            finally:
                del contents
            if not _matching_remote([copied], state, current):
                _fail('附件复制结果不匹配，状态待确认；未重传或覆盖', state, current, uncertain=True)
            mapping = {key: current[key] for key in ('remote_path', 'size', 'sha256')}
            mapping['environment_id'] = state['environment_id']
            if current.get('file_id'):
                mapping['file_id'] = current['file_id']
            state['installed'][current['input_id']] = mapping
            current.update(status='ready', write_state='confirmed')
            state['uncertain_operation'] = None
            _emit(state, on_progress)
            _cancel(state, should_cancel)

        _verify_session(client, state)
        _cancel(state, should_cancel)
        if state['uncertain_operation']:
            _fail('仍有附件写入结果待确认；未提交聊天轮次', state, uncertain=True)
        state['outcome'] = 'ready'
        _emit(state, on_progress)
        return deepcopy(state)
    except InputPreparationError as error:
        # The caller receives the last safe receipt even if its progress sink dies.
        try:
            _emit(error.state, on_progress)
        except Exception:
            pass
        raise
    except Exception as error:
        uncertain = bool(state.get('uncertain_operation'))
        safe = safe_request_error(error, phase=state.get('last_request_phase'))
        state['diagnostics'] = safe.diagnostics
        message = (str(error) if isinstance(error, (ToolConfigurationError, ReasoningConfigurationError)) else
                   '附件本地快照不可用或已变化；未提交聊天轮次' if isinstance(error, InputFileError)
                   else str(safe) + '；未提交聊天轮次')
        state['outcome'] = 'uncertain' if uncertain else 'failed'
        state['error'] = message
        if current:
            current.update(status='failed', error=message)
            if uncertain:
                current['write_state'] = 'uncertain'
        try:
            _emit(state, on_progress)
        except Exception:
            pass
        raise InputPreparationError(message, deepcopy(state), safe.diagnostics) from None
