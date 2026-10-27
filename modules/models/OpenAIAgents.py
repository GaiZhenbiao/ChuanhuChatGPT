"""A durable Agent session in the existing ChuanhuChat conversation surface."""
from copy import deepcopy
import hashlib
import logging
import json
import re
from pathlib import Path
import tempfile
from threading import RLock
from uuid import uuid4

import gradio as gr
from modules import shared
from modules.agent.transport import worker_messages, connection_for_model
from modules.agent.completion_timing import safe_timing, mark as mark_completion
from modules.agent.store import BindingStore, owner_identity
from modules.model_capabilities import AGENT_CAPABILITIES, require_capability
from modules.agent.settings import load_settings
from modules.agent.operations import OperationScope, TaskScope
from modules.agent.input_state import AgentInputState, InputPreparationStopped
from modules.agent.tools import validate_settings, tool_availability
from modules.agent.reasoning import normalize_reasoning, compatible_reasoning
from modules.presets import i18n
from .base_model import BaseLLMModel, HISTORY_DIR

TERMINAL = {'completed', 'failed', 'cancelled', 'not_started'}
SESSION_CONFIG_LOCKED = '会话创建后工具、联网和系统提示词已固定，请新建聊天后修改'
STATUS = {'starting': '正在连接', 'in_progress': '正在运行', 'requires_action': '等待授权或登录',
          'restoring': '正在恢复历史', 'cancel_requested': '正在停止', 'cancelled': '已停止',
          'completed': '已完成', 'failed': '执行失败', 'not_started': '准备就绪',
          'incomplete': '暂时无法确认状态', 'uncertain': '暂时无法确认状态'}
_UNSPECIFIED_GENERATION = object()
_SYNC_WARNING = '云端历史尚未完整同步，现有回答已保留'
_SYNC_NOTICE = '当前轮已结束，但云端历史尚未完整同步；回答已保留，请重新连接后继续'
_bindings = {}  # Backward-compatible test hook; authority lives in BindingStore.
_bindings_lock = RLock()
_session_locks = {}
_cancel_sessions = {}


class ModelUpdateError(Exception):
    """A next-turn parameter update failed before the task was submitted."""


def browser_owner(request):
    if request is None or not request.session_hash:
        raise gr.Error('需要在当前登录会话中操作')
    return owner_identity(request.username or '')


