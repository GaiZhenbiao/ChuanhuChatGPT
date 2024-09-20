import json
import logging
import textwrap
import uuid

import os
from groq import Groq
import gradio as gr
import PIL
import requests

from modules.presets import i18n

from ..index_func import construct_index
from ..utils import count_token, construct_system
from .base_model import BaseLLMModel


class Groq_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(
            model_name=model_name, 
            user=user_name, 
            config={
                "api_key": api_key
            }
        )
        self.client = Groq(
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url=self.api_host,
        )

    def _get_groq_style_input(self):
        messages = [construct_system(self.system_prompt), *self.history]
        return messages

    def get_answer_at_once(self):
        messages = self._get_groq_style_input()
        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model=self.model_name,
        )
        return chat_completion.choices[0].message.content, chat_completion.usage.total_tokens


    def get_answer_stream_iter(self):
        messages = self._get_groq_style_input()
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_generation_token,
            top_p=self.top_p,
            stream=True,
            stop=self.stop_sequence,
        )

        partial_text = ""
        for chunk in completion:
            partial_text += chunk.choices[0].delta.content or ""
            yield partial_text
