
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
from ..presets import *
from ..utils import *

from .base_model import BaseLLMModel


class Claude_Client(BaseLLMModel):
    def __init__(self, model_name, api_secret) -> None:
        super().__init__(model_name=model_name)
        self.api_secret = api_secret
        if None in [self.api_secret]:
            raise Exception("请在配置文件或者环境变量中设置Claude的API Secret")
        self.claude_client = Anthropic(api_key=self.api_secret)


    def get_answer_stream_iter(self):
        system_prompt = self.system_prompt
        history = self.history
        if system_prompt is not None:
            history = [construct_system(system_prompt), *history]

        completion = self.claude_client.completions.create(
            model=self.model_name,
            max_tokens_to_sample=300,
            prompt=f"{HUMAN_PROMPT}{history}{AI_PROMPT}",
            stream=True,
        )
        if completion is not None:
            partial_text = ""
            for chunk in completion:
                partial_text += chunk.completion
                yield partial_text
        else:
            yield STANDARD_ERROR_MSG + GENERAL_ERROR_MSG


    def get_answer_at_once(self):
        system_prompt = self.system_prompt
        history = self.history
        if system_prompt is not None:
            history = [construct_system(system_prompt), *history]

        completion = self.claude_client.completions.create(
            model=self.model_name,
            max_tokens_to_sample=300,
            prompt=f"{HUMAN_PROMPT}{history}{AI_PROMPT}",
        )
        if completion is not None:
            return completion.completion, len(completion.completion)
        else:
            return "获取资源错误", 0


