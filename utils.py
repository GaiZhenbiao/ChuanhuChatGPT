# -*- coding:utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Type
import logging
import json
import gradio as gr
# import openai
import os
import traceback
import requests
# import markdown
import csv
import mdtex2html
from pypinyin import lazy_pinyin
from presets import *
import tiktoken
from tqdm import tqdm
import colorama
from duckduckgo_search import ddg
import datetime

# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s")

if TYPE_CHECKING:
    from typing import TypedDict

    class DataframeData(TypedDict):
        headers: List[str]
        data: List[List[str | int | bool]]

initial_prompt = "You are a helpful assistant."
API_URL = "https://api.openai.com/v1/chat/completions"
HISTORY_DIR = "history"
TEMPLATES_DIR = "templates"

def postprocess(
        self, y: List[Tuple[str | None, str | None]]
    ) -> List[Tuple[str | None, str | None]]:
        """
        Parameters:
            y: List of tuples representing the message and response pairs. Each message and response should be a string, which may be in Markdown format.
        Returns:
            List of tuples representing the message and response. Each message and response will be a string of HTML.
        """
        if y is None:
            return []
        for i, (message, response) in enumerate(y):
            y[i] = (
                # None if message is None else markdown.markdown(message),
                # None if response is None else markdown.markdown(response),
                None if message is None else message,
                None if response is None else mdtex2html.convert(response),
            )
        return y

def count_token(input_str):
    encoding = tiktoken.get_encoding("cl100k_base")
    length = len(encoding.encode(input_str))
    return length

def parse_text(text):
    lines = text.split("\n")
    lines = [line for line in lines if line != ""]
    count = 0
    for i, line in enumerate(lines):
        if "```" in line:
            count += 1
            items = line.split('`')
            if count % 2 == 1:
                lines[i] = f'<pre><code class="language-{items[-1]}">'
            else:
                lines[i] = f'<br></code></pre>'
        else:
            if i > 0:
                if count % 2 == 1:
                    line = line.replace("`", "\`")
                    line = line.replace("<", "&lt;")
                    line = line.replace(">", "&gt;")
                    line = line.replace(" ", "&nbsp;")
                    line = line.replace("*", "&ast;")
                    line = line.replace("_", "&lowbar;")
                    line = line.replace("-", "&#45;")
                    line = line.replace(".", "&#46;")
                    line = line.replace("!", "&#33;")
                    line = line.replace("(", "&#40;")
                    line = line.replace(")", "&#41;")
                    line = line.replace("$", "&#36;")
                lines[i] = "<br>"+line
    text = "".join(lines)
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

def get_response(openai_api_key, system_prompt, history, temperature, top_p, stream, selected_model):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}"
    }

    history = [construct_system(system_prompt), *history]

    payload = {
        "model": selected_model,
        "messages": history,  # [{"role": "user", "content": f"{inputs}"}],
        "temperature": temperature,  # 1.0,
        "top_p": top_p,  # 1.0,
        "n": 1,
        "stream": stream,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }
    if stream:
        timeout = timeout_streaming
    else:
        timeout = timeout_all
    response = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=timeout)
    return response

