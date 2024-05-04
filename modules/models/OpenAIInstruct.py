from openai import OpenAI

client = OpenAI()
from .base_model import BaseLLMModel
from .. import shared
from ..config import retrieve_proxy


class OpenAI_Instruct_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name, config={"api_key": api_key})

    def _get_instruct_style_input(self):
        return "".join([item["content"] for item in self.history])

    @shared.state.switching_api_key
    def get_answer_at_once(self):
        prompt = self._get_instruct_style_input()
        with retrieve_proxy():
            response = client.completions.create(
                model=self.model_name,
                prompt=prompt,
                temperature=self.temperature,
                top_p=self.top_p,
            )
        return response.choices[0].text.strip(), response.usage.total_tokens
