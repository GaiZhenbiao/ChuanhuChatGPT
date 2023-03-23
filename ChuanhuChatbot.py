# -*- coding:utf-8 -*-
import os
import logging
import sys

import gradio as gr

from utils import *
from presets import *
from overwrites import *
from chat_func import *

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
        with open("auth.json", "r") as f:
            auth = json.load(f)
            username = auth["username"]
            password = auth["password"]
            if username != "" and password != "":
                authflag = True

gr.Chatbot.postprocess = postprocess
PromptHelper.compact_text_chunks = compact_text_chunks

with open("custom.css", "r", encoding="utf-8") as f:
    customCSS = f.read()

with gr.Blocks(
    css=customCSS,
    theme=gr.themes.Soft(
        primary_hue=gr.themes.Color(
            c50="#02C160",
            c100="rgba(2, 193, 96, 0.2)",
            c200="#02C160",
            c300="rgba(2, 193, 96, 0.32)",
            c400="rgba(2, 193, 96, 0.32)",
            c500="rgba(2, 193, 96, 1.0)",
            c600="rgba(2, 193, 96, 1.0)",
            c700="rgba(2, 193, 96, 0.32)",
            c800="rgba(2, 193, 96, 0.32)",
            c900="#02C160",
            c950="#02C160",
        ),
        secondary_hue=gr.themes.Color(
            c50="#576b95",
            c100="#576b95",
            c200="#576b95",
            c300="#576b95",
            c400="#576b95",
            c500="#576b95",
            c600="#576b95",
            c700="#576b95",
            c800="#576b95",
            c900="#576b95",
            c950="#576b95",
        ),
        neutral_hue=gr.themes.Color(
            name="gray",
            c50="#f9fafb",
            c100="#f3f4f6",
            c200="#e5e7eb",
            c300="#d1d5db",
            c400="#B2B2B2",
            c500="#808080",
            c600="#636363",
            c700="#515151",
            c800="#393939",
            c900="#272727",
            c950="#171717",
        ),
        radius_size=gr.themes.sizes.radius_sm,
    ).set(
        button_primary_background_fill="#06AE56",
        button_primary_background_fill_dark="#06AE56",
        button_primary_background_fill_hover="#07C863",
        button_primary_border_color="#06AE56",
        button_primary_border_color_dark="#06AE56",
        button_primary_text_color="#FFFFFF",
        button_primary_text_color_dark="#FFFFFF",
        button_secondary_background_fill="#F2F2F2",
        button_secondary_background_fill_dark="#2B2B2B",
        button_secondary_text_color="#393939",
        button_secondary_text_color_dark="#FFFFFF",
        # background_fill_primary="#F7F7F7",
        # background_fill_primary_dark="#1F1F1F",
        block_title_text_color="*primary_500",
        block_title_background_fill="*primary_100",
        input_background_fill="#F6F6F6",
    ),
) as demo:
    history = gr.State([])
    token_count = gr.State([])
    promptTemplates = gr.State(load_template(get_template_names(plain=True)[0], mode=2))
    user_api_key = gr.State(my_api_key)
    TRUECOMSTANT = gr.State(True)
    FALSECONSTANT = gr.State(False)
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

    keyTxt.submit(submit_key, keyTxt, [user_api_key, status_display])
    keyTxt.change(submit_key, keyTxt, [user_api_key, status_display])
    # Chatbot
    user_input.submit(
        predict,
        [
            user_api_key,
            systemPromptTxt,
            history,
            user_input,
            chatbot,
            token_count,
            top_p,
            temperature,
            use_streaming_checkbox,
            model_select_dropdown,
            use_websearch_checkbox,
            index_files,
        ],
        [chatbot, history, status_display, token_count],
        show_progress=True,
    )
    user_input.submit(reset_textbox, [], [user_input])

    # submitBtn.click(return_cancel_btn, [], [submitBtn, cancelBtn])
    submitBtn.click(
        predict,
        [
            user_api_key,
            systemPromptTxt,
            history,
            user_input,
            chatbot,
            token_count,
            top_p,
            temperature,
            use_streaming_checkbox,
            model_select_dropdown,
            use_websearch_checkbox,
            index_files,
        ],
        [chatbot, history, status_display, token_count],
        show_progress=True,
    )
    submitBtn.click(reset_textbox, [], [user_input])

    emptyBtn.click(
        reset_state,
        outputs=[chatbot, history, token_count, status_display],
        show_progress=True,
    )

    retryBtn.click(
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
        ],
        [chatbot, history, status_display, token_count],
        show_progress=True,
    )

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
                server_name="0.0.0.0", server_port=7860, auth=(username, password),
                favicon_path="./assets/favicon.png"
            )
        else:
            demo.queue(concurrency_count=CONCURRENT_COUNT).launch(server_name="0.0.0.0", server_port=7860, share=False, favicon_path="./assets/favicon.png")
    # if not running in Docker
    else:
        if authflag:
            demo.queue(concurrency_count=CONCURRENT_COUNT).launch(share=False, auth=(username, password), favicon_path="./assets/favicon.png", inbrowser=True)
        else:
            demo.queue(concurrency_count=CONCURRENT_COUNT).launch(share=False, favicon_path="./assets/favicon.ico", inbrowser=True)  # 改为 share=True 可以创建公开分享链接
        # demo.queue(concurrency_count=CONCURRENT_COUNT).launch(server_name="0.0.0.0", server_port=7860, share=False) # 可自定义端口
        # demo.queue(concurrency_count=CONCURRENT_COUNT).launch(server_name="0.0.0.0", server_port=7860,auth=("在这里填写用户名", "在这里填写密码")) # 可设置用户名与密码
        # demo.queue(concurrency_count=CONCURRENT_COUNT).launch(auth=("在这里填写用户名", "在这里填写密码")) # 适合Nginx反向代理
