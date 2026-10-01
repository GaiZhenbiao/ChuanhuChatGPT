"""Optional Agent UI; a separate SDK process keeps core dependencies intact."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid
import gradio as gr
from modules import shared
from modules.plugin_callbacks import on_toolbox_tab, guarded_callback

from modules.presets import i18n

_TRANSLATIONS = {'尚未安装隔离 Agents 环境，请查看 docs/agents.md。普通聊天不受影响。': 'Isolated Agents environment is missing. See '
                                                  'docs/agents.md. Ordinary chat remains available.',
 'Agents 子进程返回了无效响应。未重发任务。': 'The Agents worker returned an invalid response. The task was not resent.',
 '本地等待超时；关闭连接不会停止远程 Agent，请点击停止并恢复状态。': 'Local wait timed out. Closing the connection does not stop the '
                                        'remote Agent; click Stop and recover its status.',
 '需要有效的浏览器会话。': 'A valid browser session is required.',
 'Agent 会话不属于当前浏览器。': 'This Agent session belongs to another browser.',
 '未开始': 'Not started',
 '请先确认发送至官方 API 并允许托管沙箱运行代码；调用会产生费用。': 'Confirm sending to the official API and allowing sandbox code '
                                       'execution; charges apply.',
 '任务内容须为 1–20000 字符。': 'Task must contain 1–20000 characters.',
 '已有未确认结束的任务。先停止或恢复状态，避免重复发送。': 'A previous task has an unconfirmed outcome. Stop it or recover its status '
                                'before sending again.',
 '启动独立运行器': 'Starting isolated worker',
 '发送前已停止，没有提交新的任务。': 'Stopped before sending. No new task was submitted.',
 '完成': 'Completed',
 '停止请求失败': 'Cancellation request failed',
 '子进程提前结束。未重发；请恢复状态。': 'Worker ended early. Task was not resent; recover its status.',
 '目标 turn 已结束。': 'The target turn has ended.',
 '已请求停止；新 turn 的标识到达后执行远程取消。': 'Stop requested; remote cancellation will be sent when the new turn ID '
                               'arrives.',
 '任务仍在运行；先停止或等当前连接结束，再恢复 / 下载 / 清理。': 'A task is still running. Stop it or wait for the current connection '
                                      'to finish before recovering, downloading or deleting.',
 '当前浏览器没有可管理的 Agent session。未知创建结果时不要重发；请查看私有恢复记录。': 'This browser has no manageable Agent session. If '
                                                     'creation is uncertain, do not resend; check the '
                                                     'private recovery journal.',
 '请确认已保存所需产物，再清理当前 session。': 'Confirm that you saved the artifacts you need before deleting this session.',
 '旧操作结果已忽略，当前任务继续。': 'Ignored an outdated operation result; the current task continues.',
 '操作失败': 'Operation failed',
 '当前 session 已清理；可开始新任务。': 'Current session deleted. You can start a new task.',
 '产物路径无效。': 'Invalid artifact path.',
 '无': 'None',
 '子进程未返回确认，请恢复状态。': 'Worker did not confirm the outcome; recover its status.',
 'Agent 在 OpenAI 托管沙箱运行多步任务，不访问本机文件。沙箱网络关闭、子 Agent 关闭；不暴露其他插件工具。每次发送会计费。继续任务沿用当前 session 的模型与工具授权。': 'Agent '
                                                                                                     'runs '
                                                                                                     'multi-step '
                                                                                                     'tasks '
                                                                                                     'in an '
                                                                                                     'OpenAI '
                                                                                                     'hosted '
                                                                                                     'sandbox, '
                                                                                                     'without '
                                                                                                     'local '
                                                                                                     'file '
                                                                                                     'access. '
                                                                                                     'Sandbox '
                                                                                                     'networking '
                                                                                                     'and '
                                                                                                     'sub-agents '
                                                                                                     'are '
                                                                                                     'disabled; '
                                                                                                     'other '
                                                                                                     'plugin '
                                                                                                     'tools '
                                                                                                     'are '
                                                                                                     'not '
                                                                                                     'exposed. '
                                                                                                     'Each '
                                                                                                     'send '
                                                                                                     'is '
                                                                                                     'billed. '
                                                                                                     'Follow-up '
                                                                                                     'tasks '
                                                                                                     'retain '
                                                                                                     'this '
                                                                                                     'session’s '
                                                                                                     'model '
                                                                                                     'and '
                                                                                                     'tool '
                                                                                                     'permissions.',
 'Agent 对话': 'Agent conversation',
 '任务 / 继续对话': 'Task / follow-up',
 '生成一个可运行的 Python CSV 分析脚本，用合成数据验证，并保存报告。': 'Create a runnable Python CSV analysis script, validate it with '
                                            'synthetic data, and save a report.',
 '官方 Agent 模型 ID': 'Official Agent model ID',
 '允许 text_statistics 工具：仅统计你提供的文本，不读文件或联网': 'Allow text_statistics: counts supplied text only, without file '
                                            'or network access',
 '我同意本次内容发往 OpenAI 官方 API，并授权托管沙箱执行代码和写文件；会产生费用': 'I agree to send this content to the official OpenAI API '
                                                  'and authorize the hosted sandbox to execute code and '
                                                  'write files; charges apply',
 '发送任务 / 继续': 'Send task / follow-up',
 '停止远程任务': 'Stop remote task',
 '进度与 session': 'Progress and session',
 '下载产物': 'Download artifacts',
 '恢复 / 对账状态（不重发）': 'Recover / reconcile status (no resend)',
 '取回产物': 'Retrieve artifacts',
 '我已保存所需产物，确认清理当前 session': 'I have saved the artifacts I need and confirm deleting this session',
 '清理 session 并开始新任务': 'Delete session and start a new task',
 '浏览器断开不会停止远程任务。未知结局时先恢复状态，不重复发送。关闭页面前请停止并对账；确认保存产物后再清理。': 'Disconnecting the browser does not stop the '
                                                           'remote task. Recover uncertain outcomes before '
                                                           'sending again. Stop and reconcile before closing '
                                                           'the page; save artifacts before deleting the '
                                                           'session.',
 '状态：{outcome}\n进度：{progress}\nsession：{session}\nturn：{turn}': 'Status: {outcome}\nProgress: '
                                                                   '{progress}\nsession: {session}\nturn: '
                                                                   '{turn}',
 '下载 {count} 个产物；每文件最多 10 MiB，总计最多 50 MiB。': 'Downloaded {count} artifacts; 10 MiB per file, 50 MiB total '
                                             'maximum.',
 '已对账；产物：': 'Reconciled; artifacts: '}

def tr(text):
    language = getattr(i18n, "language", "zh_CN") or "zh_CN"
    return text if language.startswith("zh") else _TRANSLATIONS.get(text, text)


ROOT = Path(shared.chuanhu_path).resolve()
JOURNAL_DIR = ROOT / 'plugin_data' / 'agents'
MAX_OUTPUT = 100000


def worker_messages(command):
    executable = os.environ.get('CHUANHU_AGENT_PYTHON') or str(ROOT / '.agents-runtime' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
    if not Path(executable).is_file():
        yield {'type': 'error', 'message': tr('尚未安装隔离 Agents 环境，请查看 docs/agents.md。普通聊天不受影响。')}
        return
    environment = dict(os.environ)
    for name in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_API_BASE', 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID', 'OPENAI_LOG'):
        environment.pop(name, None)
    process = subprocess.Popen([executable, '-u', str(ROOT / 'optional/agents/worker.py')],
                               cwd=ROOT, env=environment, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding='utf-8')
    messages = queue.Queue()
    def reader():
        try:
            for line in process.stdout:
                if len(line) <= 1000000:
                    messages.put(line)
        finally:
            messages.put(None)
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        process.stdin.write(json.dumps(command, ensure_ascii=False) + '\n')
        process.stdin.close()
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            try:
                line = messages.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                message = json.loads(line)
            except ValueError:
                yield {'type': 'error', 'message': tr('Agents 子进程返回了无效响应。未重发任务。')}
                break
            yield message
        else:
            yield {'type': 'error', 'message': tr('本地等待超时；关闭连接不会停止远程 Agent，请点击停止并恢复状态。')}
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        process.stdout.close()
        thread.join(timeout=1)


def owner_id(request):
    if not request or not request.session_hash:
        raise gr.Error(tr('需要有效的浏览器会话。'))
    return hashlib.sha256(((request.username or '') + ':' + request.session_hash).encode()).hexdigest()


def own_state(state, request):
    state = dict(state or {})
    owner = owner_id(request)
    if state.get('owner') and state['owner'] != owner:
        raise gr.Error(tr('Agent 会话不属于当前浏览器。'))
    state['owner'] = owner
    state.setdefault('journal_id', uuid.uuid4().hex)
    return state


def persist(state):
    if not state.get('session_id') and state.get('outcome') != 'uncertain':
        return
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    # Store IDs/status only, never credentials, prompts or answers. The journal
    # enables operator recovery after a browser closes without resubmitting.
    target = JOURNAL_DIR / (state['journal_id'] + '.json')
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({k: state.get(k) for k in ('owner', 'session_id', 'turn_id', 'outcome', 'model', 'allow_text_tool', 'generation')}, indent=2), encoding='utf-8')
    temporary.replace(target)


def describe(state, progress=''):
    return tr('状态：{outcome}\n进度：{progress}\nsession：{session}\nturn：{turn}').format(outcome=state.get('outcome', tr('未开始')), progress=progress, session=state.get('session_id') or '-', turn=state.get('turn_id') or '-')


_slots = {}
_slots_lock = threading.RLock()


class OwnerSlot:
    def __init__(self):
        self.lock = threading.RLock()
        self.state = {}
        self.history = []
        self.files = []
        self.running = False
        self.cancel_requested = False
        self.cancel_sent = False


def owner_slot(request):
    owner = owner_id(request)
    with _slots_lock:
        return _slots.setdefault(owner, OwnerSlot())


def snapshot(slot, detail=''):
    return dict(slot.state), [list(row) for row in slot.history], describe(slot.state, detail), list(slot.files)


def submit_task(prompt, model, allow_text_tool, consent, state, history, request: gr.Request):
    provided = own_state(state, request)
    slot = owner_slot(request)
    if not consent:
        raise gr.Error(tr('请先确认发送至官方 API 并允许托管沙箱运行代码；调用会产生费用。'))
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        raise gr.Error(tr('任务内容须为 1–20000 字符。'))
    # Reserve before the first generator yield. A second click receives the
    # canonical owner state even if Gradio has not published the first output.
    with slot.lock:
        state = dict(slot.state or provided)
        if slot.running or state.get('outcome') in ('starting', 'incomplete', 'in_progress', 'cancel_requested', 'uncertain'):
            raise gr.Error(tr('已有未确认结束的任务。先停止或恢复状态，避免重复发送。'))
        if state.get('session_id'):
            model = state['model']
            allow_text_tool = state.get('allow_text_tool', False)
        else:
            state.update(model=model, allow_text_tool=bool(allow_text_tool))
        previous_state = dict(state)
        previous_history = [list(row) for row in (slot.history or history or [])]
        previous_files = list(slot.files)
        previous_turn_id = state.get('turn_id')
        previous_outcome = state.get('outcome', 'not_started')
        generation = uuid.uuid4().hex
        state.update(outcome='starting', downloaded=False, turn_id=None, generation=generation)
        slot.state = state
        slot.history = [list(row) for row in (slot.history or history or [])] + [[prompt, '']]
        slot.files = []
        slot.running = True
        slot.cancel_requested = slot.cancel_sent = False
        initial = snapshot(slot, tr('启动独立运行器'))
    command = {'action': 'run', 'prompt': prompt, 'model': model, 'allow_text_tool': bool(allow_text_tool), 'session_id': state.get('session_id'), 'run_id': generation}
    terminal = False
    worker_started = False
    try:
        yield initial
        with slot.lock:
            if slot.cancel_requested:
                slot.state['outcome'] = previous_outcome if state.get('session_id') else 'not_started'
                slot.state['turn_id'] = previous_turn_id
                terminal = True
        if terminal:
            with slot.lock:
                stopped = snapshot(slot, tr('发送前已停止，没有提交新的任务。'))
            yield stopped
            return
        worker_started = True
        for message in worker_messages(command):
            with slot.lock:
                if slot.state.get('generation') != generation:
                    return
                for key in ('session_id', 'turn_id', 'outcome'):
                    if message.get(key) is not None:
                        slot.state[key] = message[key]
                if isinstance(message.get('text'), str):
                    slot.history[-1][1] = message['text'][:MAX_OUTPUT]
                error = message.get('type') == 'error'
                if error:
                    slot.state['outcome'] = message.get('outcome') or ('incomplete' if slot.state.get('session_id') else 'not_started')
                    if not slot.state.get('session_id') and slot.state['outcome'] == 'incomplete':
                        slot.state['outcome'] = 'uncertain'
                    terminal = True
                if message.get('type') == 'result':
                    terminal = True
                needs_cancel = (slot.cancel_requested and not slot.cancel_sent and slot.state.get('session_id')
                                and slot.state.get('turn_id') and not terminal)
                if needs_cancel:
                    slot.cancel_sent = True
                cancellation_id = slot.state.get('session_id')
                if slot.cancel_requested and not terminal:
                    slot.state['outcome'] = 'cancel_requested'
                persist(slot.state)
                update = snapshot(slot, message.get('message') or message.get('progress', tr('完成')))
            if needs_cancel:
                # A stop clicked before IDs arrived is applied once the new
                # turn is known, never to a previous completed turn.
                for confirmation in worker_messages({'action': 'cancel', 'session_id': cancellation_id}):
                    if confirmation.get('type') == 'error':
                        with slot.lock:
                            slot.cancel_sent = False
                            update = snapshot(slot, confirmation.get('message', tr('停止请求失败')))
            yield update
            if error:
                return
    finally:
        with slot.lock:
            if slot.state.get('generation') == generation:
                if not worker_started:
                    slot.state = previous_state
                    slot.state['outcome'] = previous_outcome
                    slot.history = previous_history
                    slot.files = previous_files
                elif not terminal:
                    slot.state['outcome'] = 'incomplete' if slot.state.get('session_id') else 'uncertain'
                slot.running = False
                persist(slot.state)
    if not terminal:
        with slot.lock:
            update = snapshot(slot, tr('子进程提前结束。未重发；请恢复状态。'))
        yield update


def manage(action, state, history, confirm_delete, request: gr.Request):
    provided = own_state(state, request)
    slot = owner_slot(request)
    with slot.lock:
        if not slot.state:
            slot.state = provided
            slot.history = [list(row) for row in (history or [])]
        current = dict(slot.state)
        generation = current.get('generation')
        if action == 'cancel' and slot.running and current.get('outcome') in ('completed', 'failed', 'cancelled'):
            return snapshot(slot, tr('目标 turn 已结束。'))
        if action == 'cancel' and slot.running:
            slot.cancel_requested = True
            slot.state['outcome'] = 'cancel_requested'
            if not current.get('turn_id') or not current.get('session_id'):
                return snapshot(slot, tr('已请求停止；新 turn 的标识到达后执行远程取消。'))
            slot.cancel_sent = True
        elif slot.running:
            return snapshot(slot, tr('任务仍在运行；先停止或等当前连接结束，再恢复 / 下载 / 清理。'))
        unknown_recovery = action == 'inspect' and not current.get('session_id') and current.get('outcome') == 'uncertain'
        if not current.get('session_id') and not unknown_recovery:
            raise gr.Error(tr('当前浏览器没有可管理的 Agent session。未知创建结果时不要重发；请查看私有恢复记录。'))
        if action == 'delete' and not confirm_delete:
            raise gr.Error(tr('请确认已保存所需产物，再清理当前 session。'))
    command = {'action': 'recover_unknown' if unknown_recovery else action, 'session_id': current.get('session_id'), 'turn_id': current.get('turn_id'), 'run_id': current.get('generation')}
    for message in worker_messages(command):
        with slot.lock:
            # A late inspect/cancel/download response must never mutate the
            # state or answer of a later generation.
            if slot.state.get('generation') != generation:
                return snapshot(slot, tr('旧操作结果已忽略，当前任务继续。'))
            if message.get('type') == 'error':
                if action == 'cancel':
                    slot.cancel_sent = False
                return snapshot(slot, message.get('message', tr('操作失败')))
            if message.get('type') != 'result':
                continue
            if action == 'delete':
                journal = JOURNAL_DIR / (slot.state['journal_id'] + '.json')
                journal.unlink(missing_ok=True)
                slot.state = {'owner': slot.state['owner'], 'outcome': 'deleted', 'journal_id': uuid.uuid4().hex}
                slot.history = []
                slot.files = []
                return snapshot(slot, tr('当前 session 已清理；可开始新任务。'))
            if action == 'download':
                files = message.get('files', [])
                import tempfile
                temporary_root = Path(tempfile.gettempdir()).resolve()
                if any(temporary_root not in Path(path).resolve().parents for path in files):
                    raise gr.Error(tr('产物路径无效。'))
                slot.state['downloaded'] = True
                slot.files = files
                return snapshot(slot, tr('下载 {count} 个产物；每文件最多 10 MiB，总计最多 50 MiB。').format(count=len(files)))
            for key in ('session_id', 'turn_id'):
                if message.get(key):
                    slot.state[key] = message[key]
            if message.get('outcome') and not (action == 'cancel' and slot.state.get('outcome') in ('completed', 'failed', 'cancelled')):
                slot.state['outcome'] = message['outcome']
            if action == 'inspect' and slot.history and message.get('text'):
                slot.history[-1][1] = message['text'][:MAX_OUTPUT]
            persist(slot.state)
            artifact_names = [Path(item.get('path', '')).name for item in message.get('artifacts', [])]
            detail = message.get('text') if action == 'cancel' else tr('已对账；产物：') + (', '.join(artifact_names) or tr('无'))
            return snapshot(slot, detail)
    with slot.lock:
        return snapshot(slot, tr('子进程未返回确认，请恢复状态。'))


def cancel(state, history, request: gr.Request):
    return manage('cancel', state, history, False, request)


def recover(state, history, request: gr.Request):
    return manage('inspect', state, history, False, request)


def download(state, history, request: gr.Request):
    return manage('download', state, history, False, request)


def cleanup(state, history, confirm, request: gr.Request):
    return manage('delete', state, history, confirm, request)


@on_toolbox_tab
def render_controls():
    gr.Markdown(tr('Agent 在 OpenAI 托管沙箱运行多步任务，不访问本机文件。沙箱网络关闭、子 Agent 关闭；不暴露其他插件工具。每次发送会计费。继续任务沿用当前 session 的模型与工具授权。'))
    state = gr.State({})
    history = gr.Chatbot(label=tr('Agent 对话'), sanitize_html=True)
    prompt = gr.Textbox(label=tr('任务 / 继续对话'), lines=4, placeholder=tr('生成一个可运行的 Python CSV 分析脚本，用合成数据验证，并保存报告。'))
    model = gr.Textbox(label=tr('官方 Agent 模型 ID'), value='gpt-6-astra')
    allow_tool = gr.Checkbox(label=tr('允许 text_statistics 工具：仅统计你提供的文本，不读文件或联网'), value=False)
    consent = gr.Checkbox(label=tr('我同意本次内容发往 OpenAI 官方 API，并授权托管沙箱执行代码和写文件；会产生费用'), value=False)
    with gr.Row():
        start = gr.Button(tr('发送任务 / 继续'), variant='primary')
        stop = gr.Button(tr('停止远程任务'))
    status = gr.Textbox(label=tr('进度与 session'), interactive=False, lines=4)
    files = gr.File(label=tr('下载产物'), file_count='multiple')
    with gr.Row():
        inspect = gr.Button(tr('恢复 / 对账状态（不重发）'))
        save = gr.Button(tr('取回产物'))
    confirm = gr.Checkbox(label=tr('我已保存所需产物，确认清理当前 session'), value=False)
    delete = gr.Button(tr('清理 session 并开始新任务'))
    outputs = [state, history, status, files]
    start.click(guarded_callback(submit_task), inputs=[prompt, model, allow_tool, consent, state, history], outputs=outputs, concurrency_limit=4, api_name='agent_submit')
    # This is a real cancellation event, not a Gradio stream-only cancellation.
    stop.click(guarded_callback(cancel), inputs=[state, history], outputs=outputs, concurrency_limit=None, queue=False, api_name='agent_cancel')
    inspect.click(guarded_callback(recover), inputs=[state, history], outputs=outputs, api_name='agent_recover')
    save.click(guarded_callback(download), inputs=[state, history], outputs=outputs, api_name='agent_download')
    delete.click(guarded_callback(cleanup), inputs=[state, history, confirm], outputs=outputs, api_name='agent_cleanup')
    gr.Markdown(tr('浏览器断开不会停止远程任务。未知结局时先恢复状态，不重复发送。关闭页面前请停止并对账；确认保存产物后再清理。'))
