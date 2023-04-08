# -*- coding:utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Type
import logging
import json
import os
import datetime
import hashlib
import csv
import requests
import re
import html
import sys
import subprocess

import gradio as gr
from pypinyin import lazy_pinyin
import tiktoken
import mdtex2html
from markdown import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
import pandas as pd

from modules.presets import *
from . import shared
from modules.config import retrieve_proxy

if TYPE_CHECKING:
    from typing import TypedDict

    class DataframeData(TypedDict):
        headers: List[str]
        data: List[List[str | int | bool]]


def count_token(message):
    encoding = tiktoken.get_encoding("cl100k_base")
    input_str = f"role: {message['role']}, content: {message['content']}"
    length = len(encoding.encode(input_str))
    return length


def markdown_to_html_with_syntax_highlight(md_str):
    def replacer(match):
        lang = match.group(1) or "text"
        code = match.group(2)

        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except ValueError:
            lexer = get_lexer_by_name("text", stripall=True)

        formatter = HtmlFormatter()
        highlighted_code = highlight(code, lexer, formatter)

        return f'<pre><code class="{lang}">{highlighted_code}</code></pre>'

    code_block_pattern = r"```(\w+)?\n([\s\S]+?)\n```"
    md_str = re.sub(code_block_pattern, replacer, md_str, flags=re.MULTILINE)

    html_str = markdown(md_str)
    return html_str


def normalize_markdown(md_text: str) -> str:
    lines = md_text.split("\n")
    normalized_lines = []
    inside_list = False

    for i, line in enumerate(lines):
        if re.match(r"^(\d+\.|-|\*|\+)\s", line.strip()):
            if not inside_list and i > 0 and lines[i - 1].strip() != "":
                normalized_lines.append("")
            inside_list = True
            normalized_lines.append(line)
        elif inside_list and line.strip() == "":
            if i < len(lines) - 1 and not re.match(
                r"^(\d+\.|-|\*|\+)\s", lines[i + 1].strip()
            ):
                normalized_lines.append(line)
            continue
        else:
            inside_list = False
            normalized_lines.append(line)

    return "\n".join(normalized_lines)


def convert_mdtext(md_text):
    code_block_pattern = re.compile(r"```(.*?)(?:```|$)", re.DOTALL)
    inline_code_pattern = re.compile(r"`(.*?)`", re.DOTALL)
    code_blocks = code_block_pattern.findall(md_text)
    non_code_parts = code_block_pattern.split(md_text)[::2]

    result = []
    for non_code, code in zip(non_code_parts, code_blocks + [""]):
        if non_code.strip():
            non_code = normalize_markdown(non_code)
            if inline_code_pattern.search(non_code):
                result.append(markdown(non_code, extensions=["tables"]))
            else:
                result.append(mdtex2html.convert(non_code, extensions=["tables"]))
        if code.strip():
            # _, code = detect_language(code)  # 暂时去除代码高亮功能，因为在大段代码的情况下会出现问题
            # code = code.replace("\n\n", "\n") # 暂时去除代码中的空行，因为在大段代码的情况下会出现问题
            code = f"\n```{code}\n\n```"
            code = markdown_to_html_with_syntax_highlight(code)
            result.append(code)
    result = "".join(result)
    result += ALREADY_CONVERTED_MARK
    return result


def convert_asis(userinput):
    return (
        f'<p style="white-space:pre-wrap;">{html.escape(userinput)}</p>'
        + ALREADY_CONVERTED_MARK
    )


def detect_converted_mark(userinput):
    if userinput.endswith(ALREADY_CONVERTED_MARK):
        return True
    else:
        return False


def detect_language(code):
    if code.startswith("\n"):
        first_line = ""
    else:
        first_line = code.strip().split("\n", 1)[0]
    language = first_line.lower() if first_line else ""
    code_without_language = code[len(first_line) :].lstrip() if first_line else code
    return language, code_without_language


def construct_text(role, text):
    return {"role": role, "content": text}


def construct_user(text):
    return construct_text("user", text)


def construct_system(text):
    return construct_text("system", text)


def construct_assistant(text):
    return construct_text("assistant", text)


