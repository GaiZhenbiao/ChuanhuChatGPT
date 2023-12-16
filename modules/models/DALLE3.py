import logging
from .base_model import BaseLLMModel
from .. import shared
import requests
from ..presets import *
from ..config import retrieve_proxy, sensitive_id

class OpenAI_DALLE3_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        self.api_key = api_key
        self._refresh_header()

    def _get_dalle3_prompt(self):
        prompt = self.history[-1]["content"]
        if prompt.endswith("--raw"):
            prompt = "I NEED to test how the tool works with extremely simple prompts. DO NOT add any detail, just use it AS-IS:" + prompt
        return prompt

    def get_answer_at_once(self, stream=False):
        prompt = self._get_dalle3_prompt()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "quality": "standard",
        }
        if stream:
            timeout = TIMEOUT_STREAMING
        else:
            timeout = TIMEOUT_ALL

        if shared.state.images_completion_url != IMAGES_COMPLETION_URL:
            logging.debug(f"使用自定义API URL: {shared.state.images_completion_url}")

        with retrieve_proxy():
            try:
                response = requests.post(
                    shared.state.images_completion_url,
                    headers=headers,
                    json=payload,
                    stream=stream,
                    timeout=timeout,
                )
                response.raise_for_status()  # 根据HTTP状态码引发异常
                response_data = response.json()
                image_url = response_data['data'][0]['url']
                img_tag = f'<!-- S O PREFIX --><a data-fancybox="gallery" target="_blank" href="{image_url}"><img src="{image_url}" /></a><!-- E O PREFIX -->'
                revised_prompt = response_data['data'][0].get('revised_prompt', '')
                return img_tag + revised_prompt, 0
            except requests.exceptions.RequestException as e:
                return str(e), 0

    def _refresh_header(self):
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {sensitive_id}",
        }