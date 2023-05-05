from __future__ import annotations
from typing import TYPE_CHECKING, List

import logging
import json
import commentjson as cjson
import os
import sys
import requests
import urllib3
import platform
import base64
from io import BytesIO
from PIL import Image

from tqdm import tqdm
import colorama
from duckduckgo_search import ddg
import asyncio
import aiohttp
from enum import Enum
import uuid

from ..presets import *
from ..llama_func import *
from ..utils import *
from .. import shared
from ..config import retrieve_proxy, usage_limit
from modules import config
from .base_model import BaseLLMModel, ModelType


class OpenAIClient(BaseLLMModel):
    def __init__(
        self,
        model_name,
        api_key,
        system_prompt=INITIAL_SYSTEM_PROMPT,
        temperature=1.0,
        top_p=1.0,
        user_name=""
    ) -> None:
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            top_p=top_p,
            system_prompt=system_prompt,
            user=user_name
        )
        self.api_key = api_key
        self.need_api_key = True
        self._refresh_header()

    def get_answer_stream_iter(self):
        response = self._get_response(stream=True)
        if response is not None:
            iter = self._decode_chat_response(response)
            partial_text = ""
            for i in iter:
                partial_text += i
                yield partial_text
        else:
            yield STANDARD_ERROR_MSG + GENERAL_ERROR_MSG

    def get_answer_at_once(self):
        response = self._get_response()
        response = json.loads(response.text)
        content = response["choices"][0]["message"]["content"]
        total_token_count = response["usage"]["total_tokens"]
        return content, total_token_count

    def count_token(self, user_input):
        input_token_count = count_token(construct_user(user_input))
        if self.system_prompt is not None and len(self.all_token_counts) == 0:
            system_prompt_token_count = count_token(
                construct_system(self.system_prompt)
            )
            return input_token_count + system_prompt_token_count
        return input_token_count

    def billing_info(self):
        try:
            curr_time = datetime.datetime.now()
            last_day_of_month = get_last_day_of_month(
                curr_time).strftime("%Y-%m-%d")
            first_day_of_month = curr_time.replace(day=1).strftime("%Y-%m-%d")
            usage_url = f"{shared.state.usage_api_url}?start_date={first_day_of_month}&end_date={last_day_of_month}"
            try:
                usage_data = self._get_billing_data(usage_url)
            except Exception as e:
                logging.error(f"获取API使用情况失败:" + str(e))
                return i18n("**获取API使用情况失败**")
            # rounded_usage = "{:.5f}".format(usage_data["total_usage"] / 100)
            rounded_usage = round(usage_data["total_usage"] / 100, 5)
            usage_percent = round(usage_data["total_usage"] / usage_limit, 2)
            # return i18n("**本月使用金额** ") + f"\u3000 ${rounded_usage}"
            return """\
                <b>""" + i18n("本月使用金额") + f"""</b>
                <div class="progress-bar">
                    <div class="progress" style="width: {usage_percent}%;">
                        <span class="progress-text">{usage_percent}%</span>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between;"><span>${rounded_usage}</span><span>${usage_limit}</span></div>
                """
        except requests.exceptions.ConnectTimeout:
            status_text = (
                STANDARD_ERROR_MSG + CONNECTION_TIMEOUT_MSG + ERROR_RETRIEVE_MSG
            )
            return status_text
        except requests.exceptions.ReadTimeout:
            status_text = STANDARD_ERROR_MSG + READ_TIMEOUT_MSG + ERROR_RETRIEVE_MSG
            return status_text
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.error(i18n("获取API使用情况失败:") + str(e))
            return STANDARD_ERROR_MSG + ERROR_RETRIEVE_MSG

    def set_token_upper_limit(self, new_upper_limit):
        pass

    @shared.state.switching_api_key  # 在不开启多账号模式的时候，这个装饰器不会起作用
    def _get_response(self, stream=False):
        openai_api_key = self.api_key
        system_prompt = self.system_prompt
        history = self.history
        logging.debug(colorama.Fore.YELLOW +
                      f"{history}" + colorama.Fore.RESET)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}",
        }

        if system_prompt is not None:
            history = [construct_system(system_prompt), *history]

        payload = {
            "model": self.model_name,
            "messages": history,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "n": self.n_choices,
            "stream": stream,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
        }

        if self.max_generation_token is not None:
            payload["max_tokens"] = self.max_generation_token
        if self.stop_sequence is not None:
            payload["stop"] = self.stop_sequence
        if self.logit_bias is not None:
            payload["logit_bias"] = self.logit_bias
        if self.user_identifier:
            payload["user"] = self.user_identifier

        if stream:
            timeout = TIMEOUT_STREAMING
        else:
            timeout = TIMEOUT_ALL

        # 如果有自定义的api-host，使用自定义host发送请求，否则使用默认设置发送请求
        if shared.state.completion_url != COMPLETION_URL:
            logging.info(f"使用自定义API URL: {shared.state.completion_url}")

        with retrieve_proxy():
            try:
                response = requests.post(
                    shared.state.completion_url,
                    headers=headers,
                    json=payload,
                    stream=stream,
                    timeout=timeout,
                )
            except:
                return None
        return response

    def _refresh_header(self):
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _get_billing_data(self, billing_url):
        with retrieve_proxy():
            response = requests.get(
                billing_url,
                headers=self.headers,
                timeout=TIMEOUT_ALL,
            )

        if response.status_code == 200:
            data = response.json()
            return data
        else:
            raise Exception(
                f"API request failed with status code {response.status_code}: {response.text}"
            )

    def _decode_chat_response(self, response):
        error_msg = ""
        for chunk in response.iter_lines():
            if chunk:
                chunk = chunk.decode()
                chunk_length = len(chunk)
                try:
                    chunk = json.loads(chunk[6:])
                except json.JSONDecodeError:
                    print(i18n("JSON解析错误,收到的内容: ") + f"{chunk}")
                    error_msg += chunk
                    continue
                if chunk_length > 6 and "delta" in chunk["choices"][0]:
                    if chunk["choices"][0]["finish_reason"] == "stop":
                        break
                    try:
                        yield chunk["choices"][0]["delta"]["content"]
                    except Exception as e:
                        # logging.error(f"Error: {e}")
                        continue
        if error_msg:
            raise Exception(error_msg)

    def set_key(self, new_access_key):
        ret = super().set_key(new_access_key)
        self._refresh_header()
        return ret


