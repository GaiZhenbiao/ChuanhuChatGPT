from __future__ import annotations

import logging
import os

import colorama
import commentjson as cjson

from modules import config

from ..index_func import *
from ..presets import *
from ..utils import *
from .base_model import BaseLLMModel, ModelType


def get_model(
    model_name,
    lora_model_path=None,
    access_key=None,
    temperature=None,
    top_p=None,
    system_prompt=None,
    user_name="",
    original_model = None
) -> BaseLLMModel:
    msg = i18n("模型设置为了：") + f" {model_name}"
    model_type = ModelType.get_type(model_name)
    lora_selector_visibility = False
    lora_choices = ["No LoRA"]
    dont_change_lora_selector = False
    if model_type != ModelType.OpenAI:
        config.local_embedding = True
    # del current_model.model
    model = original_model
    try:
        if model_type == ModelType.OpenAIVision or model_type == ModelType.OpenAI:
            logging.info(f"正在加载 OpenAI 模型: {model_name}")
            from .OpenAIVision import OpenAIVisionClient
            access_key = os.environ.get("OPENAI_API_KEY", access_key)
            model = OpenAIVisionClient(
                model_name, api_key=access_key, user_name=user_name)
        elif model_type == ModelType.OpenAIInstruct:
            logging.info(f"正在加载OpenAI Instruct模型: {model_name}")
            from .OpenAIInstruct import OpenAI_Instruct_Client
            access_key = os.environ.get("OPENAI_API_KEY", access_key)
            model = OpenAI_Instruct_Client(
                model_name, api_key=access_key, user_name=user_name)
        elif model_type == ModelType.ChatGLM:
            logging.info(f"正在加载ChatGLM模型: {model_name}")
            from .ChatGLM import ChatGLM_Client
            model = ChatGLM_Client(model_name, user_name=user_name)
        elif model_type == ModelType.Groq:
            logging.info(f"正在加载Groq模型: {model_name}")
            from .Groq import Groq_Client
            model = Groq_Client(model_name, access_key, user_name=user_name)
        elif model_type == ModelType.LLaMA and lora_model_path == "":
            msg = f"现在请为 {model_name} 选择LoRA模型"
            logging.info(msg)
            lora_selector_visibility = True
            if os.path.isdir("lora"):
                lora_choices = ["No LoRA"] + get_file_names_by_pinyin("lora", filetypes=[""])
        elif model_type == ModelType.LLaMA and lora_model_path != "":
            logging.info(f"正在加载LLaMA模型: {model_name} + {lora_model_path}")
            from .LLaMA import LLaMA_Client
            dont_change_lora_selector = True
            if lora_model_path == "No LoRA":
                lora_model_path = None
                msg += " + No LoRA"
            else:
                msg += f" + {lora_model_path}"
            model = LLaMA_Client(
                model_name, lora_model_path, user_name=user_name)
        elif model_type == ModelType.XMChat:
            from .XMChat import XMChat
            if os.environ.get("XMCHAT_API_KEY") != "":
                access_key = os.environ.get("XMCHAT_API_KEY")
            model = XMChat(api_key=access_key, user_name=user_name)
        elif model_type == ModelType.StableLM:
            from .StableLM import StableLM_Client
            model = StableLM_Client(model_name, user_name=user_name)
        elif model_type == ModelType.MOSS:
            from .MOSS import MOSS_Client
            model = MOSS_Client(model_name, user_name=user_name)
        elif model_type == ModelType.YuanAI:
            from .inspurai import Yuan_Client
            model = Yuan_Client(model_name, api_key=access_key,
                                user_name=user_name, system_prompt=system_prompt)
        elif model_type == ModelType.Minimax:
            from .minimax import MiniMax_Client
            if os.environ.get("MINIMAX_API_KEY") != "":
                access_key = os.environ.get("MINIMAX_API_KEY")
            model = MiniMax_Client(
                model_name, api_key=access_key, user_name=user_name, system_prompt=system_prompt)
        elif model_type == ModelType.ChuanhuAgent:
            from .ChuanhuAgent import ChuanhuAgent_Client
            model = ChuanhuAgent_Client(model_name, access_key, user_name=user_name)
            msg = i18n("启用的工具：") + ", ".join([i.name for i in model.tools])
        elif model_type == ModelType.GooglePaLM:
            from .GooglePaLM import Google_PaLM_Client
            access_key = os.environ.get("GOOGLE_GENAI_API_KEY", access_key)
            model = Google_PaLM_Client(
                model_name, access_key, user_name=user_name)
        elif model_type == ModelType.GoogleGemini:
            from .GoogleGemini import GoogleGeminiClient
            access_key = os.environ.get("GOOGLE_GENAI_API_KEY", access_key)
            model = GoogleGeminiClient(
                model_name, access_key, user_name=user_name)
        elif model_type == ModelType.LangchainChat:
            from .Azure import Azure_OpenAI_Client
            model = Azure_OpenAI_Client(model_name, user_name=user_name)
        elif model_type == ModelType.Midjourney:
            from .midjourney import Midjourney_Client
            mj_proxy_api_secret = os.getenv("MIDJOURNEY_PROXY_API_SECRET")
            model = Midjourney_Client(
                model_name, mj_proxy_api_secret, user_name=user_name)
        elif model_type == ModelType.Spark:
            from .spark import Spark_Client
            model = Spark_Client(model_name, os.getenv("SPARK_APPID"), os.getenv(
                "SPARK_API_KEY"), os.getenv("SPARK_API_SECRET"), user_name=user_name)
        elif model_type == ModelType.Claude:
            from .Claude import Claude_Client
            model = Claude_Client(model_name=model_name, api_secret=os.getenv("CLAUDE_API_SECRET"))
        elif model_type == ModelType.Qwen:
            from .Qwen import Qwen_Client
            model = Qwen_Client(model_name, user_name=user_name)
        elif model_type == ModelType.ERNIE:
            from .ERNIE import ERNIE_Client
            model = ERNIE_Client(model_name, api_key=os.getenv("ERNIE_APIKEY"),secret_key=os.getenv("ERNIE_SECRETKEY"))
        elif model_type == ModelType.DALLE3:
            from .DALLE3 import OpenAI_DALLE3_Client
            access_key = os.environ.get("OPENAI_API_KEY", access_key)
            model = OpenAI_DALLE3_Client(model_name, api_key=access_key, user_name=user_name)
        elif model_type == ModelType.Ollama:
            from .Ollama import OllamaClient
            ollama_host = os.environ.get("OLLAMA_HOST", access_key)
            model = OllamaClient(model_name, user_name=user_name, backend_model=lora_model_path)
            model_list = model.get_model_list()
            lora_selector_visibility = True
            lora_choices = [i["name"] for i in model_list["models"]]
        elif model_type == ModelType.GoogleGemma:
            from .GoogleGemma import GoogleGemmaClient
            model = GoogleGemmaClient(
                model_name, access_key, user_name=user_name)
        elif model_type == ModelType.Unknown:
            raise ValueError(f"Unknown model: {model_name}")
        else:
            raise ValueError(f"Unimplemented model type: {model_type}")
        logging.info(msg)
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = f"{STANDARD_ERROR_MSG}: {e}"
    modelDescription = i18n(model.description)
    presudo_key = hide_middle_chars(access_key)
    if original_model is not None and model is not None:
        model.history = original_model.history
        model.history_file_path = original_model.history_file_path
        model.system_prompt = original_model.system_prompt
    if dont_change_lora_selector:
        return model, msg, gr.update(label=model_name, placeholder=setPlaceholder(model=model)), gr.update(), access_key, presudo_key, modelDescription
    else:
        return model, msg, gr.update(label=model_name, placeholder=setPlaceholder(model=model)), gr.Dropdown(choices=lora_choices, visible=lora_selector_visibility), access_key, presudo_key, modelDescription