def fingerprint(history):
    return hashlib.sha256(json.dumps(history, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def display_signature(chatbot):
    return [(row[0], row[1]) for row in chatbot or [] if isinstance(row, (tuple, list)) and len(row) == 2 and isinstance(row[0], (str, type(None))) and isinstance(row[1], (str, type(None)))]


def _text_history(history):
    return [{'role': item['role'], 'content': item['content']} for item in history
            if isinstance(item, dict) and item.get('role') in ('user', 'assistant') and isinstance(item.get('content'), str)]


def _rows(history):
    rows = []
    for message in history:
        if message['role'] == 'user': rows.append([message['content'], None])
        elif rows and rows[-1][1] is None: rows[-1][1] = message['content']
        else: rows.append([None, message['content']])
    return rows


class OpenAIAgentsClient(AgentInputState, BaseLLMModel):
    is_hosted_agent = True
    ui_capabilities = AGENT_CAPABILITIES

    def __init__(self, model_name, user_name='', owner=None, api_key=None):
        super().__init__(model_name=model_name, user=user_name, config={'stream': True})
        self._selection_name = model_name
        self.need_api_key = False
        self._connection_key = self.api_key or api_key
        self.api_key = None  # Credentials never enter exported chat metadata.
        self._default_instructions = self.system_prompt
        self._owner = owner
        self._lock = RLock()
        self._running = self._retired = False
        self._history_deleted = False
        self._cancel_requested = self._cancel_sent = False
        self._conversation_id = uuid4().hex
        self._state = {'outcome': 'not_started'}
        self._display, self._artifacts, self._cloud_items = [], [], []
        self._transcript, self._transcript_preview = None, []
        self._item_receipts = []
        self._activity_records = []
        self._active_input_cards = []
        self._answer_index = self._answer_row = None
        self._session_settings = None
        self._importing = self._needs_sync = False
        self._allow_text_tool = False
        self._reasoning = None
        self._reasoning_notice = ''
        self._last_request_error = {}
        self._pending_actions = []
        self._notice = ''
        self._sync_notice_receipt = None
        self._unavailable = False
        self._connection_mismatch = False
        self._fork_previous = None
        self._auto_named = False
        self._first_prompt = None
        self._pending_network = None
        self._pending_model_settings = None
        self._choice_revision = 0
        self._choice_epoch = uuid4().hex
        self._tool_revision = 0
        self._active_file_retries = set()
        self._initialize_inputs()
        self.metadata = {}
        self._tool_settings = load_settings(shared.chuanhu_path, owner) if owner else validate_settings({})

    def bind_owner(self, request):
        owner = browser_owner(request)
        with self._lock:
            if self._owner is not None and self._owner != owner: raise gr.Error('此会话不属于当前登录用户')
            if self.user_name != (request.username or ''): raise gr.Error('聊天存储身份与当前登录用户不一致')
            if self._owner is None: self._tool_settings = load_settings(shared.chuanhu_path, owner)
            self._owner = owner

    def _connection(self):
        return connection_for_model(api_key=self._connection_key, api_host=self.api_host)

    def _connection_reference(self):
        from modules.agent.connection import AgentConnectionError
        try:
            connection = self._connection()
            return {key: connection.get(key) for key in ('base_url', 'organization', 'project')}
        except AgentConnectionError:
            return {'base_url': getattr(shared.state, 'openai_api_base', ''), 'organization': '', 'project': ''}

    def record_ui_error(self, message, key=None, *, source=None, operation=None):
        with self._lock:
            operation = operation or getattr(self, '_predict_error_operation', None) or self._state.get('generation')
            event = (self._conversation_id, operation, source, key or str(message))
            seen = getattr(self, '_ui_error_seen', set())
            if event in seen: return
            seen.add(event)
            self._ui_error_seen = seen
            self._ui_errors = [*getattr(self, '_ui_errors', []), {
                'owner': self._owner, 'conversation': self._conversation_id,
                'generation': self._state.get('generation'), 'operation': operation,
                'source': source, 'message': str(message)}]

    def _take_operation_errors(self, operation, source=None):
        errors = getattr(self, '_ui_errors', [])
        own = lambda record: record['operation'] == operation and record['source'] == source
        self._ui_errors = [record for record in errors if not own(record)]
        return [record for record in errors if own(record)]

    def take_ui_error(self, *, operation=None, source=None):
        # Offline/internal callers can inspect one exact operation; never drain
        # the whole ledger on behalf of an unrelated successful callback.
        with self._lock:
            operation = self._state.get('generation') if operation is None else operation
            return '\n'.join(record['message'] for record in self._take_operation_errors(operation, source))

    def has_ui_error(self, operation):
        with self._lock:
            return any(record['operation'] == operation and record['source'] is None
                       for record in getattr(self, '_ui_errors', []))

    def complete_error_operation(self, operation, *, source=None):
        """Freeze an immutable receipt only after cleanup and final UI output."""
        with self._lock:
            records = self._take_operation_errors(operation, source)
            if self._retired: return
            valid = [record for record in records if record['owner'] == self._owner
                     and record['conversation'] == self._conversation_id
                     and record['generation'] == self._state.get('generation')]
            if valid:
                receipt = {'id': operation, 'owner': self._owner,
                           'conversation': self._conversation_id,
                           'generation': self._state.get('generation'),
                           'messages': [record['message'] for record in valid]}
                self._ui_error_outbox = [*getattr(self, '_ui_error_outbox', []), receipt]

    def take_completed_ui_errors(self):
        """Atomically deliver completed receipts once; active errors stay private."""
        with self._lock:
            receipts = getattr(self, '_ui_error_outbox', [])
            self._ui_error_outbox = []
            if self._retired: return ''
            return '\n'.join(message for receipt in receipts
                if receipt['owner'] == self._owner and receipt['conversation'] == self._conversation_id
                and receipt['generation'] == self._state.get('generation')
                for message in receipt['messages'])

    def _record_message_error(self, message, *, operation=None):
        preparation = message.get('preparation') or {}
        if preparation.get('outcome') == 'cancelled': return
        if message.get('type') == 'error' or message.get('outcome') == 'failed' or preparation.get('outcome') == 'failed':
            self.record_ui_error(message.get('message') or preparation.get('error') or 'Agent 执行失败', operation=operation)
        if message.get('sync_complete') is False:
            self.record_ui_error(_SYNC_WARNING, operation=operation)
        if message.get('artifact_error'):
            self.record_ui_error('文件获取失败：' + str(message['artifact_error']), operation=operation)
        for record in message.get('artifacts', []):
            if record.get('status') == 'failed':
                self.record_ui_error(record.get('error') or '文件获取失败，可重试', ('artifact', record.get('id'), record.get('error')), operation=operation)

    def _resolve_sync_warning(self, operation=None):
        # Resolve only this operation's obsolete sync warning after safe merge.
        operation = operation or getattr(self, '_predict_error_operation', None) or self._state.get('generation')
        self._ui_errors = [record for record in getattr(self, '_ui_errors', [])
            if not (record['owner'] == self._owner and record['conversation'] == self._conversation_id
                    and record['generation'] == self._state.get('generation') and record['operation'] == operation
                    and record['source'] is None and record['message'] == _SYNC_WARNING)]
        getattr(self, '_ui_error_seen', set()).discard((self._conversation_id, operation, None, _SYNC_WARNING))
        receipt = (self._owner, self._conversation_id, self._state.get('generation'), operation)
        if self._notice == _SYNC_NOTICE and self._sync_notice_receipt == receipt:
            self._notice = ''
            self._sync_notice_receipt = None

    def _execution_scope(self, **kwargs):
        return (TaskScope if getattr(self, "_task_backend", False) else OperationScope).capture(self, **kwargs)

    def background_predict(self, *args, **kwargs):
        from modules.agent.tasks import TASKS
        with self._lock:
            if not self.history and self._state.get('outcome') == 'not_started':
                root = Path(HISTORY_DIR) / self.user_name
                path = Path(self.history_file_path)
                path = path if path.is_absolute() else root / path
                if path.is_file() or TASKS.find_history(self.user_name, path) is not None:
                    self.history_file_path = path.stem + '-' + uuid4().hex[:10] + '.json'
                    self._submission_history_path = self.history_file_path
            task = TASKS.start(self, lambda: self.predict(*args, **kwargs))
        yield from task.subscribe(self)

    def background_reconnect(self):
        from modules.agent.tasks import TASKS
        task = TASKS.find(self)
        if task is None:
            task = TASKS.start(self, self.reconnect)
        self._background_task = task
        yield from task.subscribe(self)

    def new_view(self):
        """A fresh UI model cannot mutate the background task it leaves."""
        model = OpenAIAgentsClient(self._selection_name, self.user_name, self._owner, self._connection_key)
        model.api_host = self.api_host
        model._connection_key = self._connection_key
        model._default_instructions = self._default_instructions
        model.system_prompt = self.system_prompt
        # New chat carries the latest saved user choice, including default=None,
        # rather than the previous cloud session's effective configuration.
        model.model_name, model._reasoning = self.agent_model_choice
        model._tool_settings = deepcopy(self._tool_settings)
        model._repair_reasoning_choice()
        return model

    def _worker(self, command):
        from modules.agent.connection import AgentConnectionError
        try:
            connection = self._connection()
        except AgentConnectionError as error:
            yield {'type': 'error', 'outcome': 'not_started', 'message': str(error)}
            return
        wire = dict(command, connection=connection, owner=self.user_name)
        self._tool_log_key = connection.get('api_key')
        if command.get('action') in ('run', 'recover', 'recover_unknown', 'observe', 'observe_unknown'):
            self._file_connection = deepcopy(connection)
            self._file_connection_generation = self._state.get('generation')
        if command.get('action') in ('run', 'recover', 'recover_unknown', 'download'):
            scope = self._execution_scope()
            caller_cancelled = command.get('_observe_cancel')
            wire['_observe_cancel'] = lambda: not scope.current(self) or bool(caller_cancelled and caller_cancelled())
        if 'skip_artifact_ids' not in wire:
            wire['skip_artifact_ids'] = [record['id'] for record in self._artifacts
                                         if record.get('status') == 'ready' and Path(record.get('path', '')).is_file()]
        try:
            from modules.agent.runtime import _safe_diagnostics
            for message in worker_messages(wire):
                if message.get('type') == 'error':
                    diagnostics = _safe_diagnostics(message.get('diagnostics') or {})
                    if diagnostics:
                        with self._lock:
                            if diagnostics != self._last_request_error:
                                logging.warning('Agent 请求诊断：%s', json.dumps(diagnostics, ensure_ascii=False, sort_keys=True))
                            self._last_request_error = diagnostics
                yield message
        finally:
            wire.pop('response', None)
            wire.pop('connection', None)

    def _key(self): return self._owner, str(self.history_file_path).removesuffix('.json')
    def _store(self): return BindingStore(getattr(self, "_task_root", shared.chuanhu_path))

    def _local_history_deleted(self):
        return bool(self._history_deleted or (self._owner and
                    self._store().is_history_deleted(self._owner, self.history_file_path, self._conversation_id)))

    def _persistence_owner(self):
        if self._local_history_deleted(): return False
        from modules.agent.tasks import TASKS
        active = TASKS.find(self)
        attached = getattr(self, '_background_task', None)
        return ((active is None or active.model is self)
                and (attached is None or attached.model is self))

    def _remember(self):
        with self._store().history_guard(self._owner, self.history_file_path):
            if self._owner:
                from modules.agent.file_jobs import overlay_model
                overlay_model(self)
            try:
                self._remember_binding()
            except Exception:
                self._state['persistence_failed'] = True
                raise

    def _remember_task_end(self):
        if (self._state.get('outcome') in TERMINAL and not self._needs_sync
                and not self._state.get('persistence_failed') and self._persistence_owner()):
            if self._store().settle_task(self._owner, self.history_file_path, self._conversation_id, self._state): return
        self._remember()

    def _remember_binding(self):
        if not self._persistence_owner(): return
        if not self._owner or self._importing: return
        if (not self._state.get('session_id') and self._state.get('outcome') != 'uncertain' and not self._input_context
                and not (getattr(self, '_task_backend', False) and self.history)): return
        state = {key: deepcopy(value) for key, value in self._state.items() if key not in ('required_actions', 'settings', 'items')}
        record = {'state': state, 'conversation_id': self._conversation_id, 'artifacts': deepcopy(self._artifacts),
                  'transcript': self._private_transcript(), 'transcript_preview': deepcopy(self._transcript_preview),
                  'item_receipts': deepcopy(self._item_receipts),
                  'settings': deepcopy(self._session_settings), 'connection_ref': self._connection_reference(),
                  'items': deepcopy(self._cloud_items), 'auto_named': self._auto_named, 'first_prompt': self._first_prompt,
                  'next_model_settings': self._pending_model_settings,
                  'local_phase': (getattr(self, '_task_phase', 'receiving') if getattr(self, '_background_busy', False)
                                  else 'uncertain' if self._state.get('outcome') not in TERMINAL else 'settled')}
        record.update(self._input_binding())
        record['last_request_error'] = deepcopy(self._last_request_error)
        self._store().put(self._owner, self.history_file_path, record)

    def _private_transcript(self):
        # Even a redacted display field named authorization is forbidden by
        # BindingStore. Keep that guard intact; omit these inert display fields.
        denied = {'api_key', 'authorization', 'password', 'access_token', 'credential_values'}
        def clean(value):
            if isinstance(value, dict): return {key: clean(item) for key, item in value.items() if key.lower() not in denied}
            if isinstance(value, list): return [clean(item) for item in value]
            return value
        snapshot = clean(deepcopy(self._transcript))
        if snapshot:
            for old, new in zip(self._transcript['timeline'], snapshot['timeline']):
                if old != new: new.setdefault('capture', {})['omitted'] = True
            for old, new in zip(self._transcript['turns'], snapshot['turns']):
                if old != new: new.setdefault('error_capture', {})['omitted'] = True
        return snapshot

    def adopt_local_history(self, original):
        self.history = deepcopy(original.history)
        self.history_file_path = original.history_file_path
        self.chatbot = deepcopy(getattr(original, 'chatbot', []))
        self._display = deepcopy(self.chatbot)
        self._restore_binding()

    def _restore_binding(self):
        self._activity_records = []
        self._choice_epoch = uuid4().hex
        self._active_input_cards = []
        self._cancel_requested = self._cancel_sent = False
        self._draft_token = self._draft_conversation = None
        self._draft_submitted = self._draft_acknowledged = False
        self._tool_ui_patch = None
        self._fork_previous = None
        binding = None if self._importing or not self._owner else self._store().get(self._owner, self.history_file_path)
        self._pending_actions = []
        if binding:
            from modules.agent.runtime import _safe_diagnostics
            self._last_request_error = _safe_diagnostics(binding.get('last_request_error') or {})
            self._restore_input_binding(binding)
            self._pending_model_settings = binding.get('next_model_settings')
            if self._pending_model_settings:
                self._pending_model_settings = (self._pending_model_settings[0], normalize_reasoning(self._pending_model_settings[1]))
            if binding.get('connection_ref') != self._connection_reference():
                self._notice = '当前连接配置与原会话不同，未连接云端；可恢复原配置，或明确按现配置新建并继续'
                self._state = dict(binding['state'], outcome='incomplete', public_text_streaming=False)
                self._needs_sync = True
                self._connection_mismatch = True
            else:
                self._state = dict(binding['state'], public_text_streaming=False)
                if not self._state.get('session_id') and self._state.get('outcome') not in TERMINAL:
                    self._state['outcome'] = 'uncertain'
                self._needs_sync = True
                self._connection_mismatch = False
            self._conversation_id = binding['conversation_id']
            self._auto_named = binding.get('auto_named', True)
            self._first_prompt = binding.get('first_prompt')
            self._artifacts = binding.get('artifacts', [])
            for artifact in self._artifacts:
                if artifact.get('status') == 'ready' and not Path(artifact.get('path', '')).is_file():
                    artifact.update(status='failed', error='本地下载缓存已失效，可重新获取')
                    artifact.pop('path', None)
            self._cloud_items = binding.get('items', [])
            self._transcript = deepcopy(binding.get('transcript'))
            self._transcript_preview = deepcopy(binding.get('transcript_preview', []))
            self._item_receipts = deepcopy(binding.get('item_receipts', []))
            self._session_settings = binding.get('settings')
            if self._session_settings:
                self.model_name = self._session_settings['model']
                self._reasoning = normalize_reasoning(self._session_settings.get('reasoning'))
                self._session_settings['reasoning'] = self._reasoning
                self.system_prompt = self._session_settings.get('instructions', self.system_prompt)
                self._tool_settings = deepcopy(self._session_settings.get('tools', self._tool_settings))
            self._repair_reasoning_choice()
            if self._failed_preparation_environment():
                self._state = dict(self._state, outcome='failed')
                self._needs_sync = False
                self._notice = self._failed_environment_notice()
            self._notice = self._notice or '已找到原会话，发送前将按云端记录恢复历史'
        else:
            self._fresh()
            if self.history: self._notice = '将根据这份历史创建新的 Agent 会话：带入全部可用文字；不继承旧工具状态、沙盒文件和任务'

    def _fresh(self):
        self._choice_epoch = uuid4().hex
        self._tool_ui_patch = None
        self._draft_token = self._draft_conversation = None
        self._draft_submitted = self._draft_acknowledged = False
        self._reset_inputs()
        self._tool_revision = 0
        self._fork_previous = None
        self._auto_named = False
        self._first_prompt = None
        self._pending_network = None
        self._state = {'outcome': 'not_started'}
        self._conversation_id = uuid4().hex
        self._artifacts, self._cloud_items, self._pending_actions = [], [], []
        self._transcript, self._transcript_preview = None, []
        self._item_receipts = []
        self._activity_records = []
        self._active_input_cards = []
        self._answer_index = self._answer_row = self._session_settings = None
        self._needs_sync = self._connection_mismatch = self._unavailable = False
        self._last_request_error = {}
        self._repair_reasoning_choice()

    def _assert_idle(self):
        if self._local_history_deleted(): raise gr.Error('此本地历史已删除，请新建聊天')
        if self._failed_preparation_environment(): raise gr.Error(self._failed_environment_notice())
        from threading import current_thread
        from modules.agent.tasks import TASKS
        active = TASKS.find(self)
        task = getattr(self, '_background_task', None)
        if task is not None and task.model is not self and task.done and active is None:
            task.project(self)
            self._background_task = None
            task = None
        background_busy = bool(getattr(self, '_background_busy', False) and (task is None or current_thread() is not task.thread))
        if (active is not None and active.model is not self) or background_busy or self._running or getattr(self, '_pending_send', None) or self._state.get('outcome') not in TERMINAL or self._needs_sync or self._state.get('persistence_failed'):
            raise gr.Error('当前任务仍在运行或状态尚待确认，请先停止或重新连接')

    def prepare_model_switch(self):
        with self._lock: self._assert_idle(); self._clear_input_selection(); self._remember()
    def retire(self):
        with self._lock:
            task = getattr(self, "_background_task", None)
            self._choice_epoch = uuid4().hex
            if getattr(self, "_task_backend", False) and task is not None and not task.done:
                self._ui_detached = True
                return
            self._retired = True
            self._release_input_stager()
    def billing_info(self): return ''
    def set_key(self, new_key):
        with self._lock:
            self._assert_idle()
            self._connection_key = new_key
        return gr.update(value=new_key), '已更新连接密钥；下次连接时使用'
    def set_streaming(self, streaming):
        require_capability(self, 'output_mode')
    def _status(self, detail=''):
        return ' · '.join(part for part in (STATUS.get(self._state.get('outcome'), '暂时无法确认状态'), detail or self._notice, self._reasoning_notice) if part)

    def _current_settings(self):
        self._repair_reasoning_choice()
        snapshot = self._session_settings if self._state.get('session_id') else None
        return {'model': self.model_name, 'reasoning': self._reasoning,
                'instructions': (snapshot or {}).get('instructions', self.system_prompt),
                'tools': deepcopy((snapshot or {}).get('tools', self._tool_settings))}

    def _reserve_input_session(self, session):
        key = (self._owner, session)
        with _bindings_lock:
            if key in _cancel_sessions or (key in _session_locks and _session_locks[key] is not self):
                raise InputPreparationStopped('另一窗口正在操作此会话，消息未发送')
            _session_locks[key] = self
        self._input_session_reservation = key

    @property
    def agent_model_choice(self):
        return tuple(self._pending_model_settings or (self.model_name, self._reasoning))

    @property
    def agent_choice_target(self):
        return self._conversation_id + ':' + self._choice_epoch

    def _repair_reasoning_choice(self):
        model, reasoning = self.agent_model_choice
        corrected, notice = compatible_reasoning(model, reasoning)
        if not notice: return
        self._reasoning_notice = notice
        if self._state.get('session_id'):
            # Keep the effective cloud settings until the update is confirmed.
            self._pending_model_settings = (model, corrected)
        else:
            self.model_name, self._reasoning = model, corrected
            self._pending_model_settings = None
            if self._session_settings:
                self._session_settings.update(model=model, reasoning=corrected)

    def set_agent_model(self, model, reasoning, revision=None, target=None):
        with self._lock:
            if target is not None and target != self.agent_choice_target: return None
            if revision is not None:
                if not isinstance(revision, (int, float)) or revision < 0 or int(revision) != revision:
                    raise gr.Error('无效的设置版本')
                if revision <= self._choice_revision: return None
            if self._retired: raise gr.Error('聊天已切换，请在当前聊天中选择')
            if not isinstance(model, str) or not model.strip(): raise gr.Error('请选择 Agent 子模型')
            model = model.strip()
            reasoning, notice = compatible_reasoning(model, reasoning)
            self._reasoning_notice = notice
            if (model, reasoning) == self.agent_model_choice:
                if revision is not None: self._choice_revision = int(revision)
                return None
            self._assert_idle()
            choice = (model, reasoning)
            self._pending_model_settings = choice if choice != (self.model_name, self._reasoning) else None
            if revision is not None: self._choice_revision = int(revision)
            self._remember()
        return notice or '已保存，下一轮自动使用'

    def _apply_next_model(self, generation):
        with self._lock:
            self._repair_reasoning_choice()
            if not self._pending_model_settings: return
            model, reasoning = self._pending_model_settings
            reasoning = normalize_reasoning(reasoning)
            session = self._state.get('session_id')
            if (model, reasoning) == (self.model_name, self._reasoning):
                self._pending_model_settings = None
                return
        try:
            if session:
                confirmed = None
                for message in self._worker({'action': 'update', 'session_id': session, 'model': model, 'reasoning': reasoning}):
                    if message.get('type') == 'error':
                        with self._lock:
                            self._needs_sync = (message.get('diagnostics') or {}).get('status_code') not in (400, 401, 403, 404, 422)
                        raise ModelUpdateError(message.get('message', '参数更新失败'))
                    if message.get('type') == 'result': confirmed = message.get('settings')
                if not confirmed or confirmed.get('model') != model or (reasoning is not None and confirmed.get('reasoning') != reasoning):
                    with self._lock: self._needs_sync = True
                    raise ModelUpdateError('参数更新结果尚未确认，请重新连接')
        except ModelUpdateError:
            raise
        except Exception:
            with self._lock: self._needs_sync = True
            raise ModelUpdateError('参数更新连接中断，请重新连接确认') from None
        with self._lock:
            if self._state.get('generation') != generation or self._retired:
                raise ModelUpdateError('聊天已变化，消息未发送')
            self.model_name, self._reasoning = model, normalize_reasoning(confirmed.get('reasoning', reasoning) if session else reasoning)
            self._pending_model_settings = None
            if self._session_settings:
                self._session_settings.update(model=model, reasoning=self._reasoning)
            self._remember()

    def _assert_configuration_owner(self):
        if not self._owner: raise gr.Error('需要在当前登录会话中修改配置')
        if self._retired: raise gr.Error('聊天已切换，请在当前聊天中修改配置')

    def _configuration_revision(self, revision, target):
        self._assert_configuration_owner()
        if target != self._conversation_id:
            raise gr.Error('聊天已切换，未修改旧会话配置')
        if (type(revision) not in (int, float) or revision < 0
                or (isinstance(revision, float) and not revision.is_integer())):
            raise gr.Error('无效的工具设置版本')
        return int(revision)

    def stage_agent_tools(self, value, revision, target):
        with self._lock:
            revision = self._configuration_revision(revision, target)
            if revision <= getattr(self, '_tool_revision', 0): return None
            settings = validate_settings(value)
            if self._state.get('session_id') and settings != self._current_settings()['tools']:
                raise gr.Error(SESSION_CONFIG_LOCKED)
            self._assert_idle()
            if not self._state.get('session_id'):
                self._tool_settings = settings
            self._tool_revision = revision
            return '当前会话配置未变化' if self._state.get('session_id') else '已选择，创建会话时生效'

    def freeze_agent_configuration(self, value, instructions, revision, target):
        # The caller holds this lock through reserve_submission. The complete
        # Send snapshot wins over input callbacks still waiting to be handled.
        with self._lock:
            revision = self._configuration_revision(revision, target)
            if revision < getattr(self, '_tool_revision', 0):
                raise gr.Error('工具配置已变化，请重新发送')
            settings = validate_settings(value)
            if not isinstance(instructions, str): raise gr.Error('系统提示词必须为文字')
            if self._state.get('session_id'):
                current = self._current_settings()
                if settings != current['tools'] or instructions != current['instructions']:
                    raise gr.Error(SESSION_CONFIG_LOCKED)
                # An unchanged restored session can still use Send's existing
                # reconnect path. Active or queued local sends stay exclusive.
                if self._running or getattr(self, '_pending_send', None):
                    raise gr.Error('当前会话正在提交或生成，请等待完成或先停止')
            else:
                self._assert_idle()
                self._tool_settings = settings
                self.system_prompt = instructions
            self._tool_revision = revision

    def set_system_prompt(self, new_system_prompt):
        with self._lock:
            self._assert_configuration_owner()
            if self._state.get('session_id'):
                if new_system_prompt != self._current_settings()['instructions']:
                    raise gr.Error(SESSION_CONFIG_LOCKED)
                return
            self._assert_idle()
            self.system_prompt = new_system_prompt
            self.auto_save()

    def save_agent_tools(self, settings):
        with self._lock:
            self._assert_configuration_owner()
            settings = validate_settings(settings)
            if self._state.get('session_id'):
                if settings != self._current_settings()['tools']:
                    raise gr.Error(SESSION_CONFIG_LOCKED)
                return '当前会话配置未变化'
            self._assert_idle()
            self._tool_settings = settings
            return '已选择，创建会话时生效'

    def new_session_from_history(self):
        from modules.agent.tasks import TASKS
        with self._lock:
            active = TASKS.find(self)
            if active is not None or getattr(self, '_background_busy', False):
                raise gr.Error('后台任务仍在执行或保存文件，请完成后再创建独立会话')
            task = getattr(self, '_background_task', None)
            if task is not None and task.done and task.model is not self:
                task.project(self)
                self._background_task = None
            if self._running or getattr(self, '_pending_send', None) or (not self._unavailable and (self._state.get('outcome') not in TERMINAL or self._needs_sync)):
                raise gr.Error('请先停止或确认当前任务状态，再创建独立会话')
            self.auto_save(self.chatbot)
            backup = {name: deepcopy(getattr(self, name)) for name in
                ('history_file_path', '_state', '_session_settings', '_tool_settings', 'system_prompt', '_artifacts', '_cloud_items', '_transcript', '_transcript_preview', '_item_receipts', '_activity_records', 'history', 'chatbot', '_display', '_conversation_id', '_auto_named', '_first_prompt', '_answer_index', '_answer_row', '_needs_sync', '_unavailable', '_connection_mismatch', 'model_name', '_reasoning', '_pending_model_settings', '_input_context', '_installed_inputs', '_input_seed_reference', '_input_messages')}
            self.new_auto_history_filename()
            self._fresh()
            self._fork_previous = backup
            self._notice = '已保留原聊天。下一条消息将携带现有文字引用创建新会话；旧工具状态和文件不继承'
        return deepcopy(self.chatbot), self._status()

    def _cancel(self, generation, *, error_operation=None, error_source='stop'):
        with self._lock:
            if self._state.get('generation') != generation or self._state.get('outcome') in TERMINAL: return
            if self._cancel_sent or not self._state.get('session_id') or not self._state.get('turn_id'): return
            self._cancel_sent = True
            command = {'action': 'cancel', 'session_id': self._state['session_id'], 'turn_id': self._state['turn_id']}
        cancel_key = (self._owner, command['session_id'])
        with _bindings_lock: _cancel_sessions[cancel_key] = _cancel_sessions.get(cancel_key, 0) + 1
        try:
            for message in self._worker(command):
                with self._lock:
                    if self._state.get('generation') != generation: return
                    if message.get('type') == 'error':
                        self._cancel_sent = False
                        self._notice = '尚未确认停止：' + message.get('message', '连接失败')
                        self.record_ui_error(self._notice, source=error_source, operation=error_operation)
                    elif message.get('type') == 'result':
                        if self._state.get('outcome') not in TERMINAL:
                            self._state['outcome'] = message.get('outcome', 'cancel_requested')
                        self._notice = message.get('message', '已请求停止，等待云端确认')
                    self._remember()
        finally:
            with _bindings_lock:
                remaining = _cancel_sessions.get(cancel_key, 0) - 1
                if remaining > 0: _cancel_sessions[cancel_key] = remaining
                else: _cancel_sessions.pop(cancel_key, None)

    def interrupt(self, *, expected_task=None, expected_generation=_UNSPECIFIED_GENERATION):
        operation = uuid4().hex
        with self._lock:
            if expected_generation is not _UNSPECIFIED_GENERATION and self._state.get('generation') != expected_generation:
                return '该轮任务已结束，未停止后续任务'
            if expected_task is not None and (getattr(self, '_background_task', None) is not expected_task
                    or expected_task.done or (expected_generation is not _UNSPECIFIED_GENERATION and self._state.get('generation') != expected_generation)):
                return '该轮任务已结束，未停止后续任务'
            if self._input_context:
                try: self._cancel_input_preparation()
                except OSError:
                    self._notice = '附件准备连接已中断，消息尚未发送'
                    self.record_ui_error(self._notice, source='stop', operation=operation)
                    self.complete_error_operation(operation, source='stop')
            if self._state.get('outcome') in TERMINAL: return self._status('当前轮已结束')
            self._cancel_requested = True
            self._state['outcome'] = 'cancel_requested'
            generation = self._state.get('generation')
            self._pending_actions = []
            self._remember()
        try:
            self._cancel(generation, error_operation=operation)
        finally:
            self.complete_error_operation(operation, source='stop')
        return self._status()

    @staticmethod
    def _message_items(items):
        unique = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str): continue
            if item.get('type') != 'message' or item.get('role') not in ('user', 'assistant'): continue
            content = '\n'.join(part['text'] for part in item.get('content', []) if isinstance(part, dict) and part.get('type') in ('input_text', 'output_text', 'text') and isinstance(part.get('text'), str))
            unique[item['id']] = {'id': item['id'], 'role': item['role'], 'content': content, 'turn_id': item.get('turn_id'), 'phase': item.get('phase')}
        return list(unique.values())

    def _capture_transcript(self, message):
        from modules.agent import transcript
        from modules.agent.tool_logging import known_secrets
        items = message.get('items', [])
        occurrences = {int(key): value for key, value in message.get('item_occurrences', {}).items()}
        for index, item in enumerate(items):
            source = item.get('id') if isinstance(item, dict) else None
            if not isinstance(source, str): source = None
            receipts = {record['receipt'] for record in self._item_receipts if source and record.get('source_id') == source}
            if index not in occurrences and len(receipts) == 1: occurrences[index] = receipts.pop()
        mappings = [dict(record, wire_sha256=digest) for digest, record in self._input_messages.items()] if items else []
        from modules.agent.activity import safe_records
        observed=safe_records(message.get('activity',self._activity_records))
        incoming = transcript.normalize(items, scope_id=self._conversation_id,
            turns=message.get('turns', []), artifacts=list(message.get('transcript_artifacts') or []) + list(message.get('artifacts') or []),
            input_mappings=mappings, capture=message.get('capture', {'items': 'complete' if message.get('sync_complete') is True and isinstance(message.get('items'), list) else 'partial' if items else 'not_collected'}),
            occurrence_ids=occurrences,
            session_id=self._state.get('session_id'), secrets=known_secrets(self),activity=observed)
        authoritative = (message.get('sync_complete') is True and isinstance(message.get('items'), list)
                         and incoming['capture']['items'] == 'complete')
        if self._transcript_preview and (message.get('turn_complete') is True or message.get('history_authoritative')):
            current_turn = self._state.get('turn_id')
            refs = {turn['id'] for turn in incoming['turns'] if turn.get('source_id') == current_turn}
            if not any(entry.get('role') == 'user' and entry.get('turn_ref') in refs for entry in incoming['timeline']):
                # The durable submitted intent has application identity even
                # when this output stream carries no API user-message item.
                user = deepcopy(self._transcript_preview[0])
                receipt = user.pop('id')
                user.update(id=None, turn_id=current_turn, status='completed')
                local = transcript.normalize([user], scope_id=self._conversation_id,
                    session_id=self._state.get('session_id'), occurrence_ids={0: receipt},
                    input_mappings=[{'wire_sha256': hashlib.sha256(user['content'][0]['text'].encode()).hexdigest(), 'files': deepcopy(self._active_input_cards)}],
                    capture={'items': 'partial'}, secrets=known_secrets(self))
                incoming = transcript.merge(local, incoming)
        previous = self._transcript
        if previous is None and 'items' not in message and self.history:
            previous = self.history_document({'history': self.history, 'chatbot': self._display})['agent_transcript']
        snapshot = transcript.merge(previous, incoming, authoritative=authoritative) if previous else incoming
        # Keep actual application receipts privately. After the caller explicitly
        # bridges a null-ID occurrence to an API ID, future GETs can match that
        # exact ID; never bridge by page position or message text.
        receipts = {record['receipt']: record for record in self._item_receipts}
        valid_sources = {entry.get('source_id') for entry in incoming['timeline']}
        for index, receipt in occurrences.items():
            source = items[index].get('id')
            if not isinstance(source, str) or source not in valid_sources: source = None
            receipts[receipt] = {'receipt': receipt, 'source_id': source}
        if len(receipts) > transcript.MAX_RECORDS: raise transcript.TranscriptError('Too many application message receipts')
        if previous:
            old_entries={entry['id']:entry for entry in previous['timeline']}
            for entry in snapshot['timeline']:
                old=old_entries.get(entry['id'])
                if old and old.get('turn_ref')==entry.get('turn_ref'):
                    for key in ('elapsed_ms','output_index'):
                        if key not in entry and key in old:entry[key]=old[key]
        if message.get('turn_complete') is True or message.get('history_authoritative'):
            current_refs = {turn['id'] for turn in snapshot['turns'] if turn.get('source_id') == self._state.get('turn_id')}
            current_users = [entry for entry in snapshot['timeline'] if entry.get('role') == 'user' and entry.get('turn_ref') in current_refs]
            if len(current_users) == 1:
                user = current_users[0]
                timeline = [entry for entry in snapshot['timeline'] if entry is not user]
                position = next((index for index, entry in enumerate(timeline) if entry.get('turn_ref') in current_refs), len(timeline))
                # Repair a late submitted/GET user before its own outputs;
                # preserve an already correct user and unrelated turn order.
                if position < snapshot['timeline'].index(user):
                    timeline.insert(position, user)
                    snapshot['timeline'] = timeline
        self._transcript = snapshot
        if isinstance(message.get('activity'),list):
            self._activity_records=observed
        self._item_receipts = list(receipts.values())
        current_turn = self._state.get('turn_id')
        turn_refs = {turn['id']: turn.get('source_id') for turn in self._transcript['turns']}
        if authoritative or message.get('turn_complete') is True or any(entry['kind'] == 'message' and entry.get('role') == 'user'
                and current_turn and turn_refs.get(entry.get('turn_ref')) == current_turn for entry in incoming['timeline']):
            self._transcript_preview = []
        return authoritative or message.get('turn_complete') is True

    def history_document(self, document):
        """Display data only; private run/cache bindings never enter JSON."""
        from modules.agent import transcript
        from modules.agent.tool_logging import known_secrets
        secrets = known_secrets(self)
        if self._transcript is None or (not self._transcript['timeline'] and self._input_seed_reference is not None):
            reference = self._legacy_document(document)
            if self._transcript_preview:
                reference = self._legacy_document(dict(document, history=self.history[:-2], chatbot=_rows(self.history[:-2])))
            snapshot = transcript.migrate(reference, scope_id=self._conversation_id, secrets=secrets)['agent_transcript']
        else:
            snapshot = deepcopy(self._transcript)
        if self._transcript_preview:
            preview = deepcopy(self._transcript_preview)
            if self._answer_index is not None and self._answer_index < len(self.history):
                preview[-1]['content'] = [{'type': 'output_text', 'text': self.history[self._answer_index]['content']}]
            mappings = [{'wire_sha256': hashlib.sha256(preview[0]['content'][0]['text'].encode()).hexdigest(), 'files': deepcopy(self._active_input_cards)}]
            occurrences = {index: item['id'] for index, item in enumerate(preview)}
            for item in preview: item['id'] = None
            incoming = transcript.normalize(preview, scope_id=self._conversation_id, input_mappings=mappings,
                                            capture={'items': 'partial'}, secrets=secrets, occurrence_ids=occurrences)
            snapshot = transcript.merge(snapshot, incoming)
        return transcript.migrate(dict(document, history_format={'name': 'chuanhu', 'version': 2}, agent_transcript=snapshot),
                                  scope_id=self._conversation_id, secrets=secrets)

    @staticmethod
    def _legacy_document(document):
        # Old ordinary histories store native image cells separately from text.
        # Their inert filenames remain in chatbot for migrate's metadata cards;
        # image paths are never converted to prompts or opened by this adapter.
        if isinstance(document, dict) and 'agent_transcript' not in document and isinstance(document.get('history'), list):
            history = [item for item in document['history'] if not (isinstance(item, dict) and item.get('role') == 'image')]
            if len(history) != len(document['history']): return dict(document, history=history)
        return document

    def _load_document(self, wire, *, scope_id, imported=False):
        from modules.agent import transcript
        from modules.agent.tool_logging import known_secrets
        if len(wire.encode()) > transcript.MAX_DOCUMENT_BYTES: raise transcript.TranscriptError('History exceeds the document size limit')
        try: document = json.loads(wire)
        except (ValueError, RecursionError): raise transcript.TranscriptError('Invalid history JSON') from None
        document = transcript.migrate(self._legacy_document(document), scope_id=scope_id, secrets=known_secrets(self))
        return transcript.loads(transcript.serialize(document), scope_id=scope_id, secrets=known_secrets(self), imported=True) if imported else document

    def _transcript_messages(self):
        return [dict(id=entry['id'], role=entry['role'], turn_id=entry.get('turn_ref'),
                     content='\n'.join(part['text'] for part in entry['content'] if part['type'] == 'text'))
                for entry in (self._transcript or {}).get('timeline', []) if entry['kind'] == 'message']

    def _sync_items(self, items):
        self._cloud_items = self._message_items(items)
        from modules.agent.message_files import group_turn_messages
        source = self._transcript_messages() if self._transcript is not None else self._cloud_items
        self.history = [{'role': item['role'], 'content': self._project_input_text(item['content']) if item['role']=='user' else item['content']} for item in group_turn_messages(source)]
        if not source and self._input_seed_reference is not None:
            # The empty session was created only to prepare files. These local
            # references have not been sent yet and must survive reconnect.
            self.history = deepcopy(self._input_seed_reference)
        if any(item['role']=='user' for item in source): self._input_seed_reference = None
        self._display = _rows(self.history)
        self._answer_index = len(self.history) - 1 if self.history and self.history[-1]['role'] == 'assistant' else None
        self._answer_row = len(self._display) - 1 if self._answer_index is not None else None
        # Keep the live text destination after a user-only authoritative
        # snapshot. Ownership comes from the canonical turn, not row text.
        current_refs = {turn['id'] for turn in (self._transcript or {}).get('turns', [])
                        if turn.get('source_id') == self._state.get('turn_id') and self._state.get('turn_id')}
        current_users = [item for item in source if item['role'] == 'user' and item.get('turn_id') in current_refs]
        if current_refs and self._answer_index is not None and source[-1].get('turn_id') not in current_refs:
            self._answer_index = self._answer_row = None
        if (self._state.get('outcome') not in TERMINAL and len(current_users) == 1
                and source and source[-1] is current_users[0]
                and not any(item['role'] == 'assistant' and item.get('turn_id') in current_refs for item in source)):
            self.history.append({'role': 'assistant', 'content': ''})
            self._answer_index, self._answer_row = len(self.history) - 1, len(self._display) - 1
            # Preserve None for canonical row alignment until text arrives.

    def _log_final_answer(self, message):
        if (message.get('type') != 'result' or self._state.get('outcome') not in TERMINAL
                or message.get('sync_complete') is False
                or not any(key in message for key in ('text', 'items'))):
            return
        turn_id = self._state.get('turn_id')
        if not turn_id:
            return
        if isinstance(message.get('items'), list):
            from modules.agent.message_files import group_turn_messages
            if self._transcript is not None:
                current_refs = {turn['id'] for turn in self._transcript['turns'] if turn.get('source_id') == turn_id}
                current_items = [item for item in self._transcript_messages()
                                 if item.get('turn_id') in current_refs and item['role'] == 'assistant']
            else:
                current_items = [item for item in self._message_items(message['items'])
                                 if item.get('turn_id') == turn_id and item['role'] == 'assistant']
            answer = '\n\n'.join(item['content'] for item in group_turn_messages(current_items) if item['content'])
        else:
            answer = message.get('text', '') if message.get('turn_id') == turn_id else ''
        if not answer:
            return
        key = (self._state.get('session_id'), turn_id)
        digest = hashlib.sha256(answer.encode()).hexdigest()
        logged = getattr(self, '_logged_answers', {})
        if logged.get(key) == digest:
            return
        logging.info('回答为：%s', answer)
        logged[key] = digest
        self._logged_answers = logged

    def _log_tool_results(self, message, artifacts=()):
        from modules.agent.tool_logging import ToolLog
        if not hasattr(self, '_tool_log'):
            self._tool_log = ToolLog()
        self._tool_log.observe(self, message, artifacts)

    def _accept(self, message, generation, *, restoring=False, error_operation=None, scope=None, log_updates=None):
        if self._local_history_deleted(): return False
        if scope is not None and not scope.current(self): return False
        if (self._retired and not getattr(self, "_task_backend", False)) or self._state.get('generation') != generation: return False
        session = message.get('session_id')
        if session and self._state.get('session_id') and session != self._state['session_id']: return False
        turn = message.get('turn_id')
        if turn and self._state.get('turn_id') and turn != self._state['turn_id']:
            if not restoring: return False
            # An earlier stop belongs to the old exact turn, not a newer turn
            # discovered during cross-browser recovery.
            self._cancel_requested = self._cancel_sent = False
        for key in ('session_id', 'turn_id', 'baseline_turn_ids', 'submission_started', 'observation'):
            if key in message and message[key] is not None: self._state[key] = message[key]
        if message.get('submission_started') is True:
            self._draft_submitted = True
            if self._input_stager is not None:
                # Any turn can edit earlier sandbox files, including uploads
                # whose own message was cancelled before submission.
                self._input_stager.mark_submitted(self._installed_inputs)
        if getattr(self, '_draft_submitted', False) and not getattr(self, '_draft_acknowledged', False) and message.get('turn_id'):
            self._draft_acknowledged = True
            self._remove_input_selection(getattr(self, '_draft_input_ids', ()))
            self._input_context = None
            self._release_input_stager()
        if (message.get('submission_started') is True
                and getattr(self, '_history_submission_saved_generation', None) != generation):
            self.chatbot = deepcopy(self._display)
            self.auto_save(self.chatbot)
            self._history_submission_saved_generation = generation
        # Ephemeral public output activity, scoped by the generation/session/turn
        # guards above. File-only progress does not change the text stream phase.
        if type(message.get('public_text_streaming')) is bool:
            self._state['public_text_streaming'] = message['public_text_streaming']
        elif isinstance(message.get('items'), list):
            self._state.pop('public_text_streaming', None)
        timing = safe_timing(message.get('completion_timing'))
        if timing is not None:
            self._completion_timing = timing
            if message.get('type') == 'result': mark_completion(timing, 'result_received')
        outcome = message.get('outcome')
        if outcome and (not self._cancel_requested or outcome in TERMINAL): self._state['outcome'] = outcome
        # Publish already-known file metadata in the same snapshot as body.
        # Provider paths never become download paths; byte work stays separate.
        # Nonterminal history metadata retains its existing inert-card path.
        from modules.agent.artifacts import preparing_artifacts
        metadata = list(message.get('artifact_metadata') or [])
        if message.get('type') == 'result' and self._state.get('outcome') in TERMINAL:
            metadata += list(message.get('transcript_artifacts') or [])
        known = preparing_artifacts(metadata, session_id=self._state.get('session_id'), turn_id=self._state.get('turn_id'))
        if known:
            message = dict(message, artifacts=known + list(message.get('artifacts') or []))
        items_complete = False
        if any(isinstance(message.get(key), list) for key in ('items', 'artifacts', 'transcript_artifacts')):
            try: items_complete = self._capture_transcript(message)
            except ValueError as error:
                self._needs_sync = True
                self._notice = '部分历史缺少稳定消息身份或无法安全合并，已有记录已保留；请重新连接读取完整记录'
                self.record_ui_error(self._notice, operation=error_operation)
                raise gr.Error(self._notice) from error
        if (items_complete or message.get('history_authoritative')) and isinstance(message.get('items'), list):
            self._sync_items(message['items'])
            if items_complete:
                self._needs_sync = False
                self._resolve_sync_warning(error_operation)
        elif self._answer_index is not None and 'text' in message:
            if isinstance(message.get('items'), list):
                known = {item['id']: item for item in self._cloud_items}
                known.update((item['id'], item) for item in self._message_items(message['items']))
                self._cloud_items = list(known.values())
            self.history[self._answer_index]['content'] = str(message['text'])
            self._display[self._answer_row][1] = self.history[self._answer_index]['content']
            if message.get('type') == 'result' and self._state.get('outcome') in TERMINAL and not isinstance(message.get('items'), list):
                self._transcript = self.history_document({'history': self.history, 'chatbot': self._display})['agent_transcript']
                self._transcript_preview = []
        if message.get('sync_complete') is False or (message.get('sync_complete') is True and not items_complete):
            self._needs_sync = True
            self._notice = _SYNC_NOTICE
            operation = error_operation or getattr(self, '_predict_error_operation', None) or self._state.get('generation')
            self._sync_notice_receipt = (self._owner, self._conversation_id, self._state.get('generation'), operation)
            self.record_ui_error(_SYNC_WARNING, operation=operation)
        if 'required_actions' in message:
            self._pending_actions = [] if self._cancel_requested else deepcopy(message['required_actions'])
        if self._state.get('outcome') in TERMINAL: self._pending_actions = []
        settings = message.get('settings') or {}
        if restoring and settings.get('agent') and self._session_settings:
            agent = settings['agent']
            self.model_name = agent.get('model', self.model_name)
            self._reasoning = normalize_reasoning((agent.get('reasoning') or {}).get('effort'))
            self._session_settings.update(model=self.model_name, reasoning=self._reasoning)
            self._repair_reasoning_choice()
        if isinstance(message.get('artifacts'), list):
            self._merge_artifacts(message['artifacts'])
        self._record_message_error(message, operation=error_operation)
        should_log = not restoring if log_updates is None else log_updates
        sync_unconfirmed = message.get('sync_complete') is True and not items_complete
        if should_log:
            if not sync_unconfirmed: self._log_final_answer(message)
            self._log_tool_results(message, self._artifacts if 'artifacts' in message else ())
        if message.get('turn_complete') is True and message.get('type') == 'result' and items_complete:
            self._state['turn_committed'] = {'session_id': self._state.get('session_id'), 'turn_id': self._state.get('turn_id')}
        if (message.get('type') == 'result' and self._state.get('outcome') in TERMINAL
                and message.get('sync_complete') is not False and not sync_unconfirmed
                and (message.get('sync_complete') is True or message.get('history_authoritative') is True or 'text' in message)
                and self._state.get('session_id') and self._state.get('turn_id')):
            # Private receipt: terminal progress is not authoritative completion.
            # Persist alongside run state so a new view/process can distinguish
            # a historical final snapshot from the first reconciled result.
            self._state['log_reconciled'] = {'session_id': self._state['session_id'], 'turn_id': self._state['turn_id']}
        timing = getattr(self, '_completion_timing', None)
        if message.get('type') == 'result': mark_completion(timing, 'persistence_start')
        self._remember()
        if getattr(self, '_task_backend', False):
            import time
            now = time.monotonic()
            identity = (self._state.get('session_id'), self._state.get('turn_id'), self._state.get('submission_started'))
            if (identity != getattr(self, '_last_persist_identity', None) or self._state.get('outcome') in TERMINAL
                    or now - getattr(self, '_last_stream_save', 0) >= .5):
                self.chatbot = deepcopy(self._display)
                self.auto_save(self.chatbot)
                self._last_stream_save, self._last_persist_identity = now, identity
        if message.get('type') == 'result': mark_completion(timing, 'persistence_end')
        return True

    def _merge_artifacts(self, records):
        records = deepcopy(records)
        root = Path(tempfile.gettempdir()).resolve()
        for record in records:
            if record.get('status') != 'ready': continue
            path = Path(record.get('path', ''))
            if path.is_symlink() or not path.is_file() or not ((root in path.resolve().parents and any(parent.name.startswith('chuanhu-agent-artifacts-') for parent in path.parents)) or (Path(shared.chuanhu_path).resolve() / 'agent_data' / 'artifacts' / hashlib.sha256(self.user_name.encode()).hexdigest()) in path.resolve().parents):
                record.update(status='failed', error='文件缓存校验失败，请重新获取')
                record.pop('path', None)
        previous = {record['id']: record for record in self._artifacts}
        for record in records:
            if not isinstance(record.get('id'), str): continue
            old = previous.get(record['id'])
            if (old and old.get('status') == 'ready' and record.get('status') == 'preparing'
                    and old.get('session_id') == record.get('session_id')
                    and old.get('turn_id') == record.get('turn_id')):
                path = Path(old.get('path', ''))
                trusted_root = Path(shared.chuanhu_path).resolve() / 'agent_data' / 'artifacts' / hashlib.sha256(self.user_name.encode()).hexdigest()
                if (not path.is_symlink() and path.is_file() and
                        ((root in path.resolve().parents and any(parent.name.startswith('chuanhu-agent-artifacts-') for parent in path.parents))
                         or trusted_root in path.resolve().parents)):
                    record = dict(old, **{key:value for key,value in record.items() if key not in ('status','path','error')})
            previous[record['id']] = record
        self._artifacts = list(previous.values())

    def _file_runner(self):
        # Capture the authorized connection and interpreter transport once.
        # A later view/generation cannot retarget this file operation.
        connection = deepcopy(self._file_connection if getattr(self, '_file_connection_generation', None) == self._state.get('generation') and getattr(self, '_file_connection', None) else self._connection())
        transport, owner = worker_messages, self.user_name
        def run(command):
            yield from transport(dict(command, connection=connection, owner=owner))
        from modules.agent.tool_logging import ToolLog
        from types import SimpleNamespace
        if not hasattr(self, '_tool_log'): self._tool_log = ToolLog()
        logger, tools, key = self._tool_log, deepcopy(self._tool_settings), self._connection_key
        def log_files(job, records):
            target = SimpleNamespace(_state={'session_id':job['session_id'], 'turn_id':job['turn_id']},
                _tool_settings=tools, _connection_key=key, _tool_log_key=connection.get('api_key'))
            logger.observe(target, {'session_id':job['session_id']}, records)
        run.log_artifacts = log_files
        run.connection_ref = {key: connection.get(key) for key in ('base_url', 'organization', 'project')}
        return run

    def _queue_files(self, artifact_ids=None, *, turn_id=None, log_updates=True):
        from modules.agent.file_jobs import FILE_JOBS, create_job, jobs_for
        store = self._store()
        with store.history_guard(self._owner, self.history_file_path):
            if self._local_history_deleted() or not self._owner or (artifact_ids is None and self._state.get('outcome') not in TERMINAL): return
            if self._connection_mismatch: raise gr.Error('当前连接配置与原会话不同，请恢复原配置后重试文件')
            runner = self._file_runner()
            target_turn = turn_id or self._state.get('turn_id')
            source = next((job for job in jobs_for(store, self._owner, self._conversation_id)
                if job['session_id'] == self._state.get('session_id') and job['turn_id'] == target_turn), None)
            if source and source['connection_ref'] != runner.connection_ref:
                raise gr.Error('当前连接配置与原会话不同，请恢复原配置后重试文件')
            job = create_job(store, owner=self._owner, conversation=self._conversation_id,
                history=self.history_file_path, session=self._state.get('session_id'),
                turn=target_turn, generation=source['generation'] if source else self._state.get('generation'),
                connection_ref=runner.connection_ref, artifact_ids=artifact_ids, cache_owner=hashlib.sha256(self.user_name.encode()).hexdigest(), log_updates=log_updates)
        if job:
            FILE_JOBS.submit(store, job, runner, Path(HISTORY_DIR) / self.user_name)
        return job

    def refresh_files(self, *, resume=True):
        from modules.agent.file_jobs import FILE_JOBS, jobs_for, overlay_model
        with self._lock:
            if self._local_history_deleted() or not self._owner: return
            overlay_model(self)
            if not resume or self._connection_mismatch: return
            jobs = [job for job in jobs_for(self._store(), self._owner, self._conversation_id)
                if job['status'] in ('pending', 'running') and job['session_id'] == self._state.get('session_id')
                and job['connection_ref'] == self._connection_reference()]
            if jobs:
                runner = self._file_runner()
                for job in jobs:
                    FILE_JOBS.submit(self._store(), job, runner, Path(HISTORY_DIR) / self.user_name)

    def _download(self, generation, artifact_ids=None, *, error_operation=None, scope=None, log_updates=True):
        with self._lock:
            scope = scope or self._execution_scope()
            if not scope.current(self) or self._state.get('generation') != generation: return
            self._queue_files(artifact_ids, log_updates=log_updates)
            self.refresh_files(resume=False)
            frame = deepcopy(self._display), self._status()
        if scope.current(self): yield frame

    def retry_artifact(self, artifact_id, *, error_operation=None):
        from modules.agent.file_jobs import jobs_for, records_for
        with self._lock:
            if self._retired: return
            scope = OperationScope.capture(self)
            self.refresh_files(resume=False)
            record = next((record for record in self._artifacts if record['id'] == artifact_id), None)
            if record is None: raise gr.Error('文件不属于当前会话')
            if (self._state.get('session_id'), artifact_id) in self._active_file_retries:
                raise gr.Error('文件正在重新获取')
            if any(job['status'] in ('pending', 'running') and job['artifact_ids'] == [artifact_id]
                    for job in jobs_for(self._store(), self._owner, self._conversation_id)):
                raise gr.Error('文件正在重新获取')
            turn = record.get('turn_id')
            if not turn:
                # Unassociated metadata retains the source job's exact target;
                # this is a retry filter, not an assignment to a message.
                with self._store()._connect() as db:
                    row = db.execute('SELECT sequence FROM artifact_receipts WHERE owner=? AND conversation=? AND session=? AND artifact=?',
                        (self._owner, self._conversation_id, self._state.get('session_id'), artifact_id)).fetchone()
                if row:
                    turn = next((job['turn_id'] for job in jobs_for(self._store(), self._owner, self._conversation_id) if job['sequence'] == row[0]), None)
            if not turn: raise gr.Error('文件归属尚未确认，请重新连接后重试')
            self._queue_files([artifact_id], turn_id=turn)
            frame = deepcopy(self._display), self._status()
        if scope.current(self): yield frame

    def _network_request(self, inputs):
        commands = {'开网': True, '开启联网': True, '允许联网': True, '打开联网': True,
                    '关网': False, '关闭联网': False, '禁用联网': False, '关闭云端联网': False}
        normalized = inputs.strip().strip('。！!').removeprefix('请')
        if normalized not in commands: return None
        with self._lock:
            self._assert_configuration_owner()
            desired = commands[normalized]
            word = '开启' if desired else '关闭'
            self._pending_network = None
            if self._state.get('session_id'):
                self._notice = SESSION_CONFIG_LOCKED
                raise gr.Error(SESSION_CONFIG_LOCKED)
            else:
                self._assert_idle()
                self._tool_settings = validate_settings(dict(self._tool_settings, network=desired))
                self._tool_ui_patch = {'token': uuid4().hex, 'conversation': self._conversation_id,
                                       'revision': self._tool_revision, 'network': desired}
                self._notice = f'新会话的云端执行环境联网已设为{word}；请输入任务。内置网页搜索单独配置'
            return deepcopy(self._display), self._status()

    def predict(self, inputs, chatbot, use_websearch=False, files=None, reply_language=None, should_check_token_count=True):
        from modules.agent.message_files import decode_rows
        chatbot = decode_rows(chatbot, self._conversation_id)
        if not self._owner: raise gr.Error('需要在当前登录会话中发送')
        if self._failed_preparation_environment(): raise gr.Error(self._failed_environment_notice())
        input_records = self._take_input_files(files)
        if not isinstance(inputs, str) or (not inputs.strip() and not input_records): raise gr.Error('请输入文字任务或添加附件')
        inputs = inputs.strip() or '请查看上传的附件。'
        display_input = inputs
        if use_websearch: raise gr.Error('当前 Agent 不支持原外部搜索入口，请使用 Agent 工具配置')
        if self._needs_sync:
            yield from self.reconnect()
            chatbot = self.chatbot
        network_result = self._network_request(inputs) if not input_records else None
        if network_result is not None:
            self._draft_submitted = True  # A local configuration command was handled.
            self._draft_acknowledged = True
            yield network_result
            return
        with self._lock:
            if (self._retired and not getattr(self, '_task_backend', False)) or (self._display and display_signature(chatbot) != display_signature(self._display)): raise gr.Error('聊天内容已变化，请在当前聊天中重新发送')
            self._assert_idle()
            reservation = (self._owner, self._state.get('session_id') or self._key()[1])
            with _bindings_lock:
                if reservation in _session_locks or reservation in _cancel_sessions:
                    raise gr.Error('另一窗口正在提交此会话，请等待该任务结束或重新连接')
                _session_locks[reservation] = self
            settings = self._current_settings()
            if self._state.get('session_id') and self._session_settings:
                # Saved defaults apply only after an explicit fork. Continuing
                # the original chat always sends its actual effective settings.
                settings = deepcopy(self._session_settings)
            if input_records and not settings['tools']['code_execution']:
                with _bindings_lock: _session_locks.pop(reservation, None)
                raise gr.Error('当前会话没有文件执行环境，请启用后按新配置新建' if self._state.get('session_id') else '请先在工具设置中开启代码与文件执行')
            self._draft_input_ids = tuple(record.input_id for record in input_records)
            previous_input_cards = deepcopy(self._active_input_cards)
            previous = (deepcopy(self._state), deepcopy(self.history), deepcopy(self._display), self._answer_index, self._answer_row)
            reference = deepcopy(self._input_seed_reference) if self._input_seed_reference is not None else _text_history(self.history) if not self._state.get('session_id') else None
            if not self._state.get('session_id') or self._input_seed_reference is not None: self._first_prompt = display_input
            generation = uuid4().hex
            self._state = dict(self._state, generation=generation, turn_id=None, outcome='starting', baseline_turn_ids=None, submission_started=False, public_text_streaming=False)
            self._display = [list(row) for row in chatbot or []] + [[display_input, '']]
            self.history.extend([{'role': 'user', 'content': display_input}, {'role': 'assistant', 'content': ''}])
            self._answer_index, self._answer_row = len(self.history) - 1, len(self._display) - 1
            self._active_input_cards = [{'id':record.input_id,'name':record.name,'size':record.size} for record in input_records]
            self._transcript_preview = [dict(id='local-' + generation + '-' + role, type='message', role=role,
                turn_id='local-' + generation, content=[{'type': 'input_text' if role == 'user' else 'output_text', 'text': display_input if role == 'user' else ''}])
                for role in ('user', 'assistant')]
            self._running = True
            self._draft_submitted = self._draft_acknowledged = False
            self._cancel_requested = self._cancel_sent = False
            self._notice = ''
            command = {'action': 'run', 'prompt': inputs, 'model': self.model_name, 'reasoning': self._reasoning,
                       'instructions': settings['instructions'], 'tool_settings': deepcopy(settings['tools']),
                       'session_id': self._state.get('session_id'), 'run_id': generation, 'history_reference': reference,
                       'observation': deepcopy(self._state.get('observation'))}
            scope = self._execution_scope(history_target=True)
        started = terminal = False
        update_error = False
        try:
            from modules.agent.tool_logging import safe_text, known_secrets
            logging.info('用户%s的输入为：%s', safe_text(self.user_name, 100),
                         safe_text(inputs, secrets=known_secrets(self)))
            if getattr(self, '_task_backend', False):
                self.chatbot = deepcopy(self._display)
                self.auto_save(self.chatbot)  # durable intent before POST/attachment preparation
            yield deepcopy(self._display), self._status()
            with self._lock:
                if self._cancel_requested: return
            self._apply_next_model(generation)
            settings.update(model=self.model_name, reasoning=self._reasoning)
            installed_inputs = yield from self._prepare_input_frames(input_records, generation, settings, reference)
            with self._lock:
                if self._cancel_requested: return
                settings.update(model=self.model_name, reasoning=self._reasoning)
                command.update(model=self.model_name, reasoning=self._reasoning)
                command['session_id'] = self._state.get('session_id')
                if installed_inputs:
                    command['input_files'] = installed_inputs
                if installed_inputs or reference:
                    from modules.agent.runtime import format_input_text
                    self._remember_input_message(format_input_text(inputs, reference, installed_inputs), display_input, installed_inputs)
                started = True
                if getattr(self, "_background_busy", False): self._task_phase = "receiving"
                self._session_settings = settings
                self._remember()
            for message in self._worker(command):
                with self._lock:
                    if not scope.current(self): return
                    if not self._accept(message, generation, scope=scope): continue
                    detail = str(message.get('message') or '')
                    if message.get('type') == 'error':
                        if self._state.get('outcome') not in TERMINAL: self._state['outcome'] = 'incomplete' if self._state.get('session_id') else 'uncertain'
                        terminal = self._state.get('outcome') in TERMINAL
                        self._notice = detail
                    elif message.get('type') == 'result': terminal = self._state.get('outcome') in TERMINAL
                    if self._state.get('outcome') in TERMINAL:
                        terminal = True
                        # 先持久化完整回答，再允许新一轮或切换历史，避免旧生成器丢失最后一帧。
                        self.chatbot = deepcopy(self._display)
                        if not getattr(self, '_task_backend', False): self.auto_save(self.chatbot)
                        self._running = False
                        with _bindings_lock:
                            if _session_locks.get(reservation) is self: _session_locks.pop(reservation, None)
                            input_reservation = getattr(self, '_input_session_reservation', None)
                            if input_reservation is not None and _session_locks.get(input_reservation) is self: _session_locks.pop(input_reservation, None)
                            self._input_session_reservation = None
                if self._cancel_requested: self._cancel(generation, error_operation=getattr(self, '_predict_error_operation', None) or generation, error_source=None)
                yield deepcopy(self._display), self._status(detail)
            if not scope.current(self): return
        except (ModelUpdateError, InputPreparationStopped) as error:
            with self._lock:
                update_error = True
                self._notice = '消息未发送：' + str(error)
                preparation = (self._input_context or {}).get('resume_state') or {}
                if not self._cancel_requested and preparation.get('outcome') != 'cancelled':
                    self.record_ui_error(self._notice)
        finally:
            with self._lock:
                if scope.current(self):
                    if not started:
                        self._transcript_preview = []
                        self._active_input_cards = previous_input_cards
                        rollback = self._input_rollback_state(previous[0], generation)
                        self._state, self.history, self._display, self._answer_index, self._answer_row = (rollback, *previous[1:])
                        # The first frame already displayed this user message and
                        # cleared its draft. Keep it copyable locally, while the
                        # submitted history/state roll back truthfully.
                        self._display.append([display_input, ''])
                        # This owned rollback changes generation, not the visit.
                        scope = self._execution_scope(history_target=True)
                        for error_record in getattr(self, '_ui_errors', []):
                            if (error_record['operation'] == (getattr(self, '_predict_error_operation', None) or generation) and error_record['owner'] == self._owner
                                    and error_record['conversation'] == self._conversation_id):
                                error_record['generation'] = self._state.get('generation')
                        if self._cancel_requested: self._notice = '本轮尚未发送，已取消'
                    elif not terminal and self._state.get('outcome') not in TERMINAL:
                        self._state['outcome'] = 'incomplete' if self._state.get('session_id') else 'uncertain'
                    self._running = False
                    with _bindings_lock:
                        if _session_locks.get(reservation) is self: _session_locks.pop(reservation, None)
                        input_reservation = getattr(self, '_input_session_reservation', None)
                        if input_reservation is not None and _session_locks.get(input_reservation) is self:
                            _session_locks.pop(input_reservation, None)
                        self._input_session_reservation = None
                    self.chatbot = deepcopy(self._display)
                    if not (terminal and getattr(self, '_task_backend', False) and not self._needs_sync and not self._state.get('persistence_failed')):
                        self._remember()
                    if not started and self._input_context:
                        preparation = self._input_context.get('resume_state') or {}
                        if preparation.get('outcome') == 'preparing': self._refresh_input_journal()
                        self.auto_save(self.chatbot)
                    if started:
                        if not (terminal and getattr(self, '_task_backend', False) and not self._state.get('persistence_failed')):
                            self.auto_save(self.chatbot)
                        if self._fork_previous and self._state.get('outcome') == 'not_started' and not self._state.get('session_id'):
                            # Keep the failed attempt as a separate local record,
                            # and return control to the original preserved session.
                            failed_conversation = self._conversation_id
                            for name, value in self._fork_previous.items(): setattr(self, name, value)
                            for error_record in getattr(self, '_ui_errors', []):
                                if error_record['operation'] == (getattr(self, '_predict_error_operation', None) or generation) and error_record['conversation'] == failed_conversation and error_record['owner'] == self._owner:
                                    error_record.update(conversation=self._conversation_id, generation=self._state.get('generation'))
                            self._fork_previous = None
                            self._notice = '新会话未创建，已回到原会话；本次未发送内容另存于本地历史，新配置仍已保存'
                        elif self._state.get('session_id'):
                            self._fork_previous = None
        if scope.current(self) and terminal and self._state.get('session_id') and not self._state.get('persistence_failed'):
            with self._lock: self._queue_files()
        if scope.current(self) and (update_error or self._notice.startswith('新会话未创建')):
            yield deepcopy(self._display), self._status()

    def observe_history(self, *, error_operation=None):
        """Observe trusted history through GET/SSE; never execute tool actions."""
        with self._lock:
            if self._retired or not self._owner or not self._needs_sync: return
            observer = error_operation or uuid4().hex
            self._history_epoch = observer
            if self._connection_mismatch:
                self.record_ui_error('当前连接配置与原会话不同，未读取云端历史', operation=observer)
                return
            if not self._state.get('session_id') and self._state.get('generation') and self._state.get('outcome') == 'starting':
                self._state['outcome'] = 'uncertain'
            session = self._state.get('session_id')
            original_generation = self._state.get('generation')
            resume_logs = self._state.get('log_reconciled') != {'session_id': self._state.get('session_id'), 'turn_id': self._state.get('turn_id')}
            restored_turn = self._state.get('turn_id')
            if not session and self._state.get('outcome') != 'uncertain': return
            if not session and not original_generation: return
            target = self._conversation_id
            generation = original_generation or uuid4().hex
            self._state['generation'] = generation
            self._history_observing = observer
            self._history_epoch = observer
            def cancelled():
                return self._retired or self._conversation_id != target or self._state.get('generation') != generation or getattr(self, '_history_observing', None) != observer
            command = {'action': 'observe' if session else 'observe_unknown', 'session_id': session,
                       'turn_id': self._state.get('turn_id'), 'run_id': original_generation,
                       'baseline_turn_ids': self._state.get('baseline_turn_ids'),
                       'submission_started': self._state.get('submission_started') is True,
                       'observation': self._recovery_observation(),
                       '_observe_cancel': cancelled}
        try:
            for message in self._worker(command):
                with self._lock:
                    if cancelled(): return
                    if message.get('type') == 'error':
                        self._record_message_error(message, operation=observer)
                        self._needs_sync = True
                        self._unavailable = True
                        # Never replace preserved history with a partial error snapshot.
                        chat = deepcopy(self._display)
                    else:
                        if not self._accept(message, generation, restoring=True, error_operation=observer, log_updates=resume_logs or bool(message.get('turn_id') and message['turn_id'] != restored_turn)): continue
                        self.chatbot = deepcopy(self._display)
                        chat = deepcopy(self._display)
                if self._cancel_requested and message.get('type') != 'error':
                    self._cancel(generation, error_operation=observer, error_source=None)
                late_stop_failure = self._cancel_requested and self.has_ui_error(observer)
                if late_stop_failure:
                    with self._lock:
                        if not cancelled(): self._needs_sync = self._unavailable = True
                yield chat, self._status()
                if message.get('type') == 'error' or late_stop_failure: return
            if not cancelled() and self._state.get('outcome') in TERMINAL and self._state.get('session_id'):
                yield from self._download(generation, error_operation=observer, log_updates=resume_logs or self._state.get('turn_id') != restored_turn)
        finally:
            with self._lock:
                if not cancelled():
                    self._remember()
                    self.auto_save(self.chatbot)
                    self._history_observing = None

    def _recovery_observation(self):
        receipt = self._state.get('observation')
        if receipt is not None: return deepcopy(receipt)
        session, current = self._state.get('session_id'), self._state.get('turn_id')
        if not session or not current: return None
        transcript = self._transcript or {}
        turns = {turn['id']: turn for turn in transcript.get('turns', [])}
        root = next((turn for turn in turns.values() if turn.get('source_id') == current), {})
        records, parts = [], []
        for entry in transcript.get('timeline', []):
            source = entry.get('source_id')
            if not source or turns.get(entry.get('turn_ref'), {}).get('source_id') != current: continue
            item = {'id': source, 'turn_id': current, 'status': entry.get('status')}
            group = None
            if entry.get('kind') == 'message':
                item.update(type='message', role=entry['role'], content=deepcopy(entry['content']))
                group = 'content'
            elif entry.get('kind') == 'summary':
                item.update(type='reasoning', summary=deepcopy(entry['content']))
                group = 'summary'
            elif entry.get('source_type'): item['type'] = entry['source_type']
            else: continue
            records.append(item)
            if group:
                shapes = [[group, index, 'summary_text' if group == 'summary' else None, True]
                          for index, part in enumerate(entry['content']) if isinstance(part.get('text'), str)]
                parts.append({'item_id': source, 'shapes': shapes})
        identity = [session, current, root['agent_source_id']] if root.get('agent_source_id') else None
        # Even an old receipt with no public body anchors the known turn. Never
        # claim facts not present in the private binding/transcript.
        return {'version': 1, 'session_id': session, 'turns': [{'turn_id': current,
            'root_identity': identity, 'items': records, 'parts': parts, 'unverifiable': False}]}

    def reconnect(self):
        empty_result = None
        with self._lock:
            if self._running or self._retired: raise gr.Error('当前连接仍在运行')
            if getattr(self, '_connection_mismatch', False): raise gr.Error(self._notice)
            if self._input_context and self._refresh_input_journal():
                raise gr.Error(self._notice)
            if not self._state.get('session_id') and self._state.get('generation') and self._state.get('outcome') == 'starting':
                self._state['outcome'] = 'uncertain'
            session = self._state.get('session_id')
            if not session and self._state.get('outcome') != 'uncertain':
                empty_result = (deepcopy(self._display), self._status())
            else:
                generation = self._state.get('generation') or uuid4().hex
                self._state['generation'] = generation
                self._running = True
                self._notice = ''
                command = {'action': 'recover' if session else 'recover_unknown', 'session_id': session,
                           'turn_id': self._state.get('turn_id'), 'run_id': generation,
                           'baseline_turn_ids': self._state.get('baseline_turn_ids'), 'submission_started': self._state.get('submission_started') is True,
                           'tool_settings': (self._session_settings or {}).get('tools', self._tool_settings),
                           'observation': self._recovery_observation()}
            resume_logs = self._state.get('log_reconciled') != {'session_id': self._state.get('session_id'), 'turn_id': self._state.get('turn_id')}
            restored_turn = self._state.get('turn_id')
            scope = self._execution_scope(history_target=True)
        if empty_result is not None:
            yield empty_result
            return
        try:
            yield deepcopy(self._display), '正在恢复历史'
            for message in self._worker(command):
                with self._lock:
                    if not scope.current(self): return
                    if message.get('type') == 'error':
                        if (message.get('diagnostics') or {}).get('status_code') in (403, 404, 410): self._unavailable = True
                        self._notice = '历史尚未同步完整，现有内容已保留：' + message.get('message', '')
                        self._needs_sync = True
                        message = {key: value for key, value in message.items() if key not in ('outcome', 'items', 'sync_complete')}
                    if not self._accept(message, generation, restoring=True, scope=scope, log_updates=resume_logs or bool(message.get('turn_id') and message['turn_id'] != restored_turn)): continue
                    self.chatbot = deepcopy(self._display)
                    if self._state.get('outcome') in TERMINAL:
                        self.auto_save(self.chatbot)
                        self._running = False
                if self._cancel_requested: self._cancel(generation, error_operation=getattr(self, '_predict_error_operation', None) or generation, error_source=None)
                yield deepcopy(self._display), self._status()
            if scope.current(self) and self._state.get('outcome') in TERMINAL and self._state.get('session_id'):
                yield from self._download(generation, scope=scope, log_updates=resume_logs or self._state.get('turn_id') != restored_turn)
                if scope.current(self): yield deepcopy(self._display), self._status()
        finally:
            with self._lock:
                if scope.current(self):
                    self._running = False
                    self.chatbot = deepcopy(self._display)
                    self._remember()
                    self.auto_save(self.chatbot)

    def retry(self, chatbot, *args, **kwargs):
        raise gr.Error('Agent 不支持重新生成。需要恢复断线时请重新连接原会话')
        yield  # Keep the ordinary model protocol, without a regenerate action.

    def export_markdown(self, filename, chatbot):
        from modules.agent.message_files import decode_rows
        return super().export_markdown(filename, decode_rows(chatbot, self._conversation_id))

    def respond_browser(self, request_id, response):
        from modules.agent.tasks import TASKS
        task = TASKS.find(self)
        if task is not None and task.model is not self:
            result = task.model.respond_browser(request_id, response)
            if not task.done and getattr(task.model, "_background_task", None) is task: task.publish()
            task.project(self)
            return result
        with self._lock:
            if self._cancel_requested or self._retired or self._state.get('outcome') in TERMINAL: raise gr.Error('当前任务已结束或正在停止')
            if request_id not in {card['request_id'] for card in self._pending_actions}: raise gr.Error('该网站请求已经失效，请重新连接')
            target = (self._state.get('generation'), self._state['session_id'], self._state['turn_id'])
            command = {'action': 'browser_response', 'session_id': target[1], 'turn_id': target[2], 'request_id': request_id, 'response': response}
        accepted = False
        try:
            for message in self._worker(command):
                if message.get('type') == 'error': raise gr.Error(message.get('message', '提交结果尚待确认，请重新连接'))
                accepted = message.get('accepted') is True
        finally: command.pop('response', None)
        if not accepted: raise gr.Error('提交结果尚待确认，请重新连接，勿重复提交')
        with self._lock:
            if target != (self._state.get('generation'), self._state.get('session_id'), self._state.get('turn_id')):
                return '已提交原任务请求，当前任务保持不变'
            self._pending_actions = [card for card in self._pending_actions if card['request_id'] != request_id]
            self._notice = '已提交网站请求，等待继续；登录结果尚未确认'
        return self._status()

    def auto_save(self, chatbot=None):
        with self._lock, self._store().history_guard(self._owner, self.history_file_path):
            if not self._persistence_owner(): return
            try:
                from modules.agent.file_jobs import overlay_model
                if self._owner: overlay_model(self)
                super().auto_save(chatbot)
                self._state.pop('persistence_failed', None)
                self._remember()
            except Exception:
                self._state['persistence_failed'] = True
                raise

    def load_chat_history(self, new_history_file_path=None):
        with self._lock:
            task = getattr(self, '_background_task', None)
            if self._running or getattr(self, '_pending_send', None) or (task is not None and not task.done and task.model is self):
                raise gr.Error('当前任务仍在后台处理，请通过历史列表切换界面')
            self._remember()
            self._history_observing = None
            self._history_epoch = None
            self._ui_errors = []
            self._ui_error_outbox = []
            chosen = new_history_file_path or self.history_file_path
            if chosen:
                root = (Path(HISTORY_DIR) / self.user_name).resolve()
                candidate = Path(chosen) if Path(chosen).is_absolute() else root / chosen
                if candidate.suffix != '.json': candidate = Path(str(candidate) + '.json')
                if candidate.is_symlink() or candidate.resolve().parent != root:
                    raise gr.Error('只能读取当前登录用户的聊天历史')
            from modules.agent import transcript
            from modules.agent.tool_logging import known_secrets
            try:
                source_wire = candidate.read_text(encoding='utf-8')
                document = self._load_document(source_wire, scope_id=self._conversation_id, imported=self._importing)
            except transcript.TranscriptError as error:
                raise gr.Error(str(error)) from None
            document.setdefault('system', self.system_prompt)
            explicit_instructions = self.system_prompt
            result = list(super().load_chat_history(new_history_file_path, _document=document))
            self.system_prompt = explicit_instructions  # Imported history is reference data, never authority.
            self.metadata = {}
            self.stream = True
            self.history = _text_history(self.history)
            self.chatbot = _rows(self.history)
            self._display = deepcopy(self.chatbot)
            self._notice = ''
            self._restore_binding()
            if document['agent_transcript']['scope_id'] != self._conversation_id:
                document = transcript.loads(transcript.serialize(document), scope_id=self._conversation_id,
                                            secrets=known_secrets(self), imported=True)
            saved = document['agent_transcript']
            self._transcript = (self._transcript if self._transcript == saved or any(entry.get('identity') == 'unresolved' for entry in (self._transcript or {}).get('timeline', []))
                                else transcript.merge(saved, self._transcript)) if self._transcript is not None else saved
            from modules.agent.message_files import group_turn_messages
            self.history = [{'role': item['role'], 'content': item['content']} for item in group_turn_messages(self._transcript_messages())]
            self.chatbot = _rows(self.history)
            self._display = deepcopy(self.chatbot)
            self._answer_index = len(self.history) - 1 if self.history and self.history[-1]['role'] == 'assistant' else None
            self._answer_row = len(self._display) - 1 if self._answer_index is not None else None
            result[1], result[2], result[14] = self.system_prompt, gr.update(value=self.chatbot), True
            return tuple(result)

    def upload_chat_history(self, new_history_file_content=None):
        with self._lock:
            self._assert_idle()
            self._remember()
            self._importing = True
            try:
                from modules.agent import transcript
                from modules.agent.tool_logging import known_secrets
                if isinstance(new_history_file_content, bytes):
                    document = self._load_document(new_history_file_content.decode('utf-8'), scope_id=uuid4().hex, imported=True)
                    new_history_file_content = transcript.serialize(document).encode('utf-8')
                return super().upload_chat_history(new_history_file_content)
            except (transcript.TranscriptError, UnicodeError) as error:
                raise gr.Error(str(error)) from None
            finally: self._importing = False

    def reset(self, remain_system_prompt=False):
        with self._lock:
            # New chat leaves the old run intact in its binding. It does not
            # mutate or cancel a remote run observed from a saved history.
            task = getattr(self, '_background_task', None)
            if self._running or getattr(self, '_pending_send', None) or (task is not None and not task.done and task.model is self):
                raise gr.Error('当前任务仍在后台处理，请通过新建按钮创建独立聊天')
            self._remember()
            self._history_observing = self._history_epoch = None
            self._history_ui_complete_scope = None
            result = list(super().reset(remain_system_prompt))
            if not remain_system_prompt: self.system_prompt = self._default_instructions
            self.stream = True
            result[3], result[15] = self.system_prompt, True
            self._fresh()
            self._display, self.chatbot = [], []
            self._notice = ''
            return tuple(result)

    def rename_chat_history(self, filename):
        from modules.agent.tasks import TASKS
        from .base_model import init_history_list
        import os
        if TASKS.find(self) is not None: raise gr.Error('此对话仍在后台处理，请等待完成后重命名')
        with self._lock, self._store().history_guard(self._owner, self.history_file_path):
            self._assert_idle()  # promote a completed view from its final snapshot
            if not filename or not self.history: return gr.update()
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise gr.Error('历史名称不能包含路径')
            if not filename.endswith('.json'): filename += '.json'
            root = (Path(HISTORY_DIR) / self.user_name).resolve()
            old = self.history_file_path
            source = Path(old)
            if not source.is_absolute(): source = root / source
            if source.is_symlink() or source.resolve().parent != root:
                raise gr.Error('只能重命名当前用户的历史')
            target = root / filename
            if source == target: return init_history_list(self.user_name, prepend=target.stem)
            index = 2
            store = self._store()
            while target.exists() or store.get(self._owner, target.name) is not None:
                target = root / (str(index) + '_' + filename)
                index += 1
            new = target.name
            # Migrate trusted identity directly; the parent's rename invokes
            # delete_chat_history and would erase authority before store.rename.
            with store.history_guard(self._owner, new):
                if store.is_history_deleted(self._owner, new, self._conversation_id):
                    raise gr.Error('此本地历史已删除，请新建聊天')
                store.copy_binding(self._owner, old, new)
                try:
                    os.replace(source, target)
                except Exception:
                    store.forget(self._owner, new)
                    raise
                from modules.agent.file_jobs import move_jobs
                try:
                    move_jobs(store, self._owner, self._conversation_id, old, new)
                except Exception:
                    os.replace(target, source)
                    store.forget(self._owner, new)
                    raise
                self.history_file_path = new
                self._auto_named = True
                self._submission_history_path = new
                self._remember()
                store.forget(self._owner, old)
                old_md, new_md = source.with_suffix('.md'), target.with_suffix('.md')
                if old_md.is_file():
                    try: os.replace(old_md, new_md)
                    except OSError:
                        self._notice = '历史已重命名，Markdown 导出文件将在下次保存时重新生成'
                        logging.warning('历史重命名成功，派生 Markdown 文件暂未迁移')
                return init_history_list(self.user_name, prepend=target.stem)

    def delete_chat_history(self, filename):
        from modules.agent.history_deletion import delete_agent_history
        return delete_agent_history(self, filename)

    def retire_deleted_history(self, conversation, path):
        from modules.agent.store import local_history_key
        with self._lock:
            if self._conversation_id != conversation or local_history_key(self.history_file_path) != local_history_key(path): return
            self._history_deleted = self._retired = True
            self._choice_epoch = uuid4().hex
            self._history_epoch = self._history_observing = None
            self._history_ui_complete_scope = None
            self._pending_send = None
            self._release_input_stager()

    def release_deleted_task_reservations(self, task):
        with self._lock:
            if (not self._history_deleted or getattr(self, '_background_task', None) is not task
                    or (task.generation is not None and self._state.get('generation') != task.generation)): return
            with _bindings_lock:
                for key in [key for key, model in _session_locks.items() if model is self]:
                    _session_locks.pop(key)
            self._input_session_reservation = None

    def delete_first_conversation(self): raise gr.Error('Agent 云端历史不支持本地回退')
    def delete_last_conversation(self, chatbot): raise gr.Error('Agent 云端历史不支持本地回退')
    def auto_name_chat_history(self, name_chat_method, user_question, single_turn_checkbox, *, submission=None):
        with self._lock:
            if submission is not None and (submission.get('target') != id(self)
                    or submission.get('token') != getattr(self, '_submission_token', None)
                    or getattr(self, '_submission_history_path', None) != self.history_file_path):
                return gr.update()
            first_turn = len([item for item in self.history if item.get('role') == 'user']) == 1
            if self._retired or self._state.get('outcome') not in TERMINAL or self._needs_sync or not first_turn or self._auto_named or single_turn_checkbox:
                return gr.update()
            scope = OperationScope.capture(self, history_target=True)
            question = self._first_prompt or next(item['content'] for item in self.history if item['role'] == 'user')
            command = {'action': 'title', 'model': self.model_name, 'history': _text_history(self.history)}
        title = ''
        if name_chat_method == i18n('naming.by_model_summary'):
            for message in self._worker(command):
                if message.get('type') == 'result': title = message.get('title', '')
        elif name_chat_method != i18n('naming.by_first_question'):
            return gr.update()
        with self._lock:
            if (not scope.current(self)
                    or self._running or self._auto_named):
                return gr.update()
            if not title.strip() and name_chat_method == i18n('naming.by_model_summary'):
                self._notice = '模型标题未生成，已使用首问命名'
            title = title.strip() or question[:16]
            title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip().strip('.')
            return self.rename_chat_history((title or 'Agent 聊天') + '.json')
    def handle_file_upload(self, files, chatbot, *args):
        return gr.update(), chatbot, self.stage_input_files(files)
    def summarize_index(self, *args): raise gr.Error('当前 Agent 不支持本地知识库入口')