def stream_predict(openai_api_key, system_prompt, history, inputs, chatbot, all_token_counts, top_p, temperature, selected_model):
    def get_return_value():
        return chatbot, history, status_text, all_token_counts

    logging.info("实时回答模式")
    partial_words = ""
    counter = 0
    status_text = "开始实时传输回答……"
    history.append(construct_user(inputs))
    history.append(construct_assistant(""))
    chatbot.append((parse_text(inputs), ""))
    user_token_count = 0
    if len(all_token_counts) == 0:
        system_prompt_token_count = count_token(system_prompt)
        user_token_count = count_token(inputs) + system_prompt_token_count
    else:
        user_token_count = count_token(inputs)
    all_token_counts.append(user_token_count)
    logging.info(f"输入token计数: {user_token_count}")
    yield get_return_value()
    try:
        response = get_response(openai_api_key, system_prompt, history, temperature, top_p, True, selected_model)
    except requests.exceptions.ConnectTimeout:
        status_text = standard_error_msg + connection_timeout_prompt + error_retrieve_prompt
        yield get_return_value()
        return
    except requests.exceptions.ReadTimeout:
        status_text = standard_error_msg + read_timeout_prompt + error_retrieve_prompt
        yield get_return_value()
        return

    yield get_return_value()
    error_json_str = ""

    for chunk in tqdm(response.iter_lines()):
        if counter == 0:
            counter += 1
            continue
        counter += 1
        # check whether each line is non-empty
        if chunk:
            chunk = chunk.decode()
            chunklength = len(chunk)
            try:
                chunk = json.loads(chunk[6:])
            except json.JSONDecodeError:
                logging.info(chunk)
                error_json_str += chunk
                status_text = f"JSON解析错误。请重置对话。收到的内容: {error_json_str}"
                yield get_return_value()
                continue
            # decode each line as response data is in bytes
            if chunklength > 6 and "delta" in chunk['choices'][0]:
                finish_reason = chunk['choices'][0]['finish_reason']
                status_text = construct_token_message(sum(all_token_counts), stream=True)
                if finish_reason == "stop":
                    yield get_return_value()
                    break
                try:
                    partial_words = partial_words + chunk['choices'][0]["delta"]["content"]
                except KeyError:
                    status_text = standard_error_msg + "API回复中找不到内容。很可能是Token计数达到上限了。请重置对话。当前Token计数: " + str(sum(all_token_counts))
                    yield get_return_value()
                    break
                history[-1] = construct_assistant(partial_words)
                chatbot[-1] = (parse_text(inputs), parse_text(partial_words))
                all_token_counts[-1] += 1
                yield get_return_value()


def predict_all(openai_api_key, system_prompt, history, inputs, chatbot, all_token_counts, top_p, temperature, selected_model):
    logging.info("一次性回答模式")
    history.append(construct_user(inputs))
    history.append(construct_assistant(""))
    chatbot.append((parse_text(inputs), ""))
    all_token_counts.append(count_token(inputs))
    try:
        response = get_response(openai_api_key, system_prompt, history, temperature, top_p, False, selected_model)
    except requests.exceptions.ConnectTimeout:
        status_text = standard_error_msg + connection_timeout_prompt + error_retrieve_prompt
        return chatbot, history, status_text, all_token_counts
    except requests.exceptions.ProxyError:
        status_text = standard_error_msg + proxy_error_prompt + error_retrieve_prompt
        return chatbot, history, status_text, all_token_counts
    except requests.exceptions.SSLError:
        status_text = standard_error_msg + ssl_error_prompt + error_retrieve_prompt
        return chatbot, history, status_text, all_token_counts
    response = json.loads(response.text)
    content = response["choices"][0]["message"]["content"]
    history[-1] = construct_assistant(content)
    chatbot[-1] = (parse_text(inputs), parse_text(content))
    total_token_count = response["usage"]["total_tokens"]
    all_token_counts[-1] = total_token_count - sum(all_token_counts)
    status_text = construct_token_message(total_token_count)
    return chatbot, history, status_text, all_token_counts


