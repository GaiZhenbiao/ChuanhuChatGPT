import logging
from threading import Thread

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

from ..presets import *
from .base_model import BaseLLMModel


class GoogleGemmaClient(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)

        global GEMMA_TOKENIZER, GEMMA_MODEL
        # self.deinitialize()
        self.default_max_generation_token = self.token_upper_limit
        self.max_generation_token = self.token_upper_limit
        if GEMMA_TOKENIZER is None or GEMMA_MODEL is None:
            model_path = None
            if os.path.exists("models"):
                model_dirs = os.listdir("models")
                if model_name in model_dirs:
                    model_path = f"models/{model_name}"
            if model_path is not None:
                model_source = model_path
            else:
                if os.path.exists(
                    os.path.join("models", MODEL_METADATA[model_name]["model_name"])
                ):
                    model_source = os.path.join(
                        "models", MODEL_METADATA[model_name]["model_name"]
                    )
                else:
                    try:
                        model_source = MODEL_METADATA[model_name]["repo_id"]
                    except:
                        model_source = model_name
            dtype = torch.bfloat16
            GEMMA_TOKENIZER = AutoTokenizer.from_pretrained(
                model_source, use_auth_token=os.environ["HF_AUTH_TOKEN"]
            )
            GEMMA_MODEL = AutoModelForCausalLM.from_pretrained(
                model_source,
                device_map="auto",
                torch_dtype=dtype,
                trust_remote_code=True,
                resume_download=True,
                use_auth_token=os.environ["HF_AUTH_TOKEN"],
            )

    def deinitialize(self):
        global GEMMA_TOKENIZER, GEMMA_MODEL
        GEMMA_TOKENIZER = None
        GEMMA_MODEL = None
        self.clear_cuda_cache()
        logging.info("GEMMA deinitialized")

    def _get_gemma_style_input(self):
        global GEMMA_TOKENIZER
        # messages = [{"role": "system", "content": self.system_prompt}, *self.history] # system prompt is not supported
        messages = self.history
        prompt = GEMMA_TOKENIZER.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = GEMMA_TOKENIZER.encode(
            prompt, add_special_tokens=True, return_tensors="pt"
        )
        return inputs

    def get_answer_at_once(self):
        global GEMMA_TOKENIZER, GEMMA_MODEL
        inputs = self._get_gemma_style_input()
        outputs = GEMMA_MODEL.generate(
            input_ids=inputs.to(GEMMA_MODEL.device),
            max_new_tokens=self.max_generation_token,
        )
        generated_token_count = outputs.shape[1] - inputs.shape[1]
        outputs = GEMMA_TOKENIZER.decode(outputs[0], skip_special_tokens=True)
        outputs = outputs.split("<start_of_turn>model\n")[-1][:-5]
        self.clear_cuda_cache()
        return outputs, generated_token_count

    def get_answer_stream_iter(self):
        global GEMMA_TOKENIZER, GEMMA_MODEL
        inputs = self._get_gemma_style_input()
        streamer = TextIteratorStreamer(
            GEMMA_TOKENIZER, timeout=10.0, skip_prompt=True, skip_special_tokens=True
        )
        input_kwargs = dict(
            input_ids=inputs.to(GEMMA_MODEL.device),
            max_new_tokens=self.max_generation_token,
            streamer=streamer,
        )
        t = Thread(target=GEMMA_MODEL.generate, kwargs=input_kwargs)
        t.start()

        partial_text = ""
        for new_text in streamer:
            partial_text += new_text
            yield partial_text
        self.clear_cuda_cache()
