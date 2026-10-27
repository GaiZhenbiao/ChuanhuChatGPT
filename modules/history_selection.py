"""按已保存的模型选择打开历史，不把历史文件当作凭据来源。"""
import json
from pathlib import Path

import gradio as gr

from modules.model_capabilities import is_busy, model_lock


def load_history_model(current_model, filename, request: gr.Request = None):
    """显式切换历史可以离开 Agent；普通模型下拉切换仍受会话锁约束。"""
    if isinstance(filename, dict):
        with model_lock(current_model):
            if getattr(current_model, '_retired', False) or getattr(current_model, '_chat_retired', False):
                return tuple(gr.update() for _ in range(24))
            expected = current_model.agent_choice_target if getattr(current_model, 'is_hosted_agent', False) else getattr(current_model, '_history_visit', '')
            if (set(filename) != {'filename', 'visit'} or filename['visit'] != expected
                    or not isinstance(filename['filename'], str)):
                return (current_model, *(gr.update() for _ in range(23)))
            # Keep visit validation and loading in the same reentrant lock.
            return load_history_model(current_model, filename['filename'], request)
    # Clearing the selection for a new draft is not a request to open a file.
    if filename in (None, ''):
        return (current_model, *(gr.update() for _ in range(23)))
    from modules import shared
    from modules.presets import HISTORY_DIR, MODEL_METADATA, i18n
    from modules.models.models import get_model
    from modules.agent.store import BindingStore, owner_identity

    with model_lock(current_model):
        if request is not None:
            username = request.username or ''
            if current_model.user_name != username:
                raise gr.Error('只能读取当前登录用户的聊天历史')
            if getattr(current_model, 'is_hosted_agent', False):
                current_model.bind_owner(request)
        else:
            username = current_model.user_name
        agent_current = getattr(current_model, 'is_hosted_agent', False)
        if (not agent_current and is_busy(current_model)) or getattr(current_model, '_pending_send', None):
            raise gr.Error('当前输入正在提交或生成，请先停止再改变聊天历史')
        root = (Path(HISTORY_DIR) / username).resolve()
        chosen = Path(filename)
        if not chosen.is_absolute():
            chosen = root / chosen
        if chosen.suffix != '.json':
            chosen = Path(str(chosen) + '.json')
        if chosen.is_symlink() or chosen.resolve().parent != root:
            raise gr.Error('只能读取当前登录用户的聊天历史')
        try:
            saved = json.loads(chosen.read_text(encoding='utf-8'))
            if not isinstance(saved, dict) or not isinstance(saved['history'], list) or not isinstance(saved['chatbot'], list):
                raise ValueError
        except FileNotFoundError:
            raise gr.Error(i18n('ui.history.file_missing')) from None
        except (OSError, ValueError, KeyError):
            raise gr.Error(i18n('ui.history.file_invalid')) from None

        selection = saved.get('model_selection')
        if selection is None:
            # 旧版 Agent JSON 只记录子模型，绑定库才是会话身份的可信来源。
            database = Path(shared.chuanhu_path) / 'agent_data' / 'bindings.sqlite3'
            binding = BindingStore(shared.chuanhu_path).get(owner_identity(username), chosen.stem) if database.is_file() else None
            if binding:
                selection = 'OpenAI Agent'
            else:
                previous = saved.get('model_name')
                selection = previous if previous in MODEL_METADATA else next(
                    (name for name, metadata in MODEL_METADATA.items() if metadata.get('model_name') == previous),
                    getattr(current_model, '_selection_name', current_model.model_name) if previous is None else None)
        if selection not in MODEL_METADATA:
            raise gr.Error('历史记录使用的模型当前不可用，请先恢复该模型配置')

        current_selection = getattr(current_model, '_selection_name', current_model.model_name)
        model = current_model.new_view() if agent_current else current_model
        header = (gr.update(),) * 5
        chat_metadata = {}
        if selection != current_selection:
            # 不转交另一个服务商的密钥，也不从 JSON 恢复密钥或连接地址。
            created = get_model(selection, user_name=username, request=request)
            model = created[0]
            if model is None:
                raise gr.Error('历史记录使用的模型无法初始化')
            chat_metadata = created[2]
            header = (created[3], created[4], created[5], created[6], created[1])
        values = list(model.load_chat_history(chosen.name))
        if getattr(model, "is_hosted_agent", False):
            from modules.agent.tasks import TASKS
            task = TASKS.find(model, chosen.name)
            if task is not None and model._connection_reference() == task.model._connection_reference():
                task.project(model)
                model._background_task = task
                values[2] = gr.update(value=model.chatbot)
        values[2] = dict(chat_metadata, **values[2])
        values[2]['label'] = selection
        if model is not current_model:
            if getattr(current_model, 'is_hosted_agent', False):
                current_model._remember()
                current_model.retire()
            else:
                current_model._chat_retired = True
        return (model, gr.update(value=selection), *values, *header)
