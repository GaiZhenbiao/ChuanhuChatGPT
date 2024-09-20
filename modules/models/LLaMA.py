from __future__ import annotations

import json
import os
from llama_cpp import Llama

from ..index_func import *
from ..presets import *
from ..utils import *
from .base_model import BaseLLMModel, download

SYS_PREFIX = "<<SYS>>\n"
SYS_POSTFIX = "\n<</SYS>>\n\n"
INST_PREFIX = "<s>[INST] "
INST_POSTFIX = " "
OUTPUT_PREFIX = "[/INST] "
OUTPUT_POSTFIX = "</s>"


class LLaMA_Client(BaseLLMModel):
    def __init__(self, model_name, lora_path=None, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)

        self.max_generation_token = 1000
        if model_name in MODEL_METADATA:
            path_to_model = download(
                MODEL_METADATA[model_name]["repo_id"],
                MODEL_METADATA[model_name]["filelist"][0],
            )
        else:
            dir_to_model = os.path.join("models", model_name)
            # look for nay .gguf file in the dir_to_model directory and its subdirectories
            path_to_model = None
            for root, dirs, files in os.walk(dir_to_model):
                for file in files:
                    if file.endswith(".gguf"):
                        path_to_model = os.path.join(root, file)
                        break
                if path_to_model is not None:
                    break
        self.system_prompt = ""

        if lora_path is not None:
            lora_path = os.path.join("lora", lora_path)
            self.model = Llama(model_path=path_to_model, lora_path=lora_path)
        else:
            self.model = Llama(model_path=path_to_model)

    def _get_llama_style_input(self):
        context = []
        for conv in self.history:
            if conv["role"] == "system":
                context.append(SYS_PREFIX + conv["content"] + SYS_POSTFIX)
            elif conv["role"] == "user":
                context.append(
                    INST_PREFIX + conv["content"] + INST_POSTFIX + OUTPUT_PREFIX
                )
            else:
                context.append(conv["content"] + OUTPUT_POSTFIX)
        return "".join(context)
        # for conv in self.history:
        #     if conv["role"] == "system":
        #         context.append(conv["content"])
        #     elif conv["role"] == "user":
        #         context.append(
        #             conv["content"]
        #         )
        #     else:
        #         context.append(conv["content"])
        # return "\n\n".join(context)+"\n\n"

    def get_answer_at_once(self):
        context = self._get_llama_style_input()
        response = self.model(
            context,
            max_tokens=self.max_generation_token,
            stop=[],
            echo=False,
            stream=False,
        )
        return response, len(response)

    def get_answer_stream_iter(self):
        context = self._get_llama_style_input()
        iter = self.model(
            context,
            max_tokens=self.max_generation_token,
            stop=[SYS_PREFIX, SYS_POSTFIX, INST_PREFIX, OUTPUT_PREFIX, OUTPUT_POSTFIX],
            echo=False,
            stream=True,
        )
        partial_text = ""
        for i in iter:
            response = i["choices"][0]["text"]
            partial_text += response
            yield partial_text
