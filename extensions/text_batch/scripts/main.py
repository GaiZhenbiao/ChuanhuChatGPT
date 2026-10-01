"""Offline batch example: no module-level task state or network calls."""
import json
import re
import tempfile
from pathlib import Path
import gradio as gr
from modules.plugin_callbacks import on_toolbox_tab, guarded_callback

from modules.presets import i18n

_TRANSLATIONS = {'只支持 .txt 和 .md': 'Only .txt and .md are supported',
 '文件超过 2 MiB': 'File exceeds 2 MiB',
 '请选择 1–30 个文本文件。': 'Select 1–30 text files.',
 '无法读取 UTF-8 文本、类型不支持或超过大小限制': 'Cannot read UTF-8 text, unsupported type or size limit exceeded',
 '离线提取行数、Markdown 标题和未完成待办。每文件最大 2 MiB，最多 30 个，不上传至模型。': 'Extract line counts, Markdown headings and '
                                                         'unchecked tasks offline. Up to 30 files, 2 MiB '
                                                         'each. Files are not sent to a model.',
 '文本文件': 'Text files',
 '开始整理': 'Analyze files',
 '取消': 'Cancel',
 '进度': 'Progress',
 '部分或完整结果': 'Partial or complete results',
 '已处理 {index}/{total}；取消会保留已生成的部分结果。': 'Processed {index}/{total}; cancelling preserves partial results.'}

def tr(text):
    language = getattr(i18n, "language", "zh_CN") or "zh_CN"
    return text if language.startswith("zh") else _TRANSLATIONS.get(text, text)


MAX_FILES = 30
MAX_BYTES = 2 * 1024 * 1024


def inspect_text(path):
    path = Path(path)
    if path.suffix.lower() not in ('.txt', '.md'):
        raise ValueError(tr('只支持 .txt 和 .md'))
    with path.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(tr('文件超过 2 MiB'))
    text = raw.decode('utf-8-sig')
    return {'filename': path.name, 'characters': len(text), 'lines': len(text.splitlines()),
            'headings': re.findall(r'^#{1,6}\s+(.+)$', text, re.M),
            'tasks': re.findall(r'^\s*[-*]\s+\[ \]\s+(.+)$', text, re.M)}


def analyze_files(files):
    if not files or len(files) > MAX_FILES:
        raise gr.Error(tr('请选择 1–30 个文本文件。'))
    results = []
    directory = Path(tempfile.mkdtemp(prefix='chuanhu-batch-'))
    output = directory / 'text-report.json'
    for index, filename in enumerate(files, 1):
        try:
            result = inspect_text(filename)
        except (OSError, ValueError, UnicodeError):
            result = {'filename': Path(filename).name, 'error': tr('无法读取 UTF-8 文本、类型不支持或超过大小限制')}
        results.append(result)
        output.write_text(json.dumps({'results': results, 'processed': index, 'total': len(files)}, ensure_ascii=False, indent=2), encoding='utf-8')
        # A snapshot per file remains downloadable if later files fail or the
        # generator is cancelled. All state belongs to this invocation.
        snapshot = directory / ('text-report-' + str(index) + '.json')
        snapshot.write_bytes(output.read_bytes())
        yield tr('已处理 {index}/{total}；取消会保留已生成的部分结果。').format(index=index, total=len(files)), str(snapshot)


@on_toolbox_tab
def render_controls():
    gr.Markdown(tr('离线提取行数、Markdown 标题和未完成待办。每文件最大 2 MiB，最多 30 个，不上传至模型。'))
    files = gr.File(file_count='multiple', file_types=['.txt', '.md'], type='filepath', label=tr('文本文件'))
    with gr.Row():
        start = gr.Button(tr('开始整理'))
        cancel = gr.Button(tr('取消'))
    status = gr.Textbox(label=tr('进度'), interactive=False)
    output = gr.File(label=tr('部分或完整结果'))
    job = start.click(guarded_callback(analyze_files), inputs=files, outputs=[status, output])
    cancel.click(fn=None, cancels=[job])
