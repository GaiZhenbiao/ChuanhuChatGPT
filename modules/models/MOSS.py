import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer
import time
import numpy as np
from torch.nn import functional as F
import os
from accelerate import init_empty_weights, load_checkpoint_and_dispatch
from transformers import MossForCausalLM, MossConfig

from .base_model import BaseLLMModel

MOSS_MODEL = None
MOSS_TOKENIZER = None

class MOSS_Client(BaseLLMModel):
    def __init__(self, model_name) -> None:
        super().__init__(model_name=model_name)
        global MOSS_MODEL, MOSS_TOKENIZER
        config = MossConfig.from_pretrained("fnlp/moss-16B-sft")
        print("MOSS Model Parallelism Devices: ", torch.cuda.device_count())
        with init_empty_weights():
            raw_model = MossForCausalLM._from_config(config, torch_dtype=torch.float16)
        raw_model.tie_weights()
        MOSS_MODEL = load_checkpoint_and_dispatch(
            raw_model,
            "fnlp/moss-16B-sft",
            device_map="auto",
            no_split_module_classes=["MossBlock"],
            dtype=torch.float16
        )

if __name__ == "__main__":
    model = MOSS_Client("MOSS")
