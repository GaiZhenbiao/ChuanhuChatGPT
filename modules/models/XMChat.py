from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from io import BytesIO

import requests
from PIL import Image

from ..index_func import *
from ..presets import *
from ..utils import *
from .base_model import BaseLLMModel


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
        if self.api_host is not None:
            self.url = self.api_host
        self.last_conv_id = None

    def reset(self, remain_system_prompt=False):
        self.session_id = str(uuid.uuid4())
        self.last_conv_id = None
        return super().reset()

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
            img = img.resize((new_width, new_height), Image.LANCZOS)

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
            return i18n("msg.xmchat.like_no_message")
        data = {
            "uuid": self.last_conv_id,
            "appraise": "good"
        }
        requests.post(self.url, json=data)
        return i18n("msg.xmchat.like_ok")

    def dislike(self):
        if self.last_conv_id is None:
            return i18n("msg.xmchat.dislike_no_message")
        data = {
            "uuid": self.last_conv_id,
            "appraise": "bad"
        }
        requests.post(self.url, json=data)
        return i18n("msg.xmchat.dislike_ok")

    def prepare_inputs(self, real_inputs, use_websearch, files, reply_language, chatbot):
        fake_inputs = real_inputs
        display_append = ""
        limited_context = False
        return limited_context, fake_inputs, display_append, real_inputs, chatbot

    def handle_file_upload(self, files, chatbot, language):
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
