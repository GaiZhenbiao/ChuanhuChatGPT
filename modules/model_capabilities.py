"""One model capability contract for native controls, custom UI and callbacks."""
from dataclasses import dataclass, asdict, replace
import html
import json
from pathlib import Path
from uuid import uuid4
import gradio as gr


@dataclass(frozen=True)
class ModelCapabilities:
    input_attachments: bool = True
    knowledge: bool = True
    external_websearch: bool = True
    sampling: bool = True
    token_limits: bool = True
    single_turn: bool = True
    output_mode: bool = True
    regenerate: bool = True
    history_delete: bool = True
    history_edit: bool = True
    history_rollback: bool = True
    message_copy: bool = True
    message_markdown: bool = True
    output_artifacts: bool = False
    agent_tools: bool = False
    sandbox_attachments: bool = False
    billing: bool = True
    reply_language: bool = True

    @property
    def parameters(self): return self.sampling or self.token_limits


AGENT_CAPABILITIES = ModelCapabilities(input_attachments=True, sandbox_attachments=True, knowledge=False, external_websearch=False,
    sampling=False, token_limits=False, single_turn=False, output_mode=False, regenerate=False,
    history_delete=False, history_edit=False, history_rollback=False, output_artifacts=True, agent_tools=True, billing=False, reply_language=False)


def capabilities(model):
    declaration = getattr(type(model), 'ui_capabilities', None)
    if declaration is None: return ModelCapabilities()
    if not isinstance(declaration, ModelCapabilities): raise TypeError('模型能力声明必须为 ModelCapabilities')
    return declaration


def require_capability(model, name):
    if not getattr(capabilities(model), name):
        raise gr.Error('当前模型不支持此操作：' + {
            'sampling':'普通采样参数', 'token_limits':'普通 token 设置', 'input_attachments':'输入附件',
            'knowledge':'本地知识库', 'external_websearch':'原外部网页搜索', 'single_turn':'单轮模式',
            'output_mode':'输出方式切换', 'regenerate':'重新生成', 'history_delete':'删除聊天轮次',
            'history_edit':'编辑重跑', 'history_rollback':'历史回退',
        }.get(name,name))


def model_lock(model):
    return getattr(model, '_lock', model._chat_lock)


def is_busy(model):
    return bool(model and (getattr(model,'_running',False) or getattr(model,'_background_busy',False) or getattr(model,'_chat_running',False) or getattr(model,'_pending_send',None)))


def reserve_submission(model, text, files=None):
    with model_lock(model):
        if is_busy(model) or getattr(model,'_retired',False) or getattr(model,'_chat_retired',False):
            raise gr.Error('当前会话正在提交或生成，请等待完成或先停止')
        if hasattr(model, 'freeze_input_files'): model._reserved_inputs = model.freeze_input_files(files)
        token = uuid4().hex
        model._pending_send = token
        model._submission_token = token
        model._submission_history_path = model.history_file_path
        if getattr(model, 'is_hosted_agent', False):
            model._draft_token, model._draft_submitted = token, False
            model._draft_acknowledged = False
            model._draft_presented = False
            model._draft_text, model._draft_conversation = text, model._conversation_id
            model._draft_input_ids = tuple(record.input_id for record in model._reserved_inputs)
        return {'text': text, 'target': id(model), 'token': token}


def consume_submission(model, inputs):
    if not isinstance(inputs, dict): return inputs
    if set(inputs) != {'text','target','token'} or inputs.get('target') != id(model) or inputs.get('token') != getattr(model,'_pending_send',None):
        raise gr.Error('这条排队输入的会话已变化或已取消，未发送；请在当前聊天重新提交')
    model._pending_send = None
    if hasattr(model, '_reserved_inputs'):
        model._consumed_inputs = model._reserved_inputs
        model._reserved_inputs = None
    return inputs['text']


class CapabilityUI:
    def __init__(self, bindings, selector, marker, submit=None, cancel=None):
        self.bindings, self.selector, self.marker = bindings, selector, marker
        self.submit, self.cancel = submit, cancel
        self.outputs = [component for _,component,_ in bindings] + [selector,marker] + ([submit,cancel] if submit is not None and cancel is not None else [])

    @property
    def stream_outputs(self):
        return [self.selector, self.marker] + ([self.submit, self.cancel] if self.submit is not None and self.cancel is not None else [])

    def stream_values(self, model):
        values = self.values(model)
        return [values[self.outputs.index(component)] for component in self.stream_outputs]

    def values(self, model):
        caps = capabilities(model)
        results=[]
        for name, component, clear in self.bindings:
            supported=getattr(caps,name)
            # Preserve a component's normal visibility, including proxy native
            # controls intentionally hidden in the ordinary interface.
            update={'visible': supported and self._visible[component._id]}
            if not supported and clear is not None: update['value']=clear
            results.append(gr.update(**update))
        read_only = bool(getattr(model, '_read_only_observation', False)) and getattr(model, '_state', {}).get('outcome') in ('completed','cancelled','failed')
        payload=dict(asdict(caps), busy=is_busy(model) or bool(getattr(model, '_needs_sync', False)) or bool(getattr(model, '_state', {}).get('persistence_failed')), turn_terminal=caps.agent_tools and getattr(model, '_state', {}).get('outcome') in ('completed', 'cancelled', 'failed') and (read_only or not is_busy(model)))
        payload['history_filename'] = Path(getattr(model, 'history_file_path', '')).name.removesuffix('.json')
        payload['history_visit'] = model.agent_choice_target if caps.agent_tools else getattr(model, '_history_visit', '')
        payload['task_generation'] = getattr(model, '_state', {}).get('generation') if caps.agent_tools else None
        payload['input_target'] = getattr(model, '_conversation_id', '') if caps.sandbox_attachments else ''
        if caps.agent_tools:
            state = getattr(model, '_state', {})
            payload['agent_turn_id'] = state.get('turn_id') or ('local-' + str(state.get('generation')))
        if caps.sandbox_attachments and (getattr(model, '_draft_presented', False) or getattr(model, '_draft_acknowledged', False)) and getattr(model, '_draft_token', None):
            payload['submitted_draft'] = {'token': model._draft_token, 'conversation': model._draft_conversation, 'text': model._draft_text}
        if caps.agent_tools and getattr(model, '_tool_ui_patch', None): payload['tool_patch'] = model._tool_ui_patch
        provider_locked = caps.agent_tools and bool(getattr(model, '_state', {}).get('session_id'))
        results.extend([gr.update(interactive=not is_busy(model) and not provider_locked),
            '<span data-model-capabilities="'+html.escape(json.dumps(payload),quote=True)+'"></span>'])
        if self.submit is not None and self.cancel is not None:
            remote_running = getattr(model, '_state', {}).get('outcome') in ('starting','in_progress','requires_action','cancel_requested','incomplete','uncertain')
            running = (is_busy(model) and not read_only) or remote_running
            results.extend([gr.update(visible=not running, interactive=not is_busy(model) and not getattr(model, '_needs_sync', False) and not getattr(model, '_state', {}).get('persistence_failed')), gr.update(visible=running)])
        return results

    def wire(self, current_model, chatbot):
        self._visible = {component._id:component.visible for _,component,_ in self.bindings}
