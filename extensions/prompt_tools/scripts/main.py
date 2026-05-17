from __future__ import annotations

import html
import locale
import os
from pathlib import Path

import commentjson as json
import gradio as gr

from modules.plugin_callbacks import on_toolbox_tab


TRANSLATIONS = {
    "en_US": {
        "输出语言": "Output language",
        "中文": "Chinese",
        "润色": "Polish",
        "翻译": "Translate",
        "总结": "Summarize",
        "解释代码": "Explain code",
        "提取待办": "Extract todos",
        "写邮件": "Draft email",
        "评审改进": "Review and improve",
        "会议纪要": "Meeting notes",
        "点击按钮会把对应提示词插入到当前输入框。若输入框已有内容，会自动把提示词放到内容前面。": "Click a button to insert that prompt into the current input box. If the input box already has content, the prompt is prepended automatically.",
        "请润色以下内容，使其清晰、自然、专业。输出语言：{language}。": "Polish the following content so it is clear, natural, and professional. Output language: {language}.",
        "请把以下内容翻译为{language}，要求自然、准确，保留专有名词和原有格式。": "Translate the following content into {language}. Make it natural and accurate, and preserve proper nouns and the original format.",
        "请总结以下内容。输出语言：{language}。先给 3-5 条要点，再列出重要细节和后续行动。": "Summarize the following content. Output language: {language}. Start with 3-5 bullet points, then list important details and next actions.",
        "请解释以下代码或技术内容。输出语言：{language}。说明它做了什么、关键逻辑、潜在问题和改进建议。": "Explain the following code or technical content. Output language: {language}. Cover what it does, key logic, potential issues, and improvements.",
        "请从以下内容中提取待办事项。输出语言：{language}。按负责人、事项、截止时间、依赖或风险整理；未知项标为“未指定”。": "Extract todos from the following content. Output language: {language}. Organize by owner, task, due date, dependencies or risks; mark unknown fields as \"unspecified\".",
        "请根据以下内容起草一封邮件。输出语言：{language}。包含主题、称呼、正文和结尾，语气清晰得体。": "Draft an email from the following content. Output language: {language}. Include subject, salutation, body, and closing with a clear and appropriate tone.",
        "请评审以下内容。输出语言：{language}。指出问题、风险、遗漏点，并给出可执行的修改建议。": "Review the following content. Output language: {language}. Point out issues, risks, omissions, and actionable improvements.",
        "请把以下内容整理成会议纪要。输出语言：{language}。包含背景、结论、决策、待办事项和风险。": "Turn the following content into meeting notes. Output language: {language}. Include background, conclusions, decisions, action items, and risks.",
    }
}

PROMPTS = [
    ("润色", "请润色以下内容，使其清晰、自然、专业。输出语言：{language}。"),
    ("翻译", "请把以下内容翻译为{language}，要求自然、准确，保留专有名词和原有格式。"),
    ("总结", "请总结以下内容。输出语言：{language}。先给 3-5 条要点，再列出重要细节和后续行动。"),
    ("解释代码", "请解释以下代码或技术内容。输出语言：{language}。说明它做了什么、关键逻辑、潜在问题和改进建议。"),
    ("提取待办", "请从以下内容中提取待办事项。输出语言：{language}。按负责人、事项、截止时间、依赖或风险整理；未知项标为“未指定”。"),
    ("写邮件", "请根据以下内容起草一封邮件。输出语言：{language}。包含主题、称呼、正文和结尾，语气清晰得体。"),
    ("评审改进", "请评审以下内容。输出语言：{language}。指出问题、风险、遗漏点，并给出可执行的修改建议。"),
    ("会议纪要", "请把以下内容整理成会议纪要。输出语言：{language}。包含背景、结论、决策、待办事项和风险。"),
]


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


def _button(label: str, template: str):
    return (
        '<button type="button" class="prompt-tools-button" '
        f'data-prompt-tools-template="{html.escape(tr(template), quote=True)}">'
        f"{html.escape(tr(label))}</button>"
    )


def _render_panel():
    buttons = "\n".join(_button(label, template) for label, template in PROMPTS)
    return f"""
    <div class="prompt-tools-panel">
      <label class="prompt-tools-language">
        <span>{html.escape(tr("输出语言"))}</span>
        <select data-prompt-tools-language>
          <option value="中文">{html.escape(tr("中文"))}</option>
          <option value="English">English</option>
          <option value="日本語">日本語</option>
          <option value="한국어">한국어</option>
          <option value="Français">Français</option>
          <option value="Deutsch">Deutsch</option>
          <option value="Español">Español</option>
        </select>
      </label>
      <div class="prompt-tools-grid">{buttons}</div>
      <p class="prompt-tools-hint">{html.escape(tr("点击按钮会把对应提示词插入到当前输入框。若输入框已有内容，会自动把提示词放到内容前面。"))}</p>
    </div>
    """


@on_toolbox_tab
def render_controls():
    gr.HTML(_render_panel())
