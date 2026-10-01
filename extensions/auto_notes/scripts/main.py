"""Explicit, per-model session opt-in; private data stays outside served assets."""
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4
import re
import gradio as gr
from modules import shared
from modules.plugin_callbacks import on_after_chat, on_settings_tab, on_toolbox_tab, on_app_ready, guarded_callback

from modules.presets import i18n

_TRANSLATIONS = {'川虎 Chat 自动笔记': 'Chuanhu Chat notes',
 '仅为当前模型会话记录后续问答。默认不记录；切换模型需重新开启。笔记存放在服务器私有 plugin_data 目录。': 'Record subsequent turns for the current model '
                                                              'session only. Recording is off by default; '
                                                              'enable it again after switching models. Notes '
                                                              'are stored in the private server plugin_data '
                                                              'directory.',
 '记录后续问答': 'Record subsequent turns',
 '本次笔记标题': 'Note title',
 '标签': 'Tags',
 '保存文件名': 'Output filename',
 '保存完整回答': 'Save full answers',
 '\n\n（已截断）': '\n\n(truncated)',
 '标签：': 'Tags: ',
 '用户': 'User',
 '助手': 'Assistant'}

def tr(text):
    language = getattr(i18n, "language", "zh_CN") or "zh_CN"
    return text if language.startswith("zh") else _TRANSLATIONS.get(text, text)


DATA_DIR = Path(shared.chuanhu_path) / 'plugin_data' / 'auto_notes'
DEFAULTS = {'enabled': False, 'title': tr('川虎 Chat 自动笔记'), 'tags': '', 'filename': 'notes.md', 'include_full_answer': True}
_write_lock = Lock()


def preferences(model):
    if not hasattr(model, '_auto_notes_preferences'):
        model._auto_notes_preferences = dict(DEFAULTS, directory=uuid4().hex)
    return model._auto_notes_preferences


def set_controls(model, enabled, title, tags):
    preferences(model).update(enabled=bool(enabled), title=(title or DEFAULTS['title'])[:200], tags=(tags or '')[:500])
    return model


def set_settings(model, filename, full):
    name = re.sub(r'[^A-Za-z0-9_.-]', '_', filename or 'notes.md').lstrip('.') or 'notes.md'
    if not name.endswith('.md'):
        name += '.md'
    preferences(model).update(filename=name[:120], include_full_answer=bool(full))
    return model


@on_toolbox_tab
def render_controls():
    gr.Markdown(tr('仅为当前模型会话记录后续问答。默认不记录；切换模型需重新开启。笔记存放在服务器私有 plugin_data 目录。'))
    enabled = gr.Checkbox(label=tr('记录后续问答'), value=False)
    title = gr.Textbox(label=tr('本次笔记标题'), value=DEFAULTS['title'])
    tags = gr.Textbox(label=tr('标签'), value='')

    @on_app_ready
    def bind(context):
        for component in (enabled, title, tags):
            component.change(guarded_callback(set_controls), inputs=[context.current_model, enabled, title, tags], outputs=context.current_model)


@on_settings_tab
def render_settings():
    filename = gr.Textbox(label=tr('保存文件名'), value='notes.md')
    full = gr.Checkbox(label=tr('保存完整回答'), value=True)

    @on_app_ready
    def bind(context):
        for component in (filename, full):
            component.change(guarded_callback(set_settings), inputs=[context.current_model, filename, full], outputs=context.current_model)


@on_after_chat
def append_note(context):
    options = preferences(context.model)
    if not options['enabled'] or not isinstance(context.assistant_reply, str) or not context.assistant_reply.strip():
        return
    question = context.fake_input or (context.user_input if isinstance(context.user_input, str) else '')
    answer = context.assistant_reply.strip()
    if not options['include_full_answer'] and len(answer) > 1200:
        answer = answer[:1200] + tr('\n\n（已截断）')
    directory = DATA_DIR / options['directory']
    entry = (f"\n\n## {options['title']} - {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
             f"{tr('标签：')}{options['tags']}\n\n### {tr('用户')}\n\n{question}\n\n### {tr('助手')}\n\n{answer}\n")
    with _write_lock:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / options['filename']
        with path.open('a', encoding='utf-8') as output:
            output.write(entry)
    context.metadata['auto_notes'] = {'path': str(path)}
