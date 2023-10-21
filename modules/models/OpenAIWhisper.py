import logging
import os
from enum import Enum

import openai
import gradio as gr

from .base_model import BaseLLMModel
from .. import shared
from ..config import retrieve_proxy
from ..presets import TRANSCRIPTION_URL, TRANSLATION_URL, TIMEOUT_ALL


class WhisperMode(Enum):
    Transcription = "transcriptions"
    Translation = "translations"

valid_extensions = [".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"]

class OpenAI_Whisper_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, system_prompt="", temperature=0, user_name=""):
        super().__init__(system_prompt=system_prompt, model_name=model_name, temperature=temperature, user=user_name)
        self.api_key = api_key
        self.model_name = self.model_name.lower()
        self.audio_path = None
        if self.model_name not in ["whisper-1"]:
            raise Exception("OpenAI whisper only has \"whisper-1\" model available.")

    def _look_at_file(self, filepath):
        def look_at_file_extension(filepath):
            file_extension = os.path.splitext(filepath)[1].lower()
            return file_extension in valid_extensions

        mark = True
        if look_at_file_extension(filepath):
            with open(filepath, "rb") as tf:
                audio_bytes = tf.read()
            if len(audio_bytes) >= 26214400:
                gr.Warning("File is too large, choose another one smaller than 25 megabytes.")
                mark = False
            else:
                self.audio_path = filepath
                logging.info(f"Reading audio file: {filepath}")
        else:
            mark = False
        if not mark:
            self.audio_path = None

    def handle_file_upload(self, files, chatbot, language):
        if files:
            file = files[-1]
            if len(files) > 1:
                gr.Warning("Only one file will be used. Please upload a single file instead.")
            self._look_at_file(file.name)
            if self.audio_path is not None:
                chatbot = chatbot + [((self.audio_path,), None)]
                logging.info(f"Uploaded audio file: {self.audio_path}")

        return None, chatbot, None

    def _get_response(self):
        openai_api_key = self.api_key
        prompt = self.system_prompt
        temperature = self.temperature
        mode = self.history[-1]["content"].lower()
        if mode not in [c.value for c in WhisperMode]:
            return f"To use OpenAI whisper, Please enter either \"{WhisperMode.Transcription.value}\" or \"{WhisperMode.Translation.value}\""
        if self.audio_path is None:
            return f"Please upload an audio file. These extensions are supported: `{' '.join(valid_extensions)}.`\n\nDue to OpenAI's limitation, file size must be less than 25 megabytes. Refer to [OpenAI API docs](https://platform.openai.com/docs/guides/speech-to-text) for more info."

        with retrieve_proxy():
            try:
                if mode == WhisperMode.Transcription.value:
                    url = shared.state.transcription_url
                    if url != TRANSCRIPTION_URL:
                        logging.debug(f"使用自定义API URL: {url}")
                    response = openai.Audio.transcribe(model=self.model_name, api_base=shared.state.openai_api_base, api_key=openai_api_key,
                                                       file=open(self.audio_path, "rb"),
                                                       prompt=prompt, response_format="json", temperature=temperature)
                elif mode == WhisperMode.Translation.value:
                    url = shared.state.translation_url
                    if url != TRANSLATION_URL:
                        logging.debug(f"使用自定义API URL: {url}")
                    response = openai.Audio.translate(model=self.model_name, api_base=shared.state.openai_api_base,
                                                      api_key=openai_api_key,
                                                      file=open(self.audio_path, "rb"),
                                                      prompt=prompt, response_format="json", temperature=temperature)
                result = response.text
            except Exception as e:
                import traceback
                logging.error(e)
                traceback.print_exc()
                return traceback.format_exc()
        return result

    @shared.state.switching_api_key
    def get_answer_at_once(self):
        return self._get_response(), 0

    def auto_name_chat_history(self, name_chat_method, user_question, chatbot, user_name, single_turn_checkbox):
        pass

    def reset(self, remain_system_prompt=False):
        self.audio_path = None
        return super().reset()
