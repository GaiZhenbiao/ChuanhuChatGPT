# -*- coding:utf-8 -*-
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
)

import colorama
import gradio as gr

from modules import config
from modules.config import *
from modules.utils import *
from modules.presets import *
from modules.overwrites import *
from modules.webui import *
from modules.repo import *
from modules.train_func import *
from modules.models.models import get_model

logging.getLogger("httpx").setLevel(logging.WARNING)

gr.Chatbot._postprocess_chat_messages = postprocess_chat_messages
gr.Chatbot.postprocess = postprocess

# with open("web_assets/css/ChuanhuChat.css", "r", encoding="utf-8") as f:
#     ChuanhuChatCSS = f.read()

def create_new_model():
    return get_model(model_name = MODELS[DEFAULT_MODEL], access_key = my_api_key)[0]

with gr.Blocks(theme=small_and_beautiful_theme) as demo:
    user_name = gr.State("")
    promptTemplates = gr.State(load_template(get_template_names()[0], mode=2))
    user_question = gr.State("")
    assert type(my_api_key)==str
    user_api_key = gr.State(my_api_key)
    current_model = gr.State(create_new_model)

    topic = gr.State(i18n("未命名对话历史记录"))

    with gr.Row():
        gr.HTML(CHUANHU_TITLE, elem_id="app-title")
        status_display = gr.Markdown(get_geoip(), elem_id="status-display")
    with gr.Row(elem_id="float-display"):
        user_info = gr.Markdown(value="getting user info...", elem_id="user-info")
        config_info = gr.HTML(get_html("config_info.html").format(), visible=False, elem_id="config-info")
        update_info = gr.HTML(get_html("update.html").format(
            current_version=repo_tag_html(),
            version_time=version_time(),
            cancel_btn=i18n("取消"),
            update_btn=i18n("更新"),
            seenew_btn=i18n("详情"),
            ok_btn=i18n("好"),
            ), visible=check_update)

    with gr.Row(equal_height=True):
        with gr.Column(scale=5):
            with gr.Row():
                chatbot = gr.Chatbot(label="Chuanhu Chat", elem_id="chuanhu-chatbot", latex_delimiters=latex_delimiters_set, height=700, avatar_images=[config.user_avatar, config.bot_avatar])
            with gr.Row():
                with gr.Column(min_width=225, scale=12):
                    user_input = gr.Textbox(
                        elem_id="user-input-tb",
                        show_label=False, placeholder=i18n("在这里输入"),
                        container=False
                    )
                with gr.Column(min_width=42, scale=1):
                    submitBtn = gr.Button(value="", variant="primary", elem_id="submit-btn")
                    cancelBtn = gr.Button(value="", variant="secondary", visible=False, elem_id="cancel-btn")
            with gr.Row(elem_id="chatbot-buttons"):
                with gr.Column(min_width=120, scale=1):
                    emptyBtn = gr.Button(
                        i18n("🧹 新的对话"), elem_id="empty-btn"
                    )
                with gr.Column(min_width=120, scale=1):
                    retryBtn = gr.Button(i18n("🔄 重新生成"))
                with gr.Column(min_width=120, scale=1):
                    delFirstBtn = gr.Button(i18n("🗑️ 删除最旧对话"))
                with gr.Column(min_width=120, scale=1):
                    delLastBtn = gr.Button(i18n("🗑️ 删除最新对话"))
                with gr.Row(visible=False) as like_dislike_area:
                    with gr.Column(min_width=20, scale=1):
                        likeBtn = gr.Button(i18n("👍"))
                    with gr.Column(min_width=20, scale=1):
                        dislikeBtn = gr.Button(i18n("👎"))

        with gr.Column():
            with gr.Column(min_width=50, scale=1):
                with gr.Tab(label=i18n("模型")):
                    keyTxt = gr.Textbox(
                        show_label=True,
                        placeholder=f"Your API-key...",
                        value=hide_middle_chars(user_api_key.value),
                        type="password",
                        visible=not HIDE_MY_KEY,
                        label="API-Key",
                    )
                    if multi_api_key:
                        usageTxt = gr.Markdown(i18n("多账号模式已开启，无需输入key，可直接开始对话"), elem_id="usage-display", elem_classes="insert-block", visible=show_api_billing)
                    else:
                        usageTxt = gr.Markdown(i18n("**发送消息** 或 **提交key** 以显示额度"), elem_id="usage-display", elem_classes="insert-block", visible=show_api_billing)
                    model_select_dropdown = gr.Dropdown(
                        label=i18n("选择模型"), choices=MODELS, multiselect=False, value=MODELS[DEFAULT_MODEL], interactive=True
                    )
                    lora_select_dropdown = gr.Dropdown(
                        label=i18n("选择LoRA模型"), choices=[], multiselect=False, interactive=True, visible=False
                    )
                    with gr.Row():
                        single_turn_checkbox = gr.Checkbox(label=i18n("单轮对话"), value=False, elem_classes="switch-checkbox")
                        use_websearch_checkbox = gr.Checkbox(label=i18n("使用在线搜索"), value=False, elem_classes="switch-checkbox")
                    language_select_dropdown = gr.Dropdown(
                        label=i18n("选择回复语言（针对搜索&索引功能）"),
                        choices=REPLY_LANGUAGES,
                        multiselect=False,
                        value=REPLY_LANGUAGES[0],
                    )
                    index_files = gr.Files(label=i18n("上传"), type="file", elem_id="upload-index-file")
                    two_column = gr.Checkbox(label=i18n("双栏pdf"), value=advance_docs["pdf"].get("two_column", False))
                    summarize_btn = gr.Button(i18n("总结"))
                    # TODO: 公式ocr
                    # formula_ocr = gr.Checkbox(label=i18n("识别公式"), value=advance_docs["pdf"].get("formula_ocr", False))

                with gr.Tab(label="Prompt"):
                    systemPromptTxt = gr.Textbox(
                        show_label=True,
                        placeholder=i18n("在这里输入System Prompt..."),
                        label="System prompt",
                        value=INITIAL_SYSTEM_PROMPT,
                        lines=10
                    )
                    with gr.Accordion(label=i18n("加载Prompt模板"), open=True):
                        with gr.Column():
                            with gr.Row():
                                with gr.Column(scale=6):
                                    templateFileSelectDropdown = gr.Dropdown(
                                        label=i18n("选择Prompt模板集合文件"),
                                        choices=get_template_names(),
                                        multiselect=False,
                                        value=get_template_names()[0],
                                        container=False,
                                    )
                                with gr.Column(scale=1):
                                    templateRefreshBtn = gr.Button(i18n("🔄 刷新"))
                            with gr.Row():
                                with gr.Column():
                                    templateSelectDropdown = gr.Dropdown(
                                        label=i18n("从Prompt模板中加载"),
                                        choices=load_template(
                                            get_template_names()[0], mode=1
                                        ),
                                        multiselect=False,
                                        container=False,
                                    )

                with gr.Tab(label=i18n("保存/加载")):
                    with gr.Accordion(label=i18n("保存/加载对话历史记录"), open=True):
                        with gr.Column():
                            with gr.Row():
                                with gr.Column(scale=6):
                                    historyFileSelectDropdown = gr.Dropdown(
                                        label=i18n("从列表中加载对话"),
                                        choices=get_history_names(),
                                        multiselect=False,
                                        container=False,
                                    )
                                with gr.Row():
                                    with gr.Column(min_width=42, scale=1):
                                        historyRefreshBtn = gr.Button(i18n("🔄 刷新"))
                                    with gr.Column(min_width=42, scale=1):
                                        historyDeleteBtn = gr.Button(i18n("🗑️ 删除"))
                            with gr.Row():
                                with gr.Column(scale=6):
                                    saveFileName = gr.Textbox(
                                        show_label=True,
                                        placeholder=i18n("设置文件名: 默认为.json，可选为.md"),
                                        label=i18n("设置保存文件名"),
                                        value=i18n("对话历史记录"),
                                        elem_classes="no-container"
                                        # container=False,
                                    )
                                with gr.Column(scale=1):
                                    saveHistoryBtn = gr.Button(i18n("💾 保存对话"))
                                    exportMarkdownBtn = gr.Button(i18n("📝 导出为Markdown"))
                                    gr.Markdown(i18n("默认保存于history文件夹"))
                            with gr.Row():
                                with gr.Column():
                                    downloadFile = gr.File(interactive=True, label="下载/上传历史记录")

                with gr.Tab(label=i18n("微调")):
                    openai_train_status = gr.Markdown(label=i18n("训练状态"), value=i18n("在这里[查看使用介绍](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B#%E5%BE%AE%E8%B0%83-gpt-35)"))

                    with gr.Tab(label=i18n("准备数据集")):
                        dataset_preview_json = gr.JSON(label=i18n("数据集预览"), readonly=True)
                        dataset_selection = gr.Files(label = i18n("选择数据集"), file_types=[".xlsx", ".jsonl"], file_count="single")
                        upload_to_openai_btn = gr.Button(i18n("上传到OpenAI"), variant="primary", interactive=False)

                    with gr.Tab(label=i18n("训练")):
                        openai_ft_file_id = gr.Textbox(label=i18n("文件ID"), value="", lines=1, placeholder=i18n("上传到 OpenAI 后自动填充"))
                        openai_ft_suffix = gr.Textbox(label=i18n("模型名称后缀"), value="", lines=1, placeholder=i18n("可选，用于区分不同的模型"))
                        openai_train_epoch_slider = gr.Slider(label=i18n("训练轮数（Epochs）"), minimum=1, maximum=100, value=3, step=1, interactive=True)
                        openai_start_train_btn = gr.Button(i18n("开始训练"), variant="primary", interactive=False)

                    with gr.Tab(label=i18n("状态")):
                        openai_status_refresh_btn = gr.Button(i18n("刷新状态"))
                        openai_cancel_all_jobs_btn = gr.Button(i18n("取消所有任务"))
                        add_to_models_btn = gr.Button(i18n("添加训练好的模型到模型列表"), interactive=False)

                with gr.Tab(label=i18n("高级")):
                    gr.HTML(get_html("appearance_switcher.html").format(label=i18n("切换亮暗色主题")), elem_classes="insert-block")
                    use_streaming_checkbox = gr.Checkbox(
                            label=i18n("实时传输回答"), value=True, visible=ENABLE_STREAMING_OPTION, elem_classes="switch-checkbox"
                        )
                    checkUpdateBtn = gr.Button(i18n("🔄 检查更新..."), visible=check_update)
                    gr.Markdown(i18n("# ⚠️ 务必谨慎更改 ⚠️"), elem_id="advanced-warning")
                    with gr.Accordion(i18n("参数"), open=False):
                        temperature_slider = gr.Slider(
                            minimum=-0,
                            maximum=2.0,
                            value=1.0,
                            step=0.1,
                            interactive=True,
                            label="temperature",
                        )
                        top_p_slider = gr.Slider(
                            minimum=-0,
                            maximum=1.0,
                            value=1.0,
                            step=0.05,
                            interactive=True,
                            label="top-p",
                        )
                        n_choices_slider = gr.Slider(
                            minimum=1,
                            maximum=10,
                            value=1,
                            step=1,
                            interactive=True,
                            label="n choices",
                        )
                        stop_sequence_txt = gr.Textbox(
                            show_label=True,
                            placeholder=i18n("停止符，用英文逗号隔开..."),
                            label="stop",
                            value="",
                            lines=1,
                        )
                        max_context_length_slider = gr.Slider(
                            minimum=1,
                            maximum=32768,
                            value=2000,
                            step=1,
                            interactive=True,
                            label="max context",
                        )
                        max_generation_slider = gr.Slider(
                            minimum=1,
                            maximum=32768,
                            value=1000,
                            step=1,
                            interactive=True,
                            label="max generations",
                        )
                        presence_penalty_slider = gr.Slider(
                            minimum=-2.0,
                            maximum=2.0,
                            value=0.0,
                            step=0.01,
                            interactive=True,
                            label="presence penalty",
                        )
                        frequency_penalty_slider = gr.Slider(
                            minimum=-2.0,
                            maximum=2.0,
                            value=0.0,
                            step=0.01,
                            interactive=True,
                            label="frequency penalty",
                        )
                        logit_bias_txt = gr.Textbox(
                            show_label=True,
                            placeholder=f"word:likelihood",
                            label="logit bias",
                            value="",
                            lines=1,
                        )
                        user_identifier_txt = gr.Textbox(
                            show_label=True,
                            placeholder=i18n("用于定位滥用行为"),
                            label=i18n("用户名"),
                            value=user_name.value,
                            lines=1,
                        )

                    with gr.Accordion(i18n("网络参数"), open=False):
                        gr.Markdown(i18n("---\n⚠️ 为保证API-Key安全，请在配置文件`config.json`中修改网络设置"), elem_id="netsetting-warning")
                        default_btn = gr.Button(i18n("🔙 恢复默认网络设置"))
                        # 网络代理
                        proxyTxt = gr.Textbox(
                            show_label=True,
                            placeholder=i18n("未设置代理..."),
                            label=i18n("代理地址"),
                            value=config.http_proxy,
                            lines=1,
                            interactive=False,
                            # container=False,
                            elem_classes="view-only-textbox no-container",
                        )
                        # changeProxyBtn = gr.Button(i18n("🔄 设置代理地址"))

                        # 优先展示自定义的api_host
                        apihostTxt = gr.Textbox(
                            show_label=True,
                            placeholder="api.openai.com",
                            label="OpenAI API-Host",
                            value=config.api_host or shared.API_HOST,
                            lines=1,
                            interactive=False,
                            # container=False,
                            elem_classes="view-only-textbox no-container",
                        )
                        # changeAPIURLBtn = gr.Button(i18n("🔄 切换API地址"))
                        updateChuanhuBtn = gr.Button(visible=False, elem_classes="invisible-btn", elem_id="update-chuanhu-btn")


    gr.Markdown(CHUANHU_DESCRIPTION, elem_id="description")
    gr.HTML(get_html("footer.html").format(versions=versions_html()), elem_id="footer")

    # https://github.com/gradio-app/gradio/pull/3296
    def create_greeting(request: gr.Request):
        if hasattr(request, "username") and request.username: # is not None or is not ""
            logging.info(f"Get User Name: {request.username}")
            user_info, user_name = gr.Markdown.update(value=f"User: {request.username}"), request.username
        else:
            user_info, user_name = gr.Markdown.update(value=f"", visible=False), ""
        current_model = get_model(model_name = MODELS[DEFAULT_MODEL], access_key = my_api_key)[0]
        current_model.set_user_identifier(user_name)
        chatbot = gr.Chatbot.update(label=MODELS[DEFAULT_MODEL])
        return user_info, user_name, current_model, toggle_like_btn_visibility(DEFAULT_MODEL), *current_model.auto_load(), get_history_dropdown(user_name), chatbot
    demo.load(create_greeting, inputs=None, outputs=[user_info, user_name, current_model, like_dislike_area, systemPromptTxt, chatbot, historyFileSelectDropdown, chatbot], api_name="load")
    chatgpt_predict_args = dict(
        fn=predict,
        inputs=[
            current_model,
            user_question,
            chatbot,
            use_streaming_checkbox,
            use_websearch_checkbox,
            index_files,
            language_select_dropdown,
        ],
        outputs=[chatbot, status_display],
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
        fn=billing_info, inputs=[current_model], outputs=[usageTxt], show_progress=False
    )

    load_history_from_file_args = dict(
        fn=load_chat_history,
        inputs=[current_model, historyFileSelectDropdown, user_name],
        outputs=[saveFileName, systemPromptTxt, chatbot]
    )

    refresh_history_args = dict(
        fn=get_history_dropdown, inputs=[user_name], outputs=[historyFileSelectDropdown]
    )


    # Chatbot
    cancelBtn.click(interrupt, [current_model], [])

    user_input.submit(**transfer_input_args).then(**chatgpt_predict_args).then(**end_outputing_args)
    user_input.submit(**get_usage_args)

    submitBtn.click(**transfer_input_args).then(**chatgpt_predict_args, api_name="predict").then(**end_outputing_args)
    submitBtn.click(**get_usage_args)

    index_files.change(handle_file_upload, [current_model, index_files, chatbot, language_select_dropdown], [index_files, chatbot, status_display])
    summarize_btn.click(handle_summarize_index, [current_model, index_files, chatbot, language_select_dropdown], [chatbot, status_display])

    emptyBtn.click(
        reset,
        inputs=[current_model],
        outputs=[chatbot, status_display],
        show_progress=True,
        _js='clearChatbot',
    )

    retryBtn.click(**start_outputing_args).then(
        retry,
        [
            current_model,
            chatbot,
            use_streaming_checkbox,
            use_websearch_checkbox,
            index_files,
            language_select_dropdown,
        ],
        [chatbot, status_display],
        show_progress=True,
    ).then(**end_outputing_args)
    retryBtn.click(**get_usage_args)

    delFirstBtn.click(
        delete_first_conversation,
        [current_model],
        [status_display],
    )

    delLastBtn.click(
        delete_last_conversation,
        [current_model, chatbot],
        [chatbot, status_display],
        show_progress=False
    )

    likeBtn.click(
        like,
        [current_model],
        [status_display],
        show_progress=False
    )

    dislikeBtn.click(
        dislike,
        [current_model],
        [status_display],
        show_progress=False
    )

    two_column.change(update_doc_config, [two_column], None)

    # LLM Models
    keyTxt.change(set_key, [current_model, keyTxt], [user_api_key, status_display], api_name="set_key").then(**get_usage_args)
    keyTxt.submit(**get_usage_args)
    single_turn_checkbox.change(set_single_turn, [current_model, single_turn_checkbox], None)
    model_select_dropdown.change(get_model, [model_select_dropdown, lora_select_dropdown, user_api_key, temperature_slider, top_p_slider, systemPromptTxt, user_name], [current_model, status_display, chatbot, lora_select_dropdown, user_api_key, keyTxt], show_progress=True, api_name="get_model")
    model_select_dropdown.change(toggle_like_btn_visibility, [model_select_dropdown], [like_dislike_area], show_progress=False)
    lora_select_dropdown.change(get_model, [model_select_dropdown, lora_select_dropdown, user_api_key, temperature_slider, top_p_slider, systemPromptTxt, user_name], [current_model, status_display, chatbot], show_progress=True)

    # Template
    systemPromptTxt.change(set_system_prompt, [current_model, systemPromptTxt], None)
    templateRefreshBtn.click(get_template_dropdown, None, [templateFileSelectDropdown])
    templateFileSelectDropdown.input(
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
        [current_model, saveFileName, chatbot, user_name],
        downloadFile,
        show_progress=True,
    )
    saveHistoryBtn.click(get_history_dropdown, [user_name], [historyFileSelectDropdown])
    exportMarkdownBtn.click(
        export_markdown,
        [current_model, saveFileName, chatbot, user_name],
        downloadFile,
        show_progress=True,
    )
    historyRefreshBtn.click(**refresh_history_args)
    historyDeleteBtn.click(delete_chat_history, [current_model, historyFileSelectDropdown, user_name], [status_display, historyFileSelectDropdown, chatbot], _js='(a,b,c)=>{return showConfirmationDialog(a, b, c);}')
    historyFileSelectDropdown.change(**load_history_from_file_args)
    downloadFile.change(upload_chat_history, [current_model, downloadFile, user_name], [saveFileName, systemPromptTxt, chatbot])

    # Train
    dataset_selection.upload(handle_dataset_selection, dataset_selection, [dataset_preview_json, upload_to_openai_btn, openai_train_status])
    dataset_selection.clear(handle_dataset_clear, [], [dataset_preview_json, upload_to_openai_btn])
    upload_to_openai_btn.click(upload_to_openai, [dataset_selection], [openai_ft_file_id, openai_train_status], show_progress=True)

    openai_ft_file_id.change(lambda x: gr.update(interactive=True) if len(x) > 0 else gr.update(interactive=False), [openai_ft_file_id], [openai_start_train_btn])
    openai_start_train_btn.click(start_training, [openai_ft_file_id, openai_ft_suffix, openai_train_epoch_slider], [openai_train_status])

    openai_status_refresh_btn.click(get_training_status, [], [openai_train_status, add_to_models_btn])
    add_to_models_btn.click(add_to_models, [], [model_select_dropdown, openai_train_status], show_progress=True)
    openai_cancel_all_jobs_btn.click(cancel_all_jobs, [], [openai_train_status], show_progress=True)

    # Advanced
    max_context_length_slider.change(set_token_upper_limit, [current_model, max_context_length_slider], None)
    temperature_slider.change(set_temperature, [current_model, temperature_slider], None)
    top_p_slider.change(set_top_p, [current_model, top_p_slider], None)
    n_choices_slider.change(set_n_choices, [current_model, n_choices_slider], None)
    stop_sequence_txt.change(set_stop_sequence, [current_model, stop_sequence_txt], None)
    max_generation_slider.change(set_max_tokens, [current_model, max_generation_slider], None)
    presence_penalty_slider.change(set_presence_penalty, [current_model, presence_penalty_slider], None)
    frequency_penalty_slider.change(set_frequency_penalty, [current_model, frequency_penalty_slider], None)
    logit_bias_txt.change(set_logit_bias, [current_model, logit_bias_txt], None)
    user_identifier_txt.change(set_user_identifier, [current_model, user_identifier_txt], None)

    default_btn.click(
        reset_default, [], [apihostTxt, proxyTxt, status_display], show_progress=True
    )
    # changeAPIURLBtn.click(
    #     change_api_host,
    #     [apihostTxt],
    #     [status_display],
    #     show_progress=True,
    # )
    # changeProxyBtn.click(
    #     change_proxy,
    #     [proxyTxt],
    #     [status_display],
    #     show_progress=True,
    # )
    checkUpdateBtn.click(fn=None, _js='manualCheckUpdate')

    # Invisible elements
    updateChuanhuBtn.click(
        update_chuanhu,
        [],
        [status_display],
        show_progress=True,
    )

logging.info(
    colorama.Back.GREEN
    + "\n川虎的温馨提示：访问 http://localhost:7860 查看界面"
    + colorama.Style.RESET_ALL
)
# 默认开启本地服务器，默认可以直接从IP访问，默认不创建公开分享链接
demo.title = i18n("川虎Chat 🚀")

if __name__ == "__main__":
    reload_javascript()
    demo.queue(concurrency_count=CONCURRENT_COUNT).launch(
        blocked_paths=["config.json"],
        server_name=server_name,
        server_port=server_port,
        share=share,
        auth=auth_from_conf if authflag else None,
        favicon_path="./web_assets/favicon.ico",
        inbrowser=not dockerflag, # 禁止在docker下开启inbrowser
    )
