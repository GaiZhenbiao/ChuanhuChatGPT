from langchain.chains.summarize import load_summarize_chain
from langchain import OpenAI, PromptTemplate, LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains.mapreduce import MapReduceChain
from langchain.prompts import PromptTemplate
from langchain.text_splitter import TokenTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.agents import load_tools
from langchain.agents import initialize_agent
from langchain.agents import AgentType
from langchain.docstore.document import Document
from langchain.tools import BaseTool, StructuredTool, Tool, tool
from langchain.callbacks.stdout import StdOutCallbackHandler
from langchain.callbacks.manager import BaseCallbackManager

from pydantic import BaseModel, Field

import requests
from bs4 import BeautifulSoup

from .base_model import BaseLLMModel
from ..config import default_chuanhu_assistant_model
from ..presets import SUMMARIZE_PROMPT
import logging

class WebBrowsingInput(BaseModel):
    url: str = Field(description="URL of a webpage")

class WebAskingInput(BaseModel):
    url: str = Field(description="URL of a webpage")
    question: str = Field(description="Question that you want to know the answer to, based on the webpage's content.")


class ChuanhuAgent_Client(BaseLLMModel):
    def __init__(self, model_name, openai_api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        self.text_splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=30)
        self.api_key = openai_api_key
        self.llm = ChatOpenAI(openai_api_key=openai_api_key, temperature=0, model_name=default_chuanhu_assistant_model)
        PROMPT = PromptTemplate(template=SUMMARIZE_PROMPT, input_variables=["text"])
        self.summarize_chain = load_summarize_chain(self.llm, chain_type="map_reduce", return_intermediate_steps=True, map_prompt=PROMPT, combine_prompt=PROMPT)
        if "Pro" in self.model_name:
            self.tools = load_tools(["google-search-results-json", "llm-math", "arxiv", "wikipedia", "wolfram-alpha"], llm=self.llm)
        else:
            self.tools = load_tools(["ddg-search", "llm-math", "arxiv", "wikipedia"], llm=self.llm)

        self.tools.append(
            Tool.from_function(
                func=self.summary_url,
                name="Summary Webpage",
                description="useful when you need to know the overall content of a webpage.",
                args_schema=WebBrowsingInput
            )
        )

        self.tools.append(
            StructuredTool.from_function(
                func=self.ask_url,
                name="Ask Webpage",
                description="useful when you need to ask detailed questions about a webpage.",
                args_schema=WebAskingInput
            )
        )

    def summary(self, text):
        texts = Document(page_content=text)
        texts = self.text_splitter.split_documents([texts])
        return self.summarize_chain({"input_documents": texts}, return_only_outputs=True)["output_text"]

    def fetch_url_content(self, url):
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # 提取所有的文本
        text = ''.join(s.getText() for s in soup.find_all('p'))
        logging.info(f"Extracted text from {url}")
        return text

    def summary_url(self, url):
        text = self.fetch_url_content(url)
        text_summary = self.summary(text)
        url_content = "webpage content summary:\n" + text_summary

        return url_content

    def ask_url(self, url, question):
        text = self.fetch_url_content(url)
        texts = Document(page_content=text)
        texts = self.text_splitter.split_documents([texts])
        # use embedding
        embeddings = OpenAIEmbeddings(openai_api_key=self.api_key)

        # create vectorstore
        db = FAISS.from_documents(texts, embeddings)
        retriever = db.as_retriever()
        qa = RetrievalQA.from_chain_type(llm=self.llm, chain_type="stuff", retriever=retriever)
        return qa.run(f"{question} Reply in 中文")

    def get_answer_at_once(self):
        question = self.history[-1]["content"]
        manager = BaseCallbackManager(handlers=[StdOutCallbackHandler()])
        # llm=ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo")
        agent = initialize_agent(self.tools, self.llm, agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, verbose=True, callback_manager=manager)
        reply = agent.run(input=f"{question} Reply in 简体中文")
        return reply, -1