def save_file(filename, system, history, chatbot, user_name):
    logging.debug(f"{user_name} 保存对话历史中……")
    os.makedirs(os.path.join(HISTORY_DIR, user_name), exist_ok=True)
    if filename.endswith(".json"):
        json_s = {"system": system, "history": history, "chatbot": chatbot}
        print(json_s)
        with open(os.path.join(HISTORY_DIR, user_name, filename), "w") as f:
            json.dump(json_s, f)
    elif filename.endswith(".md"):
        md_s = f"system: \n- {system} \n"
        for data in history:
            md_s += f"\n{data['role']}: \n- {data['content']} \n"
        with open(os.path.join(HISTORY_DIR, user_name, filename), "w", encoding="utf8") as f:
            f.write(md_s)
    logging.debug(f"{user_name} 保存对话历史完毕")
    return os.path.join(HISTORY_DIR, user_name, filename)


def sorted_by_pinyin(list):
    return sorted(list, key=lambda char: lazy_pinyin(char)[0][0])


def get_file_names(dir, plain=False, filetypes=[".json"]):
    logging.debug(f"获取文件名列表，目录为{dir}，文件类型为{filetypes}，是否为纯文本列表{plain}")
    files = []
    try:
        for type in filetypes:
            files += [f for f in os.listdir(dir) if f.endswith(type)]
    except FileNotFoundError:
        files = []
    files = sorted_by_pinyin(files)
    if files == []:
        files = [""]
    logging.debug(f"files are:{files}")
    if plain:
        return files
    else:
        return gr.Dropdown.update(choices=files)


def get_history_names(plain=False, user_name=""):
    logging.debug(f"从用户 {user_name} 中获取历史记录文件名列表")
    return get_file_names(os.path.join(HISTORY_DIR, user_name), plain)


def load_template(filename, mode=0):
    logging.debug(f"加载模板文件{filename}，模式为{mode}（0为返回字典和下拉菜单，1为返回下拉菜单，2为返回字典）")
    lines = []
    if filename.endswith(".json"):
        with open(os.path.join(TEMPLATES_DIR, filename), "r", encoding="utf8") as f:
            lines = json.load(f)
        lines = [[i["act"], i["prompt"]] for i in lines]
    else:
        with open(
            os.path.join(TEMPLATES_DIR, filename), "r", encoding="utf8"
        ) as csvfile:
            reader = csv.reader(csvfile)
            lines = list(reader)
        lines = lines[1:]
    if mode == 1:
        return sorted_by_pinyin([row[0] for row in lines])
    elif mode == 2:
        return {row[0]: row[1] for row in lines}
    else:
        choices = sorted_by_pinyin([row[0] for row in lines])
        return {row[0]: row[1] for row in lines}, gr.Dropdown.update(
            choices=choices
        )


def get_template_names(plain=False):
    logging.debug("获取模板文件名列表")
    return get_file_names(TEMPLATES_DIR, plain, filetypes=[".csv", "json"])


def get_template_content(templates, selection, original_system_prompt):
    logging.debug(f"应用模板中，选择为{selection}，原始系统提示为{original_system_prompt}")
    try:
        return templates[selection]
    except:
        return original_system_prompt


def reset_textbox():
    logging.debug("重置文本框")
    return gr.update(value="")


def reset_default():
    default_host = shared.state.reset_api_host()
    retrieve_proxy("")
    return gr.update(value=default_host), gr.update(value=""), "API-Host 和代理已重置"


def change_api_host(host):
    shared.state.set_api_host(host)
    msg = f"API-Host更改为了{host}"
    logging.info(msg)
    return msg


def change_proxy(proxy):
    retrieve_proxy(proxy)
    os.environ["HTTPS_PROXY"] = proxy
    msg = f"代理更改为了{proxy}"
    logging.info(msg)
    return msg


def hide_middle_chars(s):
    if s is None:
        return ""
    if len(s) <= 8:
        return s
    else:
        head = s[:4]
        tail = s[-4:]
        hidden = "*" * (len(s) - 8)
        return head + hidden + tail


def submit_key(key):
    key = key.strip()
    msg = f"API密钥更改为了{hide_middle_chars(key)}"
    logging.info(msg)
    return key, msg


def replace_today(prompt):
    today = datetime.datetime.today().strftime("%Y-%m-%d")
    return prompt.replace("{current_date}", today)


def get_geoip():
    try:
        with retrieve_proxy():
            response = requests.get("https://ipapi.co/json/", timeout=5)
        data = response.json()
    except:
        data = {"error": True, "reason": "连接ipapi失败"}
    if "error" in data.keys():
        logging.warning(f"无法获取IP地址信息。\n{data}")
        if data["reason"] == "RateLimited":
            return (
                f"获取IP地理位置失败，因为达到了检测IP的速率限制。聊天功能可能仍然可用。"
            )
        else:
            return f"获取IP地理位置失败。原因：{data['reason']}。你仍然可以使用聊天功能。"
    else:
        country = data["country_name"]
        if country == "China":
            text = "**您的IP区域：中国。请立即检查代理设置，在不受支持的地区使用API可能导致账号被封禁。**"
        else:
            text = f"您的IP区域：{country}。"
        logging.info(text)
        return text


