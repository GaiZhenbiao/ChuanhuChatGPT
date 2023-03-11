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
from presets import *

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
    extra = "【仅包含回答的计数】 " if stream else ""
    return f"{extra}Token 计数: {token}"

def get_response(openai_api_key, system_prompt, history, temperature, top_p, stream):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}"
    }

    history = [construct_system(system_prompt), *history]

    payload = {
        "model": "gpt-3.5-turbo",
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

def stream_predict(openai_api_key, system_prompt, history, inputs, chatbot, previous_token_count, top_p, temperature):
    def get_return_value():
        return chatbot, history, status_text, [*previous_token_count, token_counter]
    token_counter = 0
    partial_words = ""
    counter = 0
    status_text = "OK"
    history.append(construct_user(inputs))
    try:
        response = get_response(openai_api_key, system_prompt, history, temperature, top_p, True)
    except requests.exceptions.ConnectTimeout:
        status_text = standard_error_msg + error_retrieve_prompt
        yield get_return_value()
        return

    chatbot.append((parse_text(inputs), ""))
    yield get_return_value()

    for chunk in response.iter_lines():
        if counter == 0:
            counter += 1
            continue
        counter += 1
        # check whether each line is non-empty
        if chunk:
            chunk = chunk.decode()
            chunklength = len(chunk)
            chunk = json.loads(chunk[6:])
            # decode each line as response data is in bytes
            if chunklength > 6 and "delta" in chunk['choices'][0]:
                finish_reason = chunk['choices'][0]['finish_reason']
                status_text = construct_token_message(sum(previous_token_count)+token_counter, stream=True)
                if finish_reason == "stop":
                    yield get_return_value()
                    break
                partial_words = partial_words + chunk['choices'][0]["delta"]["content"]
                if token_counter == 0:
                    history.append(construct_assistant(" " + partial_words))
                else:
                    history[-1] = construct_assistant(partial_words)
                chatbot[-1] = (parse_text(inputs), parse_text(partial_words))
                token_counter += 1
                yield get_return_value()


def predict_all(openai_api_key, system_prompt, history, inputs, chatbot, previous_token_count, top_p, temperature):
    history.append(construct_user(inputs))
    try:
        response = get_response(openai_api_key, system_prompt, history, temperature, top_p, False)
    except requests.exceptions.ConnectTimeout:
        status_text = standard_error_msg + error_retrieve_prompt
        return chatbot, history, status_text, previous_token_count
    response = json.loads(response.text)
    content = response["choices"][0]["message"]["content"]
    history.append(construct_assistant(content))
    chatbot.append((parse_text(inputs), parse_text(content)))
    total_token_count = response["usage"]["total_tokens"]
    previous_token_count.append(total_token_count - sum(previous_token_count))
    status_text = construct_token_message(total_token_count)
    return chatbot, history, status_text, previous_token_count


def predict(openai_api_key, system_prompt, history, inputs, chatbot, token_count, top_p, temperature, stream=False, should_check_token_count = True):  # repetition_penalty, top_k
    if stream:
        iter = stream_predict(openai_api_key, system_prompt, history, inputs, chatbot, token_count, top_p, temperature)
        for chatbot, history, status_text, token_count in iter:
            yield chatbot, history, status_text, token_count
    else:
        chatbot, history, status_text, token_count = predict_all(openai_api_key, system_prompt, history, inputs, chatbot, token_count, top_p, temperature)
        yield chatbot, history, status_text, token_count
    if stream:
        max_token = max_token_streaming
    else:
        max_token = max_token_all
    if sum(token_count) > max_token and should_check_token_count:
        iter = reduce_token_size(openai_api_key, system_prompt, history, chatbot, token_count, top_p, temperature, stream=False, hidden=True)
        for chatbot, history, status_text, token_count in iter:
            status_text = f"Token 达到上限，已自动降低Token计数至 {status_text}"
            yield chatbot, history, status_text, token_count


def retry(openai_api_key, system_prompt, history, chatbot, token_count, top_p, temperature, stream=False):
    if len(history) == 0:
        yield chatbot, history, f"{standard_error_msg}上下文是空的", token_count
        return
    history.pop()
    inputs = history.pop()["content"]
    token_count.pop()
    iter = predict(openai_api_key, system_prompt, history, inputs, chatbot, token_count, top_p, temperature, stream=stream)
    for x in iter:
        yield x


def reduce_token_size(openai_api_key, system_prompt, history, chatbot, token_count, top_p, temperature, stream=False, hidden=False):
    iter = predict(openai_api_key, system_prompt, history, summarize_prompt, chatbot, token_count, top_p, temperature, stream=stream, should_check_token_count=False)
    for chatbot, history, status_text, previous_token_count in iter:
        history = history[-2:]
        token_count = previous_token_count[-1:]
        if hidden:
            chatbot.pop()
        yield chatbot, history, construct_token_message(sum(token_count), stream=stream), token_count


def delete_last_conversation(chatbot, history, previous_token_count, streaming):
    if len(chatbot) > 0 and standard_error_msg in chatbot[-1][1]:
        chatbot.pop()
        return chatbot, history
    if len(history) > 0:
        history.pop()
        history.pop()
    if len(chatbot) > 0:
        chatbot.pop()
    if len(previous_token_count) > 0:
        previous_token_count.pop()
    return chatbot, history, previous_token_count, construct_token_message(sum(previous_token_count), streaming)


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
        with open(os.path.join(HISTORY_DIR, filename), "r") as f:
            json_s = json.load(f)
        if type(json_s["history"]) == list:
            new_history = []
            for index, item in enumerate(json_s["history"]):
                if index % 2 == 0:
                    new_history.append(construct_user(item))
                else:
                    new_history.append(construct_assistant(item))
            json_s["history"] = new_history
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
    return [], [], [], construct_token_message(0)

def compose_system(system_prompt):
    return {"role": "system", "content": system_prompt}


def compose_user(user_input):
    return {"role": "user", "content": user_input}


def reset_textbox():
    return gr.update(value='')
