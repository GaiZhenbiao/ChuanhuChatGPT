"""Reusable output-file surface and Agent controls for the main chat."""
import html
import hashlib
import json
import inspect
import re
from functools import wraps
from uuid import uuid4
from copy import deepcopy
import gradio as gr
from modules.agent.tools import FUNCTIONS, tool_availability
from modules.agent.operations import OperationScope
from modules.agent.file_icons import file_icon, file_size_label, file_type_label, split_filename
from modules.model_capabilities import capabilities, model_lock
from modules.presets import i18n
from modules.agent.reasoning import MODEL_EFFORTS, reasoning_options

REASONING_CHOICES = reasoning_options('gpt-6.1-sol')

def reasoning_choices(model='gpt-6.1-sol', current=None):
    return [('none' if value == 'none' else i18n('ui.toolbox.agent.' + ('reasoning_default' if value == 'default' else value)), value) for value in reasoning_options(model, current)]


def reasoning_info(model):
    return None if model in MODEL_EFFORTS else '该模型尚无已核实的推理选项；保留当前值或使用模型默认，其他值请按服务商说明填写'



def _agent(model):
    return model is not None and getattr(model, 'is_hosted_agent', False)


def message_file_projection(model, rows=None):
    from modules.agent.message_files import project_message_files
    from modules.agent.transcript_view import project_transcript
    projected = project_transcript(model, deepcopy(model._display if rows is None else rows))
    if projected is not None: return projected
    return project_message_files(deepcopy(model._display if rows is None else rows), model._cloud_items, model._artifacts,
        session_id=model._state.get('session_id'), conversation_id=model._conversation_id,
        current_turn_id=model._state.get('turn_id'), answer_row=model._answer_row, input_messages=getattr(model, '_input_messages', {}),
        pending_input_files=getattr(model, '_active_input_cards', []))


def _chat_frames(updates):
    """Rebase shrinking histories instead of emitting index-shifting diffs.

    Gradio 4.29 deletes list entries in ascending index order while its client
    applies them with splice. A local preview can have more rows than the
    authoritative session. Changing the update envelope forces a root replace.
    """
    previous_count = None
    wrapped = False
    for chat, status in updates:
        if isinstance(chat, (list, tuple)):
            count = len(chat)
            wrapped = previous_count is not None and count < previous_count and not wrapped
            previous_count = count
            if wrapped: chat = gr.update(value=deepcopy(chat))
        yield chat, status


class FrameUpdates:
    """每个流独立比较控件输出，仅提交变化；不缓存聊天正文。"""
    def __init__(self):
        self.previous = None

    def changes(self, values):
        values = list(values)
        result = values if self.previous is None else [gr.update() if value == old else value for value, old in zip(values, self.previous)]
        self.previous = deepcopy(values)
        return result


