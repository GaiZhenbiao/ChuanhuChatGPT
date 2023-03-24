# -*- coding:utf-8 -*-
import os
import logging
import sys

import gradio as gr

from modules.utils import *
from modules.presets import *
from modules.overwrites import *
from modules.chat_func import *

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
)

my_api_key = ""  # 在这里输入你的 API 密钥

# if we are running in Docker
if os.environ.get("dockerrun") == "yes":
    dockerflag = True
else:
    dockerflag = False

authflag = False

if dockerflag:
    my_api_key = os.environ.get("my_api_key")
    if my_api_key == "empty":
        logging.error("Please give a api key!")
        sys.exit(1)
    # auth
    username = os.environ.get("USERNAME")
    password = os.environ.get("PASSWORD")
    if not (isinstance(username, type(None)) or isinstance(password, type(None))):
        authflag = True
else:
    if (
        not my_api_key
        and os.path.exists("api_key.txt")
        and os.path.getsize("api_key.txt")
    ):
        with open("api_key.txt", "r") as f:
            my_api_key = f.read().strip()
    if os.path.exists("auth.json"):
        with open("auth.json", "r", encoding='utf-8') as f:
            auth = json.load(f)
            username = auth["username"]
            password = auth["password"]
            if username != "" and password != "":
                authflag = True

gr.Chatbot.postprocess = postprocess
PromptHelper.compact_text_chunks = compact_text_chunks

with open("assets/custom.css", "r", encoding="utf-8") as f:
    customCSS = f.read()

