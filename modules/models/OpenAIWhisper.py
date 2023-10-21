import json
import logging
import os
from enum import Enum

import requests

from .base_model import BaseLLMModel
from .. import shared
from ..config import retrieve_proxy
from ..presets import TRANSCRIPTION_URL, TRANSLATION_URL, TIMEOUT_ALL


class WhisperMode(Enum):
    Transcription = "transcriptions"
    Translation = "translations"


class OpenAI_Whisper_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, system_prompt="", mode=WhisperMode.Transcription.value, temperature=0, user_name=""):
        super().__init__(system_prompt=system_prompt, model_name=model_name, temperature=temperature, user=user_name)
        self.api_key = api_key
        self.model_name = self.model_name.lower()
        self.mode = mode.lower()
        if self.model_name not in ["whisper-1"]:
            raise Exception("OpenAI whisper only has \"whisper-1\" model available.")
        if self.mode not in [WhisperMode.Transcription.value, WhisperMode.Translation.value]:
            raise Exception(f"To use OpenAI whisper, Please fill in mode either \"{WhisperMode.Transcription.value}\" or \"{WhisperMode.Translation.value}\"")

    def look_at_file(self, filepath):
        def look_at_file_extension(filepath):
            valid_extensions = [
                ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"
            ]
            file_extension = os.path.splitext(filepath)[1].lower()
            return file_extension in valid_extensions

        if look_at_file_extension(filepath):
            with open(filepath, "rb") as tf:
                self.audio_bytes = tf.read()
            if len(self.audio_bytes) >= 26214400:
                raise Exception("File is too large, choose one smaller than 25 megabytes.")
            self.audio_path = filepath

    def handle_file_upload(self, files, chatbot, language):
        if files:
            for file in files:
                self.look_at_file(file)
                if self.audio_path is not None:
                    chatbot = chatbot + [((self.audio_path,), None)]
                if self.audio_bytes is not None:
                    logging.info(f"输入音频文件：{self.audio_path}")
                break

        return None, chatbot, None

    def _get_response(self):
        openai_api_key = self.api_key
        prompt = self.system_prompt
        temperature = self.temperature
        mode = self.mode
        headers = {
            "Content-Type": "multipart/form-data",
            "Authorization": f"Bearer {openai_api_key}",
        }
        payload = {
            "file": self.audio_bytes,
            "model": self.model_name,
            "prompt": prompt,
            "response_format": "json",
            "temperature": temperature
        }
        with retrieve_proxy():
            if mode == WhisperMode.Transcription.value:
                url = shared.state.transcription_url
                if url != TRANSCRIPTION_URL:
                    logging.debug(f"使用自定义API URL: {url}")
            elif mode == WhisperMode.Translation.value:
                url = shared.state.translation_url
                if url != TRANSLATION_URL:
                    logging.debug(f"使用自定义API URL: {url}")
            try:
                response = requests.post(
                    url=url,
                    headers=headers,
                    data=payload,
                    stream=False,
                    timeout=TIMEOUT_ALL
                )
            except Exception as e:
                import traceback
                logging.error(e)
                traceback.print_exc()
                return None
        return response

    @shared.state.switching_api_key
    def get_answer_at_once(self):
        response = self._get_response()
        response = json.loads(response.text)
        return response["text"], 0

    def reset(self, remain_system_prompt=False):
        self.audio_bytes = None
        self.audio_path = None
        return super().reset()
