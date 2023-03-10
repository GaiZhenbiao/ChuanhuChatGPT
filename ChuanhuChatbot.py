import gradio as gr
# import openai
import os
import sys
from utils import *

my_api_key = ""    # 在这里输入你的 API 密钥
HIDE_MY_KEY = False # 如果你想在UI中隐藏你的 API 密钥，将此值设置为 True

gr.Chatbot.postprocess = postprocess

#if we are running in Docker
if os.environ.get('dockerrun') == 'yes':
    dockerflag = True
else:
    dockerflag = False

if dockerflag:
    my_api_key = os.environ.get('my_api_key')
    if my_api_key == "empty":
        print("Please give a api key!")
        sys.exit(1)
    #auth
    username = os.environ.get('USERNAME')
    password = os.environ.get('PASSWORD')
    if isinstance(username, type(None)) or isinstance(password, type(None)):
        authflag = False
    else:
        authflag = True
else:
    if os.path.exists("api_key.txt"):
        with open("api_key.txt", "r") as f:
            my_api_key = f.read()
    if os.path.exists("auth.json"):
        with open("auth.json", "r") as f:
            auth = json.load(f)
            username = auth["username"]
            password = auth["password"]
            authflag = True

title = """<h1 align="center">川虎ChatGPT 🚀</h1>"""
description = """<div align=center>

由Bilibili [土川虎虎虎](https://space.bilibili.com/29125536) 和 [明昭MZhao](https://space.bilibili.com/24807452)开发

访问川虎ChatGPT的 [GitHub项目](https://github.com/GaiZhenbiao/ChuanhuChatGPT) 下载最新版脚本

此App使用 `gpt-3.5-turbo` 大语言模型
</div>
"""
customCSS = """
code {
    display: inline;
    white-space: break-spaces;
    border-radius: 6px;
    margin: 0 2px 0 2px;
    padding: .2em .4em .1em .4em;
    background-color: rgba(175,184,193,0.2);
}
pre {
    display: block;
    white-space: pre;
    background-color: hsla(0, 0%, 0%, 72%);
    border: solid 5px var(--color-border-primary) !important;
    border-radius: 8px;
    padding: 0 1.2rem 1.2rem;
    margin-top: 1em !important;
    color: #FFF;
    box-shadow: inset 0px 8px 16px hsla(0, 0%, 0%, .2)
}
pre code, pre code code {
    background-color: transparent !important;
    margin: 0;
    padding: 0;
}
"""

with gr.Blocks(css=customCSS) as demo:
    gr.HTML(title)
    keyTxt = gr.Textbox(show_label=True, placeholder=f"在这里输入你的OpenAI API-key...",
                        value=my_api_key, label="API Key", type="password", visible=not HIDE_MY_KEY).style(container=True)
    chatbot = gr.Chatbot()  # .style(color_map=("#1D51EE", "#585A5B"))
    history = gr.State([])
    promptTemplates = gr.State(load_template(get_template_names(plain=True)[0], mode=2))
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
    statusDisplay = gr.Markdown("status: ready")
    systemPromptTxt = gr.Textbox(show_label=True, placeholder=f"在这里输入System Prompt...",
                                 label="System prompt", value=initial_prompt).style(container=True)
    with gr.Accordion(label="加载Prompt模板", open=False):
        with gr.Column():
            with gr.Row():
                with gr.Column(scale=6):
                    templateFileSelectDropdown = gr.Dropdown(label="选择Prompt模板集合文件（.csv）", choices=get_template_names(plain=True), multiselect=False)
                with gr.Column(scale=1):
                    templateRefreshBtn = gr.Button("🔄 刷新")
                    templaeFileReadBtn = gr.Button("📂 读入模板")
            with gr.Row():
                with gr.Column(scale=6):
                    templateSelectDropdown = gr.Dropdown(label="从Prompt模板中加载", choices=load_template(get_template_names(plain=True)[0], mode=1), multiselect=False)
                with gr.Column(scale=1):
                    templateApplyBtn = gr.Button("⬇️ 应用")
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
                    historyFileSelectDropdown = gr.Dropdown(label="从列表中加载对话", choices=get_history_names(plain=True), multiselect=False)
                with gr.Column(scale=1):
                    historyRefreshBtn = gr.Button("🔄 刷新")
                    historyReadBtn = gr.Button("📂 读入对话")
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
               chatbot, history, systemPromptTxt], [chatbot, history, statusDisplay])
    txt.submit(reset_textbox, [], [txt])
    submitBtn.click(predict, [txt, top_p, temperature, keyTxt, chatbot,
                    history, systemPromptTxt], [chatbot, history, statusDisplay], show_progress=True)
    submitBtn.click(reset_textbox, [], [txt])
    emptyBtn.click(reset_state, outputs=[chatbot, history])
    retryBtn.click(predict, [txt, top_p, temperature, keyTxt, chatbot, history,
                   systemPromptTxt, TRUECOMSTANT], [chatbot, history, statusDisplay], show_progress=True)
    delLastBtn.click(delete_last_conversation, [chatbot, history], [
                     chatbot, history], show_progress=True)
    reduceTokenBtn.click(predict, [txt, top_p, temperature, keyTxt, chatbot, history,
                         systemPromptTxt, FALSECONSTANT, TRUECOMSTANT], [chatbot, history, statusDisplay], show_progress=True)
    saveBtn.click(save_chat_history, [
                  saveFileName, systemPromptTxt, history, chatbot], None, show_progress=True)
    saveBtn.click(get_history_names, None, [historyFileSelectDropdown])
    historyRefreshBtn.click(get_history_names, None, [historyFileSelectDropdown])
    historyReadBtn.click(load_chat_history, [historyFileSelectDropdown],  [saveFileName, systemPromptTxt, history, chatbot], show_progress=True)
    templateRefreshBtn.click(get_template_names, None, [templateFileSelectDropdown])
    templaeFileReadBtn.click(load_template, [templateFileSelectDropdown],  [promptTemplates, templateSelectDropdown], show_progress=True)
    templateApplyBtn.click(lambda x, y: x[y], [promptTemplates, templateSelectDropdown],  [systemPromptTxt], show_progress=True)

print("川虎的温馨提示：访问 http://localhost:7860 查看界面")
# 默认开启本地服务器，默认可以直接从IP访问，默认不创建公开分享链接
demo.title = "川虎ChatGPT 🚀"

#if running in Docker
if dockerflag:
    if authflag:
        demo.queue().launch(server_name="0.0.0.0", server_port=7860,auth=(username, password))
    else:
        demo.queue().launch(server_name="0.0.0.0", server_port=7860, share=False)
#if not running in Docker
else:
    if authflag:
        demo.queue().launch(share=False, auth=(username, password))
    else:
        demo.queue().launch(share=False) # 改为 share=True 可以创建公开分享链接
    #demo.queue().launch(server_name="0.0.0.0", server_port=7860, share=False) # 可自定义端口
    #demo.queue().launch(server_name="0.0.0.0", server_port=7860,auth=("在这里填写用户名", "在这里填写密码")) # 可设置用户名与密码
    #demo.queue().launch(auth=("在这里填写用户名", "在这里填写密码")) # 适合Nginx反向代理