with gr.Blocks(css=customCSS, theme=small_and_beautiful_theme) as demo:
    history = gr.State([])
    token_count = gr.State([])
    promptTemplates = gr.State(load_template(get_template_names(plain=True)[0], mode=2))
    user_api_key = gr.State(my_api_key)
    user_question = gr.State("")
    outputing = gr.State(False)
    topic = gr.State("未命名对话历史记录")

    with gr.Row():
        gr.HTML(title)
        status_display = gr.Markdown(get_geoip(), elem_id="status_display")

    with gr.Row(scale=1).style(equal_height=True):
        with gr.Column(scale=5):
            with gr.Row(scale=1):
                chatbot = gr.Chatbot(elem_id="chuanhu_chatbot").style(height="100%")
            with gr.Row(scale=1):
                with gr.Column(scale=12):
                    user_input = gr.Textbox(
                        show_label=False, placeholder="在这里输入"
                    ).style(container=False)
                with gr.Column(min_width=70, scale=1):
                    submitBtn = gr.Button("发送", variant="primary")
                    cancelBtn = gr.Button("取消", variant="secondary", visible=False)
            with gr.Row(scale=1):
                emptyBtn = gr.Button(
                    "🧹 新的对话",
                )
                retryBtn = gr.Button("🔄 重新生成")
                delLastBtn = gr.Button("🗑️ 删除一条对话")
                reduceTokenBtn = gr.Button("♻️ 总结对话")

        with gr.Column():
            with gr.Column(min_width=50, scale=1):
                with gr.Tab(label="ChatGPT"):
                    keyTxt = gr.Textbox(
                        show_label=True,
                        placeholder=f"OpenAI API-key...",
                        value=hide_middle_chars(my_api_key),
                        type="password",
                        visible=not HIDE_MY_KEY,
                        label="API-Key",
                    )
                    model_select_dropdown = gr.Dropdown(
                        label="选择模型", choices=MODELS, multiselect=False, value=MODELS[0]
                    )
                    use_streaming_checkbox = gr.Checkbox(
                        label="实时传输回答", value=True, visible=enable_streaming_option
                    )
                    use_websearch_checkbox = gr.Checkbox(label="使用在线搜索", value=False)
                    language_select_dropdown = gr.Dropdown(
                        label="选择回复语言（针对搜索&索引功能）",
                        choices=REPLY_LANGUAGES,
                        multiselect=False,
                        value=REPLY_LANGUAGES[0],
                    )
                    index_files = gr.Files(label="上传索引文件", type="file", multiple=True)

                with gr.Tab(label="Prompt"):
                    systemPromptTxt = gr.Textbox(
                        show_label=True,
                        placeholder=f"在这里输入System Prompt...",
                        label="System prompt",
                        value=initial_prompt,
                        lines=10,
                    ).style(container=False)
                    with gr.Accordion(label="加载Prompt模板", open=True):
                        with gr.Column():
                            with gr.Row():
                                with gr.Column(scale=6):
                                    templateFileSelectDropdown = gr.Dropdown(
                                        label="选择Prompt模板集合文件",
                                        choices=get_template_names(plain=True),
                                        multiselect=False,
                                        value=get_template_names(plain=True)[0],
                                    ).style(container=False)
                                with gr.Column(scale=1):
                                    templateRefreshBtn = gr.Button("🔄 刷新")
                            with gr.Row():
                                with gr.Column():
                                    templateSelectDropdown = gr.Dropdown(
                                        label="从Prompt模板中加载",
                                        choices=load_template(
                                            get_template_names(plain=True)[0], mode=1
                                        ),
                                        multiselect=False,
                                        value=load_template(
                                            get_template_names(plain=True)[0], mode=1
                                        )[0],
                                    ).style(container=False)

                with gr.Tab(label="保存/加载"):
                    with gr.Accordion(label="保存/加载对话历史记录", open=True):
                        with gr.Column():
                            with gr.Row():
                                with gr.Column(scale=6):
                                    historyFileSelectDropdown = gr.Dropdown(
                                        label="从列表中加载对话",
                                        choices=get_history_names(plain=True),
                                        multiselect=False,
                                        value=get_history_names(plain=True)[0],
                                    )
                                with gr.Column(scale=1):
                                    historyRefreshBtn = gr.Button("🔄 刷新")
                            with gr.Row():
                                with gr.Column(scale=6):
                                    saveFileName = gr.Textbox(
                                        show_label=True,
                                        placeholder=f"设置文件名: 默认为.json，可选为.md",
                                        label="设置保存文件名",
                                        value="对话历史记录",
                                    ).style(container=True)
                                with gr.Column(scale=1):
                                    saveHistoryBtn = gr.Button("💾 保存对话")
                                    exportMarkdownBtn = gr.Button("📝 导出为Markdown")
                                    gr.Markdown("默认保存于history文件夹")
                            with gr.Row():
                                with gr.Column():
                                    downloadFile = gr.File(interactive=True)

                with gr.Tab(label="高级"):
                    default_btn = gr.Button("🔙 恢复默认设置")
                    gr.Markdown("# ⚠️ 务必谨慎更改 ⚠️\n\n如果无法使用请恢复默认设置")

                    with gr.Accordion("参数", open=False):
                        top_p = gr.Slider(
                            minimum=-0,
                            maximum=1.0,
                            value=1.0,
                            step=0.05,
                            interactive=True,
                            label="Top-p",
                        )
                        temperature = gr.Slider(
                            minimum=-0,
                            maximum=2.0,
                            value=1.0,
                            step=0.1,
                            interactive=True,
                            label="Temperature",
                        )

                    apiurlTxt = gr.Textbox(
                        show_label=True,
                        placeholder=f"在这里输入API地址...",
                        label="API地址",
                        value="https://api.openai.com/v1/chat/completions",
                        lines=2,
                    )
                    changeAPIURLBtn = gr.Button("🔄 切换API地址")
                    proxyTxt = gr.Textbox(
                        show_label=True,
                        placeholder=f"在这里输入代理地址...",
                        label="代理地址（示例：http://127.0.0.1:10809）",
                        value="",
                        lines=2,
                    )
                    changeProxyBtn = gr.Button("🔄 设置代理地址")

    gr.Markdown(description)

    chatgpt_predict_args = dict(
        fn=predict,
        inputs=[
            user_api_key,
            systemPromptTxt,
            history,
            user_question,
            chatbot,
            token_count,
            top_p,
            temperature,
            use_streaming_checkbox,
            model_select_dropdown,
            use_websearch_checkbox,
            index_files,
            language_select_dropdown,
        ],
        outputs=[chatbot, history, status_display, token_count],
        show_progress=True,
    )

    start_outputing_args = dict(
        fn=start_outputing,
        inputs=[],
        outputs=[submitBtn, cancelBtn],
        show_progress=True,
    )

    end_outputing_args = dict(
        fn=end_outputing, inputs=[], outputs=[submitBtn, cancelBtn]
    )

    reset_textbox_args = dict(
        fn=reset_textbox, inputs=[], outputs=[user_input]
    )

    transfer_input_args = dict(
        fn=transfer_input, inputs=[user_input], outputs=[user_question, user_input, submitBtn, cancelBtn], show_progress=True
    )

    keyTxt.submit(submit_key, keyTxt, [user_api_key, status_display])
    keyTxt.change(submit_key, keyTxt, [user_api_key, status_display])
    # Chatbot
    cancelBtn.click(cancel_outputing, [], [])

    user_input.submit(**transfer_input_args).then(**chatgpt_predict_args).then(**end_outputing_args)

    submitBtn.click(**transfer_input_args).then(**chatgpt_predict_args).then(**end_outputing_args)

    emptyBtn.click(
        reset_state,
        outputs=[chatbot, history, token_count, status_display],
        show_progress=True,
    )
    emptyBtn.click(**reset_textbox_args)

    retryBtn.click(**start_outputing_args).then(
        retry,
        [
            user_api_key,
            systemPromptTxt,
            history,
            chatbot,
            token_count,
            top_p,
            temperature,
            use_streaming_checkbox,
            model_select_dropdown,
            language_select_dropdown,
        ],
        [chatbot, history, status_display, token_count],
        show_progress=True,
    ).then(**end_outputing_args)

    delLastBtn.click(
        delete_last_conversation,
        [chatbot, history, token_count],
        [chatbot, history, token_count, status_display],
        show_progress=True,
    )

    reduceTokenBtn.click(
        reduce_token_size,
        [
            user_api_key,
            systemPromptTxt,
            history,
            chatbot,
            token_count,
            top_p,
            temperature,
            gr.State(0),
            model_select_dropdown,
            language_select_dropdown,
        ],
        [chatbot, history, status_display, token_count],
        show_progress=True,
    )

    # Template
    templateRefreshBtn.click(get_template_names, None, [templateFileSelectDropdown])
    templateFileSelectDropdown.change(
        load_template,
        [templateFileSelectDropdown],
        [promptTemplates, templateSelectDropdown],
        show_progress=True,
    )
    templateSelectDropdown.change(
        get_template_content,
        [promptTemplates, templateSelectDropdown, systemPromptTxt],
        [systemPromptTxt],
        show_progress=True,
    )

    # S&L
    saveHistoryBtn.click(
        save_chat_history,
        [saveFileName, systemPromptTxt, history, chatbot],
        downloadFile,
        show_progress=True,
    )
    saveHistoryBtn.click(get_history_names, None, [historyFileSelectDropdown])
    exportMarkdownBtn.click(
        export_markdown,
        [saveFileName, systemPromptTxt, history, chatbot],
        downloadFile,
        show_progress=True,
    )
    historyRefreshBtn.click(get_history_names, None, [historyFileSelectDropdown])
    historyFileSelectDropdown.change(
        load_chat_history,
        [historyFileSelectDropdown, systemPromptTxt, history, chatbot],
        [saveFileName, systemPromptTxt, history, chatbot],
        show_progress=True,
    )
    downloadFile.change(
        load_chat_history,
        [downloadFile, systemPromptTxt, history, chatbot],
        [saveFileName, systemPromptTxt, history, chatbot],
    )

    # Advanced
    default_btn.click(
        reset_default, [], [apiurlTxt, proxyTxt, status_display], show_progress=True
    )
    changeAPIURLBtn.click(
        change_api_url,
        [apiurlTxt],
        [status_display],
        show_progress=True,
    )
    changeProxyBtn.click(
        change_proxy,
        [proxyTxt],
        [status_display],
        show_progress=True,
    )