if __name__ == "__main__":
    with open("config.json", "r", encoding="utf-8") as f:
        openai_api_key = cjson.load(f)["openai_api_key"]
    # set logging level to debug
    logging.basicConfig(level=logging.DEBUG)
    # client = ModelManager(model_name="gpt-3.5-turbo", access_key=openai_api_key)
    client = get_model(model_name="chatglm-6b-int4")
    chatbot = []
    stream = False
    # 测试账单功能
    logging.info(colorama.Back.GREEN + "测试账单功能" + colorama.Back.RESET)
    logging.info(client.billing_info())
    # 测试问答
    logging.info(colorama.Back.GREEN + "测试问答" + colorama.Back.RESET)
    question = "巴黎是中国的首都吗？"
    for i in client.predict(inputs=question, chatbot=chatbot, stream=stream):
        logging.info(i)
    logging.info(f"测试问答后history : {client.history}")
    # 测试记忆力
    logging.info(colorama.Back.GREEN + "测试记忆力" + colorama.Back.RESET)
    question = "我刚刚问了你什么问题？"
    for i in client.predict(inputs=question, chatbot=chatbot, stream=stream):
        logging.info(i)
    logging.info(f"测试记忆力后history : {client.history}")
    # 测试重试功能
    logging.info(colorama.Back.GREEN + "测试重试功能" + colorama.Back.RESET)
    for i in client.retry(chatbot=chatbot, stream=stream):
        logging.info(i)
    logging.info(f"重试后history : {client.history}")
    # # 测试总结功能
    # print(colorama.Back.GREEN + "测试总结功能" + colorama.Back.RESET)
    # chatbot, msg = client.reduce_token_size(chatbot=chatbot)
    # print(chatbot, msg)
    # print(f"总结后history: {client.history}")
