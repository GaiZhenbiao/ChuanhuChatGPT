import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer
import time
import numpy as np
from torch.nn import functional as F
import os
from .base_model import BaseLLMModel
from threading import Thread

STABLELM_MODEL = None
STABLELM_TOKENIZER = None


class StopOnTokens(StoppingCriteria):
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        stop_ids = [50278, 50279, 50277, 1, 0]
        for stop_id in stop_ids:
            if input_ids[0][-1] == stop_id:
                return True
        return False


class StableLM_Client(BaseLLMModel):
    def __init__(self, model_name, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        global STABLELM_MODEL, STABLELM_TOKENIZER
        print(f"Starting to load StableLM to memory")
        if model_name == "StableLM":
            model_name = "stabilityai/stablelm-tuned-alpha-7b"
        else:
            model_name = f"models/{model_name}"
        if STABLELM_MODEL is None:
            STABLELM_MODEL = AutoModelForCausalLM.from_pretrained(
                model_name, torch_dtype=torch.float16).cuda()
        if STABLELM_TOKENIZER is None:
            STABLELM_TOKENIZER = AutoTokenizer.from_pretrained(model_name)
        self.generator = pipeline(
            'text-generation', model=STABLELM_MODEL, tokenizer=STABLELM_TOKENIZER, device=0)
        print(f"Sucessfully loaded StableLM to the memory")
        self.system_prompt = """StableAssistant
- StableAssistant is A helpful and harmless Open Source AI Language Model developed by Stability and CarperAI.
- StableAssistant is excited to be able to help the user, but will refuse to do anything that could be considered harmful to the user.
- StableAssistant is more than just an information source, StableAssistant is also able to write poetry, short stories, and make jokes.
- StableAssistant will refuse to participate in anything that could harm a human."""
        self.max_generation_token = 1024
        self.top_p = 0.95
        self.temperature = 1.0

    def _get_stablelm_style_input(self):
        history = self.history + [{"role": "assistant", "content": ""}]
        print(history)
        messages = self.system_prompt + \
            "".join(["".join(["<|USER|>"+history[i]["content"], "<|ASSISTANT|>"+history[i + 1]["content"]])
                    for i in range(0, len(history), 2)])
        return messages

    def _generate(self, text, bad_text=None):
        stop = StopOnTokens()
        result = self.generator(text, max_new_tokens=self.max_generation_token, num_return_sequences=1, num_beams=1, do_sample=True,
                                temperature=self.temperature, top_p=self.top_p, top_k=1000, stopping_criteria=StoppingCriteriaList([stop]))
        return result[0]["generated_text"].replace(text, "")

    def get_answer_at_once(self):
        messages = self._get_stablelm_style_input()
        return self._generate(messages), len(messages)

    def get_answer_stream_iter(self):
        stop = StopOnTokens()
        messages = self._get_stablelm_style_input()

        # model_inputs = tok([messages], return_tensors="pt")['input_ids'].cuda()[:, :4096-1024]
        model_inputs = STABLELM_TOKENIZER(
            [messages], return_tensors="pt").to("cuda")
        streamer = TextIteratorStreamer(
            STABLELM_TOKENIZER, timeout=10., skip_prompt=True, skip_special_tokens=True)
        generate_kwargs = dict(
            model_inputs,
            streamer=streamer,
            max_new_tokens=self.max_generation_token,
            do_sample=True,
            top_p=self.top_p,
            top_k=1000,
            temperature=self.temperature,
            num_beams=1,
            stopping_criteria=StoppingCriteriaList([stop])
        )
        t = Thread(target=STABLELM_MODEL.generate, kwargs=generate_kwargs)
        t.start()

        partial_text = ""
        for new_text in streamer:
            partial_text += new_text
            yield partial_text
