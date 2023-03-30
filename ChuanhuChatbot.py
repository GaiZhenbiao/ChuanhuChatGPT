# -*- coding:utf-8 -*-
import os
import logging
import sys

import gradio as gr

from modules.utils import *
from modules.presets import *
from modules.overwrites import *
from modules.chat_func import *
from modules.openai_func import get_usage

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
)

# 在这里输入你的 API 密钥
my_api_key = ""
# 在这里输入你的 自定义API地址 
my_api_url = BASE_API_URL
# 在这里输入你的 自定义代理地址
my_proxy_url = ""

# 判断代码中是否修改my_api_url & 读取配置文件中的API地址
# 如果代码中修改过my_api_url，为了保证代码中填写值得优先级最高，不会再读取文件中的内容
if my_api_url == BASE_API_URL and os.path.exists(CONFIG_FILE_API_URL):
    with open(CONFIG_FILE_API_URL, mode="r", encoding="utf-8") as f:
        api_url_from_file = f.readline().strip()

    # 空值判断
    if api_url_from_file:
        my_api_url = api_url_from_file

# 判断my_api_url是否变化，变化则修改自定义API URL
if my_api_url != BASE_API_URL:
    change_api_url(my_api_url)

# 判断代码中是否修改my_proxy_url and 读取配置文件中的代理地址
# 如果代码中修改过my_proxy_url，为了保证代码中填写值得优先级最高，不会再读取文件中的内容
if (not my_proxy_url.strip()) and os.path.exists(CONFIG_FILE_PROXY_URL):
    with open(CONFIG_FILE_PROXY_URL, mode="r", encoding="utf-8") as f:
        proxy_url_from_file = f.readline().strip()
    
    # 空值判断
    if proxy_url_from_file:
        my_proxy_url = proxy_url_from_file

# 判断my_proxy_url是否填写，填写则修改自定义代理
if my_proxy_url.strip():
    change_proxy(my_proxy_url)

# if we are running in Docker
dockerflag = os.environ.get("dockerrun") == "yes"

authflag = False
auth_list = []

if dockerflag:
    my_api_key = os.environ.get("my_api_key")
    if my_api_key == "empty":
        logging.error("Please give a api key!")
        sys.exit(1)
    # auth
    username = os.environ.get("USERNAME")
    password = os.environ.get("PASSWORD")
    if not (isinstance(username, type(None)) or isinstance(password, type(None))):
        auth_list.append((os.environ.get("USERNAME"), os.environ.get("PASSWORD")))
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
        authflag = True
        with open("auth.json", "r", encoding='utf-8') as f:
            auth = json.load(f)
            for _ in auth:
                if auth[_]["username"] and auth[_]["password"]:
                    auth_list.append((auth[_]["username"], auth[_]["password"]))
                else:
                    logging.error("请检查auth.json文件中的用户名和密码！")
                    sys.exit(1)

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

    with gr.Row().style(equal_height=True):
        with gr.Column(scale=5):
            with gr.Row():
                chatbot = gr.Chatbot(elem_id="chuanhu_chatbot").style(height="100%")
            with gr.Row():
                with gr.Column(scale=12):
                    user_input = gr.Textbox(
                        show_label=False, placeholder="在这里输入"
                    ).style(container=False)
                with gr.Column(min_width=70, scale=1):
                    submitBtn = gr.Button("发送", variant="primary")
                    cancelBtn = gr.Button("取消", variant="secondary", visible=False)
            with gr.Row():
                emptyBtn = gr.Button(
                    "🧹 新的对话",
                )
                retryBtn = gr.Button("🔄 重新生成")
                delFirstBtn = gr.Button("🗑️ 删除最旧对话")
                delLastBtn = gr.Button("🗑️ 删除最新对话")
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
                    usageTxt = gr.Markdown("**发送消息** 或 **提交key** 以显示额度", elem_id="usage_display")
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
                    gr.Markdown("# ⚠️ 务必谨慎更改 ⚠️\n\n如果无法使用请恢复默认设置")
                    default_btn = gr.Button("🔙 恢复默认设置")

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

                    with gr.Accordion("网络设置", open=False):
                        apiurlTxt = gr.Textbox(
                            show_label=True,
                            placeholder=f"在这里输入API地址...",
                            label="API地址",
                            value=my_api_url,
                            lines=2,
                        )
                        changeAPIURLBtn = gr.Button("🔄 切换API地址")
                        proxyTxt = gr.Textbox(
                            show_label=True,
                            placeholder=f"在这里输入代理地址...",
                            label="代理地址（示例：http://127.0.0.1:10809）",
                            value=my_proxy_url,
                            lines=2,
                        )
                        changeProxyBtn = gr.Button("🔄 设置代理地址")

    gr.Markdown(description)
    gr.HTML(footer.format(versions=versions_html()), elem_id="footer")
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

    get_usage_args = dict(
        fn=get_usage, inputs=[user_api_key], outputs=[usageTxt], show_progress=False
    )


    # Chatbot
    cancelBtn.click(cancel_outputing, [], [])

    user_input.submit(**transfer_input_args).then(**chatgpt_predict_args).then(**end_outputing_args)
    user_input.submit(**get_usage_args)

    submitBtn.click(**transfer_input_args).then(**chatgpt_predict_args).then(**end_outputing_args)
    submitBtn.click(**get_usage_args)

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
    retryBtn.click(**get_usage_args)

    delFirstBtn.click(
        delete_first_conversation,
        [history, token_count],
        [history, token_count, status_display],
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
            gr.State(sum(token_count.value[-4:])),
            model_select_dropdown,
            language_select_dropdown,
        ],
        [chatbot, history, status_display, token_count],
        show_progress=True,
    )
    reduceTokenBtn.click(**get_usage_args)

    # ChatGPT
    keyTxt.change(submit_key, keyTxt, [user_api_key, status_display]).then(**get_usage_args)
    keyTxt.submit(**get_usage_args)

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
                auth=auth_list,
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
                auth=auth_list,
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
