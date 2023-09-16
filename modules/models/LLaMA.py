from __future__ import annotations

import json
import os

from huggingface_hub import hf_hub_download
from llama_cpp import Llama

from ..index_func import *
from ..presets import *
from ..utils import *
from .base_model import BaseLLMModel

SYS_PREFIX = "<<SYS>>\n"
SYS_POSTFIX = "\n<</SYS>>\n\n"
INST_PREFIX = "<s>[INST] "
INST_POSTFIX = " "
OUTPUT_PREFIX = "[/INST] "
OUTPUT_POSTFIX = "</s>"


def download(repo_id, filename, retry=10):
    if os.path.exists("./models/downloaded_models.json"):
        with open("./models/downloaded_models.json", "r") as f:
            downloaded_models = json.load(f)
        if repo_id in downloaded_models:
            return downloaded_models[repo_id]["path"]
    else:
        downloaded_models = {}
    while retry > 0:
        try:
            model_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir="models",
                resume_download=True,
            )
            downloaded_models[repo_id] = {"path": model_path}
            with open("./models/downloaded_models.json", "w") as f:
                json.dump(downloaded_models, f)
            break
        except:
            print("Error downloading model, retrying...")
            retry -= 1
    if retry == 0:
        raise Exception("Error downloading model, please try again later.")
    return model_path


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
            stop=[],
            echo=False,
            stream=True,
        )
        partial_text = ""
        for i in iter:
            response = i["choices"][0]["text"]
            partial_text += response
            yield partial_text
