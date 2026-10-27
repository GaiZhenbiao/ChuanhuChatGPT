"""Owner-bound pending uploads and preparation state for the main Agent model."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re

import gradio as gr
from modules.agent.input_files import AgentInputFiles, InputFileError


class InputPreparationStopped(Exception):
    pass


class AgentInputState:
    def _initialize_inputs(self):
        self._input_stager = None
        self._input_upload_roots = None
        self._pending_upload_paths = ()
        self._reserved_inputs = self._consumed_inputs = None
        self._input_context = None
        self._installed_inputs = {}
        self._input_seed_reference = None
        self._input_messages = {}
        self._input_statuses = []
        self._input_preparing = False
        self._input_stager_jobs = set()

    def _clear_input_selection(self):
        if self._input_stager is not None: self._input_stager.clear()
        self._pending_upload_paths = ()
        self._reserved_inputs = self._consumed_inputs = None
        self._input_statuses = []

    def _remove_input_selection(self, identifiers):
        """Detach presented IDs, retaining immutable preparation/run snapshots."""
        with self._lock:
            if self._input_stager is None or not identifiers: return
            records = self._input_stager.snapshot()
            selected = set(identifiers)
            self._pending_upload_paths = tuple(path for path, record in zip(self._pending_upload_paths, records)
                                               if record.input_id not in selected)
            for identifier in selected: self._input_stager.remove(identifier)

    def _reset_inputs(self):
        self._clear_input_selection()
        self._release_input_stager()
        self._input_context = None
        self._installed_inputs = {}
        self._input_seed_reference = None
        self._input_messages = {}

    def _release_input_stager(self):
        """仅清理已无人使用的私有副本，后台准备尚未确定结束时保留。"""
        preparation = (self._input_context or {}).get('resume_state') or {}
        if self._pending_upload_paths or self._input_preparing or preparation.get('outcome') in ('preparing', 'uncertain'):
            # 仍在当前会话使用的副本不转移所有权；恢复记录确认结束后再清理。
            return
        if self._input_stager is not None:
            from modules.agent.secure_io import SecureDirectory
            try:
                with SecureDirectory(self._input_stager.staging_root) as directory:
                    for run_id in self._input_stager_jobs:
                        try:
                            with directory.lock('.prepare-' + run_id + '.lock', create=False):
                                pass
                        except FileNotFoundError:
                            pass
            except BlockingIOError:
                return
            self._input_upload_roots = tuple(prefix for prefix, _ in self._input_stager._upload_prefixes)
            self._input_stager.close()
            self._input_stager = None
            self._input_stager_jobs.clear()

    def stage_input_files(self, files):
        """Stage locally only; cloud preparation starts inside the first Send.

        Selecting attachments must not create a session or freeze its settings.
        """
        with self._lock:
            paths = tuple(str(path) for path in files or [])
            if not paths and not self._pending_upload_paths: return '附件已清空'
            if paths == self._pending_upload_paths: return f'已添加 {len(paths)} 个附件，发送时交给 Agent'
            if self._retired: raise gr.Error('聊天已切换，请重新选择附件')
            self._assert_idle()
            if self._input_stager is None: self._input_stager = AgentInputFiles(upload_roots=self._input_upload_roots)
            try: records = self._input_stager.set_pending(paths)
            except InputFileError as error: raise gr.Error(str(error)) from None
            self._pending_upload_paths = paths
            self._input_statuses = [dict(record.to_dict(), status='prepared') for record in records]
            return f'已添加 {len(records)} 个附件，发送时交给 Agent' if records else '附件已清空'

    def freeze_input_files(self, files=None):
        if files is not None and tuple(str(path) for path in files or []) != self._pending_upload_paths:
            raise gr.Error('附件仍在准备或已经变化，请确认上传完成后再发送')
        return self._input_stager.snapshot() if self._input_stager is not None else ()

    def add_input_files(self, files, target):
        with self._lock:
            if target != self._conversation_id: raise gr.Error('聊天已变化，附件未添加，请重新选择')
            paths = list(dict.fromkeys([*self._pending_upload_paths, *(str(path) for path in files or [])]))
            return self.stage_input_files(paths)

    def remove_input_ids(self, identifiers, target):
        with self._lock:
            if target != self._conversation_id: raise gr.Error('聊天已变化，附件未移除')
            self._assert_idle()
            records = self._input_stager.snapshot() if self._input_stager is not None else ()
            selected = set(identifiers)
            paths = [path for path, record in zip(self._pending_upload_paths, records) if record.input_id not in selected]
            return self.stage_input_files(paths)

    def _take_input_files(self, files):
        with self._lock:
            if self._consumed_inputs is not None:
                result = self._consumed_inputs
                self._consumed_inputs = None
                return result
            return self.freeze_input_files(files)

    def _input_binding(self):
        return {'input_context': deepcopy(self._input_context), 'installed_inputs': deepcopy(self._installed_inputs),
                'input_seed_reference': deepcopy(self._input_seed_reference), 'input_messages': deepcopy(self._input_messages)}

    def _restore_input_binding(self, binding):
        self._clear_input_selection()
        self._input_context = deepcopy(binding.get('input_context'))
        self._installed_inputs = deepcopy(binding.get('installed_inputs', {}))
        self._input_seed_reference = deepcopy(binding.get('input_seed_reference'))
        self._input_messages = deepcopy(binding.get('input_messages', {}))

    def _input_paths(self):
        context = self._input_context
        if not context or not re.fullmatch(r'[a-f0-9]{32}', context.get('run_id', '')): return None
        root = Path(context['staging_root'])
        if not root.is_absolute() or '..' in root.parts or not root.name.startswith('chuanhu-agent-inputs-') or root.is_symlink(): return None
        return root / ('.prepare-' + context['run_id'] + '.json'), root / ('.prepare-' + context['run_id'] + '.lock'), root / ('.cancel-' + context['run_id'])

    def _cancel_input_preparation(self):
        from modules.agent.secure_io import SecureDirectory
        paths = self._input_paths()
        if paths is not None:
            with SecureDirectory(paths[2].parent) as directory:
                directory.touch(paths[2].name)

    def _refresh_input_journal(self):
        """只读取服务端所属的准备记录，不恢复上传或跟随链接。"""
        from modules.agent.secure_io import SecureDirectory
        paths = self._input_paths()
        if paths is None: return False
        busy = False
        with SecureDirectory(paths[0].parent) as directory:
            try:
                preparation = directory.read_json(paths[0].name)
                self._adopt_input_preparation(preparation)
            except FileNotFoundError: pass
            try:
                with directory.lock(paths[1].name, create=False):
                    pass
            except BlockingIOError: busy = True
            except FileNotFoundError: pass
        if busy:
            self._state.update(outcome='incomplete', turn_id=None, submission_started=False)
            self._needs_sync = True
            self._notice = '附件仍在后台准备，消息尚未发送；可停止或稍后重新连接'
        return busy

    def _adopt_input_preparation(self, preparation):
        if not isinstance(preparation, dict) or preparation.get('run_id') != self._input_context['run_id']:
            raise InputPreparationStopped('附件准备记录不匹配，消息未发送')
        session = preparation.get('session_id')
        if session:
            if self._state.get('session_id') and self._state['session_id'] != session:
                raise InputPreparationStopped('附件不属于当前会话，消息未发送')
            self._state['session_id'] = session
            if self._running and self._input_preparing: self._reserve_input_session(session)
        self._input_context['resume_state'] = deepcopy(preparation)
        self._installed_inputs.update(deepcopy(preparation.get('installed', {})))
        self._input_statuses = deepcopy(preparation.get('files', []))
        self._remember()

    def _prepare_input_frames(self, records, generation, settings, reference):
        if not records: return []
        identifiers = [record.input_id for record in records]
        with self._lock:
            if self._input_stager is None: raise InputPreparationStopped('附件暂存已失效，请重新上传')
            root = str(self._input_stager.staging_root)
            if not self._input_context or self._input_context['input_ids'] != identifiers or self._input_context['staging_root'] != root:
                self._input_context = {'run_id': generation, 'staging_root': root, 'input_ids': identifiers, 'resume_state': None}
            if not self._state.get('session_id'):
                self._input_seed_reference = deepcopy(reference or [])
            self._session_settings = deepcopy(settings)
            self._input_preparing = True
            self._input_stager_jobs.add(generation)
            self._input_statuses = [dict(record.to_dict(), status='prepared') for record in records]
            self.auto_save(self.chatbot)
            paths = self._input_paths()
            if paths is None: raise InputPreparationStopped('附件暂存路径无效')
            from modules.agent.secure_io import SecureDirectory
            with SecureDirectory(paths[2].parent) as directory:
                directory.unlink(paths[2].name, missing_ok=True)
            command = {'action': 'prepare_inputs', 'session_id': self._state.get('session_id'),
                       'run_id': self._input_context['run_id'], 'staging_root': root,
                       'inputs': [record.to_dict() for record in records],
                       'model': settings['model'], 'reasoning': settings['reasoning'], 'instructions': settings['instructions'],
                       'tool_settings': settings['tools'], 'installed': deepcopy(self._installed_inputs),
                       'resume_state': deepcopy(self._input_context['resume_state'])}
        ready = False
        try:
            yield deepcopy(self._display), '正在准备附件，消息尚未发送'
            for message in self._worker(command):
                with self._lock:
                    if self._retired or self._state.get('generation') != generation: return []
                    preparation = message.get('preparation')
                    if preparation: self._adopt_input_preparation(preparation)
                    if message.get('type') == 'error':
                        raise InputPreparationStopped(message.get('message', '附件准备失败，消息未发送'))
                    ready = message.get('type') == 'result' and preparation and preparation.get('outcome') == 'ready'
                    completed = sum(record.get('status') == 'ready' for record in self._input_statuses)
                    status = f'正在准备附件 {completed}/{len(records)}，消息尚未发送'
                yield deepcopy(self._display), status
            with self._lock:
                if self._cancel_requested: return []
                if not ready: raise InputPreparationStopped('附件准备尚未确认，消息未发送，请重新连接检查')
                return [dict(self._installed_inputs[record.input_id], input_id=record.input_id, name=record.name) for record in records]
        finally:
            with self._lock: self._input_preparing = False

    @staticmethod
    def _confirmed_preparation_failure(preparation):
        phase = preparation.get('last_request_phase')
        failed = ((phase == 'preparation.session_retrieve' and preparation.get('session_status') == 'failed')
                  or (phase == 'preparation.environment_retrieve' and preparation.get('environment_status') == 'failed'))
        return bool(failed and preparation.get('outcome') == 'failed'
                    and preparation.get('submission_started') is False
                    and not preparation.get('uncertain_operation'))

    def _failed_preparation_environment(self):
        preparation = (self._input_context or {}).get('resume_state') or {}
        return bool(self._confirmed_preparation_failure(preparation)
                    and preparation.get('session_id') == self._state.get('session_id')
                    and preparation.get('session_id'))

    def _failed_environment_notice(self):
        preparation = (self._input_context or {}).get('resume_state') or {}
        phase = preparation.get('last_request_phase')
        if phase == 'preparation.session_retrieve':
            return '会话准备失败（code=unknown；phase=preparation.session_retrieve）；该会话无法继续，请主动新建聊天；未提交聊天轮次'
        code = (preparation.get('environment_error') or {}).get('code')
        known = {'environment_connection_failed', 'environment_connection_timeout',
                 'sandbox_error', 'executor_version_incompatible', 'internal_error', 'idle_timeout'}
        code = code if code in known else 'unknown'
        return '执行环境准备失败（code=' + code + '；phase=preparation.environment_retrieve）；该会话无法继续，请主动新建聊天；未提交聊天轮次'

    def _input_rollback_state(self, previous, generation):
        context = self._input_context
        if not context: return previous
        preparation = context.get('resume_state') or {}
        session = preparation.get('session_id') or self._state.get('session_id')
        if session and (preparation.get('outcome')=='uncertain' or preparation.get('uncertain_operation')):
            self._needs_sync = True
            return dict(previous, session_id=session, turn_id=None, outcome='incomplete', submission_started=False)
        if session and self._confirmed_preparation_failure(preparation):
            return dict(previous, session_id=session, turn_id=None, outcome='failed', submission_started=False)
        if session and not previous.get('session_id'):
            return dict(previous, session_id=session, turn_id=None, outcome='not_started', submission_started=False)
        if not session and preparation.get('session_creation_started'):
            self._needs_sync = True
            return dict(previous, outcome='uncertain', generation=context['run_id'], submission_started=False)
        return previous

    def _remember_input_message(self, wire_text, display_text, files=()):
        self._input_messages[hashlib.sha256(wire_text.encode()).hexdigest()] = {'text': display_text,
            'files': [{'id':item['input_id'],'name':item['name'],'size':item.get('size')} for item in files]}

    def _project_input_text(self, text):
        value = self._input_messages.get(hashlib.sha256(text.encode()).hexdigest(), text)
        return value.get('text', text) if isinstance(value, dict) else value
