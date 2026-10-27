# -*- coding:utf-8 -*-
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
)

from modules.models.models import get_model, change_model
from modules.history_selection import load_history_model
from modules.agent.ui import AgentPanel
from modules.model_capabilities import CapabilityUI
from modules.train_func import *
from modules.repo import *
from modules.webui import *
from modules.overwrites import patch_gradio
from modules.presets import *
from modules.utils import *
from modules.config import *
from modules import config
import gradio as gr
import colorama

logging.getLogger("httpx").setLevel(logging.WARNING)

patch_gradio()

# with open("web_assets/css/ChuanhuChat.css", "r", encoding="utf-8") as f:
#     ChuanhuChatCSS = f.read()


def create_new_model():
    return get_model(model_name=MODELS[DEFAULT_MODEL], access_key=my_api_key)[0]


with gr.Blocks(theme=small_and_beautiful_theme) as demo:
    user_name = gr.Textbox("", visible=False)
    promptTemplates = gr.State(load_template(get_template_names()[0], mode=2))
    user_question = gr.State("")
    assert type(my_api_key) == str
    user_api_key = gr.State(my_api_key)
    current_model = gr.State()

    topic = gr.State(i18n("ui.history.unnamed"))

    with gr.Row(elem_id="chuanhu-header"):
        gr.HTML(get_html("header_title.html").format(
            app_title=CHUANHU_TITLE), elem_id="app-title")
        status_display = gr.Markdown(get_geoip, elem_id="status-display")
    with gr.Row(elem_id="float-display"):
        user_info = gr.Markdown(
            value="getting user info...", elem_id="user-info")
        update_info = gr.HTML(get_html("update.html").format(
            current_version=repo_tag_html(),
            version_time=version_time(),
            cancel_btn=i18n("ui.common.cancel"),
            update_btn=i18n("ui.common.update"),
            seenew_btn=i18n("ui.common.details"),
            ok_btn=i18n("ui.common.ok"),
            close_btn=i18n("ui.common.close"),
            reboot_btn=i18n("ui.common.restart_now"),
        ), visible=check_update)

    with gr.Row(equal_height=True, elem_id="chuanhu-body"):

        with gr.Column(elem_id="menu-area"):
            with gr.Column(elem_id="chuanhu-history"):
                with gr.Group():
                    with gr.Row(elem_id="chuanhu-history-header"):
                        with gr.Row(elem_id="chuanhu-history-search-row"):
                            with gr.Column(min_width=150, scale=2):
                                historySearchTextbox = gr.Textbox(show_label=False, container=False, placeholder=i18n("ui.history.search_placeholder"), lines=1, elem_id="history-search-tb")
                            with gr.Column(min_width=52, scale=1, elem_id="gr-history-header-btns"):
                                uploadHistoryBtn = gr.UploadButton(
                                    interactive=True, label="", file_types=[".json"], elem_id="gr-history-upload-btn", type="binary")
                                historyRefreshBtn = gr.Button("", elem_id="gr-history-refresh-btn")


                    with gr.Row(elem_id="chuanhu-history-body"):
                        with gr.Column(scale=6, elem_id="history-select-wrap"):
                            historySelectList = gr.Radio(
                                label=i18n("ui.history.load_from_list"),
                                choices=get_history_names(),
                                value=get_first_history_name(),
                                # multiselect=False,
                                container=False,
                                elem_id="history-select-dropdown"
                            )
                            historyIntentBtn = gr.Button(visible=False, elem_id="history-intent-submit")
                        with gr.Row(visible=False):
                            with gr.Column(min_width=42, scale=1):
                                historyDeleteBtn = gr.Button(
                                    "🗑️", elem_id="gr-history-delete-btn")
                    with gr.Row(visible=False):
                        with gr.Column(scale=6):
                            saveFileName = gr.Textbox(
                                show_label=True,
                                placeholder=i18n("ui.history.filename_placeholder"),
                                label=i18n("ui.history.filename_label"),
                                value=i18n("ui.history.default_name"),
                                elem_classes="no-container"
                                # container=False,
                            )
                        with gr.Column(scale=1):
                            renameHistoryBtn = gr.Button(
                                i18n("ui.history.save"), elem_id="gr-history-save-btn")
                            downloadHistoryJSONBtn = gr.DownloadButton(
                                i18n("ui.history.export_json"), elem_id="gr-history-download-json-btn")
                            downloadHistoryMarkdownBtn = gr.DownloadButton(
                                i18n("ui.history.export_markdown"), elem_id="gr-history-download-md-btn")

            with gr.Column(elem_id="chuanhu-menu-footer"):
                with gr.Row(elem_id="chuanhu-func-nav"):
                    gr.HTML(get_html("func_nav.html"))
                # gr.HTML(get_html("footer.html").format(versions=versions_html()), elem_id="footer")
                # gr.Markdown(CHUANHU_DESCRIPTION, elem_id="chuanhu-author")

        with gr.Column(elem_id="chuanhu-area", scale=5):
            with gr.Column(elem_id="chatbot-area"):
                with gr.Row(elem_id="chatbot-header"):
                    model_select_dropdown = gr.Dropdown(
                        label=i18n("ui.chat.model_select"), choices=MODELS, multiselect=False, value=MODELS[DEFAULT_MODEL], interactive=True,
                        show_label=False, container=False, elem_id="model-select-dropdown", filterable=False
                    )
                    lora_select_dropdown = gr.Dropdown(
                        label=i18n("ui.chat.model_select"), choices=[], multiselect=False, interactive=True, visible=False,
                        container=False,
                    )
                    gr.HTML(get_html("chatbot_header_btn.html").format(
                        json_label=i18n("ui.history.export_json"),
                        md_label=i18n("ui.history.export_markdown")
                    ), elem_id="chatbot-header-btn-bar")
                with gr.Column(elem_id="chatbot-content", min_width=0):
                    with gr.Row(elem_id="chatbot-messages"):
                        chatbot = gr.Chatbot(
                            label="Chuanhu Chat",
                            elem_id="chuanhu-chatbot",
                            latex_delimiters=latex_delimiters_set,
                            sanitize_html=False,
                            show_label=False,
                            avatar_images=[config.user_avatar, config.bot_avatar],
                            show_share_button=False,
                            placeholder=setPlaceholder(model_name=MODELS[DEFAULT_MODEL]),
                        )
                    with gr.Column(elem_id="model-output-panels", min_width=0, scale=0):
                        agent_panel = AgentPanel(convert_user_before_marked, convert_bot_before_marked)
                        agent_panel.output_components()
                with gr.Row(elem_id="chatbot-footer"):
                    with gr.Column(elem_id="chatbot-input-box"):
                        agent_panel.input_components()
                        with gr.Row(elem_id="chatbot-input-row"):
                            gr.HTML(get_html("chatbot_more.html").format(
                                single_turn_label=i18n("ui.chat.single_turn"),
                                websearch_label=i18n("ui.chat.web_search"),
                                upload_file_label=i18n("ui.chat.upload_file"),
                                uploaded_files_label=i18n("ui.chat.knowledge_files"),
                                uploaded_files_tip=i18n("ui.chat.knowledge_files_tip")
                            ))
                            with gr.Row(elem_id="chatbot-input-tb-row"):
                                with gr.Column(min_width=225, scale=12):
                                    user_input = gr.Textbox(
                                        elem_id="user-input-tb",
                                        show_label=False,
                                        placeholder=i18n("ui.chat.input_placeholder"),
                                        elem_classes="no-container",
                                        max_lines=5,
                                        # container=False
                                    )
                                with gr.Column(min_width=42, scale=1, elem_id="chatbot-ctrl-btns"):
                                    submitBtn = gr.Button(
                                        value="", variant="primary", elem_id="submit-btn")
                                    cancelBtn = gr.Button(
                                        value="", variant="secondary", visible=False, elem_id="cancel-btn")
                        # Note: Buttons below are set invisible in UI. But they are used in JS.
                        with gr.Row(elem_id="chatbot-buttons", visible=False):
                            with gr.Column(min_width=120, scale=1):
                                emptyBtn = gr.Button(
                                    i18n("ui.chat.new_conversation"), elem_id="empty-btn"
                                )
                            with gr.Column(min_width=120, scale=1):
                                retryBtn = gr.Button(
                                    i18n("ui.chat.regenerate_btn"), elem_id="gr-retry-btn")
                            with gr.Column(min_width=120, scale=1):
                                delFirstBtn = gr.Button(i18n("ui.chat.delete_oldest"))
                            with gr.Column(min_width=120, scale=1):
                                delLastBtn = gr.Button(
                                    i18n("ui.chat.delete_latest"), elem_id="gr-dellast-btn")
                            with gr.Row(visible=False) as like_dislike_area:
                                with gr.Column(min_width=20, scale=1):
                                    likeBtn = gr.Button(
                                        "👍", elem_id="gr-like-btn")
                                with gr.Column(min_width=20, scale=1):
                                    dislikeBtn = gr.Button(
                                        "👎", elem_id="gr-dislike-btn")

        with gr.Column(elem_id="toolbox-area", scale=1):
            # For CSS setting, there is an extra box. Don't remove it.
            with gr.Group(elem_id="chuanhu-toolbox"):
                with gr.Row():
                    gr.Markdown("## "+i18n("ui.toolbox.title"))
                    gr.HTML(get_html("close_btn.html").format(
                        obj="toolbox"), elem_classes="close-btn")
                with gr.Tabs(elem_id="chuanhu-toolbox-tabs"):
                    with gr.Tab(label=i18n("ui.toolbox.tab.conversation")) as conversation_tab:
                        agent_panel.model_panel_visible = not HIDE_MY_KEY
                        with gr.Accordion(label=i18n("ui.toolbox.model.title"), open=not HIDE_MY_KEY, visible=not HIDE_MY_KEY, elem_id="agent-settings-accordion") as agent_panel.accordion:
                            modelDescription = gr.Markdown(
                                elem_id="gr-model-description",
                                value=i18n(MODEL_METADATA[MODELS[DEFAULT_MODEL]]["description"]),
                                visible=False,
                            )
                            keyTxt = gr.Textbox(
                                show_label=True,
                                placeholder=f"Your API-key...",
                                value=hide_middle_chars(user_api_key.value),
                                type="password",
                                visible=not HIDE_MY_KEY,
                                label="API-Key",
                                elem_id="api-key"
                            )
                            if multi_api_key:
                                usageTxt = gr.Markdown(i18n("ui.toolbox.model.multi_account_hint"), elem_id="usage-display", elem_classes="insert-block", visible=show_api_billing)
                            else:
                                usageTxt = gr.Markdown(i18n("ui.toolbox.model.usage_hint"), elem_id="usage-display", elem_classes="insert-block", visible=show_api_billing)
                            agent_panel.selectors()
                        agent_panel.settings_components()
                        prompt_separator = gr.Markdown("---", elem_classes="hr-line", visible=not HIDE_MY_KEY)
                        agent_panel.separator = gr.Markdown("---", elem_classes="hr-line", elem_id="agent-prompt-separator", visible=False)
                        with gr.Accordion(label="Prompt", open=True) as prompt_group:
                            systemPromptTxt = gr.Textbox(
                                show_label=True,
                                placeholder=i18n("ui.toolbox.prompt.system_placeholder"),
                                label="System prompt",
                                value=INITIAL_SYSTEM_PROMPT,
                                lines=8
                            )
                            retain_system_prompt_checkbox = gr.Checkbox(
                                label=i18n("ui.toolbox.prompt.retain_on_new"), value=False, visible=True, elem_classes="switch-checkbox")
                            with gr.Accordion(label=i18n("ui.toolbox.prompt.load_template"), open=False):
                                with gr.Column():
                                    with gr.Row():
                                        with gr.Column(scale=6):
                                            templateFileSelectDropdown = gr.Dropdown(
                                                label=i18n("ui.toolbox.prompt.select_collection"),
                                                choices=get_template_names(),
                                                multiselect=False,
                                                value=get_template_names()[0],
                                                # container=False,
                                            )
                                        with gr.Column(scale=1):
                                            templateRefreshBtn = gr.Button(
                                                i18n("ui.common.refresh"))
                                    with gr.Row():
                                        with gr.Column():
                                            templateSelectDropdown = gr.Dropdown(
                                                label=i18n("ui.toolbox.prompt.load_from_template"),
                                                choices=load_template(
                                                    get_template_names()[
                                                        0], mode=1
                                                ),
                                                multiselect=False,
                                                # container=False,
                                            )
                        knowledge_separator = gr.Markdown("---", elem_classes="hr-line")
                        with gr.Accordion(label=i18n("ui.toolbox.knowledge.title"), open=True, elem_id="gr-kb-accordion") as knowledge_group:
                            use_websearch_checkbox = gr.Checkbox(label=i18n("ui.toolbox.knowledge.use_web_search"), value=False, elem_classes="switch-checkbox", elem_id="gr-websearch-cb", visible=False)
                            index_files = gr.Files(label=i18n("ui.toolbox.knowledge.upload"), type="filepath", file_types=[".pdf", ".docx", ".pptx", ".epub", ".xlsx", ".txt", "text", "image"], elem_id="upload-index-file")
                            two_column = gr.Checkbox(label=i18n("ui.toolbox.knowledge.two_column_pdf"), value=advance_docs["pdf"].get("two_column", False))
                            summarize_btn = gr.Button(i18n("ui.toolbox.knowledge.summarize_btn"))
                            # TODO: 公式ocr
                            # formula_ocr = gr.Checkbox(label=i18n("ui.toolbox.knowledge.formula_ocr"), value=advance_docs["pdf"].get("formula_ocr", False))

                    with gr.Tab(label=i18n("ui.toolbox.tab.parameters")) as parameter_tab:
                        gr.Markdown(i18n("ui.toolbox.parameters.warning"),
                                    elem_id="advanced-warning")
                        with gr.Accordion(i18n("ui.toolbox.parameters.title"), open=True):
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
                                placeholder=i18n("ui.toolbox.parameters.stop_placeholder"),
                                label="stop",
                                value="",
                                lines=1,
                            )
                            max_context_length_slider = gr.Slider(
                                minimum=1,
                                maximum=1048576,
                                value=2000,
                                step=1,
                                interactive=True,
                                label="max context",
                            )
                            max_generation_slider = gr.Slider(
                                minimum=1,
                                maximum=128000,
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
                                placeholder=i18n("ui.toolbox.parameters.user_id_tip"),
                                label=i18n("ui.toolbox.parameters.user_id"),
                                value=user_name.value,
                                lines=1,
                            )
                    with gr.Tab(label=i18n("ui.toolbox.tab.extensions")):
                        gr.Markdown(
                            "Will be here soon...\n(We hope)\n\nAnd we hope you can help us to make more extensions!")

                    # changeAPIURLBtn = gr.Button(i18n("ui.toolbox.extensions.switch_api"))

    with gr.Row(elem_id="popup-wrapper"):
        with gr.Group(elem_id="chuanhu-popup"):
            with gr.Group(elem_id="chuanhu-setting"):
                with gr.Row():
                    gr.Markdown("## "+i18n("ui.settings.title"))
                    gr.HTML(get_html("close_btn.html").format(
                        obj="box"), elem_classes="close-btn")
                with gr.Tabs(elem_id="chuanhu-setting-tabs"):
                    # with gr.Tab(label=i18n("ui.settings.model.title")):

                        # model_select_dropdown = gr.Dropdown(
                        #     label=i18n("ui.settings.model.select"), choices=MODELS, multiselect=False, value=MODELS[DEFAULT_MODEL], interactive=True
                        # )
                        # lora_select_dropdown = gr.Dropdown(
                        #     label=i18n("ui.settings.model.select_lora"), choices=[], multiselect=False, interactive=True, visible=False
                        # )
                        # with gr.Row():


                    with gr.Tab(label=i18n("ui.settings.advanced.title")):
                        gr.HTML(get_html("appearance_switcher.html").format(
                            label=i18n("ui.settings.advanced.toggle_theme")), elem_classes="insert-block", visible=False)
                        use_streaming_checkbox = gr.Checkbox(
                            label=i18n("ui.settings.advanced.stream_output"), value=True, visible=ENABLE_STREAMING_OPTION, elem_classes="switch-checkbox no-container"
                        )
                        language_select_dropdown = gr.Dropdown(
                            label=i18n("ui.settings.advanced.reply_language"),
                            choices=REPLY_LANGUAGES,
                            multiselect=False,
                            value=REPLY_LANGUAGES[0],
                            elem_classes="no-container",
                        )
                        name_chat_method = gr.Dropdown(
                            label=i18n("ui.settings.advanced.naming_method"),
                            choices=HISTORY_NAME_METHODS,
                            multiselect=False,
                            interactive=True,
                            value=HISTORY_NAME_METHODS[chat_name_method_index],
                            elem_classes="no-container",
                        )
                        single_turn_checkbox = gr.Checkbox(label=i18n("ui.settings.advanced.single_turn"), value=False, elem_classes="switch-checkbox", elem_id="gr-single-session-cb", visible=False)
                        # checkUpdateBtn = gr.Button(i18n("ui.settings.advanced.check_update"), visible=check_update)

                        logout_btn = gr.Button("Logout", link="/logout")

                    with gr.Tab(i18n("ui.settings.network.title")):
                        gr.Markdown(
                            i18n("ui.settings.network.security_warning"), elem_id="netsetting-warning")
                        default_btn = gr.Button(i18n("ui.settings.network.reset"))
                        # 网络代理
                        proxyTxt = gr.Textbox(
                            show_label=True,
                            placeholder=i18n("ui.settings.network.proxy_placeholder"),
                            label=i18n("ui.settings.network.proxy_label"),
                            value=config.http_proxy,
                            lines=1,
                            interactive=False,
                            # container=False,
                            elem_classes="view-only-textbox no-container",
                        )
                        # changeProxyBtn = gr.Button(i18n("ui.settings.network.set_proxy"))

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

                    with gr.Tab(label=i18n("ui.settings.about.title"), elem_id="about-tab"):
                        gr.Markdown(
                            '<img alt="Chuanhu Chat logo" src="file=web_assets/icon/any-icon-512.png" style="max-width: 144px;">')
                        gr.Markdown("# "+i18n("ui.settings.about.name"))
                        gr.HTML(get_html("footer.html").format(
                            versions=versions_html()), elem_id="footer")
                        gr.Markdown(CHUANHU_DESCRIPTION, elem_id="description")

            with gr.Group(elem_id="chuanhu-training"):
                with gr.Row():
                    gr.Markdown("## "+i18n("ui.training.title"))
                    gr.HTML(get_html("close_btn.html").format(
                        obj="box"), elem_classes="close-btn")
                with gr.Tabs(elem_id="chuanhu-training-tabs"):
                    with gr.Tab(label="OpenAI "+i18n("ui.training.openai.finetune")):
                        openai_train_status = gr.Markdown(label=i18n("ui.training.openai.status_label"), value=i18n("ui.training.openai.usage_guide"))

                        with gr.Tab(label=i18n("ui.training.dataset.title")):
                            dataset_previewjson = gr.JSON(
                                label=i18n("ui.training.dataset.preview"))
                            dataset_selection = gr.Files(label=i18n("ui.training.dataset.select"), file_types=[
                                                         ".xlsx", ".jsonl"], file_count="single")
                            upload_to_openai_btn = gr.Button(
                                i18n("ui.training.dataset.upload"), variant="primary", interactive=False)

                        with gr.Tab(label=i18n("ui.training.train.title")):
                            openai_ft_file_id = gr.Textbox(label=i18n("ui.training.train.file_id"), value="", lines=1, placeholder=i18n("ui.training.train.file_id_placeholder"))
                            openai_ft_suffix = gr.Textbox(label=i18n("ui.training.train.suffix"), value="", lines=1, placeholder=i18n("ui.training.train.suffix_placeholder"))
                            openai_train_epoch_slider = gr.Slider(label=i18n("ui.training.train.epochs"), minimum=1, maximum=100, value=3, step=1, interactive=True)
                            openai_start_train_btn = gr.Button(
                                i18n("ui.training.train.start"), variant="primary", interactive=False)

                        with gr.Tab(label=i18n("ui.training.status.title")):
                            openai_status_refresh_btn = gr.Button(i18n("ui.training.status.refresh"))
                            openai_cancel_all_jobs_btn = gr.Button(
                                i18n("ui.training.status.cancel_all"))
                            add_to_models_btn = gr.Button(
                                i18n("ui.training.status.add_model"), interactive=False)

            with gr.Group(elem_id="web-config", visible=False):
                gr.HTML(get_html('web_config.html').format(
                    enableCheckUpdate_config=check_update,
                    hideHistoryWhenNotLoggedIn_config=hide_history_when_not_logged_in,
                    forView_i18n=i18n("ui.settings.view_only"),
                    deleteConfirm_i18n_pref=i18n("ui.history.confirm_delete"),
                    deleteConfirm_i18n_suff=i18n("ui.history.confirm_delete_suffix"),
                    usingLatest_i18n=i18n("ui.settings.update.latest"),
                    updatingMsg_i18n=i18n("ui.settings.update.trying"),
                    updateSuccess_i18n=i18n("ui.settings.update.success"),
                    updateFailure_i18n=i18n("ui.settings.update.failed"),
                    regenerate_i18n=i18n("ui.chat.regenerate"),
                    deleteRound_i18n=i18n("ui.chat.delete_round"),
                    renameChat_i18n=i18n("ui.history.rename"),
                    validFileName_i18n=i18n("ui.history.invalid_filename"),
                    clearFileHistoryMsg_i18n=i18n("ui.chat.knowledge_clear_first"),
                    dropUploadMsg_i18n=i18n("ui.chat.drop_to_upload"),
                ))
            with gr.Group(elem_id="fake-gradio-components", visible=False):
                updateChuanhuBtn = gr.Button(
                    visible=False, elem_classes="invisible-btn", elem_id="update-chuanhu-btn")
                rebootChuanhuBtn = gr.Button(
                    visible=False, elem_classes="invisible-btn", elem_id="reboot-chuanhu-btn")
                changeSingleSessionBtn = gr.Button(
                    visible=False, elem_classes="invisible-btn", elem_id="change-single-session-btn")
                changeOnlineSearchBtn = gr.Button(
                    visible=False, elem_classes="invisible-btn", elem_id="change-online-search-btn")
                historySelectBtn = gr.Button(
                    visible=False, elem_classes="invisible-btn", elem_id="history-select-btn")  # Not used

    capability_marker = gr.HTML('', elem_id='model-capability-state')
    capability_ui = CapabilityUI([
        ('knowledge', prompt_separator, None),
        ('knowledge', index_files, []), ('knowledge', knowledge_group, None), ('knowledge', knowledge_separator, None),
        ('external_websearch', use_websearch_checkbox, False), ('single_turn', single_turn_checkbox, False),
        ('output_mode', use_streaming_checkbox, True), ('regenerate', retryBtn, None),
        ('history_rollback', delFirstBtn, None), ('history_delete', delLastBtn, None),
        ('parameters', parameter_tab, None), ('sampling', temperature_slider, None), ('sampling', top_p_slider, None),
        ('sampling', n_choices_slider, None), ('sampling', stop_sequence_txt, None),
        ('token_limits', max_context_length_slider, None), ('token_limits', max_generation_slider, None),
        ('sampling', presence_penalty_slider, None), ('sampling', frequency_penalty_slider, None),
        ('sampling', logit_bias_txt, None), ('sampling', user_identifier_txt, None),
        ('billing', usageTxt, None), ('reply_language', language_select_dropdown, None),
    ], model_select_dropdown, capability_marker, submitBtn, cancelBtn)
    agent_panel.bind_sidebar(conversation_tab, systemPromptTxt, templateSelectDropdown, prompt_group, i18n("ui.toolbox.tab.conversation"))
    capability_ui.wire(current_model, chatbot)
    agent_panel.wire(current_model, chatbot, status_display, capability_ui)

    # https://github.com/gradio-app/gradio/pull/3296

    def create_greeting(request: gr.Request):
        if hasattr(request, "username") and request.username:  # is not None or is not ""
            logging.info(f"Get User Name: {request.username}")
            user_info, user_name = gr.Markdown(
                value=f"User: {request.username}"), request.username
        else:
            user_info, user_name = gr.Markdown(
                value=f"", visible=False), ""
        current_model = get_model(
            model_name=MODELS[DEFAULT_MODEL], access_key=my_api_key, user_name=user_name, request=request)[0]
        if not hide_history_when_not_logged_in or user_name:
            loaded_stuff = current_model.auto_load()
            # Refresh restores the saved provider and attaches to an existing
            # local task instead of treating Agent history as an ordinary chat.
            saved_path = current_model.history_file_path
            from pathlib import Path
            candidate = Path(saved_path)
            if not candidate.is_absolute(): candidate = Path(HISTORY_DIR) / user_name / candidate
            if candidate.is_file():
                restored = load_history_model(current_model, str(candidate), request=request)
                current_model, loaded_stuff = restored[0], restored[2:19]
        else:
            current_model.new_auto_history_filename()
            loaded_stuff = [gr.update(), gr.update(), gr.Chatbot(label=MODELS[DEFAULT_MODEL]), current_model.single_turn, current_model.temperature, current_model.top_p, current_model.n_choices, current_model.stop_sequence, current_model.token_upper_limit, current_model.max_generation_token, current_model.presence_penalty, current_model.frequency_penalty, current_model.logit_bias, current_model.user_identifier, current_model.stream, gr.DownloadButton(), gr.DownloadButton()]
        cap_values = capability_ui.stream_values(current_model)
        cap_values[0] = dict(cap_values[0], value=current_model._selection_name)
        return user_info, user_name, current_model, toggle_like_btn_visibility(DEFAULT_MODEL), *cap_values, *loaded_stuff, init_history_list(user_name, prepend=current_model.history_file_path.removesuffix(".json"))
    demo.load(create_greeting, inputs=None, outputs=[
              user_info, user_name, current_model, like_dislike_area, *capability_ui.stream_outputs, saveFileName, systemPromptTxt, chatbot, single_turn_checkbox, temperature_slider, top_p_slider, n_choices_slider, stop_sequence_txt, max_context_length_slider, max_generation_slider, presence_penalty_slider, frequency_penalty_slider, logit_bias_txt, user_identifier_txt, use_streaming_checkbox, downloadHistoryJSONBtn, downloadHistoryMarkdownBtn, historySelectList], api_name="load").then(agent_panel.values, [current_model], agent_panel.outputs, show_progress='hidden').then(agent_panel.chat_value, [current_model], [chatbot], show_progress='hidden').then(capability_ui.values, [current_model], capability_ui.outputs, show_progress='hidden').then(agent_panel.observe_history, [current_model], agent_panel.history_outputs, queue=True, concurrency_limit=None, show_progress='hidden').then(agent_panel.history_boundary_values(capability_ui), [current_model], [*agent_panel.outputs, *capability_ui.outputs], show_progress='hidden').then(agent_panel.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
    submission_ui_args = dict(fn=agent_panel.boundary_values(capability_ui), inputs=[current_model],
        outputs=[*agent_panel.outputs, *capability_ui.outputs], show_progress='hidden')

    agent_panel.history_list = historySelectList

    chatgpt_predict_args = dict(
        fn=agent_panel.status_callback(agent_panel.wrap_predict(predict, capability_ui, compact=True), 1, header=True),
        inputs=[
            current_model,
            user_question,
            chatbot,
            use_websearch_checkbox,
            index_files,
            language_select_dropdown,
            agent_panel.input_files,
        ],
        outputs=[chatbot, status_display, *agent_panel.stream_outputs, *capability_ui.stream_outputs, agent_panel.activity],
        show_progress='hidden',
        concurrency_limit=CONCURRENT_COUNT
    )

    start_outputing_args = dict(
        fn=start_outputing,
        inputs=[],
        outputs=[submitBtn, cancelBtn],
        show_progress=True,
    )

    end_outputing_args = dict(
        fn=agent_panel.boundary_values(capability_ui), inputs=[current_model], outputs=[*agent_panel.outputs, *capability_ui.outputs], show_progress='hidden'
    )

    finish_submission_args = dict(fn=agent_panel.status_callback(agent_panel.finish_submission, 1, header=True),
        inputs=[current_model, user_question, user_input], outputs=[user_input, status_display, agent_panel.activity], show_progress='hidden')

    reset_textbox_args = dict(
        fn=reset_textbox, inputs=[], outputs=[user_input]
    )

    transfer_input_args = dict(
        fn=agent_panel.wrap_transfer(transfer_input), inputs=[user_input, current_model, agent_panel.model, agent_panel.reasoning, agent_panel.choice_revision, agent_panel.input_files,
            *agent_panel.config_inputs, systemPromptTxt, agent_panel.config_target, agent_panel.tool_revision], outputs=[
            user_question, user_input, submitBtn, cancelBtn], show_progress='hidden',
        js='''(text, model, name, effort, unused, files, ...configuration) => {
            const root = typeof gradioApp === 'function' ? gradioApp() : document;
            if (window.chuanhuInputConversation?.() &&
                ((window.chuanhuAgentUploading && window.chuanhuAgentUploadTarget === window.chuanhuInputConversation()) ||
                 root.querySelector('#agent-upload-files .uploading, #agent-upload-files .file-preview-holder')))
                throw new Error('附件仍在上传，请等待完成后发送');
            if (window.chuanhuInputConversation?.())
                window.chuanhuAgentPendingDraft = {conversation: window.chuanhuInputConversation(), text, revision: window.chuanhuDraftEditRevision || 0};
            if (window.chuanhuInputConversation?.()) configuration[12] = window.chuanhuInputConversation();
            configuration[13] = window.chuanhuAgentToolRevision || 0;
            return [text, model, name, effort, window.chuanhuAgentChoiceRevision || 0, files, ...configuration.slice(0, 14)];
        }'''
    )

    get_usage_args = dict(
        fn=billing_info, inputs=[current_model], outputs=[
            usageTxt], show_progress=False
    )

    history_load_legacy_outputs_args = [current_model, model_select_dropdown, saveFileName, systemPromptTxt, chatbot, single_turn_checkbox, temperature_slider, top_p_slider, n_choices_slider, stop_sequence_txt, max_context_length_slider, max_generation_slider, presence_penalty_slider, frequency_penalty_slider, logit_bias_txt, user_identifier_txt, use_streaming_checkbox, downloadHistoryJSONBtn, downloadHistoryMarkdownBtn, lora_select_dropdown, user_api_key, keyTxt, modelDescription, status_display]
    history_load_outputs_args = list(dict.fromkeys([*history_load_legacy_outputs_args, *agent_panel.outputs, *capability_ui.outputs, historySelectList]))
    load_history_from_file_args = dict(
        fn=agent_panel.wrap_history_load(load_history_model, capability_ui, legacy_outputs=history_load_legacy_outputs_args),
        trigger_mode="always_last",
        js='(model, filename) => { const selected = window.chuanhuHistorySelection?.() || null; if (selected) window.chuanhuAgentPendingDraft = null; return [model, selected]; }',
        inputs=[current_model, historySelectList],
        outputs=history_load_outputs_args,
    )

    refresh_history_args = dict(
        fn=get_history_list, inputs=[user_name], outputs=[historySelectList]
    )

    auto_name_chat_history_args = dict(
        fn=auto_name_chat_history,
        inputs=[current_model, name_chat_method, user_question, single_turn_checkbox],
        outputs=[historySelectList],
        show_progress=False,
    )

    # Chatbot
    cancelBtn.click(agent_panel.status_callback(interrupt, header=True), [current_model, agent_panel.stop_target], [status_display, agent_panel.activity], queue=False, concurrency_limit=None,
        js="""(model, unused) => {
            const root = typeof gradioApp === 'function' ? gradioApp() : document;
            let caps = {}; try { caps = JSON.parse(root.querySelector('[data-model-capabilities]')?.dataset.modelCapabilities || '{}'); } catch (_) { return [model, {}]; }
            return [model, caps.agent_tools ? {conversation:caps.input_target, generation:caps.task_generation ?? null} : null];
        }""").then(agent_panel.emit_stop_error, [current_model], [], queue=False, concurrency_limit=None)

    user_input.submit(**transfer_input_args).success(**submission_ui_args).success(**
                                                  chatgpt_predict_args).then(**finish_submission_args).then(**end_outputing_args).then(agent_panel.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None).then(**auto_name_chat_history_args)
    user_input.submit(**get_usage_args)

    # user_input.submit(auto_name_chat_history, [current_model, user_question, chatbot, user_name], [historySelectList], show_progress=False)

    submitBtn.click(**transfer_input_args).success(**submission_ui_args).success(**chatgpt_predict_args,
                                                api_name="predict").then(**finish_submission_args).then(**end_outputing_args).then(agent_panel.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None).then(**auto_name_chat_history_args)
    submitBtn.click(**get_usage_args)

    # submitBtn.click(auto_name_chat_history, [current_model, user_question, chatbot, user_name], [historySelectList], show_progress=False)

    index_files.upload(handle_file_upload, [current_model, index_files, chatbot, language_select_dropdown], [
                       index_files, chatbot, status_display])
    summarize_btn.click(handle_summarize_index, [
                        current_model, index_files, chatbot, language_select_dropdown], [chatbot, status_display])

    emptyBtn.click(
        agent_panel.status_callback(agent_panel.wrap_reset(reset, capability_ui), len(capability_ui.stream_outputs) + 2, header=True, returned_model=0),
        inputs=[current_model, retain_system_prompt_checkbox],
        outputs=[current_model, *capability_ui.stream_outputs, chatbot, status_display, historySelectList, systemPromptTxt, single_turn_checkbox, temperature_slider, top_p_slider, n_choices_slider, stop_sequence_txt, max_context_length_slider, max_generation_slider, presence_penalty_slider, frequency_penalty_slider, logit_bias_txt, user_identifier_txt, use_streaming_checkbox, agent_panel.activity],
        show_progress=True,
        js='(a,b)=>{return clearChatbot(a,b);}',
    ).then(agent_panel.values, [current_model], agent_panel.outputs, show_progress='hidden').then(agent_panel.chat_value, [current_model], [chatbot], show_progress='hidden').then(capability_ui.values, [current_model], capability_ui.outputs, show_progress='hidden')

    retryBtn.click(**start_outputing_args).then(
        retry,
        [
            current_model,
            chatbot,
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
    keyTxt.change(agent_panel.status_callback(set_key, 1, header=True), [current_model, keyTxt], [
                  user_api_key, status_display, agent_panel.activity], api_name="set_key").then(**get_usage_args)
    keyTxt.submit(**get_usage_args)
    single_turn_checkbox.input(
        set_single_turn, [current_model, single_turn_checkbox], None, show_progress=False)
    use_streaming_checkbox.input(set_streaming, [current_model, use_streaming_checkbox], None, show_progress=False)
    model_change_legacy_args = [current_model, status_display, chatbot, lora_select_dropdown, user_api_key, keyTxt, modelDescription, use_streaming_checkbox, model_select_dropdown, systemPromptTxt]
    model_change_outputs_args = list(dict.fromkeys([current_model, *agent_panel.outputs, *capability_ui.stream_outputs, *model_change_legacy_args[1:]]))
    model_select_dropdown.input(agent_panel.status_callback(agent_panel.wrap_model_change(change_model, capability_ui, model_change_legacy_args), model_change_outputs_args.index(status_display), header=True, returned_model=0), [model_select_dropdown, lora_select_dropdown, user_api_key, temperature_slider, top_p_slider, systemPromptTxt, user_name, current_model], [*model_change_outputs_args, agent_panel.activity], show_progress=True, api_name="get_model", js="(...args) => { window.chuanhuAgentPendingDraft = null; window.chuanhuClearHistoryIntent?.(); return args; }").then(capability_ui.values, [current_model], capability_ui.outputs, show_progress='hidden').then(agent_panel.observe_history, [current_model], agent_panel.history_outputs, queue=True, concurrency_limit=None, show_progress='hidden').then(agent_panel.history_boundary_values(capability_ui), [current_model], [*agent_panel.outputs, *capability_ui.outputs], show_progress='hidden').then(agent_panel.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
    model_select_dropdown.change(toggle_like_btn_visibility, [model_select_dropdown], [
                                 like_dislike_area], show_progress=False)
    # model_select_dropdown.change(
    #     toggle_file_type, [model_select_dropdown], [index_files], show_progress=False)
    lora_select_dropdown.change(agent_panel.status_callback(get_model, 1, header=True, returned_model=0), [model_select_dropdown, lora_select_dropdown, user_api_key, temperature_slider,
                                top_p_slider, systemPromptTxt, user_name, current_model], [current_model, status_display, chatbot, modelDescription, agent_panel.activity], show_progress=True)

    # Template
    systemPromptTxt.change(agent_panel.status_callback(set_system_prompt, header=True), [
                           current_model, systemPromptTxt], [status_display, agent_panel.activity]).then(agent_panel.values, [current_model], agent_panel.outputs, show_progress='hidden')
    templateRefreshBtn.click(get_template_dropdown, None, [
                             templateFileSelectDropdown])
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
    renameHistoryBtn.click(
        rename_chat_history,
        [current_model, saveFileName],
        [historySelectList],
        show_progress=True,
        js='(a,b,c,d)=>{return saveChatHistory(a,b,c,d);}'
    )
    historyRefreshBtn.click(**refresh_history_args)
    historyDeleteBtn.click(delete_chat_history, [current_model, historySelectList], [status_display, historySelectList, chatbot], js='(a,b,c)=>{return showConfirmationDialog(a, b, c);}').then(
        agent_panel.status_callback(agent_panel.wrap_reset(reset, capability_ui), len(capability_ui.stream_outputs) + 2, header=True, returned_model=0),
        inputs=[current_model, retain_system_prompt_checkbox],
        outputs=[current_model, *capability_ui.stream_outputs, chatbot, status_display, historySelectList, systemPromptTxt, single_turn_checkbox, temperature_slider, top_p_slider, n_choices_slider, stop_sequence_txt, max_context_length_slider, max_generation_slider, presence_penalty_slider, frequency_penalty_slider, logit_bias_txt, user_identifier_txt, use_streaming_checkbox, agent_panel.activity],
        show_progress='hidden',
        js='(a,b)=>{return clearChatbot(a,b);}',
    ).then(agent_panel.values, [current_model], agent_panel.outputs, show_progress='hidden').then(agent_panel.chat_value, [current_model], [chatbot], show_progress='hidden').then(capability_ui.values, [current_model], capability_ui.outputs, show_progress='hidden')
    historyIntentBtn.click(**load_history_from_file_args).then(agent_panel.observe_history, [current_model], agent_panel.history_outputs, queue=True, concurrency_limit=None, show_progress='hidden').then(agent_panel.history_boundary_values(capability_ui), [current_model], [*agent_panel.outputs, *capability_ui.outputs], show_progress='hidden').then(agent_panel.emit_ui_error, [current_model], [], queue=False, concurrency_limit=None)
    uploadHistoryBtn.upload(upload_chat_history, [current_model, uploadHistoryBtn], [
                        saveFileName, systemPromptTxt, chatbot, single_turn_checkbox, temperature_slider, top_p_slider, n_choices_slider, stop_sequence_txt, max_context_length_slider, max_generation_slider, presence_penalty_slider, frequency_penalty_slider, logit_bias_txt, user_identifier_txt, use_streaming_checkbox, downloadHistoryJSONBtn, downloadHistoryMarkdownBtn, historySelectList]).then(**refresh_history_args).then(agent_panel.values, [current_model], agent_panel.outputs, show_progress='hidden').then(agent_panel.chat_value, [current_model], [chatbot], show_progress='hidden').then(capability_ui.values, [current_model], capability_ui.outputs, show_progress='hidden')
    historySearchTextbox.input(
        filter_history,
        [user_name, historySearchTextbox],
        [historySelectList]
    )

    # Train
    dataset_selection.upload(handle_dataset_selection, dataset_selection, [
                             dataset_previewjson, upload_to_openai_btn, openai_train_status])
    dataset_selection.clear(handle_dataset_clear, [], [
                            dataset_previewjson, upload_to_openai_btn])
    upload_to_openai_btn.click(upload_to_openai, [dataset_selection], [
                               openai_ft_file_id, openai_train_status], show_progress=True)

    openai_ft_file_id.change(lambda x: gr.update(interactive=True) if len(
        x) > 0 else gr.update(interactive=False), [openai_ft_file_id], [openai_start_train_btn])
    openai_start_train_btn.click(start_training, [
                                 openai_ft_file_id, openai_ft_suffix, openai_train_epoch_slider], [openai_train_status])

    openai_status_refresh_btn.click(get_training_status, [], [
                                    openai_train_status, add_to_models_btn])
    add_to_models_btn.click(add_to_models, [], [
                            model_select_dropdown, openai_train_status], show_progress=True)
    openai_cancel_all_jobs_btn.click(
        cancel_all_jobs, [], [openai_train_status], show_progress=True)

    # Advanced
    temperature_slider.input(
        set_temperature, [current_model, temperature_slider], None, show_progress=False)
    top_p_slider.input(set_top_p, [current_model, top_p_slider], None, show_progress=False)
    n_choices_slider.input(
        set_n_choices, [current_model, n_choices_slider], None, show_progress=False)
    stop_sequence_txt.input(
        set_stop_sequence, [current_model, stop_sequence_txt], None, show_progress=False)
    max_context_length_slider.input(
        set_token_upper_limit, [current_model, max_context_length_slider], None, show_progress=False)
    max_generation_slider.input(
        set_max_tokens, [current_model, max_generation_slider], None, show_progress=False)
    presence_penalty_slider.input(
        set_presence_penalty, [current_model, presence_penalty_slider], None, show_progress=False)
    frequency_penalty_slider.input(
        set_frequency_penalty, [current_model, frequency_penalty_slider], None, show_progress=False)
    logit_bias_txt.input(
        set_logit_bias, [current_model, logit_bias_txt], None, show_progress=False)
    user_identifier_txt.input(set_user_identifier, [
                               current_model, user_identifier_txt], None, show_progress=False)

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
    # checkUpdateBtn.click(fn=None, js='manualCheckUpdate')

    # Invisible elements
    updateChuanhuBtn.click(
        update_chuanhu,
        [user_name],
        [status_display],
        show_progress=True,
    )
    rebootChuanhuBtn.click(
        reboot_chuanhu,
        [],
        [],
        show_progress=True,
        js='rebootingChuanhu'
    )
    changeSingleSessionBtn.click(
        fn=lambda value: gr.Checkbox(value=value),
        inputs=[single_turn_checkbox],
        outputs=[single_turn_checkbox],
        js='(a)=>{return bgChangeSingleSession(a);}'
    )
    changeOnlineSearchBtn.click(
        fn=lambda value: gr.Checkbox(value=value),
        inputs=[use_websearch_checkbox],
        outputs=[use_websearch_checkbox],
        js='(a)=>{return bgChangeOnlineSearch(a);}'
    )
    historySelectBtn.click(  # This is an experimental feature... Not actually used.
        fn=load_history_model,
        inputs=[current_model, historySelectList],
        outputs=[current_model, model_select_dropdown, saveFileName, systemPromptTxt, chatbot, single_turn_checkbox, temperature_slider, top_p_slider, n_choices_slider, stop_sequence_txt, max_context_length_slider, max_generation_slider, presence_penalty_slider, frequency_penalty_slider, logit_bias_txt, user_identifier_txt, use_streaming_checkbox, downloadHistoryJSONBtn, downloadHistoryMarkdownBtn, lora_select_dropdown, user_api_key, keyTxt, modelDescription, status_display],
        js='(a,b)=>{return bgSelectHistory(a,b);}'
    )
# 默认开启本地服务器，默认可以直接从IP访问，默认不创建公开分享链接
demo.title = i18n("app.title")

if __name__ == "__main__":
    reload_javascript()
    setup_wizard()
    _allowed_paths = ["web_assets"]
    if config.midjourney_temp_folder:
        _allowed_paths.append(config.midjourney_temp_folder)
    demo.queue().launch(
        allowed_paths=_allowed_paths,
        blocked_paths=["config.json", ".env.agents", ".agents-runtime", "agent_data", "files", "models", "lora", "modules", "history"],
        server_name=server_name,
        server_port=server_port,
        share=share,
        auth=auth_from_conf if authflag else None,
        favicon_path="./web_assets/favicon.ico",
        inbrowser=autobrowser and not dockerflag,  # 禁止在docker下开启inbrowser
    )
