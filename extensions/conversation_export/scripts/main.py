"""Export only the chatbot value supplied by this browser's Gradio event."""
import json
import tempfile
from pathlib import Path
import gradio as gr
from modules.plugin_callbacks import on_toolbox_tab, on_app_ready, guarded_callback

from modules.presets import i18n

_TRANSLATIONS = {'当前会话没有可导出的文本。': 'This conversation has no text to export.',
 '未知导出格式。': 'Unknown export format.',
 '只在点击导出时读取当前会话文本。附件不打包，JSON 不含密钥或模型设置。': 'Reads the current conversation only when you export. Attachments '
                                          'are excluded; JSON contains no keys or model settings.',
 '导出格式': 'Export format',
 '导出当前会话': 'Export current conversation',
 '下载文件': 'Download file'}

def tr(text):
    language = getattr(i18n, "language", "zh_CN") or "zh_CN"
    return text if language.startswith("zh") else _TRANSLATIONS.get(text, text)



def normalize_messages(chatbot):
    messages = []
    for row in chatbot or []:
        if isinstance(row, dict):
            if row.get('role') in ('user', 'assistant', 'system') and isinstance(row.get('content'), str):
                messages.append({'role': row['role'], 'content': row['content']})
        elif isinstance(row, (list, tuple)) and len(row) == 2:
            for role, content in zip(('user', 'assistant'), row):
                if isinstance(content, str):
                    messages.append({'role': role, 'content': content})
    return messages


def export_conversation(chatbot, format_name):
    messages = normalize_messages(chatbot)
    if not messages:
        raise gr.Error(tr('当前会话没有可导出的文本。'))
    if format_name not in ('Markdown', 'JSON'):
        raise gr.Error(tr('未知导出格式。'))
    directory = Path(tempfile.mkdtemp(prefix='chuanhu-export-'))
    if format_name == 'JSON':
        path = directory / 'conversation.json'
        path.write_text(json.dumps({'schema_version': 1, 'messages': messages}, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        path = directory / 'conversation.md'
        path.write_text('# Conversation\n\n' + '\n\n'.join('## ' + m['role'] + '\n\n' + m['content'] for m in messages), encoding='utf-8')
    return str(path)


@on_toolbox_tab
def render_controls():
    gr.Markdown(tr('只在点击导出时读取当前会话文本。附件不打包，JSON 不含密钥或模型设置。'))
    format_name = gr.Radio(['Markdown', 'JSON'], value='Markdown', label=tr('导出格式'))
    button = gr.Button(tr('导出当前会话'))
    output = gr.File(label=tr('下载文件'))

    @on_app_ready
    def bind(context):
        button.click(guarded_callback(export_conversation), inputs=[context.chatbot, format_name], outputs=output)
