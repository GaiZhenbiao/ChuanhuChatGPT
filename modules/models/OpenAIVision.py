from __future__ import annotations

import json
import logging
import traceback
import base64
from math import ceil

import colorama
import requests
from io import BytesIO
import uuid

import requests
from PIL import Image

from .. import shared
from ..config import retrieve_proxy, sensitive_id, usage_limit
from ..index_func import *
from ..presets import *
from ..utils import *
from .base_model import BaseLLMModel


class OpenAIVisionClient(BaseLLMModel):
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
        self.image_token = 0
        self.api_key = api_key
        self.need_api_key = True
        self.max_generation_token = 4096
        self.images = []
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

    def try_read_image(self, filepath):
        def is_image_file(filepath):
            # 判断文件是否为图片
            valid_image_extensions = [
                ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff"]
            file_extension = os.path.splitext(filepath)[1].lower()
            return file_extension in valid_image_extensions
        def image_to_base64(image_path):
            # 打开并加载图片
            img = Image.open(image_path)

            # 获取图片的宽度和高度
            width, height = img.size

            # 计算压缩比例，以确保最长边小于4096像素
            max_dimension = 2048
            scale_ratio = min(max_dimension / width, max_dimension / height)

            if scale_ratio < 1:
                # 按压缩比例调整图片大小
                width = int(width * scale_ratio)
                height = int(height * scale_ratio)
                img = img.resize((width, height), Image.LANCZOS)
            # 使用新的宽度和高度计算图片的token数量
            self.image_token = self.count_image_tokens(width, height)

            # 将图片转换为jpg格式的二进制数据
            buffer = BytesIO()
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(buffer, format='JPEG')
            binary_image = buffer.getvalue()

            # 对二进制数据进行Base64编码
            base64_image = base64.b64encode(binary_image).decode('utf-8')

            return base64_image

        if is_image_file(filepath):
            logging.info(f"读取图片文件: {filepath}")
            base64_image = image_to_base64(filepath)
            self.images.append({
                "path": filepath,
                "base64": base64_image,
            })

    def handle_file_upload(self, files, chatbot, language):
        """if the model accepts multi modal input, implement this function"""
        if files:
            for file in files:
                if file.name:
                    self.try_read_image(file.name)
        if self.images is not None:
                chatbot = chatbot + [([image["path"] for image in self.images], None)]
        return None, chatbot, None

    def prepare_inputs(self, real_inputs, use_websearch, files, reply_language, chatbot):
        fake_inputs = real_inputs
        display_append = ""
        limited_context = False
        return limited_context, fake_inputs, display_append, real_inputs, chatbot


    def count_token(self, user_input):
        input_token_count = count_token(construct_user(user_input))
        if self.system_prompt is not None and len(self.all_token_counts) == 0:
            system_prompt_token_count = count_token(
                construct_system(self.system_prompt)
            )
            return input_token_count + system_prompt_token_count
        return input_token_count

    def count_image_tokens(self, width: int, height: int):
        h = ceil(height / 512)
        w = ceil(width / 512)
        n = w * h
        total = 85 + 170 * n
        return total

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
                # logging.error(f"获取API使用情况失败: " + str(e))
                if "Invalid authorization header" in str(e):
                    return i18n("**获取API使用情况失败**，需在填写`config.json`中正确填写sensitive_id")
                elif "Incorrect API key provided: sess" in str(e):
                    return i18n("**获取API使用情况失败**，sensitive_id错误或已过期")
                return i18n("**获取API使用情况失败**")
            # rounded_usage = "{:.5f}".format(usage_data["total_usage"] / 100)
            rounded_usage = round(usage_data["total_usage"] / 100, 5)
            usage_percent = round(usage_data["total_usage"] / usage_limit, 2)
            from ..webui import get_html

            # return i18n("**本月使用金额** ") + f"\u3000 ${rounded_usage}"
            return get_html("billing_info.html").format(
                    label = i18n("本月使用金额"),
                    usage_percent = usage_percent,
                    rounded_usage = rounded_usage,
                    usage_limit = usage_limit
                )
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

    @shared.state.switching_api_key  # 在不开启多账号模式的时候，这个装饰器不会起作用
    def _get_response(self, stream=False):
        openai_api_key = self.api_key
        system_prompt = self.system_prompt
        history = self.history
        if self.images:
            self.history[-1]["content"] = [
                {"type": "text", "text": self.history[-1]["content"]},
                *[{"type": "image_url", "image_url": "data:image/jpeg;base64,"+image["base64"]} for image in self.images]
            ]
            self.images = []
            # 添加图片token到总计数中
            self.all_token_counts[-1] += self.image_token
            self.image_token = 0

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
            "max_tokens": 4096
        }

        if self.stop_sequence is not None:
            payload["stop"] = self.stop_sequence
        if self.logit_bias is not None:
            payload["logit_bias"] = self.encoded_logit_bias()
        if self.user_identifier:
            payload["user"] = self.user_identifier

        if stream:
            timeout = TIMEOUT_STREAMING
        else:
            timeout = TIMEOUT_ALL

        # 如果有自定义的api-host，使用自定义host发送请求，否则使用默认设置发送请求
        if shared.state.chat_completion_url != CHAT_COMPLETION_URL:
            logging.debug(f"使用自定义API URL: {shared.state.chat_completion_url}")

        with retrieve_proxy():
            try:
                response = requests.post(
                    shared.state.chat_completion_url,
                    headers=headers,
                    json=payload,
                    stream=stream,
                    timeout=timeout,
                )
            except:
                traceback.print_exc()
                return None
        return response

    def _refresh_header(self):
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {sensitive_id}",
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
                except:
                    print(i18n("JSON解析错误,收到的内容: ") + f"{chunk}")
                    error_msg += chunk
                    continue
                try:
                    if chunk_length > 6 and "delta" in chunk["choices"][0]:
                        if "finish_details" in chunk["choices"][0]:
                            finish_reason = chunk["choices"][0]["finish_details"]
                        elif "finish_reason" in chunk["choices"][0]:
                            finish_reason = chunk["choices"][0]["finish_reason"]
                        else:
                            finish_reason = chunk["finish_details"]
                        if finish_reason == "stop":
                            break
                        try:
                            yield chunk["choices"][0]["delta"]["content"]
                        except Exception as e:
                            # logging.error(f"Error: {e}")
                            continue
                except:
                    traceback.print_exc()
                    print(f"ERROR: {chunk}")
                    continue
        if error_msg and not error_msg=="data: [DONE]":
            raise Exception(error_msg)

    def set_key(self, new_access_key):
        ret = super().set_key(new_access_key)
        self._refresh_header()
        return ret

    def _single_query_at_once(self, history, temperature=1.0):
        timeout = TIMEOUT_ALL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "temperature": f"{temperature}",
        }
        payload = {
            "model": self.model_name,
            "messages": history,
        }
        # 如果有自定义的api-host，使用自定义host发送请求，否则使用默认设置发送请求
        if shared.state.chat_completion_url != CHAT_COMPLETION_URL:
            logging.debug(f"使用自定义API URL: {shared.state.chat_completion_url}")

        with retrieve_proxy():
            response = requests.post(
                shared.state.chat_completion_url,
                headers=headers,
                json=payload,
                stream=False,
                timeout=timeout,
            )

        return response
