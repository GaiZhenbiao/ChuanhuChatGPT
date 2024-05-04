from .base_model import BaseLLMModel
import google.generativeai as palm


class Google_PaLM_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name, config={"api_key": api_key})

    def _get_palm_style_input(self):
        new_history = []
        for item in self.history:
            if item["role"] == "user":
                new_history.append({'author': '1', 'content': item["content"]})
            else:
                new_history.append({'author': '0', 'content': item["content"]})
        return new_history

    def get_answer_at_once(self):
        palm.configure(api_key=self.api_key)
        messages = self._get_palm_style_input()
        response = palm.chat(context=self.system_prompt, messages=messages,
                             temperature=self.temperature, top_p=self.top_p, model=self.model_name)
        if response.last is not None:
            return response.last, len(response.last)
        else:
            reasons = '\n\n'.join(
                reason['reason'].name for reason in response.filters)
            return "由于下面的原因，Google 拒绝返回 PaLM 的回答：\n\n" + reasons, 0
