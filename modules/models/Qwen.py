from transformers import AutoModelForCausalLM, AutoTokenizer
import os
from transformers.generation import GenerationConfig
import logging
import colorama
from .base_model import BaseLLMModel
from ..presets import MODEL_METADATA


class Qwen_Client(BaseLLMModel):
    def __init__(self, model_name, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        model_source = None
        if os.path.exists("models"):
            model_dirs = os.listdir("models")
            if model_name in model_dirs:
                model_source = f"models/{model_name}"
        if model_source is None:
            try:
                model_source = MODEL_METADATA[model_name]["repo_id"]
            except KeyError:
                model_source = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_source, trust_remote_code=True, resume_download=True)
        self.model = AutoModelForCausalLM.from_pretrained(model_source, device_map="cuda", trust_remote_code=True, resume_download=True).eval()

    def generation_config(self):
        return GenerationConfig.from_dict({
            "chat_format": "chatml",
            "do_sample": True,
            "eos_token_id": 151643,
            "max_length": self.token_upper_limit,
            "max_new_tokens": 512,
            "max_window_size": 6144,
            "pad_token_id": 151643,
            "top_k": 0,
            "top_p": self.top_p,
            "transformers_version": "4.33.2",
            "trust_remote_code": True,
            "temperature": self.temperature,
            })

    def _get_glm_style_input(self):
        history = [x["content"] for x in self.history]
        query = history.pop()
        logging.debug(colorama.Fore.YELLOW +
                      f"{history}" + colorama.Fore.RESET)
        assert (
            len(history) % 2 == 0
        ), f"History should be even length. current history is: {history}"
        history = [[history[i], history[i + 1]]
                   for i in range(0, len(history), 2)]
        return history, query

    def get_answer_at_once(self):
        history, query = self._get_glm_style_input()
        self.model.generation_config = self.generation_config()
        response, history = self.model.chat(self.tokenizer, query, history=history)
        return response, len(response)

    def get_answer_stream_iter(self):
        history, query = self._get_glm_style_input()
        self.model.generation_config = self.generation_config()
        for response in self.model.chat_stream(
                self.tokenizer,
                query,
                history,
            ):
                yield response
