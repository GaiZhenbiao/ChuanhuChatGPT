import logging
import os

import tempfile
import time
from enum import Enum

import gradio as gr
import openai

from .base_model import BaseLLMModel
from .. import shared
from ..config import retrieve_proxy
from ..presets import TRANSCRIPTION_URL, TRANSLATION_URL

openai_whisper_temp_folder = os.getenv("OPENAI_WHISPER_TEMP_FOLDER")

class WhisperMode(Enum):
    Transcription = "transcriptions"
    Translation = "translations"

valid_extensions = [".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"]

class OpenAI_Whisper_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, system_prompt="", temperature=0, user_name=""):
        super().__init__(system_prompt=system_prompt, model_name=model_name, temperature=temperature, user=user_name)
        self.api_key = api_key
        self.model_name = self.model_name.lower()
        self.audio_path = None
        if self.model_name not in ["whisper-1"]:
            raise Exception("OpenAI whisper only has \"whisper-1\" model available.")
        if openai_whisper_temp_folder:
            temp = openai_whisper_temp_folder
            if user_name:
                temp = os.path.join(temp, user_name)
            if not os.path.exists(temp):
                os.makedirs(temp)
            self.temp_path = tempfile.mkdtemp(dir=temp)
            logging.info(f"OpenAI Whisper model temporary directory: {self.temp_path}")
        else:
            self.temp_path = None

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
                chatbot += [((self.audio_path,), None)]
                logging.info(f"Uploaded audio file: {self.audio_path}")

        return None, chatbot, None

    def _get_response(self):
        openai_api_key = self.api_key
        prompt = self.system_prompt
        temperature = self.temperature
        content = self.history[-1]["content"].lower().split()
        mode = content[0]
        response_format = content[1] if len(content) >= 2 else "json"

        # Experimental: Reuse the last uploaded file without re-uploading again. How to fetch "chatbot" object?

        if (len(content) < 1
                or mode not in [c.value for c in WhisperMode]
                or response_format not in ["json", "text", "srt", "vtt"]
                or self.audio_path is None):
            return self.get_help()

        with retrieve_proxy():
            try:
                if mode == WhisperMode.Transcription.value:
                    url = shared.state.transcription_url
                    if url != TRANSCRIPTION_URL:
                        logging.debug(f"使用自定义API URL: {url}")
                    response = openai.Audio.transcribe(model=self.model_name,
                                                       api_base=shared.state.openai_api_base,
                                                       api_key=openai_api_key,
                                                       file=open(self.audio_path, "rb"),
                                                       prompt=prompt, response_format=response_format, temperature=temperature)
                elif mode == WhisperMode.Translation.value:
                    url = shared.state.translation_url
                    if url != TRANSLATION_URL:
                        logging.debug(f"使用自定义API URL: {url}")
                    response = openai.Audio.translate(model=self.model_name,
                                                      api_base=shared.state.openai_api_base,
                                                      api_key=openai_api_key,
                                                      file=open(self.audio_path, "rb"),
                                                      prompt=prompt, response_format=response_format, temperature=temperature)
                result = response if isinstance(response, str) else response.text

                txtstr = ""
                if self.temp_path:
                    txtstr = f"{self.temp_path}/{self.model_name}-{str(int(time.time() * 1000))}.txt"
                    with open(txtstr, "w") as savetext:
                        savetext.write(result)
                result = result.replace("\n", "\n\n")
                if txtstr:
                    result += f"\n\n[Click to download file](/file={txtstr})"

            except Exception as e:
                import traceback
                logging.error(e)
                traceback.print_exc()
                return traceback.format_exc()
        return result

    def get_help(self):
        return f"""
To use OpenAI whisper, Please select a mode either `{WhisperMode.Transcription.value}` or `{WhisperMode.Translation.value}`

Example:

Get transcription: `{WhisperMode.Transcription.value}`

Get transcription in `srt` format: `{WhisperMode.Transcription.value} srt`

Get translation: `{WhisperMode.Translation.value}`

Get translation in `vtt` format: `{WhisperMode.Translation.value} vtt`

Please upload an audio file. These extensions are supported: `{' '.join(valid_extensions)}`.

Due to OpenAI's limitation, file size must be less than 25 megabytes.

Refer to https://platform.openai.com/docs/guides/speech-to-text for more info.
        """

    @shared.state.switching_api_key
    def get_answer_at_once(self):
        return self._get_response(), 0

    def token_message(self, token_lst=None):
        return ""

    def reset(self, remain_system_prompt=False):
        self.audio_path = None
        return super().reset(remain_system_prompt)
