import json
import logging
import textwrap
import uuid

import google.generativeai as genai
import gradio as gr
import PIL
import requests

from modules.presets import i18n

from ..index_func import construct_index
from ..utils import count_token
from .base_model import BaseLLMModel


class GoogleGeminiClient(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name, config={"api_key": api_key})
        if "vision" in model_name.lower():
            self.multimodal = True
        else:
            self.multimodal = False
        self.image_paths = []

    def _get_gemini_style_input(self):
        self.history.extend([{"role": "image", "content": i} for i in self.image_paths])
        self.image_paths = []
        messages = []
        for item in self.history:
            if item["role"] == "image":
                messages.append(PIL.Image.open(item["content"]))
            else:
                messages.append(item["content"])
        return messages

    def to_markdown(self, text):
        text = text.replace("•", "  *")
        return textwrap.indent(text, "> ", predicate=lambda _: True)

    def handle_file_upload(self, files, chatbot, language):
        if files:
            if self.multimodal:
                for file in files:
                    if file.name:
                        self.image_paths.append(file.name)
                        chatbot = chatbot + [((file.name,), None)]
                return None, chatbot, None
            else:
                construct_index(self.api_key, file_src=files)
                status = i18n("索引构建完成")
                return gr.update(), chatbot, status

    def get_answer_at_once(self):
        genai.configure(api_key=self.api_key)
        messages = self._get_gemini_style_input()
        model = genai.GenerativeModel(self.model_name)
        response = model.generate_content(messages)
        try:
            return self.to_markdown(response.text), len(response.text)
        except ValueError:
            return (
                i18n("由于下面的原因，Google 拒绝返回 Gemini 的回答：\n\n")
                + str(response.prompt_feedback),
                0,
            )

    def get_answer_stream_iter(self):
        genai.configure(api_key=self.api_key)
        messages = self._get_gemini_style_input()
        model = genai.GenerativeModel(self.model_name)
        response = model.generate_content(messages, stream=True)
        partial_text = ""
        for i in response:
            response = i.text
            partial_text += response
            yield partial_text
        self.all_token_counts[-1] = count_token(partial_text)
        yield partial_text
