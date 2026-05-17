from __future__ import annotations

from datetime import datetime
import locale
import os
from pathlib import Path
import re

import commentjson as json
import gradio as gr

from modules.plugin_callbacks import on_after_chat, on_settings_tab, on_toolbox_tab
from modules.plugin_context import ChatContext


PLUGIN_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PLUGIN_DIR / "data"

TRANSLATIONS = {
    "en_US": {
        "川虎 Chat 自动笔记": "Chuanhu Chat auto notes",
        "记录后续问答": "Record future Q&A",
        "本次笔记标题": "Note title",
        "标签": "Tags",
        "例如：会议, 需求, 调试": "For example: meeting, requirements, debugging",
        "保存文件名": "Save filename",
        "保存完整回答": "Save full answers",
        "笔记会保存到": "Notes will be saved to",
        "（已截断，可在设置中启用完整回答）": "(truncated; enable full answers in settings)",
        "（未捕获到用户输入）": "(user input was not captured)",
        "标签：": "Tags: ",
        "用户": "User",
        "助手": "Assistant",
    }
}


def _language():
    language = "auto"
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                language = json.load(f).get("language", language)
        except Exception:
            pass
    language = os.environ.get("LANGUAGE", language).replace("-", "_")
    if language == "auto":
        language = locale.getdefaultlocale()[0] or "zh_CN"
    return language


LANGUAGE = _language()


def tr(text: str):
    if LANGUAGE.startswith("zh"):
        return text
    translations = TRANSLATIONS.get(LANGUAGE) or TRANSLATIONS.get(LANGUAGE.split("_", 1)[0]) or TRANSLATIONS["en_US"]
    return translations.get(text, text)

STATE = {
    "enabled": False,
    "title": tr("川虎 Chat 自动笔记"),
    "tags": "",
    "filename": "notes.md",
    "include_full_answer": True,
}


def _set_enabled(value: bool):
    STATE["enabled"] = bool(value)


def _set_title(value: str):
    STATE["title"] = value or tr("川虎 Chat 自动笔记")


def _set_tags(value: str):
    STATE["tags"] = value or ""


def _set_filename(value: str):
    value = value or "notes.md"
    value = re.sub(r"[^A-Za-z0-9_.-]", "_", value)
    if not value.endswith(".md"):
        value += ".md"
    STATE["filename"] = value


def _set_include_full_answer(value: bool):
    STATE["include_full_answer"] = bool(value)


@on_toolbox_tab
def render_controls():
    with gr.Group(elem_classes="auto-notes"):
        enabled = gr.Checkbox(label=tr("记录后续问答"), value=STATE["enabled"])
        title = gr.Textbox(label=tr("本次笔记标题"), value=STATE["title"], lines=1)
        tags = gr.Textbox(label=tr("标签"), value=STATE["tags"], lines=1, placeholder=tr("例如：会议, 需求, 调试"))

    enabled.change(_set_enabled, inputs=enabled)
    title.change(_set_title, inputs=title)
    tags.change(_set_tags, inputs=tags)


@on_settings_tab
def render_settings():
    filename = gr.Textbox(
        label=tr("保存文件名"),
        value=STATE["filename"],
        lines=1,
        elem_classes="no-container",
    )
    include_full_answer = gr.Checkbox(
        label=tr("保存完整回答"),
        value=STATE["include_full_answer"],
        elem_classes="switch-checkbox",
    )
    gr.Markdown(tr("笔记会保存到") + f" `{DATA_DIR}`。", elem_classes="auto-notes-muted")

    filename.change(_set_filename, inputs=filename)
    include_full_answer.change(_set_include_full_answer, inputs=include_full_answer)


def _extract_user_text(context: ChatContext) -> str:
    if context.fake_input:
        return context.fake_input
    if isinstance(context.user_input, str):
        return context.user_input
    if isinstance(context.user_input, list) and context.user_input:
        first = context.user_input[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return first["text"]
    return ""


def _clip_answer(answer: str) -> str:
    if STATE["include_full_answer"]:
        return answer
    limit = 1200
    if len(answer) <= limit:
        return answer
    return answer[:limit].rstrip() + "\n\n..." + tr("（已截断，可在设置中启用完整回答）")


def _note_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / STATE["filename"]


@on_after_chat
def append_note(context: ChatContext):
    if not STATE["enabled"]:
        return
    if not isinstance(context.assistant_reply, str) or not context.assistant_reply.strip():
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_text = _extract_user_text(context).strip() or tr("（未捕获到用户输入）")
    answer = _clip_answer(context.assistant_reply.strip())
    tags = STATE["tags"].strip()
    tags_line = f"\n{tr('标签：')}{tags}" if tags else ""

    entry = (
        f"\n\n## {STATE['title']} - {now}\n"
        f"{tags_line}\n\n"
        f"### {tr('用户')}\n\n{user_text}\n\n"
        f"### {tr('助手')}\n\n{answer}\n"
    )
    path = _note_path()
    if not path.exists():
        path.write_text(f"# {STATE['title']}\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(entry)

    context.metadata["auto_notes"] = {"path": str(path)}
