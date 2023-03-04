import json
import gradio as gr
import openai
import os
import sys
import traceback
# import markdown

my_api_key = ""    # 在这里输入你的 API 密钥
initial_prompt = "You are a helpful assistant."

if my_api_key == "":
    my_api_key = os.environ.get('my_api_key')

if my_api_key == "empty":
    print("Please give a api key!")
    sys.exit(1)

if my_api_key == "":
    initial_keytxt = None
elif len(str(my_api_key)) == 51:
    initial_keytxt = "默认api-key（未验证）：" + str(my_api_key[:4] + "..." + my_api_key[-4:])
else:
    initial_keytxt = "默认api-key无效，请重新输入"

def parse_text(text):
    lines = text.split("\n")
    for i,line in enumerate(lines):
        if "```" in line:
            items = line.split('`')
            if items[-1]:
                lines[i] = f'<pre><code class="{items[-1]}">'
            else:
                lines[i] = f'</code></pre>'
        else:
            if i>0:
                line = line.replace("<", "&lt;")
                line = line.replace(">", "&gt;")
                lines[i] = '<br/>'+line.replace(" ", "&nbsp;")
    return "".join(lines)

def get_response(system, context, myKey, raw = False):
    openai.api_key = myKey
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[system, *context],
    )
    openai.api_key = ""
    if raw:
        return response
    else:
        statistics = f'本次对话Tokens用量【{response["usage"]["total_tokens"]} / 4096】 （ 提问+上文 {response["usage"]["prompt_tokens"]}，回答 {response["usage"]["completion_tokens"]} ）'
        message = response["choices"][0]["message"]["content"]

        message_with_stats = f'{message}\n\n================\n\n{statistics}'
        # message_with_stats = markdown.markdown(message_with_stats)

        return message, parse_text(message_with_stats)

def predict(chatbot, input_sentence, system, context, myKey):
    if len(input_sentence) == 0:
        return []
    context.append({"role": "user", "content": f"{input_sentence}"})

    try:
        message, message_with_stats = get_response(system, context, myKey)
    except openai.error.AuthenticationError:
        chatbot.append((input_sentence, "请求失败，请检查API-key是否正确。"))
        return chatbot, context
    except openai.error.Timeout:
        chatbot.append((input_sentence, "请求超时，请检查网络连接。"))
        return chatbot, context
    except openai.error.APIConnectionError:
        chatbot.append((input_sentence, "连接失败，请检查网络连接。"))
        return chatbot, context
    except openai.error.RateLimitError:
        chatbot.append((input_sentence, "请求过于频繁，请5s后再试。"))
        return chatbot, context
    except:
        chatbot.append((input_sentence, "发生了未知错误Orz"))
        return chatbot, context

    context.append({"role": "assistant", "content": message})

    chatbot.append((input_sentence, message_with_stats))

    return chatbot, context

def retry(chatbot, system, context, myKey):
    if len(context) == 0:
        return [], []
    
    try:
        message, message_with_stats = get_response(system, context[:-1], myKey)
    except openai.error.AuthenticationError:
        chatbot.append(("重试请求", "请求失败，请检查API-key是否正确。"))
        return chatbot, context
    except openai.error.Timeout:
        chatbot.append(("重试请求", "请求超时，请检查网络连接。"))
        return chatbot, context
    except openai.error.APIConnectionError:
        chatbot.append(("重试请求", "连接失败，请检查网络连接。"))
        return chatbot, context
    except openai.error.RateLimitError:
        chatbot.append(("重试请求", "请求过于频繁，请5s后再试。"))
        return chatbot, context
    except:
        chatbot.append(("重试请求", "发生了未知错误Orz"))
        return chatbot, context
    
    context[-1] = {"role": "assistant", "content": message}

    chatbot[-1] = (context[-2]["content"], message_with_stats)
    return chatbot, context

def delete_last_conversation(chatbot, context):
    if len(context) == 0:
        return [], []
    chatbot = chatbot[:-1]
    context = context[:-2]
    return chatbot, context

def reduce_token(chatbot, system, context, myKey):
    context.append({"role": "user", "content": "请帮我总结一下上述对话的内容，实现减少tokens的同时，保证对话的质量。在总结中不要加入这一句话。"})

    response = get_response(system, context, myKey, raw=True)

    statistics = f'本次对话Tokens用量【{response["usage"]["completion_tokens"]+12+12+8} / 4096】'
    optmz_str = parse_text( f'好的，我们之前聊了:{response["choices"][0]["message"]["content"]}\n\n================\n\n{statistics}' )
    chatbot.append(("请帮我总结一下上述对话的内容，实现减少tokens的同时，保证对话的质量。", optmz_str))

    context = []
    context.append({"role": "user", "content": "我们之前聊了什么?"})
    context.append({"role": "assistant", "content": f'我们之前聊了：{response["choices"][0]["message"]["content"]}'})
    return chatbot, context

