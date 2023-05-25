import json
import os

import colorama
import requests
import logging

from modules.models.base_model import BaseLLMModel
from modules.presets import STANDARD_ERROR_MSG, GENERAL_ERROR_MSG, TIMEOUT_STREAMING, TIMEOUT_ALL, i18n

group_id = os.environ.get("MINIMAX_GROUP_ID", "")


class MiniMax_Client(BaseLLMModel):
    """
    MiniMax Client
    接口文档见 https://api.minimax.chat/document/guides/chat
    """

    def __init__(self, model_name, api_key, user_name="", system_prompt=None):
        super().__init__(model_name=model_name, user=user_name)
        self.url = f'https://api.minimax.chat/v1/text/chatcompletion?GroupId={group_id}'
        self.history = []
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def get_answer_at_once(self):
        # minimax temperature is (0,1] and base model temperature is [0,2], and yuan 0.9 == base 1 so need to convert
        temperature = self.temperature * 0.9 if self.temperature <= 1 else 0.9 + (self.temperature - 1) / 10

        request_body = {
            "model": self.model_name.replace('minimax-', ''),
            "temperature": temperature,
            "skip_info_mask": True,
            'messages': [{"sender_type": "USER", "text": self.history[-1]['content']}]
        }
        if self.n_choices:
            request_body['beam_width'] = self.n_choices
        if self.system_prompt:
            request_body['prompt'] = self.system_prompt
        if self.max_generation_token:
            request_body['tokens_to_generate'] = self.max_generation_token
        if self.top_p:
            request_body['top_p'] = self.top_p

        response = requests.post(self.url, headers=self.headers, json=request_body)

        res = response.json()
        answer = res['reply']
        total_token_count = res["usage"]["total_tokens"]
        return answer, total_token_count

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

    def _get_response(self, stream=False):
        minimax_api_key = self.api_key
        history = self.history
        logging.debug(colorama.Fore.YELLOW +
                      f"{history}" + colorama.Fore.RESET)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {minimax_api_key}",
        }

        temperature = self.temperature * 0.9 if self.temperature <= 1 else 0.9 + (self.temperature - 1) / 10

        messages = []
        for msg in self.history:
            if msg['role'] == 'user':
                messages.append({"sender_type": "USER", "text": msg['content']})
            else:
                messages.append({"sender_type": "BOT", "text": msg['content']})

        request_body = {
            "model": self.model_name.replace('minimax-', ''),
            "temperature": temperature,
            "skip_info_mask": True,
            'messages': messages
        }
        if self.n_choices:
            request_body['beam_width'] = self.n_choices
        if self.system_prompt:
            lines = self.system_prompt.splitlines()
            if lines[0].find(":") != -1 and len(lines[0]) < 20:
                request_body["role_meta"] = {
                    "user_name": lines[0].split(":")[0],
                    "bot_name": lines[0].split(":")[1]
                }
                lines.pop()
            request_body["prompt"] = "\n".join(lines)
        if self.max_generation_token:
            request_body['tokens_to_generate'] = self.max_generation_token
        else:
            request_body['tokens_to_generate'] = 512
        if self.top_p:
            request_body['top_p'] = self.top_p

        if stream:
            timeout = TIMEOUT_STREAMING
            request_body['stream'] = True
            request_body['use_standard_sse'] = True
        else:
            timeout = TIMEOUT_ALL
        try:
            response = requests.post(
                self.url,
                headers=headers,
                json=request_body,
                stream=stream,
                timeout=timeout,
            )
        except:
            return None

        return response

    def _decode_chat_response(self, response):
        error_msg = ""
        for chunk in response.iter_lines():
            if chunk:
                chunk = chunk.decode()
                chunk_length = len(chunk)
                print(chunk)
                try:
                    chunk = json.loads(chunk[6:])
                except json.JSONDecodeError:
                    print(i18n("JSON解析错误,收到的内容: ") + f"{chunk}")
                    error_msg += chunk
                    continue
                if chunk_length > 6 and "delta" in chunk["choices"][0]:
                    if "finish_reason" in chunk["choices"][0] and chunk["choices"][0]["finish_reason"] == "stop":
                        self.all_token_counts.append(chunk["usage"]["total_tokens"] - sum(self.all_token_counts))
                        break
                    try:
                        yield chunk["choices"][0]["delta"]
                    except Exception as e:
                        logging.error(f"Error: {e}")
                        continue
        if error_msg:
            try:
                error_msg = json.loads(error_msg)
                if 'base_resp' in error_msg:
                    status_code = error_msg['base_resp']['status_code']
                    status_msg = error_msg['base_resp']['status_msg']
                    raise Exception(f"{status_code} - {status_msg}")
            except json.JSONDecodeError:
                pass
            raise Exception(error_msg)
