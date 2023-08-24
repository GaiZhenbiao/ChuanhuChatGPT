# -*- coding:utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Type
import logging
import commentjson as json
import os
import datetime
import csv
import requests
import re
import html
import hashlib

import gradio as gr
from pypinyin import lazy_pinyin
import tiktoken
from markdown import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
import pandas as pd

from modules.presets import *
from . import shared
from modules.config import retrieve_proxy, hide_history_when_not_logged_in

if TYPE_CHECKING:
    from typing import TypedDict

    class DataframeData(TypedDict):
        headers: List[str]
        data: List[List[str | int | bool]]

def predict(current_model, *args):
    iter = current_model.predict(*args)
    for i in iter:
        yield i

def billing_info(current_model):
    return current_model.billing_info()

def set_key(current_model, *args):
    return current_model.set_key(*args)

def load_chat_history(current_model, *args):
    return current_model.load_chat_history(*args)

def delete_chat_history(current_model, *args):
    return current_model.delete_chat_history(*args)

def interrupt(current_model, *args):
    return current_model.interrupt(*args)

def reset(current_model, *args):
    return current_model.reset(*args)

def retry(current_model, *args):
    iter = current_model.retry(*args)
    for i in iter:
        yield i

def delete_first_conversation(current_model, *args):
    return current_model.delete_first_conversation(*args)

def delete_last_conversation(current_model, *args):
    return current_model.delete_last_conversation(*args)

def set_system_prompt(current_model, *args):
    return current_model.set_system_prompt(*args)

def save_chat_history(current_model, *args):
    return current_model.save_chat_history(*args)

def export_markdown(current_model, *args):
    return current_model.export_markdown(*args)

def load_chat_history(current_model, *args):
    return current_model.load_chat_history(*args)

def upload_chat_history(current_model, *args):
    return current_model.load_chat_history(*args)

def set_token_upper_limit(current_model, *args):
    return current_model.set_token_upper_limit(*args)

def set_temperature(current_model, *args):
    current_model.set_temperature(*args)

def set_top_p(current_model, *args):
    current_model.set_top_p(*args)

def set_n_choices(current_model, *args):
    current_model.set_n_choices(*args)

def set_stop_sequence(current_model, *args):
    current_model.set_stop_sequence(*args)

def set_max_tokens(current_model, *args):
    current_model.set_max_tokens(*args)

def set_presence_penalty(current_model, *args):
    current_model.set_presence_penalty(*args)

def set_frequency_penalty(current_model, *args):
    current_model.set_frequency_penalty(*args)

def set_logit_bias(current_model, *args):
    current_model.set_logit_bias(*args)

def set_user_identifier(current_model, *args):
    current_model.set_user_identifier(*args)

def set_single_turn(current_model, *args):
    current_model.set_single_turn(*args)

def handle_file_upload(current_model, *args):
    return current_model.handle_file_upload(*args)

def handle_summarize_index(current_model, *args):
    return current_model.summarize_index(*args)

def like(current_model, *args):
    return current_model.like(*args)

def dislike(current_model, *args):
    return current_model.dislike(*args)


def count_token(input_str):
    encoding = tiktoken.get_encoding("cl100k_base")
    if type(input_str) == dict:
        input_str = f"role: {input_str['role']}, content: {input_str['content']}"
    length = len(encoding.encode(input_str))
    return length


def markdown_to_html_with_syntax_highlight(md_str): # deprecated
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


def normalize_markdown(md_text: str) -> str: # deprecated
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


def convert_mdtext(md_text): # deprecated
    code_block_pattern = re.compile(r"```(.*?)(?:```|$)", re.DOTALL)
    inline_code_pattern = re.compile(r"`(.*?)`", re.DOTALL)
    code_blocks = code_block_pattern.findall(md_text)
    non_code_parts = code_block_pattern.split(md_text)[::2]

    result = []
    raw = f'<div class="raw-message hideM">{html.escape(md_text)}</div>'
    for non_code, code in zip(non_code_parts, code_blocks + [""]):
        if non_code.strip():
            non_code = normalize_markdown(non_code)
            result.append(markdown(non_code, extensions=["tables"]))
        if code.strip():
            # _, code = detect_language(code)  # 暂时去除代码高亮功能，因为在大段代码的情况下会出现问题
            # code = code.replace("\n\n", "\n") # 暂时去除代码中的空行，因为在大段代码的情况下会出现问题
            code = f"\n```{code}\n\n```"
            code = markdown_to_html_with_syntax_highlight(code)
            result.append(code)
    result = "".join(result)
    output = f'<div class="md-message">{result}</div>'
    output += raw
    output += ALREADY_CONVERTED_MARK
    return output


