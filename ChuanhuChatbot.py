import json
import gradio as gr
# import openai
import os
import sys
import traceback
import requests
# import markdown

my_api_key = ""    # 在这里输入你的 API 密钥
initial_prompt = "You are a helpful assistant."

API_URL = "https://api.openai.com/v1/chat/completions"

if my_api_key == "":
    my_api_key = os.environ.get('my_api_key')

if my_api_key == "empty":
    print("Please give a api key!")
    sys.exit(1)


def parse_text(text):
    lines = text.split("\n")
    count = 0
    for i, line in enumerate(lines):
        if "```" in line:
            count += 1
            items = line.split('`')
            if count % 2 == 1:
                lines[i] = f'<pre><code class="{items[-1]}">'
            else:
                lines[i] = f'</code></pre>'
        else:
            if i > 0:
                if count % 2 == 1:
                    line = line.replace("&", "&amp;")
                    line = line.replace("\"", "&quot;")
                    line = line.replace("\'", "&apos;")
                    line = line.replace("<", "&lt;")
                    line = line.replace(">", "&gt;")
                    line = line.replace(" ", "&nbsp;")
                lines[i] = '<br/>'+line
    return "".join(lines)

def predict(inputs, top_p, temperature, openai_api_key, chatbot=[], history=[], system_prompt=initial_prompt, retry=False, summary=False):  # repetition_penalty, top_k

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}"
    }

    chat_counter = len(history) // 2

    print(f"chat_counter - {chat_counter}")

    messages = [compose_system(system_prompt)]
    if chat_counter:
        for data in chatbot:
            temp1 = {}
            temp1["role"] = "user"
            temp1["content"] = data[0]
            temp2 = {}
            temp2["role"] = "assistant"
            temp2["content"] = data[1]
            if temp1["content"] != "":
                messages.append(temp1)
                messages.append(temp2)
            else:
                messages[-1]['content'] = temp2['content']
    if retry and chat_counter:
        messages.pop()
    elif summary and chat_counter:
        messages.append(compose_user(
            "请帮我总结一下上述对话的内容，实现减少字数的同时，保证对话的质量。在总结中不要加入这一句话。"))
        history = ["我们刚刚聊了什么？"]
    else:
        temp3 = {}
        temp3["role"] = "user"
        temp3["content"] = inputs
        messages.append(temp3)
        chat_counter += 1
    # messages
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": messages,  # [{"role": "user", "content": f"{inputs}"}],
        "temperature": temperature,  # 1.0,
        "top_p": top_p,  # 1.0,
        "n": 1,
        "stream": True,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }

    if not summary:
        history.append(inputs)
    print(f"payload is - {payload}")
    # make a POST request to the API endpoint using the requests.post method, passing in stream=True
    response = requests.post(API_URL, headers=headers,
                             json=payload, stream=True)
    #response = requests.post(API_URL, headers=headers, json=payload, stream=True)

    token_counter = 0
    partial_words = ""

    counter = 0
    chatbot.append((history[-1], ""))
    for chunk in response.iter_lines():
        if counter == 0:
            counter += 1
            continue
        counter += 1
        # check whether each line is non-empty
        if chunk:
            # decode each line as response data is in bytes
            if len(json.loads(chunk.decode()[6:])['choices'][0]["delta"]) == 0:
                break
            #print(json.loads(chunk.decode()[6:])['choices'][0]["delta"]    ["content"])
            partial_words = partial_words + \
                json.loads(chunk.decode()[6:])[
                    'choices'][0]["delta"]["content"]
            if token_counter == 0:
                history.append(" " + partial_words)
            else:
                history[-1] = parse_text(partial_words)
            chatbot[-1] = (history[-2], history[-1])
        #   chat = [(history[i], history[i + 1]) for i in range(0, len(history)     - 1, 2) ]  # convert to tuples of list
            token_counter += 1
            # resembles {chatbot: chat,     state: history}
            yield chatbot, history



def delete_last_conversation(chatbot, history):
    if chat_counter > 0:
        chat_counter -= 1
        chatbot.pop()
        history.pop()
        history.pop()
    return chatbot, history

def save_chat_history(filepath, system, history, chatbot):
    if filepath == "":
        return
    if not filepath.endswith(".json"):
        filepath += ".json"
    json_s = {"system": system, "history": history, "chatbot": chatbot}
    with open(filepath, "w") as f:
        json.dump(json_s, f)


def load_chat_history(filename):
    with open(filename, "r") as f:
        json_s = json.load(f)
    return filename, json_s["system"], json_s["history"], json_s["chatbot"]


def get_history_names(plain=False):
    # find all json files in the current directory and return their names
    files = [f for f in os.listdir() if f.endswith(".json")]
    if plain:
        return files
    else:
        return gr.Dropdown.update(choices=files)


def reset_state():
    return [], []


def compose_system(system_prompt):
    return {"role": "system", "content": system_prompt}


def compose_user(user_input):
    return {"role": "user", "content": user_input}


def reset_textbox():
    return gr.update(value='')