def find_n(lst, max_num):
    n = len(lst)
    total = sum(lst)

    if total < max_num:
        return n

    for i in range(len(lst)):
        if total - lst[i] < max_num:
            return n - i - 1
        total = total - lst[i]
    return 1


def start_outputing():
    logging.debug("显示取消按钮，隐藏发送按钮")
    return gr.Button.update(visible=False), gr.Button.update(visible=True)


def end_outputing():
    return (
        gr.Button.update(visible=True),
        gr.Button.update(visible=False),
    )


def cancel_outputing():
    logging.info("中止输出……")
    shared.state.interrupt()


def transfer_input(inputs):
    # 一次性返回，降低延迟
    textbox = reset_textbox()
    outputing = start_outputing()
    return (
        inputs,
        gr.update(value=""),
        gr.Button.update(visible=False),
        gr.Button.update(visible=True),
    )



def run(command, desc=None, errdesc=None, custom_env=None, live=False):
    if desc is not None:
        print(desc)
    if live:
        result = subprocess.run(command, shell=True, env=os.environ if custom_env is None else custom_env)
        if result.returncode != 0:
            raise RuntimeError(f"""{errdesc or 'Error running command'}.
Command: {command}
Error code: {result.returncode}""")

        return ""
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, env=os.environ if custom_env is None else custom_env)
    if result.returncode != 0:
        message = f"""{errdesc or 'Error running command'}.
Command: {command}
Error code: {result.returncode}
stdout: {result.stdout.decode(encoding="utf8", errors="ignore") if len(result.stdout)>0 else '<empty>'}
stderr: {result.stderr.decode(encoding="utf8", errors="ignore") if len(result.stderr)>0 else '<empty>'}
"""
        raise RuntimeError(message)
    return result.stdout.decode(encoding="utf8", errors="ignore")

def versions_html():
    git = os.environ.get('GIT', "git")
    python_version = ".".join([str(x) for x in sys.version_info[0:3]])
    try:
        commit_hash = run(f"{git} rev-parse HEAD").strip()
    except Exception:
        commit_hash = "<none>"
    if commit_hash != "<none>":
        short_commit = commit_hash[0:7]
        commit_info = f"<a style=\"text-decoration:none\" href=\"https://github.com/GaiZhenbiao/ChuanhuChatGPT/commit/{short_commit}\">{short_commit}</a>"
    else:
        commit_info = "unknown \U0001F615"
    return f"""
Python: <span title="{sys.version}">{python_version}</span>
 • 
Gradio: {gr.__version__}
 • 
Commit: {commit_info}
"""

def add_source_numbers(lst, source_name = "Source", use_source = True):
    if use_source:
        return [f'[{idx+1}]\t "{item[0]}"\n{source_name}: {item[1]}' for idx, item in enumerate(lst)]
    else:
        return [f'[{idx+1}]\t "{item}"' for idx, item in enumerate(lst)]

def add_details(lst):
    nodes = []
    for index, txt in enumerate(lst):
        brief = txt[:25].replace("\n", "")
        nodes.append(
            f"<details><summary>{brief}...</summary><p>{txt}</p></details>"
        )
    return nodes


def sheet_to_string(sheet, sheet_name = None):
    result = []
    for index, row in sheet.iterrows():
        row_string = ""
        for column in sheet.columns:
            row_string += f"{column}: {row[column]}, "
        row_string = row_string.rstrip(", ")
        row_string += "."
        result.append(row_string)
    return result

def excel_to_string(file_path):
    # 读取Excel文件中的所有工作表
    excel_file = pd.read_excel(file_path, engine='openpyxl', sheet_name=None)

    # 初始化结果字符串
    result = []

    # 遍历每一个工作表
    for sheet_name, sheet_data in excel_file.items():

        # 处理当前工作表并添加到结果字符串
        result += sheet_to_string(sheet_data, sheet_name=sheet_name)


    return result

def get_last_day_of_month(any_day):
    # The day 28 exists in every month. 4 days later, it's always next month
    next_month = any_day.replace(day=28) + datetime.timedelta(days=4)
    # subtracting the number of the current day brings us back one month
    return next_month - datetime.timedelta(days=next_month.day)

def get_model_source(model_name, alternative_source):
    if model_name == "gpt2-medium":
        return "https://huggingface.co/gpt2-medium"
