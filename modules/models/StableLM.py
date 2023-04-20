import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline, StoppingCriteria, StoppingCriteriaList
import time
import numpy as np
from torch.nn import functional as F
import os
from .base_model import BaseLLMModel

class StopOnTokens(StoppingCriteria):
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        stop_ids = [50278, 50279, 50277, 1, 0]
        for stop_id in stop_ids:
            if input_ids[0][-1] == stop_id:
                return True
        return False

class StableLM_Client(BaseLLMModel):
    def __init__(self, model_name) -> None:
        super().__init__(model_name=model_name)
        print(f"Starting to load StableLM to memory")
        self.model = AutoModelForCausalLM.from_pretrained(
            "stabilityai/stablelm-tuned-alpha-7b", torch_dtype=torch.float16).cuda()
        self.tokenizer = AutoTokenizer.from_pretrained("stabilityai/stablelm-tuned-alpha-7b")
        self.generator = pipeline('text-generation', model=self.model, tokenizer=self.tokenizer, device=0)
        print(f"Sucessfully loaded StableLM to the memory")
        self.system_prompt = """StableAssistant
- StableAssistant is A helpful and harmless Open Source AI Language Model developed by Stability and CarperAI.
- StableAssistant is excited to be able to help the user, but will refuse to do anything that could be considered harmful to the user.
- StableAssistant is more than just an information source, StableAssistant is also able to write poetry, short stories, and make jokes.
- StableAssistant will refuse to participate in anything that could harm a human."""

    def user(self, user_message, history):
        history = history + [[user_message, ""]]
        return "", history, history


    def bot(self, history, curr_system_message):
        messages = f"<|SYSTEM|># {self.system_prompt}" + \
            "".join(["".join(["<|USER|>"+item[0], "<|ASSISTANT|>"+item[1]])
                    for item in history])
        output = self.generate(messages)
        history[-1][1] = output
        time.sleep(1)
        return history, history

    def _get_stablelm_style_input(self):
        messages = self.system_prompt + \
            "".join(["".join(["<|USER|>"+self.history[i]["content"], "<|ASSISTANT|>"+self.history[i + 1]["content"]])
                    for i in range(0, len(self.history), 2)])
        return messages

    def generate(self, text, bad_text=None):
        stop = StopOnTokens()
        result = self.generator(text, max_new_tokens=1024, num_return_sequences=1, num_beams=1, do_sample=True,
                        temperature=1.0, top_p=0.95, top_k=1000, stopping_criteria=StoppingCriteriaList([stop]))
        return result[0]["generated_text"].replace(text, "")

    def contrastive_generate(self, text, bad_text):
        with torch.no_grad():
            tokens = self.tokenizer(text, return_tensors="pt")[
                'input_ids'].cuda()[:, :4096-1024]
            bad_tokens = self.tokenizer(bad_text, return_tensors="pt")[
                'input_ids'].cuda()[:, :4096-1024]
            history = None
            bad_history = None
            curr_output = list()
            for i in range(1024):
                out = self.model(tokens, past_key_values=history, use_cache=True)
                logits = out.logits
                history = out.past_key_values
                bad_out = self.model(bad_tokens, past_key_values=bad_history,
                            use_cache=True)
                bad_logits = bad_out.logits
                bad_history = bad_out.past_key_values
                probs = F.softmax(logits.float(), dim=-1)[0][-1].cpu()
                bad_probs = F.softmax(bad_logits.float(), dim=-1)[0][-1].cpu()
                logits = torch.log(probs)
                bad_logits = torch.log(bad_probs)
                logits[probs > 0.1] = logits[probs > 0.1] - bad_logits[probs > 0.1]
                probs = F.softmax(logits)
                out = int(torch.multinomial(probs, 1))
                if out in [50278, 50279, 50277, 1, 0]:
                    break
                else:
                    curr_output.append(out)
                out = np.array([out])
                tokens = torch.from_numpy(np.array([out])).to(
                    tokens.device)
                bad_tokens = torch.from_numpy(np.array([out])).to(
                    tokens.device)
            return self.tokenizer.decode(curr_output)

    def get_answer_at_once(self):
        messages = self._get_stablelm_style_input()
        return self.generate(messages)