class ChatGLM_Client(BaseLLMModel):
    def __init__(self, model_name, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        from transformers import AutoTokenizer, AutoModel
        import torch
        global CHATGLM_TOKENIZER, CHATGLM_MODEL
        if CHATGLM_TOKENIZER is None or CHATGLM_MODEL is None:
            system_name = platform.system()
            model_path = None
            if os.path.exists("models"):
                model_dirs = os.listdir("models")
                if model_name in model_dirs:
                    model_path = f"models/{model_name}"
            if model_path is not None:
                model_source = model_path
            else:
                model_source = f"THUDM/{model_name}"
            CHATGLM_TOKENIZER = AutoTokenizer.from_pretrained(
                model_source, trust_remote_code=True
            )
            quantified = False
            if "int4" in model_name:
                quantified = True
            model = AutoModel.from_pretrained(
                model_source, trust_remote_code=True
            )
            if torch.cuda.is_available():
                # run on CUDA
                logging.info("CUDA is available, using CUDA")
                model = model.half().cuda()
            # mps加速还存在一些问题，暂时不使用
            elif system_name == "Darwin" and model_path is not None and not quantified:
                logging.info("Running on macOS, using MPS")
                # running on macOS and model already downloaded
                model = model.half().to("mps")
            else:
                logging.info("GPU is not available, using CPU")
                model = model.float()
            model = model.eval()
            CHATGLM_MODEL = model

    def _get_glm_style_input(self):
        history = [x["content"] for x in self.history]
        query = history.pop()
        logging.debug(colorama.Fore.YELLOW +
                      f"{history}" + colorama.Fore.RESET)
        assert (
            len(history) % 2 == 0
        ), f"History should be even length. current history is: {history}"
        history = [[history[i], history[i + 1]]
                   for i in range(0, len(history), 2)]
        return history, query

    def get_answer_at_once(self):
        history, query = self._get_glm_style_input()
        response, _ = CHATGLM_MODEL.chat(
            CHATGLM_TOKENIZER, query, history=history)
        return response, len(response)

    def get_answer_stream_iter(self):
        history, query = self._get_glm_style_input()
        for response, history in CHATGLM_MODEL.stream_chat(
            CHATGLM_TOKENIZER,
            query,
            history,
            max_length=self.token_upper_limit,
            top_p=self.top_p,
            temperature=self.temperature,
        ):
            yield response


class LLaMA_Client(BaseLLMModel):
    def __init__(
        self,
        model_name,
        lora_path=None,
        user_name=""
    ) -> None:
        super().__init__(model_name=model_name, user=user_name)
        from lmflow.datasets.dataset import Dataset
        from lmflow.pipeline.auto_pipeline import AutoPipeline
        from lmflow.models.auto_model import AutoModel
        from lmflow.args import ModelArguments, DatasetArguments, InferencerArguments

        self.max_generation_token = 1000
        self.end_string = "\n\n"
        # We don't need input data
        data_args = DatasetArguments(dataset_path=None)
        self.dataset = Dataset(data_args)
        self.system_prompt = ""

        global LLAMA_MODEL, LLAMA_INFERENCER
        if LLAMA_MODEL is None or LLAMA_INFERENCER is None:
            model_path = None
            if os.path.exists("models"):
                model_dirs = os.listdir("models")
                if model_name in model_dirs:
                    model_path = f"models/{model_name}"
            if model_path is not None:
                model_source = model_path
            else:
                model_source = f"decapoda-research/{model_name}"
                # raise Exception(f"models目录下没有这个模型: {model_name}")
            if lora_path is not None:
                lora_path = f"lora/{lora_path}"
            model_args = ModelArguments(model_name_or_path=model_source, lora_model_path=lora_path, model_type=None, config_overrides=None, config_name=None, tokenizer_name=None, cache_dir=None,
                                        use_fast_tokenizer=True, model_revision='main', use_auth_token=False, torch_dtype=None, use_lora=False, lora_r=8, lora_alpha=32, lora_dropout=0.1, use_ram_optimized_load=True)
            pipeline_args = InferencerArguments(
                local_rank=0, random_seed=1, deepspeed='configs/ds_config_chatbot.json', mixed_precision='bf16')

            with open(pipeline_args.deepspeed, "r") as f:
                ds_config = json.load(f)
            LLAMA_MODEL = AutoModel.get_model(
                model_args,
                tune_strategy="none",
                ds_config=ds_config,
            )
            LLAMA_INFERENCER = AutoPipeline.get_pipeline(
                pipeline_name="inferencer",
                model_args=model_args,
                data_args=data_args,
                pipeline_args=pipeline_args,
            )

    def _get_llama_style_input(self):
        history = []
        instruction = ""
        if self.system_prompt:
            instruction = (f"Instruction: {self.system_prompt}\n")
        for x in self.history:
            if x["role"] == "user":
                history.append(f"{instruction}Input: {x['content']}")
            else:
                history.append(f"Output: {x['content']}")
        context = "\n\n".join(history)
        context += "\n\nOutput: "
        return context

    def get_answer_at_once(self):
        context = self._get_llama_style_input()

        input_dataset = self.dataset.from_dict(
            {"type": "text_only", "instances": [{"text": context}]}
        )

        output_dataset = LLAMA_INFERENCER.inference(
            model=LLAMA_MODEL,
            dataset=input_dataset,
            max_new_tokens=self.max_generation_token,
            temperature=self.temperature,
        )

        response = output_dataset.to_dict()["instances"][0]["text"]
        return response, len(response)

    def get_answer_stream_iter(self):
        context = self._get_llama_style_input()
        partial_text = ""
        step = 1
        for _ in range(0, self.max_generation_token, step):
            input_dataset = self.dataset.from_dict(
                {"type": "text_only", "instances": [
                    {"text": context + partial_text}]}
            )
            output_dataset = LLAMA_INFERENCER.inference(
                model=LLAMA_MODEL,
                dataset=input_dataset,
                max_new_tokens=step,
                temperature=self.temperature,
            )
            response = output_dataset.to_dict()["instances"][0]["text"]
            if response == "" or response == self.end_string:
                break
            partial_text += response
            yield partial_text


class XMChat(BaseLLMModel):
    def __init__(self, api_key, user_name=""):
        super().__init__(model_name="xmchat", user=user_name)
        self.api_key = api_key
        self.session_id = None
        self.reset()
        self.image_bytes = None
        self.image_path = None
        self.xm_history = []
        self.url = "https://xmbot.net/web"
        self.last_conv_id = None

    def reset(self):
        self.session_id = str(uuid.uuid4())
        self.last_conv_id = None
        return [], "已重置"

    def image_to_base64(self, image_path):
        # 打开并加载图片
        img = Image.open(image_path)

        # 获取图片的宽度和高度
        width, height = img.size

        # 计算压缩比例，以确保最长边小于4096像素
        max_dimension = 2048
        scale_ratio = min(max_dimension / width, max_dimension / height)

        if scale_ratio < 1:
            # 按压缩比例调整图片大小
            new_width = int(width * scale_ratio)
            new_height = int(height * scale_ratio)
            img = img.resize((new_width, new_height), Image.ANTIALIAS)

        # 将图片转换为jpg格式的二进制数据
        buffer = BytesIO()
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(buffer, format='JPEG')
        binary_image = buffer.getvalue()

        # 对二进制数据进行Base64编码
        base64_image = base64.b64encode(binary_image).decode('utf-8')

        return base64_image

    def try_read_image(self, filepath):
        def is_image_file(filepath):
            # 判断文件是否为图片
            valid_image_extensions = [
                ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff"]
            file_extension = os.path.splitext(filepath)[1].lower()
            return file_extension in valid_image_extensions

        if is_image_file(filepath):
            logging.info(f"读取图片文件: {filepath}")
            self.image_bytes = self.image_to_base64(filepath)
            self.image_path = filepath
        else:
            self.image_bytes = None
            self.image_path = None

    def like(self):
        if self.last_conv_id is None:
            return "点赞失败，你还没发送过消息"
        data = {
            "uuid": self.last_conv_id,
            "appraise": "good"
        }
        requests.post(self.url, json=data)
        return "👍点赞成功，感谢反馈～"

    def dislike(self):
        if self.last_conv_id is None:
            return "点踩失败，你还没发送过消息"
        data = {
            "uuid": self.last_conv_id,
            "appraise": "bad"
        }
        requests.post(self.url, json=data)
        return "👎点踩成功，感谢反馈～"

    def prepare_inputs(self, real_inputs, use_websearch, files, reply_language, chatbot):
        fake_inputs = real_inputs
        display_append = ""
        limited_context = False
        return limited_context, fake_inputs, display_append, real_inputs, chatbot

    def handle_file_upload(self, files, chatbot):
        """if the model accepts multi modal input, implement this function"""
        if files:
            for file in files:
                if file.name:
                    logging.info(f"尝试读取图像: {file.name}")
                    self.try_read_image(file.name)
            if self.image_path is not None:
                chatbot = chatbot + [((self.image_path,), None)]
            if self.image_bytes is not None:
                logging.info("使用图片作为输入")
                # XMChat的一轮对话中实际上只能处理一张图片
                self.reset()
                conv_id = str(uuid.uuid4())
                data = {
                    "user_id": self.api_key,
                    "session_id": self.session_id,
                    "uuid": conv_id,
                    "data_type": "imgbase64",
                    "data": self.image_bytes
                }
                response = requests.post(self.url, json=data)
                response = json.loads(response.text)
                logging.info(f"图片回复: {response['data']}")
        return None, chatbot, None

    def get_answer_at_once(self):
        question = self.history[-1]["content"]
        conv_id = str(uuid.uuid4())
        self.last_conv_id = conv_id
        data = {
            "user_id": self.api_key,
            "session_id": self.session_id,
            "uuid": conv_id,
            "data_type": "text",
            "data": question
        }
        response = requests.post(self.url, json=data)
        try:
            response = json.loads(response.text)
            return response["data"], len(response["data"])
        except Exception as e:
            return response.text, len(response.text)


def get_model(
    model_name,
    lora_model_path=None,
    access_key=None,
    temperature=None,
    top_p=None,
    system_prompt=None,
    user_name=""
) -> BaseLLMModel:
    msg = i18n("模型设置为了：") + f" {model_name}"
    model_type = ModelType.get_type(model_name)
    lora_selector_visibility = False
    lora_choices = []
    dont_change_lora_selector = False
    if model_type != ModelType.OpenAI:
        config.local_embedding = True
    # del current_model.model
    model = None
    try:
        if model_type == ModelType.OpenAI:
            logging.info(f"正在加载OpenAI模型: {model_name}")
            model = OpenAIClient(
                model_name=model_name,
                api_key=access_key,
                system_prompt=system_prompt,
                temperature=temperature,
                top_p=top_p,
                user_name=user_name,
            )
        elif model_type == ModelType.ChatGLM:
            logging.info(f"正在加载ChatGLM模型: {model_name}")
            model = ChatGLM_Client(model_name, user_name=user_name)
        elif model_type == ModelType.LLaMA and lora_model_path == "":
            msg = f"现在请为 {model_name} 选择LoRA模型"
            logging.info(msg)
            lora_selector_visibility = True
            if os.path.isdir("lora"):
                lora_choices = get_file_names(
                    "lora", plain=True, filetypes=[""])
            lora_choices = ["No LoRA"] + lora_choices
        elif model_type == ModelType.LLaMA and lora_model_path != "":
            logging.info(f"正在加载LLaMA模型: {model_name} + {lora_model_path}")
            dont_change_lora_selector = True
            if lora_model_path == "No LoRA":
                lora_model_path = None
                msg += " + No LoRA"
            else:
                msg += f" + {lora_model_path}"
            model = LLaMA_Client(
                model_name, lora_model_path, user_name=user_name)
        elif model_type == ModelType.XMChat:
            if os.environ.get("XMCHAT_API_KEY") != "":
                access_key = os.environ.get("XMCHAT_API_KEY")
            model = XMChat(api_key=access_key, user_name=user_name)
        elif model_type == ModelType.StableLM:
            from .StableLM import StableLM_Client
            model = StableLM_Client(model_name, user_name=user_name)
        elif model_type == ModelType.MOSS:
            from .MOSS import MOSS_Client
            model = MOSS_Client(model_name, user_name=user_name)
        elif model_type == ModelType.Unknown:
            raise ValueError(f"未知模型: {model_name}")
        logging.info(msg)
        chatbot = gr.Chatbot.update(label=model_name)
    except Exception as e:
        logging.error(e)
        msg = f"{STANDARD_ERROR_MSG}: {e}"
    if dont_change_lora_selector:
        return model, msg, chatbot
    else:
        return model, msg, chatbot, gr.Dropdown.update(choices=lora_choices, visible=lora_selector_visibility)


if __name__ == "__main__":
    with open("config.json", "r") as f:
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
