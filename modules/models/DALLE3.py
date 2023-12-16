import re
import json
import openai
from openai import OpenAI
from .base_model import BaseLLMModel
from .. import shared
from ..config import retrieve_proxy


class OpenAI_DALLE3_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        self.api_key = api_key

    def _get_dalle3_prompt(self):
        prompt = self.history[-1]["content"]
        if prompt.endswith("--raw"):
            prompt = "I NEED to test how the tool works with extremely simple prompts. DO NOT add any detail, just use it AS-IS:" + prompt
        return prompt

    @shared.state.switching_api_key
    def get_answer_at_once(self):
        prompt = self._get_dalle3_prompt()
        with retrieve_proxy():
            client = OpenAI(api_key=openai.api_key)
            try:
                response = client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
            except openai.BadRequestError as e:
                msg = str(e)
                match = re.search(r"'message': '([^']*)'", msg)
                return match.group(1), 0
        return f'<!-- S O PREFIX --><a data-fancybox="gallery" target="_blank" href="{response.data[0].url}"><img src="{response.data[0].url}" /></a><!-- E O PREFIX -->{response.data[0].revised_prompt}', 0
