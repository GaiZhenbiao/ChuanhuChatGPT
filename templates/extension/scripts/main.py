"""Copy this directory to extensions/my_extension, then enable and restart."""
import gradio as gr
from modules.plugin_callbacks import on_toolbox_tab, on_app_ready, guarded_callback

from modules.presets import i18n

_TRANSLATIONS = {'去除当前输入每行末尾空白；不发送消息。': 'Remove trailing whitespace from the current input without sending it.',
 '整理输入': 'Tidy input'}

def tr(text):
    language = getattr(i18n, "language", "zh_CN") or "zh_CN"
    return text if language.startswith("zh") else _TRANSLATIONS.get(text, text)



def normalize_text(text):
    return '\n'.join(line.rstrip() for line in (text or '').strip().splitlines())


@on_toolbox_tab
def render_controls():
    gr.Markdown(tr('去除当前输入每行末尾空白；不发送消息。'))
    button = gr.Button(tr('整理输入'))

    @on_app_ready
    def bind(context):
        button.click(guarded_callback(normalize_text), inputs=context.user_input, outputs=context.user_input)