def clip_rawtext(chat_message, need_escape=True):
    # first, clip hr line
    hr_pattern = r'\n\n<hr class="append-display no-in-raw" />(.*?)'
    hr_match = re.search(hr_pattern, chat_message, re.DOTALL)
    message_clipped = chat_message[:hr_match.start()] if hr_match else chat_message
    # second, avoid agent-prefix being escaped
    agent_prefix_pattern = r'<!-- S O PREFIX --><p class="agent-prefix">(.*?)<\/p><!-- E O PREFIX -->'
    agent_matches = re.findall(agent_prefix_pattern, message_clipped)
    final_message = ""
    if agent_matches:
        agent_parts = re.split(agent_prefix_pattern, message_clipped)
        for i, part in enumerate(agent_parts):
            if i % 2 == 0:
                final_message += escape_markdown(part) if need_escape else part
            else:
                final_message += f'<!-- S O PREFIX --><p class="agent-prefix">{part}</p><!-- E O PREFIX -->'
    else:
        final_message = escape_markdown(message_clipped) if need_escape else message_clipped
    return final_message


def convert_bot_before_marked(chat_message):
    """
    注意不能给输出加缩进, 否则会被marked解析成代码块
    """
    if '<div class="md-message">' in chat_message:
        return chat_message
    else:
        raw = f'<div class="raw-message hideM"><pre>{clip_rawtext(chat_message)}</pre></div>'
        # really_raw = f'{START_OF_OUTPUT_MARK}<div class="really-raw hideM">{clip_rawtext(chat_message, need_escape=False)}\n</div>{END_OF_OUTPUT_MARK}'

        code_block_pattern = re.compile(r"```(.*?)(?:```|$)", re.DOTALL)
        code_blocks = code_block_pattern.findall(chat_message)
        non_code_parts = code_block_pattern.split(chat_message)[::2]
        result = []
        for non_code, code in zip(non_code_parts, code_blocks + [""]):
            if non_code.strip():
                result.append(non_code)
            if code.strip():
                code = f"\n```{code}\n```"
                result.append(code)
        result = "".join(result)
        md = f'<div class="md-message">\n\n{result}\n</div>'
        return raw + md

def convert_user_before_marked(chat_message):
    if '<div class="user-message">' in chat_message:
        return chat_message
    else:
        return f'<div class="user-message">{escape_markdown(chat_message)}</div>'

def escape_markdown(text):
    """
    Escape Markdown special characters to HTML-safe equivalents.
    """
    escape_chars = {
        # ' ': '&nbsp;',
        '_': '&#95;',
        '*': '&#42;',
        '[': '&#91;',
        ']': '&#93;',
        '(': '&#40;',
        ')': '&#41;',
        '{': '&#123;',
        '}': '&#125;',
        '#': '&#35;',
        '+': '&#43;',
        '-': '&#45;',
        '.': '&#46;',
        '!': '&#33;',
        '`': '&#96;',
        '>': '&#62;',
        '<': '&#60;',
        '|': '&#124;',
        '$': '&#36;',
        ':': '&#58;',
        '\n': '<br>',
    }
    text = text.replace('    ', '&nbsp;&nbsp;&nbsp;&nbsp;')
    return ''.join(escape_chars.get(c, c) for c in text)


def convert_asis(userinput): # deprecated
    return (
        f'<p style="white-space:pre-wrap;">{html.escape(userinput)}</p>'
        + ALREADY_CONVERTED_MARK
    )


def detect_converted_mark(userinput): # deprecated
    try:
        if userinput.endswith(ALREADY_CONVERTED_MARK):
            return True
        else:
            return False
    except:
        return True


