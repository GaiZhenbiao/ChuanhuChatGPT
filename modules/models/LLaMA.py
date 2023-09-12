from __future__ import annotations

import json
import os

from ..index_func import *
from ..presets import *
from ..utils import *
from .base_model import BaseLLMModel


class LLaMA_Client(BaseLLMModel):
    def __init__(
        self,
        model_name,
        lora_path=None,
        user_name=""
    ) -> None:
        super().__init__(model_name=model_name, user=user_name)
        from lmflow.args import (DatasetArguments, InferencerArguments,
                                 ModelArguments)
        from lmflow.datasets.dataset import Dataset
        from lmflow.models.auto_model import AutoModel
        from lmflow.pipeline.auto_pipeline import AutoPipeline

        self.max_generation_token = 1000
        self.end_string = "\n\n"
        # We don't need input data
        data_args = DatasetArguments(dataset_path=None)
        self.dataset = Dataset(data_args)
        self.system_prompt = ""

        global LLAMA_MODEL, LLAMA_INFERENCER
        if LLAMA_MODEL is None or LLAMA_INFERENCER is None:
            model_path = None
            if os.path.exists("models"):
                model_dirs = os.listdir("models")
                if model_name in model_dirs:
                    model_path = f"models/{model_name}"
            if model_path is not None:
                model_source = model_path
            else:
                model_source = f"decapoda-research/{model_name}"
                # raise Exception(f"models目录下没有这个模型: {model_name}")
            if lora_path is not None:
                lora_path = f"lora/{lora_path}"
            model_args = ModelArguments(model_name_or_path=model_source, lora_model_path=lora_path, model_type=None, config_overrides=None, config_name=None, tokenizer_name=None, cache_dir=None,
                                        use_fast_tokenizer=True, model_revision='main', use_auth_token=False, torch_dtype=None, use_lora=False, lora_r=8, lora_alpha=32, lora_dropout=0.1, use_ram_optimized_load=True)
            pipeline_args = InferencerArguments(
                local_rank=0, random_seed=1, deepspeed='configs/ds_config_chatbot.json', mixed_precision='bf16')

            with open(pipeline_args.deepspeed, "r", encoding="utf-8") as f:
                ds_config = json.load(f)
            LLAMA_MODEL = AutoModel.get_model(
                model_args,
                tune_strategy="none",
                ds_config=ds_config,
            )
            LLAMA_INFERENCER = AutoPipeline.get_pipeline(
                pipeline_name="inferencer",
                model_args=model_args,
                data_args=data_args,
                pipeline_args=pipeline_args,
            )

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

        input_dataset = self.dataset.from_dict(
            {"type": "text_only", "instances": [{"text": context}]}
        )

        output_dataset = LLAMA_INFERENCER.inference(
            model=LLAMA_MODEL,
            dataset=input_dataset,
            max_new_tokens=self.max_generation_token,
            temperature=self.temperature,
        )

        response = output_dataset.to_dict()["instances"][0]["text"]
        return response, len(response)

    def get_answer_stream_iter(self):
        context = self._get_llama_style_input()
        partial_text = ""
        step = 1
        for _ in range(0, self.max_generation_token, step):
            input_dataset = self.dataset.from_dict(
                {"type": "text_only", "instances": [
                    {"text": context + partial_text}]}
            )
            output_dataset = LLAMA_INFERENCER.inference(
                model=LLAMA_MODEL,
                dataset=input_dataset,
                max_new_tokens=step,
                temperature=self.temperature,
            )
            response = output_dataset.to_dict()["instances"][0]["text"]
            if response == "" or response == self.end_string:
                break
            partial_text += response
            yield partial_text