"""Local history deletion retires readers without asserting remote cancellation."""
from pathlib import Path
from datetime import datetime, timezone
import gradio as gr
from modules.agent.store import BindingStore, owner_identity, local_history_key


def _store(model):
    from modules import shared
    return BindingStore(getattr(model, '_task_root', shared.chuanhu_path))


def _path(model, filename):
    from modules.models.base_model import HISTORY_DIR
    root = (Path(HISTORY_DIR) / model.user_name).resolve()
    chosen = Path(filename)
    if not chosen.is_absolute(): chosen = root / chosen
    if not str(chosen).endswith('.json'): chosen = Path(str(chosen) + '.json')
    if chosen.is_symlink() or chosen.resolve().parent != root:
        raise gr.Error('只能删除当前登录用户的聊天历史')
    md = chosen.with_suffix('.md')
    if md.is_symlink(): raise gr.Error('只能删除当前登录用户的聊天历史')
    return chosen


def has_agent_history(model, filename):
    path = _path(model, filename)
    from modules import shared
    root = Path(getattr(model, '_task_root', shared.chuanhu_path))
    return (root / 'agent_data' / 'bindings.sqlite3').is_file() and bool(_store(model).history_bindings(owner_identity(model.user_name), path.name))


def delete_agent_history(model, filename):
    from modules.agent.tasks import TASKS
    from modules.models.base_model import get_history_list
    from modules.presets import i18n
    if filename in ('CANCELED', None): return gr.update(), gr.update(), gr.update()
    if filename == '': return i18n('msg.history.none_selected'), gr.update(), gr.update()
    path = _path(model, filename)
    owner = owner_identity(model.user_name)
    if getattr(model, 'is_hosted_agent', False) and model._owner != owner:
        raise gr.Error('此会话不属于当前登录用户')
    store = _store(model)
    tasks = []
    receipts = {}
    failed = []
    try:
        with store.history_guard(owner, path.name):
            bindings = store.history_bindings(owner, path.name)
            tasks = TASKS.detach_history(model, path)
            sources = [(record.get('conversation_id'), record.get('state', {})) for _, record in bindings]
            sources += [(task.conversation, (task.snapshot[0]['_state'] if task.snapshot else {})) for task in tasks]
            if getattr(model, 'is_hosted_agent', False) and local_history_key(model.history_file_path) == local_history_key(path.name):
                sources.append((model._conversation_id, model._state.copy()))
            for conversation, state in sources:
                if not conversation: continue
                record = receipts.setdefault(conversation, {'deleted_at': datetime.now(timezone.utc).isoformat(),
                    'session_id': None, 'turn_id': None, 'generation': None, 'last_known_outcome': None,
                    'remote_stop': 'not_requested', 'remote_stop_confirmed': False})
                # An observer may not have published its first snapshot yet.
                # Do not erase the durable identity with empty task metadata.
                for field in ('session_id', 'turn_id', 'generation', 'outcome'):
                    if state.get(field) is not None:
                        record['last_known_outcome' if field == 'outcome' else field] = state[field]
            store.delete_local_history(owner, path.name, receipts)
            for file in (path, path.with_suffix('.md')):
                try: file.unlink(missing_ok=True)
                except OSError: failed.append(file.suffix)
    finally:
        # Never acquire backend/view locks while holding the file-write barrier.
        for task in tasks:
            task.model.retire_deleted_history(task.conversation, path.name)
            with task.condition: task.condition.notify_all()
        if getattr(model, 'is_hosted_agent', False):
            for conversation in receipts: model.retire_deleted_history(conversation, path.name)
    if '.json' in failed: raise gr.Error('本地历史文件删除失败，请检查文件权限')
    status = i18n('msg.history.deleted')
    unconfirmed = any(record['last_known_outcome'] not in ('not_started', 'completed', 'failed', 'cancelled') for record in receipts.values())
    if unconfirmed:
        status += '；仅删除本地记录，云端任务停止未确认'
    if '.md' in failed: status += '；Markdown 导出未能移除'
    if unconfirmed:
        # Queue notifications survive the following reset clearing status_display.
        gr.Warning(status)
    return status, get_history_list(model.user_name), []
