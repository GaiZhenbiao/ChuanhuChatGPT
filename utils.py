"""Contains all of the components that can be used with Gradio Interface / Blocks.
Along with the docs for each component, you can find the names of example demos that use
each component. These demos are located in the `demo` directory."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Type
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
                None if message is None else mdtex2html.convert((message)),
                None if response is None else mdtex2html.convert(response),
            )
        return y

def parse_text(text):
    lines = text.split("\n")
    lines = [line for line in lines if line != ""]
    count = 0
    firstline = False
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

def predict(inputs, top_p, temperature, openai_api_key, chatbot=[], history=[], system_prompt=initial_prompt, retry=False, summary=False, retry_on_crash = False, stream = True):  # repetition_penalty, top_k

    if retry_on_crash:
        retry = True

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}"
    }

    chat_counter = len(history) // 2

    print(f"chat_counter - {chat_counter}")

    messages = []
    if chat_counter:
        for index in range(0, 2*chat_counter, 2):
            temp1 = {}
            temp1["role"] = "user"
            temp1["content"] = history[index]
            temp2 = {}
            temp2["role"] = "assistant"
            temp2["content"] = history[index+1]
            if temp1["content"] != "":
                if temp2["content"] != "" or retry:
                    messages.append(temp1)
                    messages.append(temp2)
            else:
                messages[-1]['content'] = temp2['content']
    if retry and chat_counter:
        if retry_on_crash:
            messages = messages[-6:]
        messages.pop()
    elif summary:
        history = [*[i["content"] for i in messages[-2:]], "我们刚刚聊了什么？"]
        messages.append(compose_user(
            "请帮我总结一下上述对话的内容，实现减少字数的同时，保证对话的质量。在总结中不要加入这一句话。"))
    else:
        temp3 = {}
        temp3["role"] = "user"
        temp3["content"] = inputs
        messages.append(temp3)
        chat_counter += 1
    messages = [compose_system(system_prompt), *messages]
    # messages
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": messages,  # [{"role": "user", "content": f"{inputs}"}],
        "temperature": temperature,  # 1.0,
        "top_p": top_p,  # 1.0,
        "n": 1,
        "stream": stream,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }

    if not summary:
        history.append(inputs)
    else:
        print("精简中...")

    print(f"payload: {payload}")
    # make a POST request to the API endpoint using the requests.post method, passing in stream=True
    try:
        response = requests.post(API_URL, headers=headers, json=payload, stream=True)
    except:
        history.append("")
        chatbot.append((inputs, ""))
        yield history, chatbot, f"获取请求失败，请检查网络连接。"
        return

    token_counter = 0
    partial_words = ""

    counter = 0
    if stream:
        chatbot.append((parse_text(history[-1]), ""))
        for chunk in response.iter_lines():
            if counter == 0:
                counter += 1
                continue
            counter += 1
            # check whether each line is non-empty
            if chunk:
                # decode each line as response data is in bytes
                try:
                    if len(json.loads(chunk.decode()[6:])['choices'][0]["delta"]) == 0:
                        chunkjson = json.loads(chunk.decode()[6:])
                        status_text = f"id: {chunkjson['id']}, finish_reason: {chunkjson['choices'][0]['finish_reason']}"
                        yield chatbot, history, status_text
                        break
                except Exception as e:
                    if not retry_on_crash:
                        print("正在尝试使用缩短的context重新生成……")
                        chatbot.pop()
                        history.append("")
                        yield next(predict(inputs, top_p, temperature, openai_api_key, chatbot, history, system_prompt, retry, summary=False, retry_on_crash=True, stream=False))
                    else:
                        msg = "☹️发生了错误：生成失败，请检查网络"
                        print(msg)
                        history.append(inputs, "")
                        chatbot.append(inputs, msg)
                        yield chatbot, history, "status: ERROR"
                    break
                chunkjson = json.loads(chunk.decode()[6:])
                status_text = f"id: {chunkjson['id']}, finish_reason: {chunkjson['choices'][0]['finish_reason']}"
                partial_words = partial_words + \
                    json.loads(chunk.decode()[6:])[
                        'choices'][0]["delta"]["content"]
                if token_counter == 0:
                    history.append(" " + partial_words)
                else:
                    history[-1] = partial_words
                chatbot[-1] = (parse_text(history[-2]), parse_text(history[-1]))
                token_counter += 1
                yield chatbot, history, status_text
    else:
        try:
            responsejson = json.loads(response.text)
            content = responsejson["choices"][0]["message"]["content"]
            history.append(content)
            chatbot.append((parse_text(history[-2]), parse_text(content)))
            status_text = "精简完成"
        except:
            chatbot.append((parse_text(history[-1]), "☹️发生了错误，请检查网络连接或者稍后再试。"))
            status_text = "status: ERROR"
        yield chatbot, history, status_text



def delete_last_conversation(chatbot, history):
    try:
        if "☹️发生了错误" in chatbot[-1][1]:
            chatbot.pop()
            print(history)
            return chatbot, history
        history.pop()
        history.pop()
        chatbot.pop()
        print(history)
        return chatbot, history
    except:
        return chatbot, history

def save_chat_history(filename, system, history, chatbot):
    if filename == "":
        return
    if not filename.endswith(".json"):
        filename += ".json"
    os.makedirs(HISTORY_DIR, exist_ok=True)
    json_s = {"system": system, "history": history, "chatbot": chatbot}
    print(json_s)
    with open(os.path.join(HISTORY_DIR, filename), "w") as f:
        json.dump(json_s, f)


def load_chat_history(filename, system, history, chatbot):
    try:
        print("Loading from history...")
        with open(os.path.join(HISTORY_DIR, filename), "r") as f:
            json_s = json.load(f)
        print(json_s)
        return filename, json_s["system"], json_s["history"], json_s["chatbot"]
    except FileNotFoundError:
        print("File not found.")
        return filename, system, history, chatbot

def sorted_by_pinyin(list):
    return sorted(list, key=lambda char: lazy_pinyin(char)[0][0])

def get_file_names(dir, plain=False, filetypes=[".json"]):
    # find all json files in the current directory and return their names
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
    return get_file_names(HISTORY_DIR, plain)

def load_template(filename, mode=0):
    lines = []
    print("Loading template...")
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
    return get_file_names(TEMPLATES_DIR, plain, filetypes=[".csv", "json"])

def get_template_content(templates, selection, original_system_prompt):
    try:
        return templates[selection]
    except:
        return original_system_prompt

def reset_state():
    return [], []

def compose_system(system_prompt):
    return {"role": "system", "content": system_prompt}


def compose_user(user_input):
    return {"role": "user", "content": user_input}


def reset_textbox():
    return gr.update(value='')
