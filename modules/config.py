from collections import defaultdict
from contextlib import contextmanager
import os
import logging
import sys
import commentjson as json
import colorama
from collections import defaultdict

from . import shared
from . import presets
from .presets import i18n


__all__ = [
    "my_api_key",
    "sensitive_id",
    "authflag",
    "auth_list",
    "dockerflag",
    "retrieve_proxy",
    "advance_docs",
    "update_doc_config",
    "usage_limit",
    "multi_api_key",
    "server_name",
    "server_port",
    "share",
    "autobrowser",
    "check_update",
    "latex_delimiters_set",
    "hide_history_when_not_logged_in",
    "default_chuanhu_assistant_model",
    "show_api_billing",
    "chat_name_method_index",
    "HIDE_MY_KEY",
    "hfspaceflag",
]

# 添加一个统一的config文件，避免文件过多造成的疑惑（优先级最低）
# 同时，也可以为后续支持自定义功能提供config的帮助
if os.path.exists("config.json"):
    with open("config.json", "r", encoding='utf-8') as f:
        config = json.load(f)
else:
    config = {}


def load_config_to_environ(key_list):
    global config
    for key in key_list:
        if key in config:
            os.environ[key.upper()] = os.environ.get(key.upper(), config[key])

hide_history_when_not_logged_in = config.get(
    "hide_history_when_not_logged_in", False)
check_update = config.get("check_update", True)
show_api_billing = config.get("show_api_billing", False)
show_api_billing = bool(os.environ.get("SHOW_API_BILLING", show_api_billing))
chat_name_method_index = config.get("chat_name_method_index", 2)