def save_chat_history(filepath, system, context):
    if filepath == "":
        return
    history = {"system": system, "context": context}
    with open(f"{filepath}.json", "w") as f:
        json.dump(history, f)

def load_chat_history(fileobj):
    with open(fileobj.name, "r") as f:
        history = json.load(f)
    context = history["context"]
    chathistory = []
    for i in range(0, len(context), 2):
        chathistory.append((parse_text(context[i]["content"]), parse_text(context[i+1]["content"])))
    return chathistory , history["system"], context, history["system"]["content"]

def get_history_names():
    with open("history.json", "r") as f:
        history = json.load(f)
    return list(history.keys())


def reset_state():
    return [], []

def update_system(new_system_prompt):
    return {"role": "system", "content": new_system_prompt}

def set_apikey(new_api_key, myKey):
    old_api_key = myKey
    
    try:
        get_response(update_system(initial_prompt), [{"role": "user", "content": "test"}], new_api_key)
    except openai.error.AuthenticationError:
        return "无效的api-key", myKey
    except openai.error.Timeout:
        return "请求超时，请检查网络设置", myKey
    except openai.error.APIConnectionError:
        return "网络错误", myKey
    except:
        return "发生了未知错误Orz", myKey
    
    encryption_str = "验证成功，api-key已做遮挡处理：" + new_api_key[:4] + "..." + new_api_key[-4:]
    return encryption_str, new_api_key


with gr.Blocks() as demo:
    keyTxt = gr.Textbox(show_label=True, placeholder=f"在这里输入你的OpenAI API-key...", value=initial_keytxt, label="API Key").style(container=True)
    chatbot = gr.Chatbot().style(color_map=("#1D51EE", "#585A5B"))
    context = gr.State([])
    systemPrompt = gr.State(update_system(initial_prompt))
    myKey = gr.State(my_api_key)
    topic = gr.State("未命名对话历史记录")

    with gr.Row():
        with gr.Column(scale=12):
            txt = gr.Textbox(show_label=False, placeholder="在这里输入").style(container=False)
        with gr.Column(min_width=50, scale=1):
            submitBtn = gr.Button("🚀", variant="primary")
    with gr.Row():
        emptyBtn = gr.Button("🧹 新的对话")
        retryBtn = gr.Button("🔄 重新生成")
        delLastBtn = gr.Button("🗑️ 删除上条对话")
        reduceTokenBtn = gr.Button("♻️ 优化Tokens")
    newSystemPrompt = gr.Textbox(show_label=True, placeholder=f"在这里输入新的System Prompt...", label="更改 System prompt").style(container=True)
    systemPromptDisplay = gr.Textbox(show_label=True, value=initial_prompt, interactive=False, label="目前的 System prompt").style(container=True)
    with gr.Accordion(label="保存/加载对话历史记录(在文本框中输入文件名，点击“保存对话”按钮，历史记录文件会被存储到本地)", open=False):
        with gr.Column():
            with gr.Row():
                with gr.Column(scale=6):
                    saveFileName = gr.Textbox(show_label=True, placeholder=f"在这里输入保存的文件名...", label="保存对话", value="对话历史记录").style(container=True)
                with gr.Column(scale=1):
                    saveBtn = gr.Button("💾 保存对话")
                    uploadBtn = gr.UploadButton("📂 读取对话", file_count="single", file_types=["json"])

    txt.submit(predict, [chatbot, txt, systemPrompt, context, myKey], [chatbot, context], show_progress=True)
    txt.submit(lambda :"", None, txt)
    submitBtn.click(predict, [chatbot, txt, systemPrompt, context, myKey], [chatbot, context], show_progress=True)
    submitBtn.click(lambda :"", None, txt)
    emptyBtn.click(reset_state, outputs=[chatbot, context])
    newSystemPrompt.submit(update_system, newSystemPrompt, systemPrompt)
    newSystemPrompt.submit(lambda x: x, newSystemPrompt, systemPromptDisplay)
    newSystemPrompt.submit(lambda :"", None, newSystemPrompt)
    retryBtn.click(retry, [chatbot, systemPrompt, context, myKey], [chatbot, context], show_progress=True)
    delLastBtn.click(delete_last_conversation, [chatbot, context], [chatbot, context], show_progress=True)
    reduceTokenBtn.click(reduce_token, [chatbot, systemPrompt, context, myKey], [chatbot, context], show_progress=True)
    keyTxt.submit(set_apikey, [keyTxt, myKey], [keyTxt, myKey], show_progress=True)
    uploadBtn.upload(load_chat_history, uploadBtn, [chatbot, systemPrompt, context, systemPromptDisplay], show_progress=True)
    saveBtn.click(save_chat_history, [saveFileName, systemPrompt, context], None, show_progress=True)


demo.launch()