class ArtifactPanel:
    """Output files independent from input attachments and text chat bubbles."""
    def __init__(self):
        with gr.Column(visible=False, elem_id='model-output-files', min_width=0, scale=0) as self.group:
            self.list = gr.HTML(elem_id='model-output-cards')
            # CSS hides these native controls without unmounting their actual
            # download and callback behavior. Cards address files by artifact ID.
            self.files = gr.File(file_count='multiple', interactive=False, label='[]', elem_id='model-output-native-files')
            self.retry_id = gr.Textbox(elem_id='model-output-retry-id', show_label=False)
            self.retry = gr.Button('重试下载', elem_id='model-output-retry')
            self.refresh = gr.Button('刷新文件', elem_id='agent-file-refresh')
            self.refresh_wire = gr.Textbox(visible=False)

    @property
    def outputs(self): return [self.group, self.list, self.files, self.retry_id]

    @staticmethod
    def values(model):
        if _agent(model) and hasattr(model, 'refresh_files'): model.refresh_files(resume=False)
        records = getattr(model, '_artifacts', []) if capabilities(model).output_artifacts else []
        from modules.agent.file_jobs import pending, jobs_for
        managed = _agent(model) and hasattr(model, '_store')
        jobs = jobs_for(model._store(), model._owner, model._conversation_id) if managed else []
        retrying = {identifier for job in jobs if job['status'] in ('pending','running') for identifier in job['artifact_ids'] or []}
        records = deepcopy(records)
        for record in records:
            if record['id'] in retrying and record.get('status') != 'ready':
                record.update(status='preparing'); record.pop('error', None)
        projection = message_file_projection(model) if _agent(model) else None
        anchors = projection.artifact_anchors if projection else {}
        after_anchors = getattr(projection, 'artifact_after_anchors', {})
        cards, paths, ready_ids = [], [], []
        labels = {'preparing': '准备中', 'ready': '', 'failed': '下载失败'}
        for record in records:
            size = record.get('size')
            size_text = file_size_label(size)
            status = record.get('status', 'preparing')
            action = 'retry' if status == 'failed' else 'download' if status == 'ready' and record.get('path') else ''
            if action == 'download':
                paths.append(record['path']); ready_ids.append(record['id'])
            status_text = labels.get(status, '准备中')
            if status == 'failed': status_text += '，点击重试'
            error = ('：' + str(record['error'])) if record.get('error') else ''
            escape = lambda value: html.escape(str(value), quote=True)
            basename, extension = split_filename(record['name'])
            download_name = re.sub(r'[\\/\x00-\x1f\x7f]', '_', record['name'])
            if download_name in ('', '.', '..'): download_name = 'artifact'
            cards.append('<button type="button" class="model-file-card agent-file-card" data-download-name="' + escape(download_name) + '" data-artifact-id="' + escape(record['id']) + '" data-message-key="' + escape(anchors.get(record['id'], '')) + '" data-file-after-key="' + escape(after_anchors.get(record['id'], '')) + '" data-file-orphan="' + str(bool(managed and anchors.get(record['id']) and not after_anchors.get(record['id']))).lower() + '" data-conversation-id="' + escape(getattr(model, '_conversation_id', '')) + '" data-remote-path="' + escape(record.get('remote_path', '')) + '" data-file-action="' + action + '" aria-label="' + escape(record['name'] + '，' + (status_text or '下载文件')) + '"' + ('' if action else ' disabled="disabled"') + '>'
                         + file_icon(record['name']) + '<span class="model-file-content" data-file-part="content">'
                         + '<span class="model-file-name" data-file-part="name" title="' + escape(record['name']) + '"><span class="model-file-basename" data-file-part="basename">' + escape(basename) + '</span></span>'
                         + '<span class="model-file-meta" data-file-part="meta"><span class="model-file-extension">' + escape(file_type_label(record['name'])) + '</span> · <span class="model-file-size">' + size_text + '</span>' + (' · <span class="model-file-state">' + escape(status_text) + '</span>' if status_text else '') + '</span>'
                         + '<span class="model-file-error">' + escape(error) + '</span><span class="model-file-feedback" aria-live="polite"></span></span></button>')
        waiting = any(job['status'] in ('pending','running') for job in jobs)
        latest = {}
        for job in jobs: latest[(job['session_id'], job['turn_id'], tuple(job['artifact_ids'] or []))] = job
        failures = [job for job in latest.values() if job['status'] == 'failed']
        if failures:
            cards.append('<span class="model-file-error" data-file-notice="true" data-conversation-id="' + html.escape(getattr(model, '_conversation_id', ''), quote=True) + '">回答已保留，文件获取失败；请重新连接后重试</span>')
        revision = hashlib.sha256(json.dumps([records, [(job['id'],job['status']) for job in latest.values()]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        markup = '<div class="model-file-cards" aria-label="生成的文件" data-file-pending="' + str(bool(waiting)).lower() + '" data-file-revision="' + revision + '">' + ''.join(cards) + '</div>' if _agent(model) or cards else ''
        # The hidden native label travels with its File value, so the browser
        # maps stable IDs to links from the same render, even with duplicate names.
        return [gr.update(visible=bool(records or failures)), gr.update(value=markup), gr.update(value=paths, label=json.dumps(ready_ids)), gr.update() if _agent(model) else gr.update(value='')]


def describe_settings(model):
    if not _agent(model): return ''
    configured = model._tool_settings
    current = (model._session_settings or {}).get('tools')
    lines = [model._notice] if model._notice else []
    if model._pending_network is not None:
        lines.append('待确认的新会话联网设置：' + ('开启' if model._pending_network else '关闭') + '；点击按新配置新建并继续后生效')
    def summary(settings):
        enabled = [label for label, state, _ in tool_availability(settings) if state == '已启用']
        return ('云端执行环境联网：' + ('开' if settings['network'] else '关') + '；内置网页搜索：'
                + (settings['search_mode'] if settings['web_search'] else '关') + '；能力：' + '、'.join(enabled))
    lines.append('新会话将使用：' + summary(configured))
    if current:
        lines.append('当前会话实际设置：' + summary(current))
        if current != configured or model.system_prompt != model._session_settings.get('instructions'):
            lines.append('配置有变更。继续原会话会保持原设置；按新配置新建并继续只带入文字，原聊天会保留。')
    lines.append('已生效模型：' + model.model_name + '；推理：' + (model._reasoning or '模型默认'))
    return '\n\n'.join(lines)


def browser_form(model, request_id=None, request: gr.Request = None):
    if _agent(model) and request is not None: model.bind_owner(request)
    if not _agent(model): return '', gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
    cards = model._pending_actions
    card = next((card for card in cards if card['request_id'] == request_id), cards[0] if cards else None)
    if not card: return '', gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
    request = card['request']
    origin = request.get('origin') or request.get('credential_origin') or '未提供目标网站，不能提交登录'
    content = '<div id="agent-browser-form" data-request-id="' + html.escape(card['request_id'], quote=True) + '">'
    content += '<p><strong>等待授权或登录</strong></p><p>目标网站：' + html.escape(origin) + '</p>'
    content += '<p>' + html.escape(request.get('reason') or 'Agent 需要处理这个网站请求才能继续') + '</p>'
    login = request.get('type') == 'browser_authentication'
    if not login: content += '<p>批准范围仅为上述网站 origin；不会批准其他网站，也不代表同意任意外部操作。</p>'
    else:
        content += '<p>请核对网站。表单值只提交到专用登录接口，不进入聊天记录；提交后会清空。所有输入均隐藏显示。</p>'
        options = request.get('options') or []
        if options:
            content += '<label>登录方式 <select id="agent-login-option" onchange="window.chuanhuAgentLoginOption?.()">'
            content += ''.join('<option value="' + html.escape(option['id'], quote=True) + '" data-fields="' + html.escape(json.dumps(option.get('field_ids', [])), quote=True) + '">' + html.escape(option['label']) + '</option>' for option in options)
            content += '</select></label>'
        first_fields = set(options[0].get('field_ids', [])) if options else None
        for field in request.get('fields') or []:
            hidden = first_fields is not None and field['id'] not in first_fields
            content += '<label data-agent-field="' + html.escape(field['id'], quote=True) + '"' + (' hidden' if hidden else '') + '>'
            content += html.escape(field.get('label') or field['id']) + ('（必填）' if field.get('required') else '')
            content += '<input type="password" autocomplete="off" data-field-id="' + html.escape(field['id'], quote=True) + '" /></label>'
    content += '</div>'
    return content, gr.update(visible=not login), gr.update(visible=not login), gr.update(visible=True), gr.update(visible=login and bool(request.get('credential_origin')))


class AgentPanel:
    def __init__(self, format_user=None, format_assistant=None):
        self.format_user = format_user or (lambda value: value)
        self.format_assistant = format_assistant or (lambda value: value)

    def activity_value(self, model, status=None):
        """Task controls express normal state; errors use Gradio's error UI."""
        if isinstance(status, dict) and status.get('__type__') == 'update' and 'value' not in status:
            return gr.update()
        return gr.update(value='', visible=False)

    def status_callback(self, callback, index=0, *, header=False, returned_model=None, input_feedback=False):
        """Keep ordinary header results; route only Agent feedback locally."""
        def project(result, args):
            values = list(result) if isinstance(result, (tuple, list)) else [result]
            model = values[returned_model] if returned_model is not None else next(
                (arg for arg in args if hasattr(arg, 'chatbot')), None)
            local = self.activity_value(model, values[index])
            if header:
                if _agent(model) and not (isinstance(values[index], dict) and values[index].get('__type__') == 'update' and 'value' not in values[index]): values[index] = ''
                return (*values, local)
            values[index] = local
            return tuple(values) if isinstance(result, (tuple, list)) else values[0]
        if inspect.isgeneratorfunction(callback):
            @wraps(callback)
            def generator(*args, **kwargs):
                for result in callback(*args, **kwargs): yield project(result, (*args, *kwargs.values()))
            return generator
        @wraps(callback)
        def call(*args, **kwargs):
            return project(callback(*args, **kwargs), (*args, *kwargs.values()))
        return call

    def emit_ui_error(self, model, request: gr.Request):
        # This event has no outputs. It can only consume immutable completed
        # operation receipts, never active errors or shared frontend State.
        if not _agent(model) or getattr(model, '_retired', False): return
        model.bind_owner(request)
        message = model.take_completed_ui_errors()
        if message: raise gr.Error(message)

    def emit_stop_error(self, model, request: gr.Request):
        return self.emit_ui_error(model, request)

    def render_chat(self, model, rows):
        if not _agent(model): return rows
        from modules.agent.message_files import render_projection
        if isinstance(rows, dict) and rows.get('__type__') == 'update':
            if 'value' not in rows: return rows
            return dict(rows, value=self.render_chat(model, rows['value']))
        # Align identities against raw cells before making a waiting cell visible.
        # Converting None to '' first loses the canonical user-only row match.
        projection = message_file_projection(model, rows)
        return render_projection(projection, self.format_user, self.format_assistant)

    def chat_value(self, model, request: gr.Request):
        if not _agent(model): return gr.update()
        model.bind_owner(request)
        return gr.update(value=self.render_chat(model, model.chatbot))

    def input_components(self):
        with gr.Column(visible=False, elem_id='agent-input-files', min_width=0, scale=0) as self.input_group:
            self.input_feedback = gr.Markdown('', visible=False, elem_id='agent-input-feedback')
            self.input_picker = gr.File(file_count='multiple', type='filepath', label='添加消息附件', show_label=False,
                                        elem_id='agent-upload-files')
            self.input_files = gr.File(file_count='multiple', type='filepath', label='{}', show_label=True,
                                       elem_id='agent-pending-files')
            self.input_target = gr.Textbox(visible=False)
            self.input_remove_payload = gr.Textbox(elem_id='agent-input-remove-payload', show_label=False)
            self.input_remove = gr.Button('移除附件', elem_id='agent-input-remove')

    @staticmethod
    def input_value(model, interactive=None):
        if not _agent(model): return gr.update(value=[], label='{}', interactive=False)
        with model._lock:
            if interactive is None:
                interactive = not (model._running or getattr(model, '_background_busy', False) or bool(getattr(model, '_pending_send', None)) or model._needs_sync
                                   or model._state.get('outcome') not in ('not_started', 'completed', 'cancelled', 'failed'))
            records = model._input_stager.snapshot() if model._input_stager is not None else ()
            metadata = {'target': model._conversation_id, 'ids': [record.input_id for record in records], 'files': [{'id':record.input_id,'name':record.name,'basename':split_filename(record.name)[0],'size':record.size,
                        'extension': file_type_label(record.name), 'size_label': file_size_label(record.size), 'icon': file_icon(record.name, input_card=True)} for record in records]}
            return gr.update(value=list(model._pending_upload_paths), label=json.dumps(metadata), interactive=interactive)

    def selectors(self):
        with gr.Column(visible=False, elem_id='agent-model-options', min_width=0) as self.selection_group:
            self.model = gr.Dropdown(label=i18n('ui.toolbox.agent.model'), choices=list(MODEL_EFFORTS), value='gpt-6.1-sol', allow_custom_value=True, min_width=150)
            self.reasoning = gr.Dropdown(label=i18n('ui.toolbox.agent.reasoning'), choices=reasoning_choices(), value='default', min_width=120)
            self.choice_revision = gr.Number(value=0, precision=0, visible=False)
            self.choice_target = gr.Textbox(visible=False)
            self.choice_result = gr.Textbox(visible=False)

    def output_components(self):
        self.artifacts = ArtifactPanel()
        self.activity = gr.Markdown('', visible=False, elem_id='agent-activity-feedback')
        self.stop_target = gr.JSON(value=None, visible=False)
        with gr.Column(visible=False, elem_id='agent-browser-requests', min_width=0, scale=0) as self.browser_group:
            self.request_id = gr.Dropdown(label='当前网站请求', choices=[])
            self.browser_html = gr.HTML()
            with gr.Row():
                self.approve = gr.Button('批准此网站', visible=False)
                self.deny = gr.Button('拒绝此网站', visible=False)
                self.cancel_request = gr.Button('取消此请求', visible=False)
                self.login_submit = gr.Button('提交登录', visible=False)
            self.payload = gr.Textbox(type='password', visible=False)

    def settings_components(self):
        self.tools_separator = gr.Markdown('---', elem_classes='hr-line', elem_id='agent-tools-separator', visible=False)
        with gr.Accordion(i18n('ui.toolbox.agent.tools_title'), open=True, visible=False, elem_id='agent-tools-accordion') as self.settings_group:
            self.settings_status = gr.Markdown(visible=False)
            gr.Markdown(i18n('ui.toolbox.agent.locked_hint'))
            self.network = gr.Checkbox(label=i18n('ui.toolbox.agent.network'), value=True, elem_id='agent-network-access', elem_classes='switch-checkbox')
            self.code = gr.Checkbox(label=i18n('ui.toolbox.agent.code'), value=True, elem_classes='switch-checkbox')
            self.search = gr.Checkbox(label=i18n('ui.toolbox.agent.search'), value=True, elem_classes='switch-checkbox')
            self.search_mode = gr.Dropdown(label=i18n('ui.toolbox.agent.search_mode'), choices=[(i18n('ui.toolbox.agent.search_' + value), value) for value in ('live', 'cached', 'disabled')], value='live')
            self.domains = gr.Textbox(label=i18n('ui.toolbox.agent.domains'), visible=False)
            self.browser = gr.Checkbox(label=i18n('ui.toolbox.agent.browser'), value=True, elem_classes='switch-checkbox')
            self.screenshots = gr.Checkbox(label=i18n('ui.toolbox.agent.screenshots'), value=False, elem_classes='switch-checkbox')
            # Deferred until application tools are deliberately exposed in the UI.
            # Keep callback slots and backend implementations for later use.
            # self.discovery = gr.Checkbox(label=i18n('ui.toolbox.agent.discovery'), value=True, elem_classes='switch-checkbox')
            # self.programmatic = gr.Checkbox(label=i18n('ui.toolbox.agent.programmatic'), value=True, elem_classes='switch-checkbox')
            self.discovery = gr.Checkbox(value=False, visible=False, interactive=False)
            self.programmatic = gr.Checkbox(value=False, visible=False, interactive=False)
            self.functions = gr.CheckboxGroup(label=i18n('ui.toolbox.agent.functions'), choices=list(FUNCTIONS), value=[], visible=False)
            self.mcp = gr.Textbox(label=i18n('ui.toolbox.agent.mcp'), value='[]', lines=5)
            self.availability = gr.Dataframe(headers=[i18n('ui.toolbox.agent.' + key) for key in ('capability', 'status', 'description')], datatype=['str'] * 3, interactive=False, wrap=True, visible=False)
            self.fork = gr.Button(i18n('ui.toolbox.agent.fork'), visible=False)
            self.tool_revision = gr.Number(value=0, precision=0, visible=False)
            self.config_target = gr.Textbox(visible=False, elem_id="agent-config-target")
    @staticmethod
    def config_from_inputs(network, code, search, mode, domains, browser, screenshots, discovery, programmatic, functions, mcp):
        return {'network': network, 'code_execution': code, 'web_search': search, 'search_mode': mode,
                'search_domains': [s.strip() for s in domains.splitlines() if s.strip()],
                'computer_use': browser, 'include_screenshots': screenshots, 'tool_search': discovery,
                'programmatic_tool_calling': programmatic, 'functions': functions, 'mcp_servers': json.loads(mcp)}

    @staticmethod
    def user_tool_config(model, config):
        # Existing remote sessions keep their immutable configuration. New UI
        # sessions cannot enable the two deferred features through stale inputs.
        if not model._state.get('session_id'):
            return dict(config, tool_search=False, programmatic_tool_calling=False)
        return config

    def wrap_model_change(self, change, capability_ui, legacy_outputs):
        outputs = list(dict.fromkeys([legacy_outputs[0], *self.outputs, *capability_ui.stream_outputs, *legacy_outputs[1:]]))
        @wraps(change)
        def change_with_ui(*args, **kwargs):
            result = list(change(*args, **kwargs))
            model = result[0]
            if _agent(model):
                result[2] = self.render_chat(model, result[2])
            values = dict(zip(legacy_outputs, result))
            values.update(zip(self.outputs, self.values(model)))
            values.update(zip(capability_ui.stream_outputs, capability_ui.stream_values(model)))
            return tuple(values[component] for component in outputs)
        return change_with_ui

    def wrap_reset(self, reset, capability_ui):
        @wraps(reset)
        def reset_with_ui(model, remain_system_prompt=False, request: gr.Request = None):
            with model_lock(model):
                if _agent(model):
                    if request is not None: model.bind_owner(request)
                    if getattr(model, "_pending_send", None):
                        raise gr.Error("消息尚在提交，请等待提交完成")
                    previous = model
                    model = previous.new_view()
                    previous.retire()
                result = reset(model, remain_system_prompt, request=request)
                # Publish the new visit before the cleared chat/Radio in the
                # same response, not in a later dependency callback.
                return (model, *capability_ui.stream_values(model), *result)
        return reset_with_ui

    def wrap_history_load(self, load, capability_ui=None, *, legacy_outputs=None):
        outputs = (list(dict.fromkeys([*legacy_outputs, *self.outputs, *capability_ui.outputs, self.history_list]))
                   if legacy_outputs is not None else None)
        @wraps(load)
        def load_with_selection(model, filename, request: gr.Request = None):
            with model_lock(model):
                result = load(model, filename, request=request)
                current = result[0]
                if not hasattr(current, 'chatbot'):
                    return tuple(gr.update() for _ in outputs) if outputs is not None else (*result, *((gr.update(),) if capability_ui is not None else ()), gr.update())
                if _agent(current) and isinstance(result[4], dict) and 'value' in result[4]:
                    result = (*result[:4], self.render_chat(current, result[4]), *result[5:])
                if outputs is not None:
                    values = dict(zip(legacy_outputs, result))
                    values.update(zip(self.outputs, self.values(current, request=request)))
                    for component, update in zip(capability_ui.outputs, capability_ui.values(current)):
                        previous = values.get(component)
                        values[component] = dict(previous, **update) if isinstance(previous, dict) and isinstance(update, dict) else update
                    values[self.history_list] = self.history_value(current)
                    if _agent(current): current._history_ui_projection_visit = current.agent_choice_target
                    return tuple(values[component] for component in outputs)
                marker = (() if capability_ui is None else
                          (capability_ui.stream_values(current)[capability_ui.stream_outputs.index(capability_ui.marker)],))
                return (*result, *marker, self.history_value(current))
        return load_with_selection

    def wrap_transfer(self, transfer):
        def transfer_input(inputs, current_model=None, agent_model=None, agent_reasoning='default', agent_choice_revision=None, agent_files=None,
                           network=None, code=None, search=None, mode=None, domains=None, browser=None, screenshots=None,
                           discovery=None, programmatic=None, functions=None, mcp=None, instructions=None, target=None, tool_revision=None,
                           request: gr.Request = None):
            if _agent(current_model):
                current_model.bind_owner(request)
                with current_model._lock:
                    if network is not None:
                        try: config = self.config_from_inputs(network, code, search, mode, domains, browser, screenshots, discovery, programmatic, functions, mcp)
                        except (TypeError, ValueError, AttributeError): raise gr.Error(i18n('ui.toolbox.agent.invalid_tools')) from None
                        current_model.freeze_agent_configuration(self.user_tool_config(current_model, config), instructions, tool_revision, target)
                    result = list(transfer(inputs, current_model, agent_model, agent_reasoning, agent_choice_revision, agent_files, request=request))
                    # Keep the draft until its first visible bubble supplies a display receipt.
                    # Failed preparation never needs a delayed server writeback.
                    result[1] = gr.update()
                    return tuple(result)
            return transfer(inputs, current_model, agent_model, agent_reasoning, agent_choice_revision, agent_files, request=request)
        return transfer_input

    def bind_sidebar(self, tab, prompt, template, prompt_group, ordinary_label):
        self.sidebar = (tab, prompt, template, prompt_group, ordinary_label)

    def sidebar_values(self, model):
        if not hasattr(self, 'sidebar'): return []
        enabled = _agent(model)
        locked = enabled and (bool(model._state.get('session_id')) or model._running or getattr(model, '_background_busy', False) or model._needs_sync
                              or model._state.get('outcome') not in ('not_started', 'completed', 'cancelled', 'failed')
                              or bool(getattr(model, '_pending_send', None)))
        return [gr.update(label='Agent' if enabled else self.sidebar[-1]),
                gr.update(**({'value':model.system_prompt} if locked else {}), interactive=not locked, label=i18n('ui.toolbox.agent.system_prompt') if enabled else 'System prompt', lines=4 if enabled else 8),
                gr.update(interactive=not locked), gr.update(label=i18n('ui.toolbox.agent.system_prompt') if enabled else 'Prompt')]

    def finish_submission(self, model, envelope, draft, request: gr.Request):
        if not _agent(model): return gr.update(), gr.update()
        model.bind_owner(request)
        with model._lock:
            if not isinstance(envelope, dict) or envelope.get('target') != id(model) or envelope.get('token') != getattr(model, '_draft_token', None) or getattr(model, '_draft_conversation', None) != model._conversation_id:
                return gr.update(), gr.update()
            return gr.update(), model._status()

    @property
    def config_inputs(self):
        return [self.network, self.code, self.search, self.search_mode, self.domains, self.browser, self.screenshots, self.discovery, self.programmatic, self.functions, self.mcp]

    @property
    def outputs(self):
        return ([self.accordion] if hasattr(self, 'accordion') else []) + ([self.separator] if hasattr(self, 'separator') else []) + ([self.tools_separator] if hasattr(self, 'tools_separator') else []) + [self.selection_group, self.settings_group, self.settings_status, self.model, self.reasoning,
                self.browser_group, self.request_id, self.browser_html, self.approve, self.deny, self.cancel_request, self.login_submit,
                *self.artifacts.outputs, *self.config_inputs, self.availability] + ([self.input_group, self.input_files, self.input_picker, self.input_target] if hasattr(self, 'input_files') else []) + (list(self.sidebar[:4]) if hasattr(self, 'sidebar') else []) + [self.config_target, self.choice_target]

    def values(self, model, request: gr.Request = None, include_config=True):
        enabled = _agent(model)
        if enabled and request is not None: model.bind_owner(request)
        if not enabled:
            return ([gr.update(visible=getattr(self, 'model_panel_visible', False), open=getattr(self, 'model_panel_visible', False))] if hasattr(self, 'accordion') else []) + ([gr.update(visible=False)] if hasattr(self, 'separator') else []) + ([gr.update(visible=False)] if hasattr(self, 'tools_separator') else []) + [gr.update(visible=False), gr.update(visible=False), '', gr.update(), gr.update(),
                    gr.update(visible=False), gr.update(choices=[], value=None), '', *[gr.update(visible=False)] * 4,
                    *ArtifactPanel.values(model), *[gr.update()] * 12] + ([gr.update(visible=False), gr.update(value=[], interactive=False), gr.update(value=[], interactive=False), ''] if hasattr(self, 'input_files') else []) + self.sidebar_values(model) + ['', '']
        busy = model._running or getattr(model, '_background_busy', False) or bool(getattr(model, '_pending_send', None)) or model._state.get('outcome') not in ('not_started', 'completed', 'cancelled', 'failed') or model._needs_sync
        next_model, next_reasoning = model.agent_model_choice
        cards = model._pending_actions
        chosen = cards[0]['request_id'] if cards else None
        browser = browser_form(model, chosen)
        session_locked = bool(model._state.get('session_id'))
        settings = (model._session_settings or {}).get('tools', model._tool_settings) if session_locked else self.user_tool_config(model, model._tool_settings)
        config = [settings['network'], settings['code_execution'], settings['web_search'], settings['search_mode'], '\n'.join(settings['search_domains']),
                  settings['computer_use'], settings['include_screenshots'], settings['tool_search'], settings['programmatic_tool_calling'], settings['functions'],
                  json.dumps(settings['mcp_servers'], ensure_ascii=False, indent=2)]
        return ([(gr.update(visible=True, open=True) if include_config else gr.update())] if hasattr(self, 'accordion') else []) + ([gr.update(visible=True)] if hasattr(self, 'separator') else []) + ([gr.update(visible=True)] if hasattr(self, 'tools_separator') else []) + [gr.update(visible=True), gr.update(visible=True), '',
                gr.update(**({'value': next_model} if include_config else {}), interactive=not busy), gr.update(**({'value': next_reasoning or 'default', 'choices': reasoning_choices(next_model, next_reasoning), 'allow_custom_value': next_model not in MODEL_EFFORTS, 'info': reasoning_info(next_model)} if include_config else {}), interactive=not busy),
                gr.update(visible=bool(cards)), gr.update(choices=[((card['request'].get('origin') or card['request'].get('credential_origin') or '网站请求') + ' · ' + card['request_id'], card['request_id']) for card in cards], value=chosen),
                *browser, *ArtifactPanel.values(model), *[gr.update(**({'value':value} if include_config or session_locked else {}), interactive=not busy and not session_locked and component not in (self.discovery, self.programmatic)) for component, value in zip(self.config_inputs, config)], gr.update(value=tool_availability(settings))] + ([gr.update(visible=True), self.input_value(model, not busy), gr.update(interactive=not busy), model._conversation_id] if hasattr(self, 'input_files') else []) + self.sidebar_values(model) + [model._conversation_id, model.agent_choice_target]

    @property
    def stream_outputs(self):
        outputs = [self.model, self.reasoning, self.browser_group, self.request_id, self.browser_html, self.approve, self.deny, self.cancel_request, self.login_submit, *self.artifacts.outputs]
        if hasattr(self, 'input_files'): outputs += [self.input_files, self.input_picker]
        if hasattr(self, 'history_list'): outputs += [self.history_list]
        return outputs

    def history_value(self, model):
        from modules.models.base_model import get_history_names
        from pathlib import Path
        names = get_history_names(model.user_name)
        selected = Path(model.history_file_path).name.removesuffix('.json')
        return gr.update(choices=names, value=selected if selected in names else None)

    def stream_values(self, model, request=None):
        values = self.values(model, request=request, include_config=False)
        return [self.history_value(model) if component is getattr(self, 'history_list', None)
                else values[self.outputs.index(component)] for component in self.stream_outputs]

    def boundary_values(self, capability_ui):
        def values_at_boundary(model, request: gr.Request):
            return [*self.values(model, request=request, include_config=False), *capability_ui.values(model)]
        return values_at_boundary

    def history_boundary_values(self, capability_ui):
        def history_values_at_boundary(model, request: gr.Request):
            outputs = [*self.outputs, *capability_ui.outputs]
            if not _agent(model): return [gr.update() for _ in outputs]
            with model._lock:
                scope = getattr(model, '_history_ui_complete_scope', None)
                if scope is None or not scope.current(model): return [gr.update() for _ in outputs]
                model._history_ui_complete_scope = None
                values = [*self.values(model, request=request, include_config=False), *capability_ui.values(model)]
                previous = getattr(model, '_history_ui_previous_values', {})
                model._history_ui_previous_values = {}
                return [gr.update() if value == previous.get(component._id) else value for component, value in zip(outputs, values)]
        return history_values_at_boundary

    def wrap_predict(self, predict, capability_ui, compact=False):
        def predict_with_ui(model, inputs, chatbot, use_websearch=False, files=None, reply_language=None, agent_files=None, request: gr.Request = None):
            def controls():
                if compact and not _agent(model):
                    return [self.history_value(model) if component is getattr(self, 'history_list', None) else gr.update()
                            for component in [*self.stream_outputs, *capability_ui.stream_outputs]]
                return [*(self.stream_values(model, request=request) if compact else self.values(model, request=request, include_config=False)),
                        *(capability_ui.stream_values(model) if compact else capability_ui.values(model))]
            if _agent(model): files = agent_files
            operation = uuid4().hex if _agent(model) else None
            if operation is not None:
                with model._lock:
                    duplicate = bool(getattr(model, '_predict_error_operation', None)) and model._running
                    if not duplicate: model._predict_error_operation = operation
                if duplicate:
                    model.record_ui_error('当前任务仍在运行', operation=operation)
                    yield tuple(gr.update() for _ in [None, None, *(self.stream_outputs if compact else self.outputs), *(capability_ui.stream_outputs if compact else capability_ui.outputs)])
                    model.complete_error_operation(operation)
                    return
            updates = FrameUpdates()
            target, owner = (model._conversation_id, model._owner) if operation else (None, None)
            visit = model.agent_choice_target if operation else None
            if operation:
                from modules.agent.message_files import decode_rows
                previous_rows = decode_rows(chatbot, target)
            try:
                projected = ((self.render_chat(model, chat), status) for chat, status in predict(model, inputs, chatbot, use_websearch, files, reply_language, request=request))
                try:
                    for chat, status in _chat_frames(projected):
                        if operation and (model._retired or model._conversation_id != target or model._owner != owner or model.agent_choice_target != visit
                                          or getattr(model, '_predict_error_operation', None) != operation):
                            yield tuple(gr.update() for _ in [None, None, *(self.stream_outputs if compact else self.outputs), *(capability_ui.stream_outputs if compact else capability_ui.outputs)])
                            return
                        if (operation and isinstance(inputs, dict)
                                and inputs.get('token') == getattr(model, '_draft_token', None)
                                and getattr(model, '_draft_conversation', None) == target
                                and len(model._display) > len(previous_rows or [])):
                            # This response first displays the user's bubble. Its
                            # draft receipt must travel in this same UI frame,
                            # independently of remote submission acknowledgement.
                            with model._lock:
                                model._draft_presented = True
                                model._remove_input_selection(getattr(model, '_draft_input_ids', ()))
                        yield chat, status, *updates.changes(controls())
                except gr.Error as error:
                    if operation is None: raise
                    model.record_ui_error(str(error), operation=operation)
                if operation and (model._retired or model._conversation_id != target or model._owner != owner or model.agent_choice_target != visit or getattr(model, '_predict_error_operation', None) != operation):
                    yield tuple(gr.update() for _ in [None, None, *(self.stream_outputs if compact else self.outputs), *(capability_ui.stream_outputs if compact else capability_ui.outputs)])
                    return
                final_chat = gr.update(value=self.render_chat(model, model.chatbot)) if _agent(model) else gr.update()
                final_generation = model._state.get('generation') if operation else None
                yield final_chat, (model._status() if _agent(model) else gr.update()), *updates.changes(controls())
                if operation and (model._retired or model.agent_choice_target != visit or model._conversation_id != target
                        or model._owner != owner or getattr(model, '_predict_error_operation', None) != operation
                        or model._state.get('generation') != final_generation):
                    yield tuple(gr.update() for _ in [None, None, *(self.stream_outputs if compact else self.outputs), *(capability_ui.stream_outputs if compact else capability_ui.outputs)])
                    return
                if operation is not None: model.complete_error_operation(operation)
            finally:
                if operation is not None:
                    with model._lock:
                        if getattr(model, '_predict_error_operation', None) == operation: model._predict_error_operation = None
        return predict_with_ui

    def wire(self, current_model, chatbot, status_display, capability_ui=None):
        # These callbacks are Agent-only. The ordinary shared header is untouched.
        status_display = self.activity
        if hasattr(self, 'input_files'):
            def stage_files(model, files, request: gr.Request):
                if not _agent(model): return self.input_value(model)
                model.bind_owner(request)
                # File.change also fires for server renders. A stale response
                # may show an old subset; restore it, never interpret it as a
                # user removing newer attachments.
                with model._lock:
                    update = self.input_value(model)
                    if tuple(str(path) for path in files or []) == model._pending_upload_paths:
                        update.pop('value', None)
                    return update
            self.input_files.change(stage_files, [current_model, self.input_files], [self.input_files], queue=False, show_progress='hidden')
            def remove_files(model, payload, request: gr.Request):
                if not _agent(model):
                    yield '', '', self.input_value(model)
                    return
                model.bind_owner(request)
                operation = uuid4().hex
                try:
                    removal = json.loads(payload)
                    if not isinstance(removal.get('ids'), list): raise ValueError()
                    message = model.remove_input_ids(removal['ids'], removal.get('target'))
                except Exception as error:
                    message = str(error) if isinstance(error, gr.Error) else '无法移除附件，请重试'
                    model.record_ui_error(message, operation=operation)
                yield '', message, self.input_value(model)
                model.complete_error_operation(operation)
            self.input_remove.click(self.status_callback(remove_files, 1, input_feedback=True), [current_model, self.input_remove_payload],
                                    [self.input_remove_payload, self.input_feedback, self.input_files], queue=True, concurrency_limit=None).then(self.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
            def upload_files(model, files, target, request: gr.Request):
                if not _agent(model):
                    yield '', gr.update(value=[]), gr.update()
                    return
                model.bind_owner(request)
                operation = uuid4().hex
                try: message = model.add_input_files(files, target)
                except Exception as error:
                    message = str(error)
                    model.record_ui_error(message, operation=operation)
                yield message, gr.update(value=[]), self.input_value(model)
                model.complete_error_operation(operation)
            upload_event = self.input_picker.upload(self.status_callback(upload_files, input_feedback=True), [current_model, self.input_picker, self.input_target],
                                     [self.input_feedback, self.input_picker, self.input_files], queue=True, concurrency_limit=None, show_progress='hidden',
                js='(model, files, target) => { files = window.chuanhuUploadStaging?.(files) ?? files; if (!window.chuanhuUploadStaging) window.chuanhuAgentUploadStaging = true; window.chuanhuRefreshSendButton?.(); return [model, files, window.chuanhuAgentUploadTarget || target]; }')
            upload_event.then(None, [self.input_files], [], queue=False, js='(files) => { if (window.chuanhuUploadCommitted) window.chuanhuUploadCommitted(files); else { window.chuanhuAgentUploading = false; window.chuanhuAgentUploadStaging = false; window.chuanhuRefreshSendButton?.(); } }').then(self.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
        def choose_settings(model, name, effort, revision, target, request: gr.Request):
            model.bind_owner(request)
            try: message = model.set_agent_model(name, effort, revision, target=target)
            except Exception as error: raise gr.Error(str(error)) from None
            if revision != model._choice_revision or target != model.agent_choice_target:
                return gr.update(), gr.update()
            name, effort = model.agent_model_choice
            receipt = json.dumps({'target': model.agent_choice_target,
                'revision': model._choice_revision, 'value': effort or 'default',
                'choices': reasoning_choices(name, effort), 'allow_custom_value': name not in MODEL_EFFORTS, 'info': reasoning_info(name)})
            return (message if message is not None else gr.update()), receipt
        choice_js = '''(state, name, effort, unused, target) => {
            window.chuanhuAgentChoiceRevision = (window.chuanhuAgentChoiceRevision || 0) + 1;
            return [state, name, effort, window.chuanhuAgentChoiceRevision, target];
        }'''
        for selector in (self.model, self.reasoning):
            event = selector.input(self.status_callback(choose_settings), [current_model, self.model, self.reasoning, self.choice_revision, self.choice_target], [status_display, self.choice_result], queue=False, js=choice_js)
            # Native dropdown updates are committed only for the current visit
            # and latest input revision; delayed replies cannot restore minimal.
            event.then(None, [self.choice_result, self.choice_target], [self.reasoning], queue=False,
                js='''(wire, target) => {
                    let result; try { result = JSON.parse(wire); } catch { return [{__type__: "update"}]; }
                    if (result.target !== target || result.revision !== window.chuanhuAgentChoiceRevision)
                        return [{__type__: "update"}];
                    return [{__type__: "update", value: result.value, choices: result.choices,
                        allow_custom_value: result.allow_custom_value, info: result.info}];
                }''')
        def choose_tools(model, network, code, search, mode, domains, browser, screenshots, discovery, programmatic, functions, mcp, revision, target, request: gr.Request):
            model.bind_owner(request)
            try:
                value = self.config_from_inputs(network, code, search, mode, domains, browser, screenshots, discovery, programmatic, functions, mcp)
                model.stage_agent_tools(self.user_tool_config(model, value), revision, target)
                return gr.update()
            except Exception as error:
                raise gr.Error(str(error) if not isinstance(error, json.JSONDecodeError) else i18n('ui.toolbox.agent.invalid_mcp')) from None
        tools_js = '''(model, ...values) => {
            window.chuanhuAgentToolRevision = (window.chuanhuAgentToolRevision || 0) + 1;
            values[11] = window.chuanhuAgentToolRevision;
            return [model, ...values.slice(0, 13)];
        }'''
        for component in self.config_inputs:
            component.input(self.status_callback(choose_tools), [current_model, *self.config_inputs, self.tool_revision, self.config_target],
                            [status_display], queue=False, js=tools_js)
        def fork(model, request: gr.Request):
            operation = uuid4().hex
            try:
                model.bind_owner(request)
                result = model.new_session_from_history()
            except gr.Error as error:
                model.record_ui_error(str(error), operation=operation)
                result = (gr.update(), gr.update())
            model.complete_error_operation(operation)
            return result
        fork_event = self.fork.click(self.status_callback(fork, 1), [current_model], [chatbot, status_display]).then(self.values, [current_model], self.outputs).then(self.chat_value, [current_model], [chatbot])
        if capability_ui is not None: fork_event = fork_event.then(capability_ui.values, [current_model], capability_ui.outputs)
        fork_event.then(self.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
        # Called only after an authorized local history selection. This observer
        # uses GET snapshots, never recover_stream or function-action execution.
        self.history_outputs = [chatbot, status_display] + (capability_ui.stream_outputs + self.stream_outputs if capability_ui is not None else [])
        def observe_history(model, request: gr.Request):
            # Gradio 4.29 writes None to every output when a queued generator
            # ends before its first frame. Always start with explicit no-ops.
            yield tuple(gr.update() for _ in self.history_outputs)
            if not _agent(model) or model._retired: return
            model.bind_owner(request)
            target, owner = model._conversation_id, model._owner
            visit = model.agent_choice_target
            model._history_ui_complete_scope = None
            epoch = uuid4().hex
            updates = FrameUpdates()
            presented = {}
            if capability_ui is not None:
                presented = {component._id: deepcopy(value) for component, value in zip([*self.outputs, *capability_ui.outputs], [*self.values(model, request=request, include_config=False), *capability_ui.values(model)])}
                if getattr(model, '_history_ui_projection_visit', None) == visit:
                    updates.changes((*capability_ui.stream_values(model), *self.stream_values(model, request=request)))
            def remember_controls(extras):
                for component, value in zip([*capability_ui.stream_outputs, *self.stream_outputs] if capability_ui is not None else [], extras):
                    presented[component._id] = deepcopy(value)
            previous_chat = deepcopy(self.render_chat(model, model.chatbot))
            def chat_change(chat):
                nonlocal previous_chat
                rendered = self.render_chat(model, chat)
                value = rendered.get('value') if isinstance(rendered, dict) else rendered
                if value == previous_chat: return gr.update()
                previous_chat = deepcopy(value)
                return rendered
            def current():
                return not model._retired and model.agent_choice_target == visit and model._conversation_id == target and model._owner == owner and getattr(model, '_history_epoch', None) == epoch
            from modules.agent.tasks import TASKS
            task = TASKS.find(model)
            if task is None and not model._needs_sync: return
            if task is None and model._needs_sync:
                task = TASKS.start(model, lambda: model.observe_history(error_operation=epoch), read_only=model._state.get('outcome') in ('completed', 'cancelled', 'failed'))
            model._history_epoch = epoch
            source = task.subscribe(model) if task is not None else model.observe_history(error_operation=epoch)
            for chat, status in _chat_frames(source):
                if not current():
                    yield tuple(gr.update() for _ in self.history_outputs)
                    return
                extras = (*capability_ui.stream_values(model), *self.stream_values(model, request=request)) if capability_ui is not None else ()
                remember_controls(extras)
                yield chat_change(chat), status, *updates.changes(extras)
            if not current():
                yield tuple(gr.update() for _ in self.history_outputs)
                return
            extras = (*capability_ui.stream_values(model), *self.stream_values(model, request=request)) if capability_ui is not None else ()
            with model._lock:
                stale = not current()
                if not stale:
                    remember_controls(extras)
                    model._history_ui_previous_values = presented
                    model._history_ui_complete_scope = OperationScope.capture(model)
            if stale:
                yield tuple(gr.update() for _ in self.history_outputs)
                return
            yield chat_change(gr.update(value=model.chatbot)), model._status(), *updates.changes(extras)
            if not current():
                yield tuple(gr.update() for _ in self.history_outputs)
                return
            model.complete_error_operation(epoch)
        self.observe_history = self.status_callback(observe_history, 1)
        def refresh_files(model, request: gr.Request):
            if not _agent(model) or model._retired: return ''
            model.bind_owner(request)
            with model._lock:
                model.refresh_files()
                updates = ArtifactPanel.values(model)
                target, generation = model.agent_choice_target, model._state.get('generation')
            from gradio.processing_utils import move_files_to_cache
            # Cache copies run outside the model lock. A large file cannot
            # block the next send or terminal persistence. JS checks its scope.
            updates[2]['value'] = move_files_to_cache(self.artifacts.files.postprocess(updates[2]['value']), self.artifacts.files, postprocess=True)
            return json.dumps(dict(target=target, generation=generation, updates=updates), ensure_ascii=False)
        self.artifacts.refresh.click(refresh_files, [current_model], [self.artifacts.refresh_wire],
            queue=False, show_progress='hidden', concurrency_limit=None).then(None,
            [self.artifacts.refresh_wire, self.choice_target], self.artifacts.outputs, queue=False,
            js='(wire, target) => window.chuanhuAcceptFileUpdate?.(wire, target) || Array.from({length:4}, () => ({__type__: "update"}))')
        def retry_file(model, identifier, request: gr.Request):
            operation = uuid4().hex
            try:
                model.bind_owner(request)
                scope = OperationScope.capture(model)
                updates = FrameUpdates()
                for _, status in model.retry_artifact(identifier, error_operation=operation):
                    if not scope.current(model):
                        yield tuple(gr.update() for _ in [None, *self.stream_outputs])
                        return
                    yield status, *updates.changes(self.stream_values(model, request=request))
            except gr.Error as error:
                if 'scope' in locals() and not scope.current(model):
                    yield tuple(gr.update() for _ in [None, *self.stream_outputs])
                    return
                model.record_ui_error(str(error), operation=operation)
                yield tuple(gr.update() for _ in [None, *self.stream_outputs])
            if 'scope' in locals() and not scope.current(model):
                yield tuple(gr.update() for _ in [None, *self.stream_outputs])
                return
            if 'scope' in locals() and scope.current(model): model.complete_error_operation(operation)
        self.artifacts.retry.click(self.status_callback(retry_file), [current_model, self.artifacts.retry_id], [status_display, *self.stream_outputs], show_progress='hidden').then(self.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
        self.request_id.input(browser_form, [current_model, self.request_id], [self.browser_html, self.approve, self.deny, self.cancel_request, self.login_submit])
        def origin(model, identifier, decision):
            card = next((card for card in model._pending_actions if card['request_id'] == identifier), None)
            if card is None: raise gr.Error('该网站请求已失效')
            request_type = card['request']['type']
            response = {'type': request_type, 'action': 'cancel'} if request_type == 'browser_authentication' else {'type': request_type, 'decision': decision}
            return model.respond_browser(identifier, response), *self.values(model)
        def origin_callback(decision):
            def respond(model, identifier, request: gr.Request):
                operation = uuid4().hex
                try:
                    model.bind_owner(request)
                    result = origin(model, identifier, decision)
                except Exception as error:
                    model.record_ui_error(str(error), operation=operation)
                    result = (gr.update(), *[gr.update() for _ in self.outputs])
                # Direct callbacks finish all local work in one atomic response;
                # the no-output follower reports errors after that response.
                model.complete_error_operation(operation)
                return result
            return respond
        for button, decision in ((self.approve, 'approve'), (self.deny, 'deny'), (self.cancel_request, 'cancel')):
            button.click(self.status_callback(origin_callback(decision)), [current_model, self.request_id], [status_display, *self.outputs], queue=False).then(self.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
        def login(model, identifier, payload, request: gr.Request):
            model.bind_owner(request)
            operation = uuid4().hex
            try:
                response = json.loads(payload)
                message = model.respond_browser(identifier, response)
            except Exception as error:
                message = str(error) if isinstance(error, gr.Error) else '登录提交失败；请重新选择历史确认当前请求，勿重复提交'
                model.record_ui_error(message, operation=operation)
            finally: payload = None
            yield '', message, *self.values(model)
            model.complete_error_operation(operation)
        self.login_submit.click(self.status_callback(login, 1), [current_model, self.request_id, self.payload], [self.payload, status_display, *self.outputs], queue=True, concurrency_limit=None,
            js='''(model, id, unused) => {
                const root = (typeof gradioApp === 'function' ? gradioApp() : document).querySelector('#agent-browser-form');
                if (!root || root.dataset.requestId !== id) return [model, id, '{}'];
                const option = root.querySelector('#agent-login-option');
                const allowed = option ? JSON.parse(option.selectedOptions[0].dataset.fields) : null;
                const fields = Array.from(root.querySelectorAll('input[data-field-id]')).filter(x => allowed === null || allowed.includes(x.dataset.fieldId)).map(x => ({field_id: x.dataset.fieldId, value: x.value}));
                const response = {type:'browser_authentication', action:'submit', fields};
                if (option) response.selected_option = option.value;
                root.querySelectorAll('input').forEach(x => x.value='');
                return [model, id, JSON.stringify(response)];
            }''').then(self.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
        # 流式回调已携带文件与权限状态，不再由 chatbot.change 逐 token 重刷侧栏。
