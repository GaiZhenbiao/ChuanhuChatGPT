from __future__ import annotations
from typing import TYPE_CHECKING, List

import logging
import json
import commentjson as cjson
import os
import sys
import requests
import urllib3

from tqdm import tqdm
import colorama
from duckduckgo_search import ddg
import asyncio
import aiohttp
from enum import Enum

from .presets import *
from .llama_func import *
from .utils import *
from . import shared
from .config import retrieve_proxy
from .base_model import BaseLLMModel, ModelType


class OpenAIClient(BaseLLMModel):
    def __init__(
        self,
        model_name,
        api_key,
        system_prompt=INITIAL_SYSTEM_PROMPT,
        temperature=1.0,
        top_p=1.0,
    ) -> None:
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            top_p=top_p,
            system_prompt=system_prompt,
        )
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

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
            last_day_of_month = get_last_day_of_month(curr_time).strftime("%Y-%m-%d")
            first_day_of_month = curr_time.replace(day=1).strftime("%Y-%m-%d")
            usage_url = f"{shared.state.usage_api_url}?start_date={first_day_of_month}&end_date={last_day_of_month}"
            try:
                usage_data = self._get_billing_data(usage_url)
            except Exception as e:
                logging.error(f"获取API使用情况失败:" + str(e))
                return f"**获取API使用情况失败**"
            rounded_usage = "{:.5f}".format(usage_data["total_usage"] / 100)
            return f"**本月使用金额** \u3000 ${rounded_usage}"
        except requests.exceptions.ConnectTimeout:
            status_text = (
                STANDARD_ERROR_MSG + CONNECTION_TIMEOUT_MSG + ERROR_RETRIEVE_MSG
            )
            return status_text
        except requests.exceptions.ReadTimeout:
            status_text = STANDARD_ERROR_MSG + READ_TIMEOUT_MSG + ERROR_RETRIEVE_MSG
            return status_text
        except Exception as e:
            logging.error(f"获取API使用情况失败:" + str(e))
            return STANDARD_ERROR_MSG + ERROR_RETRIEVE_MSG

    @shared.state.switching_api_key  # 在不开启多账号模式的时候，这个装饰器不会起作用
    def _get_response(self, stream=False):
        openai_api_key = self.api_key
        system_prompt = self.system_prompt
        history = self.history
        logging.debug(colorama.Fore.YELLOW + f"{history}" + colorama.Fore.RESET)
        temperature = self.temperature
        top_p = self.top_p
        selected_model = self.model_name
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}",
        }

        if system_prompt is not None:
            history = [construct_system(system_prompt), *history]

        payload = {
            "model": selected_model,
            "messages": history,  # [{"role": "user", "content": f"{inputs}"}],
            "temperature": temperature,  # 1.0,
            "top_p": top_p,  # 1.0,
            "n": 1,
            "stream": stream,
            "presence_penalty": 0,
            "frequency_penalty": 0,
            "max_tokens": self.max_generation_token,
        }
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

    def _get_billing_data(self, usage_url):
        with retrieve_proxy():
            response = requests.get(
                usage_url,
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
        for chunk in response.iter_lines():
            if chunk:
                chunk = chunk.decode()
                chunk_length = len(chunk)
                try:
                    chunk = json.loads(chunk[6:])
                except json.JSONDecodeError:
                    print(f"JSON解析错误,收到的内容: {chunk}")
                    continue
                if chunk_length > 6 and "delta" in chunk["choices"][0]:
                    if chunk["choices"][0]["finish_reason"] == "stop":
                        break
                    try:
                        yield chunk["choices"][0]["delta"]["content"]
                    except Exception as e:
                        # logging.error(f"Error: {e}")
                        continue


def get_model(
    model_name, access_key=None, temperature=None, top_p=None, system_prompt=None
) -> BaseLLMModel:
    msg = f"模型设置为了： {model_name}"
    logging.info(msg)
    model_type = ModelType.get_type(model_name)
    if model_type == ModelType.OpenAI:
        model = OpenAIClient(
            model_name=model_name,
            api_key=access_key,
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
        )
    return model, msg


if __name__ == "__main__":
    with open("config.json", "r") as f:
        openai_api_key = cjson.load(f)["openai_api_key"]
    client = OpenAIClient("gpt-3.5-turbo", openai_api_key)
    chatbot = []
    stream = False
    # 测试账单功能
    print(colorama.Back.GREEN + "测试账单功能" + colorama.Back.RESET)
    print(client.billing_info())
    # 测试问答
    print(colorama.Back.GREEN + "测试问答" + colorama.Back.RESET)
    question = "巴黎是中国的首都吗？"
    for i in client.predict(inputs=question, chatbot=chatbot, stream=stream):
        print(i)
    print(f"测试问答后history : {client.history}")
    # 测试记忆力
    print(colorama.Back.GREEN + "测试记忆力" + colorama.Back.RESET)
    question = "我刚刚问了你什么问题？"
    for i in client.predict(inputs=question, chatbot=chatbot, stream=stream):
        print(i)
    print(f"测试记忆力后history : {client.history}")
    # 测试重试功能
    print(colorama.Back.GREEN + "测试重试功能" + colorama.Back.RESET)
    for i in client.retry(chatbot=chatbot, stream=stream):
        print(i)
    print(f"重试后history : {client.history}")
    # # 测试总结功能
    # print(colorama.Back.GREEN + "测试总结功能" + colorama.Back.RESET)
    # chatbot, msg = client.reduce_token_size(chatbot=chatbot)
    # print(chatbot, msg)
    # print(f"总结后history: {client.history}")