if os.path.exists("api_key.txt"):
    logging.info("检测到api_key.txt文件，正在进行迁移...")
    with open("api_key.txt", "r", encoding="utf-8") as f:
        config["openai_api_key"] = f.read().strip()
    os.rename("api_key.txt", "api_key(deprecated).txt")
    with open("config.json", "w", encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

if os.path.exists("auth.json"):
    logging.info("检测到auth.json文件，正在进行迁移...")
    auth_list = []
    with open("auth.json", "r", encoding='utf-8') as f:
        auth = json.load(f)
        for _ in auth:
            if auth[_]["username"] and auth[_]["password"]:
                auth_list.append((auth[_]["username"], auth[_]["password"]))
            else:
                logging.error("请检查auth.json文件中的用户名和密码！")
                sys.exit(1)
    config["users"] = auth_list
    os.rename("auth.json", "auth(deprecated).json")
    with open("config.json", "w", encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# 处理docker if we are running in Docker
dockerflag = config.get("dockerflag", False)
if os.environ.get("dockerrun") == "yes":
    dockerflag = True

hfspaceflag = os.environ.get("HF_SPACE", "false") == "true"

# 处理 api-key 以及 允许的用户列表
my_api_key = config.get("openai_api_key", "")
my_api_key = os.environ.get("OPENAI_API_KEY", my_api_key)
os.environ["OPENAI_API_KEY"] = my_api_key
os.environ["OPENAI_EMBEDDING_API_KEY"] = my_api_key

if config.get("legacy_api_usage", False):
    sensitive_id = my_api_key
else:
    sensitive_id = config.get("sensitive_id", "")
    sensitive_id = os.environ.get("SENSITIVE_ID", sensitive_id)

if "extra_model_metadata" in config:
    presets.MODEL_METADATA.update(config["extra_model_metadata"])
    logging.info(i18n("已添加 {extra_model_quantity} 个额外的模型元数据").format(extra_model_quantity=len(config["extra_model_metadata"])))

_model_metadata = {}
for k, v in presets.MODEL_METADATA.items():
    temp_dict = presets.DEFAULT_METADATA.copy()
    temp_dict.update(v)
    _model_metadata[k] = temp_dict
presets.MODEL_METADATA = _model_metadata

if "available_models" in config:
    presets.MODELS = config["available_models"]
    logging.info(i18n("已设置可用模型：{available_models}").format(available_models=config["available_models"]))

# 模型配置
if "extra_models" in  config:
    presets.MODELS.extend(config["extra_models"])
    logging.info(i18n("已添加额外的模型：{extra_models}").format(extra_models=config["extra_models"]))

HIDE_MY_KEY = config.get("hide_my_key", False)

google_genai_api_key = os.environ.get(
    "GOOGLE_PALM_API_KEY", "")
google_genai_api_key = os.environ.get(
    "GOOGLE_GENAI_API_KEY", "")
google_genai_api_key = config.get("google_palm_api_key", google_genai_api_key)
google_genai_api_key = config.get("google_genai_api_key", google_genai_api_key)
os.environ["GOOGLE_GENAI_API_KEY"] = google_genai_api_key

huggingface_auth_token = os.environ.get("HF_AUTH_TOKEN", "")
huggingface_auth_token = config.get("hf_auth_token", huggingface_auth_token)
os.environ["HF_AUTH_TOKEN"] = huggingface_auth_token

xmchat_api_key = config.get("xmchat_api_key", "")
os.environ["XMCHAT_API_KEY"] = xmchat_api_key

minimax_api_key = config.get("minimax_api_key", "")
os.environ["MINIMAX_API_KEY"] = minimax_api_key
minimax_group_id = config.get("minimax_group_id", "")
os.environ["MINIMAX_GROUP_ID"] = minimax_group_id

midjourney_proxy_api_base = config.get("midjourney_proxy_api_base", "")
os.environ["MIDJOURNEY_PROXY_API_BASE"] = midjourney_proxy_api_base
midjourney_proxy_api_secret = config.get("midjourney_proxy_api_secret", "")
os.environ["MIDJOURNEY_PROXY_API_SECRET"] = midjourney_proxy_api_secret
midjourney_discord_proxy_url = config.get("midjourney_discord_proxy_url", "")
os.environ["MIDJOURNEY_DISCORD_PROXY_URL"] = midjourney_discord_proxy_url
midjourney_temp_folder = config.get("midjourney_temp_folder", "")
os.environ["MIDJOURNEY_TEMP_FOLDER"] = midjourney_temp_folder

spark_api_key = config.get("spark_api_key", "")
os.environ["SPARK_API_KEY"] = spark_api_key
spark_appid = config.get("spark_appid", "")
os.environ["SPARK_APPID"] = spark_appid
spark_api_secret = config.get("spark_api_secret", "")
os.environ["SPARK_API_SECRET"] = spark_api_secret

claude_api_secret = config.get("claude_api_secret", "")
os.environ["CLAUDE_API_SECRET"] = claude_api_secret

ernie_api_key = config.get("ernie_api_key", "")
os.environ["ERNIE_APIKEY"] = ernie_api_key
ernie_secret_key = config.get("ernie_secret_key", "")
os.environ["ERNIE_SECRETKEY"] = ernie_secret_key

ollama_host = config.get("ollama_host", "")
os.environ["OLLAMA_HOST"] = ollama_host

groq_api_key = config.get("groq_api_key", "")
os.environ["GROQ_API_KEY"] = groq_api_key

load_config_to_environ(["openai_api_type", "azure_openai_api_key", "azure_openai_api_base_url",
                       "azure_openai_api_version", "azure_deployment_name", "azure_embedding_deployment_name", "azure_embedding_model_name"])


usage_limit = os.environ.get("USAGE_LIMIT", config.get("usage_limit", 120))

# 多账户机制
multi_api_key = config.get("multi_api_key", False)  # 是否开启多账户机制
if multi_api_key:
    api_key_list = config.get("api_key_list", [])
    if len(api_key_list) == 0:
        logging.error("多账号模式已开启，但api_key_list为空，请检查config.json")
        sys.exit(1)
    shared.state.set_api_key_queue(api_key_list)

auth_list = config.get("users", [])  # 实际上是使用者的列表
authflag = len(auth_list) > 0  # 是否开启认证的状态值，改为判断auth_list长度

# 处理自定义的api_host，优先读环境变量的配置，如果存在则自动装配
api_host = os.environ.get(
    "OPENAI_API_BASE", config.get("openai_api_base", None))
if api_host is not None:
    shared.state.set_api_host(api_host)
    # os.environ["OPENAI_API_BASE"] = f"{api_host}/v1"
    logging.info(f"OpenAI API Base set to: {os.environ['OPENAI_API_BASE']}")

default_chuanhu_assistant_model = config.get(
    "default_chuanhu_assistant_model", "gpt-4-turbo-preview")
for x in ["GOOGLE_CSE_ID", "GOOGLE_API_KEY", "WOLFRAM_ALPHA_APPID", "SERPAPI_API_KEY"]:
    if config.get(x, None) is not None:
        os.environ[x] = config[x]


@contextmanager
def retrieve_openai_api(api_key=None):
    old_api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key is None:
        os.environ["OPENAI_API_KEY"] = my_api_key
        yield my_api_key
    else:
        os.environ["OPENAI_API_KEY"] = api_key
        yield api_key
    os.environ["OPENAI_API_KEY"] = old_api_key



# 处理代理：
http_proxy = os.environ.get("HTTP_PROXY", "")
https_proxy = os.environ.get("HTTPS_PROXY", "")
http_proxy = config.get("http_proxy", http_proxy)
https_proxy = config.get("https_proxy", https_proxy)

# 重置系统变量，在不需要设置的时候不设置环境变量，以免引起全局代理报错
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""

local_embedding = config.get("local_embedding", False)  # 是否使用本地embedding


@contextmanager
def retrieve_proxy(proxy=None):
    """
    1, 如果proxy = NONE，设置环境变量，并返回最新设置的代理
    2，如果proxy ！= NONE，更新当前的代理配置，但是不更新环境变量
    """
    global http_proxy, https_proxy
    if proxy is not None:
        http_proxy = proxy
        https_proxy = proxy
        yield http_proxy, https_proxy
    else:
        old_var = os.environ["HTTP_PROXY"], os.environ["HTTPS_PROXY"]
        os.environ["HTTP_PROXY"] = http_proxy
        os.environ["HTTPS_PROXY"] = https_proxy
        yield http_proxy, https_proxy  # return new proxy

        # return old proxy
        os.environ["HTTP_PROXY"], os.environ["HTTPS_PROXY"] = old_var


# 处理latex options
user_latex_option = config.get("latex_option", "default")
if user_latex_option == "default":
    latex_delimiters_set = [
        {"left": "$$", "right": "$$", "display": True},
        {"left": "$", "right": "$", "display": False},
        {"left": "\\(", "right": "\\)", "display": False},
        {"left": "\\[", "right": "\\]", "display": True},
    ]
elif user_latex_option == "strict":
    latex_delimiters_set = [
        {"left": "$$", "right": "$$", "display": True},
        {"left": "\\(", "right": "\\)", "display": False},
        {"left": "\\[", "right": "\\]", "display": True},
    ]
elif user_latex_option == "all":
    latex_delimiters_set = [
        {"left": "$$", "right": "$$", "display": True},
        {"left": "$", "right": "$", "display": False},
        {"left": "\\(", "right": "\\)", "display": False},
        {"left": "\\[", "right": "\\]", "display": True},
        {"left": "\\begin{equation}", "right": "\\end{equation}", "display": True},
        {"left": "\\begin{align}", "right": "\\end{align}", "display": True},
        {"left": "\\begin{alignat}", "right": "\\end{alignat}", "display": True},
        {"left": "\\begin{gather}", "right": "\\end{gather}", "display": True},
        {"left": "\\begin{CD}", "right": "\\end{CD}", "display": True},
    ]
elif user_latex_option == "disabled":
    latex_delimiters_set = []
else:
    latex_delimiters_set = [
        {"left": "$$", "right": "$$", "display": True},
        {"left": "$", "right": "$", "display": False},
        {"left": "\\(", "right": "\\)", "display": False},
        {"left": "\\[", "right": "\\]", "display": True},
    ]
# ![IMPORTANT] PATCH gradio 4.26, disable latex for now
user_latex_option = "disabled"
latex_delimiters_set = []

# 处理advance docs
advance_docs = defaultdict(lambda: defaultdict(dict))
advance_docs.update(config.get("advance_docs", {}))


def update_doc_config(two_column_pdf):
    global advance_docs
    advance_docs["pdf"]["two_column"] = two_column_pdf

    logging.info(f"更新后的文件参数为：{advance_docs}")


# 处理gradio.launch参数
server_name = config.get("server_name", None)
server_port = config.get("server_port", None)
if server_name is None:
    if dockerflag:
        server_name = "0.0.0.0"
    else:
        server_name = "127.0.0.1"
if server_port is None:
    if dockerflag:
        server_port = 7860

assert server_port is None or type(server_port) == int, "要求port设置为int类型"

# 设置默认model
default_model = config.get("default_model", "GPT-4o-mini")
try:
    if default_model in presets.MODELS:
        presets.DEFAULT_MODEL = presets.MODELS.index(default_model)
    else:
        presets.DEFAULT_MODEL = presets.MODELS.index(next((k for k, v in presets.MODEL_METADATA.items() if v.get("model_name") == default_model), None))
    logging.info("默认模型设置为了：" + str(presets.MODELS[presets.DEFAULT_MODEL]))
except ValueError:
    logging.error("你填写的默认模型" + default_model + "不存在！请从下面的列表中挑一个填写：" + str(presets.MODELS))

share = config.get("share", False)
autobrowser = config.get("autobrowser", True)

# avatar
bot_avatar = config.get("bot_avatar", "default")
user_avatar = config.get("user_avatar", "default")
if bot_avatar == "" or bot_avatar == "none" or bot_avatar is None:
    bot_avatar = None
elif bot_avatar == "default":
    bot_avatar = "web_assets/chatbot.png"
if user_avatar == "" or user_avatar == "none" or user_avatar is None:
    user_avatar = None
elif user_avatar == "default":
    user_avatar = "web_assets/user.png"
