from .base_model import BaseLLMModel, CallbackToIterator, ChuanhuCallbackHandler
from langchain.chat_models import ChatGooglePalm

class PaLM_Client(BaseLLMModel):
    def __init__(self, model_name, user="") -> None:
        super().__init__(model_name, user)
        self.llm = ChatGooglePalm(google_api_key="")

    def get_answer_at_once(self):
        self.llm.generate(self.history)