title = """<h1 align="center">川虎ChatGPT 🚀</h1>"""
description = """<div align=center>

由Bilibili [土川虎虎虎](https://space.bilibili.com/29125536) 开发

访问川虎ChatGPT的 [GitHub项目](https://github.com/GaiZhenbiao/ChuanhuChatGPT) 下载最新版脚本

此App使用 `gpt-3.5-turbo` 大语言模型
</div>
"""
with gr.Blocks() as demo:
    gr.HTML(title)
    keyTxt = gr.Textbox(show_label=True, placeholder=f"在这里输入你的OpenAI API-key...",
                        value=my_api_key, label="API Key", type="password").style(container=True)
    chatbot = gr.Chatbot()  # .style(color_map=("#1D51EE", "#585A5B"))
    history = gr.State([])
    TRUECOMSTANT = gr.State(True)
    FALSECONSTANT = gr.State(False)
    topic = gr.State("未命名对话历史记录")

    with gr.Row():
        with gr.Column(scale=12):
            txt = gr.Textbox(show_label=False, placeholder="在这里输入").style(
                container=False)
        with gr.Column(min_width=50, scale=1):
            submitBtn = gr.Button("🚀", variant="primary")
    with gr.Row():
        emptyBtn = gr.Button("🧹 新的对话")
        retryBtn = gr.Button("🔄 重新生成")
        delLastBtn = gr.Button("🗑️ 删除上条对话")
        reduceTokenBtn = gr.Button("♻️ 总结对话")
    systemPromptTxt = gr.Textbox(show_label=True, placeholder=f"在这里输入System Prompt...",
                                 label="System prompt", value=initial_prompt).style(container=True)
    with gr.Accordion(label="保存/加载对话历史记录(在文本框中输入文件名，点击“保存对话”按钮，历史记录文件会被存储到Python文件旁边)", open=False):
        with gr.Column():
            with gr.Row():
                with gr.Column(scale=6):
                    saveFileName = gr.Textbox(
                        show_label=True, placeholder=f"在这里输入保存的文件名...", label="设置保存文件名", value="对话历史记录").style(container=True)
                with gr.Column(scale=1):
                    saveBtn = gr.Button("💾 保存对话")
            with gr.Row():
                with gr.Column(scale=6):
                    uploadDropdown = gr.Dropdown(label="从列表中加载对话", choices=get_history_names(plain=True), multiselect=False)
                with gr.Column(scale=1):
                    refreshBtn = gr.Button("🔄 刷新")
                    uploadBtn = gr.Button("📂 读取对话")
    #inputs, top_p, temperature, top_k, repetition_penalty
    with gr.Accordion("参数", open=False):
        top_p = gr.Slider(minimum=-0, maximum=1.0, value=1.0, step=0.05,
                          interactive=True, label="Top-p (nucleus sampling)",)
        temperature = gr.Slider(minimum=-0, maximum=5.0, value=1.0,
                                step=0.1, interactive=True, label="Temperature",)
        #top_k = gr.Slider( minimum=1, maximum=50, value=4, step=1, interactive=True, label="Top-k",)
        #repetition_penalty = gr.Slider( minimum=0.1, maximum=3.0, value=1.03, step=0.01, interactive=True, label="Repetition Penalty", )
    gr.Markdown(description)


    txt.submit(predict, [txt, top_p, temperature, keyTxt,
               chatbot, history, systemPromptTxt], [chatbot, history])
    txt.submit(reset_textbox, [], [txt])
    submitBtn.click(predict, [txt, top_p, temperature, keyTxt, chatbot,
                    history, systemPromptTxt], [chatbot, history], show_progress=True)
    submitBtn.click(reset_textbox, [], [txt])
    emptyBtn.click(reset_state, outputs=[chatbot, history])
    retryBtn.click(predict, [txt, top_p, temperature, keyTxt, chatbot, history,
                   systemPromptTxt, TRUECOMSTANT], [chatbot, history], show_progress=True)
    delLastBtn.click(delete_last_conversation, [chatbot, history], [
                     chatbot, history], show_progress=True)
    reduceTokenBtn.click(predict, [txt, top_p, temperature, keyTxt, chatbot, history,
                         systemPromptTxt, FALSECONSTANT, TRUECOMSTANT], [chatbot, history], show_progress=True)
    saveBtn.click(save_chat_history, [
                  saveFileName, systemPromptTxt, history, chatbot], None, show_progress=True)
    saveBtn.click(get_history_names, None, [uploadDropdown])
    refreshBtn.click(get_history_names, None, [uploadDropdown])
    uploadBtn.click(load_chat_history, [uploadDropdown],  [saveFileName, systemPromptTxt, history, chatbot], show_progress=True)

print("川虎的温馨提示：访问 http://localhost:7860 查看界面")
# 默认开启本地服务器，默认可以直接从IP访问，默认不创建公开分享链接
demo.title = "川虎ChatGPT 🚀"
demo.queue().launch(server_name="127.0.0.1", server_port=7860, share=False) # 改为 share=True 可以创建公开分享链接