def predict(openai_api_key, system_prompt, history, inputs, chatbot, all_token_counts, top_p, temperature, stream=False, selected_model = MODELS[0], use_websearch_checkbox = False, should_check_token_count = True):  # repetition_penalty, top_k
    logging.info("输入为：" +colorama.Fore.BLUE + f"{inputs}" + colorama.Style.RESET_ALL)
    if use_websearch_checkbox:
        results = ddg(inputs, max_results=3)
        web_results = []
        for idx, result in enumerate(results):
            logging.info(f"搜索结果{idx + 1}：{result}")
            web_results.append(f'[{idx+1}]"{result["body"]}"\nURL: {result["href"]}')
        web_results = "\n\n".join(web_results)
        today = datetime.datetime.today().strftime("%Y-%m-%d")
        inputs = websearch_prompt.replace("{current_date}", today).replace("{query}", inputs).replace("{web_results}", web_results)
    if len(openai_api_key) != 51:
        status_text = standard_error_msg + no_apikey_msg
        logging.info(status_text)
        chatbot.append((parse_text(inputs), ""))
        if len(history) == 0:
            history.append(construct_user(inputs))
            history.append("")
            all_token_counts.append(0)
        else:
            history[-2] = construct_user(inputs)
        yield chatbot, history, status_text, all_token_counts
        return
    if stream:
        yield chatbot, history, "开始生成回答……", all_token_counts
    if stream:
        logging.info("使用流式传输")
        iter = stream_predict(openai_api_key, system_prompt, history, inputs, chatbot, all_token_counts, top_p, temperature, selected_model)
        for chatbot, history, status_text, all_token_counts in iter:
            yield chatbot, history, status_text, all_token_counts
    else:
        logging.info("不使用流式传输")
        chatbot, history, status_text, all_token_counts = predict_all(openai_api_key, system_prompt, history, inputs, chatbot, all_token_counts, top_p, temperature, selected_model)
        yield chatbot, history, status_text, all_token_counts
    logging.info(f"传输完毕。当前token计数为{all_token_counts}")
    if len(history) > 1 and history[-1]['content'] != inputs:
        logging.info("回答为：" +colorama.Fore.BLUE + f"{history[-1]['content']}" + colorama.Style.RESET_ALL)
    if stream:
        max_token = max_token_streaming
    else:
        max_token = max_token_all
    if sum(all_token_counts) > max_token and should_check_token_count:
        status_text = f"精简token中{all_token_counts}/{max_token}"
        logging.info(status_text)
        yield chatbot, history, status_text, all_token_counts
        iter = reduce_token_size(openai_api_key, system_prompt, history, chatbot, all_token_counts, top_p, temperature, stream=False, selected_model=selected_model, hidden=True)
        for chatbot, history, status_text, all_token_counts in iter:
            status_text = f"Token 达到上限，已自动降低Token计数至 {status_text}"
            yield chatbot, history, status_text, all_token_counts


def retry(openai_api_key, system_prompt, history, chatbot, token_count, top_p, temperature, stream=False, selected_model = MODELS[0]):
    logging.info("重试中……")
    if len(history) == 0:
        yield chatbot, history, f"{standard_error_msg}上下文是空的", token_count
        return
    history.pop()
    inputs = history.pop()["content"]
    token_count.pop()
    iter = predict(openai_api_key, system_prompt, history, inputs, chatbot, token_count, top_p, temperature, stream=stream, selected_model=selected_model)
    logging.info("重试完毕")
    for x in iter:
        yield x


def reduce_token_size(openai_api_key, system_prompt, history, chatbot, token_count, top_p, temperature, stream=False, selected_model = MODELS[0], hidden=False):
    logging.info("开始减少token数量……")
    iter = predict(openai_api_key, system_prompt, history, summarize_prompt, chatbot, token_count, top_p, temperature, stream=stream, selected_model = selected_model, should_check_token_count=False)
    logging.info(f"chatbot: {chatbot}")
    for chatbot, history, status_text, previous_token_count in iter:
        history = history[-2:]
        token_count = previous_token_count[-1:]
        if hidden:
            chatbot.pop()
        yield chatbot, history, construct_token_message(sum(token_count), stream=stream), token_count
    logging.info("减少token数量完毕")


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
    return chatbot, history, previous_token_count, construct_token_message(sum(previous_token_count))


def save_chat_history(filename, system, history, chatbot):
    logging.info("保存对话历史中……")
    if filename == "":
        return
    if not filename.endswith(".json"):
        filename += ".json"
    os.makedirs(HISTORY_DIR, exist_ok=True)
    json_s = {"system": system, "history": history, "chatbot": chatbot}
    logging.info(json_s)
    with open(os.path.join(HISTORY_DIR, filename), "w") as f:
        json.dump(json_s, f, ensure_ascii=False, indent=4)
    logging.info("保存对话历史完毕")


def load_chat_history(filename, system, history, chatbot):
    logging.info("加载对话历史中……")
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
        with open(os.path.join(TEMPLATES_DIR, filename), "r", encoding="utf8") as csvfile:
            reader = csv.reader(csvfile)
            lines = list(reader)
        lines = lines[1:]
    if mode == 1:
        return sorted_by_pinyin([row[0] for row in lines])
    elif mode == 2:
        return {row[0]:row[1] for row in lines}
    else:
        choices = sorted_by_pinyin([row[0] for row in lines])
        return {row[0]:row[1] for row in lines}, gr.Dropdown.update(choices=choices, value=choices[0])

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
    return gr.update(value='')
