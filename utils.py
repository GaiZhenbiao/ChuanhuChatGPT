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

import gradio as gr
from pypinyin import lazy_pinyin
import tiktoken

from presets import *

# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s")

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


def parse_text(text):
    in_code_block = False
    in_list = False
    new_lines = []
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
        else:
            if re.match(r'(\*|-|\d+\.)\s', line):
                if not in_list:
                    in_list = True
            elif in_list and line.strip() != "":
                in_list = False
                new_lines.append("")

        if in_code_block:
            if line.strip() != "":
                new_lines.append(line)
        elif in_list:
            if line.strip() != "":
                new_lines.append(line)
        else:
            new_lines.append(line)
    if in_code_block:
        new_lines.append("```")
    text = "\n".join(new_lines)
    return text


def construct_text(role, text):
    return {"role": role, "content": text}


def construct_user(text):
    return construct_text("user", text)


def construct_system(text):
    return construct_text("system", text)


def construct_assistant(text):
    return construct_text("assistant", text)


def construct_token_message(token, stream=False):
    return f"Token 计数: {token}"


def delete_last_conversation(chatbot, history, previous_token_count):
    if len(chatbot) > 0 and standard_error_msg in chatbot[-1][1]:
        logging.info("由于包含报错信息，只删除chatbot记录")
        chatbot.pop()
        return chatbot, history
    if len(history) > 0:
        logging.info("删除了一组对话历史")
        history.pop()
        history.pop()
    if len(chatbot) > 0:
        logging.info("删除了一组chatbot对话")
        chatbot.pop()
    if len(previous_token_count) > 0:
        logging.info("删除了一组对话的token计数记录")
        previous_token_count.pop()
    return (
        chatbot,
        history,
        previous_token_count,
        construct_token_message(sum(previous_token_count)),
    )


def save_file(filename, system, history, chatbot):
    logging.info("保存对话历史中……")
    os.makedirs(HISTORY_DIR, exist_ok=True)
    if filename.endswith(".json"):
        json_s = {"system": system, "history": history, "chatbot": chatbot}
        print(json_s)
        with open(os.path.join(HISTORY_DIR, filename), "w") as f:
            json.dump(json_s, f)
    elif filename.endswith(".md"):
        md_s = f"system: \n- {system} \n"
        for data in history:
            md_s += f"\n{data['role']}: \n- {data['content']} \n"
        with open(os.path.join(HISTORY_DIR, filename), "w", encoding="utf8") as f:
            f.write(md_s)
    logging.info("保存对话历史完毕")
    return os.path.join(HISTORY_DIR, filename)


def save_chat_history(filename, system, history, chatbot):
    if filename == "":
        return
    if not filename.endswith(".json"):
        filename += ".json"
    return save_file(filename, system, history, chatbot)


def export_markdown(filename, system, history, chatbot):
    if filename == "":
        return
    if not filename.endswith(".md"):
        filename += ".md"
    return save_file(filename, system, history, chatbot)


def load_chat_history(filename, system, history, chatbot):
    logging.info("加载对话历史中……")
    if type(filename) != str:
        filename = filename.name
    try:
        with open(os.path.join(HISTORY_DIR, filename), "r") as f:
            json_s = json.load(f)
        try:
            if type(json_s["history"][0]) == str:
                logging.info("历史记录格式为旧版，正在转换……")
                new_history = []
                for index, item in enumerate(json_s["history"]):
                    if index % 2 == 0:
                        new_history.append(construct_user(item))
                    else:
                        new_history.append(construct_assistant(item))
                json_s["history"] = new_history
                logging.info(new_history)
        except:
            # 没有对话历史
            pass
        logging.info("加载对话历史完毕")
        return filename, json_s["system"], json_s["history"], json_s["chatbot"]
    except FileNotFoundError:
        logging.info("没有找到对话历史文件，不执行任何操作")
        return filename, system, history, chatbot


def sorted_by_pinyin(list):
    return sorted(list, key=lambda char: lazy_pinyin(char)[0][0])


def get_file_names(dir, plain=False, filetypes=[".json"]):
    logging.info(f"获取文件名列表，目录为{dir}，文件类型为{filetypes}，是否为纯文本列表{plain}")
    files = []
    try:
        for type in filetypes:
            files += [f for f in os.listdir(dir) if f.endswith(type)]
    except FileNotFoundError:
        files = []
    files = sorted_by_pinyin(files)
    if files == []:
        files = [""]
    if plain:
        return files
    else:
        return gr.Dropdown.update(choices=files)


def get_history_names(plain=False):
    logging.info("获取历史记录文件名列表")
    return get_file_names(HISTORY_DIR, plain)


def load_template(filename, mode=0):
    logging.info(f"加载模板文件{filename}，模式为{mode}（0为返回字典和下拉菜单，1为返回下拉菜单，2为返回字典）")
    lines = []
    logging.info("Loading template...")
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
            choices=choices, value=choices[0]
        )


def get_template_names(plain=False):
    logging.info("获取模板文件名列表")
    return get_file_names(TEMPLATES_DIR, plain, filetypes=[".csv", "json"])


def get_template_content(templates, selection, original_system_prompt):
    logging.info(f"应用模板中，选择为{selection}，原始系统提示为{original_system_prompt}")
    try:
        return templates[selection]
    except:
        return original_system_prompt


def reset_state():
    logging.info("重置状态")
    return [], [], [], construct_token_message(0)


def reset_textbox():
    return gr.update(value="")


def reset_default():
    global API_URL
    API_URL = "https://api.openai.com/v1/chat/completions"
    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("https_proxy", None)
    return gr.update(value=API_URL), gr.update(value=""), "API URL 和代理已重置"


def change_api_url(url):
    global API_URL
    API_URL = url
    msg = f"API地址更改为了{url}"
    logging.info(msg)
    return msg


def change_proxy(proxy):
    os.environ["HTTPS_PROXY"] = proxy
    msg = f"代理更改为了{proxy}"
    logging.info(msg)
    return msg


def hide_middle_chars(s):
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


def sha1sum(filename):
    sha1 = hashlib.sha1()
    sha1.update(filename.encode("utf-8"))
    return sha1.hexdigest()


def replace_today(prompt):
    today = datetime.datetime.today().strftime("%Y-%m-%d")
    return prompt.replace("{current_date}", today)

def get_geoip():
    response = requests.get('https://ipapi.co/json/', timeout=5)
    data = response.json()
    if "error" in data.keys():
        logging.warning(f"无法获取IP地址信息。\n{data}")
        if data['reason'] == "RateLimited":
            return f"获取IP地理位置失败，因为达到了检测IP的速率限制。聊天功能可能仍然可用，但请注意，如果您的IP地址在不受支持的地区，您可能会遇到问题。"
        else:
            return f"获取IP地理位置失败。原因：{data['reason']}"
    else:
        country = data['country_name']
        if country == "China":
            text = "**您的IP区域：中国。请立即检查代理设置，在不受支持的地区使用API可能导致账号被封禁。**"
        else:
            text = f"您的IP区域：{country}。"
        logging.info(text)
        return text