logging.info(
    colorama.Back.GREEN
    + "\n川虎的温馨提示：访问 http://localhost:7860 查看界面"
    + colorama.Style.RESET_ALL
)
# 默认开启本地服务器，默认可以直接从IP访问，默认不创建公开分享链接
demo.title = "川虎ChatGPT 🚀"

if __name__ == "__main__":
    reload_javascript()
    # if running in Docker
    if dockerflag:
        if authflag:
            demo.queue(concurrency_count=CONCURRENT_COUNT).launch(
                server_name="0.0.0.0",
                server_port=7860,
                auth=(username, password),
                favicon_path="./assets/favicon.ico",
            )
        else:
            demo.queue(concurrency_count=CONCURRENT_COUNT).launch(
                server_name="0.0.0.0",
                server_port=7860,
                share=False,
                favicon_path="./assets/favicon.ico",
            )
    # if not running in Docker
    else:
        if authflag:
            demo.queue(concurrency_count=CONCURRENT_COUNT).launch(
                share=False,
                auth=(username, password),
                favicon_path="./assets/favicon.ico",
                inbrowser=True,
            )
        else:
            demo.queue(concurrency_count=CONCURRENT_COUNT).launch(
                share=False, favicon_path="./assets/favicon.ico", inbrowser=True
            )  # 改为 share=True 可以创建公开分享链接
        # demo.queue(concurrency_count=CONCURRENT_COUNT).launch(server_name="0.0.0.0", server_port=7860, share=False) # 可自定义端口
        # demo.queue(concurrency_count=CONCURRENT_COUNT).launch(server_name="0.0.0.0", server_port=7860,auth=("在这里填写用户名", "在这里填写密码")) # 可设置用户名与密码
        # demo.queue(concurrency_count=CONCURRENT_COUNT).launch(auth=("在这里填写用户名", "在这里填写密码")) # 适合Nginx反向代理