def detect_language(code): # deprecated
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
        if "/" in filename or "\\" in filename:
            history_file_path = filename
        else:
            history_file_path = os.path.join(HISTORY_DIR, user_name, filename)
        with open(history_file_path, "w", encoding='utf-8') as f:
            json.dump(json_s, f, ensure_ascii=False)
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
    if user_name == "" and hide_history_when_not_logged_in:
        return ""
    else:
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
                i18n("您的IP区域：未知。")
            )
        else:
            return i18n("获取IP地理位置失败。原因：") + f"{data['reason']}" + i18n("。你仍然可以使用聊天功能。")
    else:
        country = data["country_name"]
        if country == "China":
            text = "**您的IP区域：中国。请立即检查代理设置，在不受支持的地区使用API可能导致账号被封禁。**"
        else:
            text = i18n("您的IP区域：") + f"{country}。"
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


def update_chuanhu():
    from .repo import background_update

    print("[Updater] Trying to update...")
    update_status = background_update()
    if update_status == "success":
        logging.info("Successfully updated, restart needed")
        status = '<span id="update-status" class="hideK">success</span>'
        return gr.Markdown.update(value=i18n("更新成功，请重启本程序")+status)
    else:
        status = '<span id="update-status" class="hideK">failure</span>'
        return gr.Markdown.update(value=i18n("更新失败，请尝试[手动更新](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程#手动更新)")+status)


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

def refresh_ui_elements_on_load(current_model, selected_model_name, user_name):
    current_model.set_user_identifier(user_name)
    return toggle_like_btn_visibility(selected_model_name), *current_model.auto_load()

def toggle_like_btn_visibility(selected_model_name):
    if selected_model_name == "xmchat":
        return gr.update(visible=True)
    else:
        return gr.update(visible=False)

def new_auto_history_filename(dirname):
    latest_file = get_latest_filepath(dirname)
    if latest_file:
        with open(os.path.join(dirname, latest_file), 'r', encoding="utf-8") as f:
            if len(f.read()) == 0:
                return latest_file
    now = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    return f'{now}.json'

def get_latest_filepath(dirname):
    pattern = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}')
    latest_time = None
    latest_file = None
    for filename in os.listdir(dirname):
        if os.path.isfile(os.path.join(dirname, filename)):
            match = pattern.search(filename)
            if match and match.group(0) == filename[:19]:
                time_str = filename[:19]
                filetime = datetime.datetime.strptime(time_str, '%Y-%m-%d_%H-%M-%S')
                if not latest_time or filetime > latest_time:
                    latest_time = filetime
                    latest_file = filename
    return latest_file

def get_history_filepath(username):
    dirname = os.path.join(HISTORY_DIR, username)
    os.makedirs(dirname, exist_ok=True)
    latest_file = get_latest_filepath(dirname)
    if not latest_file:
        latest_file = new_auto_history_filename(dirname)

    latest_file = os.path.join(dirname, latest_file)
    return latest_file

def beautify_err_msg(err_msg):
    if "insufficient_quota" in  err_msg:
        return i18n("剩余配额不足，[进一步了解](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/%E5%B8%B8%E8%A7%81%E9%97%AE%E9%A2%98#you-exceeded-your-current-quota-please-check-your-plan-and-billing-details)")
    if "The model: gpt-4 does not exist" in err_msg:
        return i18n("你没有权限访问 GPT4，[进一步了解](https://github.com/GaiZhenbiao/ChuanhuChatGPT/issues/843)")
    if "Resource not found" in err_msg:
        return i18n("请查看 config_example.json，配置 Azure OpenAI")
    return err_msg

def auth_from_conf(username, password):
    try:
        with open("config.json", encoding="utf-8") as f:
            conf = json.load(f)
        usernames, passwords = [i[0] for i in conf["users"]], [i[1] for i in conf["users"]]
        if username in usernames:
            if passwords[usernames.index(username)] == password:
                return True
        return False
    except:
        return False

def get_file_hash(file_src=None, file_paths=None):
    if file_src:
        file_paths = [x.name for x in file_src]
    file_paths.sort(key=lambda x: os.path.basename(x))

    md5_hash = hashlib.md5()
    for file_path in file_paths:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                md5_hash.update(chunk)

    return md5_hash.hexdigest()
