from __future__ import annotations

import json
import os

from huggingface_hub import hf_hub_download
from llama_cpp import Llama

from ..index_func import *
from ..presets import *
from ..utils import *
from .base_model import BaseLLMModel

import json
from llama_cpp import Llama
from huggingface_hub import hf_hub_download

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
            model_path = hf_hub_download(repo_id=repo_id, filename=filename, cache_dir="models", resume_download=True)
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
    def __init__(
        self,
        model_name,
        lora_path=None,
        user_name=""
    ) -> None:
        super().__init__(model_name=model_name, user=user_name)

        self.max_generation_token = 1000
        self.end_string = "\n\n"
        # We don't need input data
        path_to_model = download(MODEL_METADATA[model_name]["repo_id"], MODEL_METADATA[model_name]["filelist"][0])
        self.system_prompt = ""

        global LLAMA_MODEL
        if LLAMA_MODEL is None:
            LLAMA_MODEL = Llama(model_path=path_to_model)
            # model_path = None
            # if os.path.exists("models"):
            #     model_dirs = os.listdir("models")
            #     if model_name in model_dirs:
            #         model_path = f"models/{model_name}"
            # if model_path is not None:
            #     model_source = model_path
            # else:
            #     model_source = f"decapoda-research/{model_name}"
                # raise Exception(f"models目录下没有这个模型: {model_name}")
            # if lora_path is not None:
            #     lora_path = f"lora/{lora_path}"

    def _get_llama_style_input(self):
        history = []
        instruction = ""
        if self.system_prompt:
            instruction = (f"Instruction: {self.system_prompt}\n")
        for x in self.history:
            if x["role"] == "user":
                history.append(f"{instruction}Input: {x['content']}")
            else:
                history.append(f"Output: {x['content']}")
        context = "\n\n".join(history)
        context += "\n\nOutput: "
        return context

    def get_answer_at_once(self):
        context = self._get_llama_style_input()
        response = LLAMA_MODEL(context, max_tokens=self.max_generation_token, stop=[], echo=False, stream=False)
        return response, len(response)

    def get_answer_stream_iter(self):
        context = self._get_llama_style_input()
        iter = LLAMA_MODEL(context, max_tokens=self.max_generation_token, stop=[], echo=False, stream=True)
        partial_text = ""
        for i in iter:
            response = i["choices"][0]["text"]
            partial_text += response
            yield partial_text