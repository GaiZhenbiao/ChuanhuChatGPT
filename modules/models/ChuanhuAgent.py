from langchain.chains.summarize import load_summarize_chain
from langchain import PromptTemplate, LLMChain
from langchain.chat_models import ChatOpenAI
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
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.callbacks.base import BaseCallbackManager
from duckduckgo_search import DDGS
from itertools import islice

from typing import Any, Dict, List, Optional, Union

from langchain.callbacks.base import BaseCallbackHandler
from langchain.input import print_text
from langchain.schema import AgentAction, AgentFinish, LLMResult

from pydantic.v1 import BaseModel, Field

import requests
from bs4 import BeautifulSoup
from threading import Thread, Condition
from collections import deque

from .base_model import BaseLLMModel, CallbackToIterator, ChuanhuCallbackHandler
from ..config import default_chuanhu_assistant_model
from ..presets import SUMMARIZE_PROMPT, i18n
from ..index_func import construct_index

from langchain.callbacks import get_openai_callback
import os
import gradio as gr
import logging

class GoogleSearchInput(BaseModel):
    keywords: str = Field(description="keywords to search")

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
        self.llm = ChatOpenAI(openai_api_key=openai_api_key, temperature=0, model_name=default_chuanhu_assistant_model, openai_api_base=os.environ.get("OPENAI_API_BASE", None))
        self.cheap_llm = ChatOpenAI(openai_api_key=openai_api_key, temperature=0, model_name="gpt-3.5-turbo", openai_api_base=os.environ.get("OPENAI_API_BASE", None))
        PROMPT = PromptTemplate(template=SUMMARIZE_PROMPT, input_variables=["text"])
        self.summarize_chain = load_summarize_chain(self.cheap_llm, chain_type="map_reduce", return_intermediate_steps=True, map_prompt=PROMPT, combine_prompt=PROMPT)
        self.index_summary = None
        self.index = None
        if "Pro" in self.model_name:
            tools_to_enable = ["llm-math", "arxiv", "wikipedia"]
            # if exists GOOGLE_CSE_ID and GOOGLE_API_KEY, enable google-search-results-json
            if os.environ.get("GOOGLE_CSE_ID", None) is not None and os.environ.get("GOOGLE_API_KEY", None) is not None:
                tools_to_enable.append("google-search-results-json")
            else:
                logging.warning("GOOGLE_CSE_ID and/or GOOGLE_API_KEY not found, google-search-results-json is disabled.")
            # if exists WOLFRAM_ALPHA_APPID, enable wolfram-alpha
            if os.environ.get("WOLFRAM_ALPHA_APPID", None) is not None:
                tools_to_enable.append("wolfram-alpha")
            else:
                logging.warning("WOLFRAM_ALPHA_APPID not found, wolfram-alpha is disabled.")
            # if exists SERPAPI_API_KEY, enable serpapi
            if os.environ.get("SERPAPI_API_KEY", None) is not None:
                tools_to_enable.append("serpapi")
            else:
                logging.warning("SERPAPI_API_KEY not found, serpapi is disabled.")
            self.tools = load_tools(tools_to_enable, llm=self.llm)
        else:
            self.tools = load_tools(["ddg-search", "llm-math", "arxiv", "wikipedia"], llm=self.llm)
            self.tools.append(
                Tool.from_function(
                    func=self.google_search_simple,
                    name="Google Search JSON",
                    description="useful when you need to search the web.",
                    args_schema=GoogleSearchInput
                )
            )

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

    def google_search_simple(self, query):
        results = []
        with DDGS() as ddgs:
            ddgs_gen = ddgs.text(query, backend="lite")
            for r in islice(ddgs_gen, 10):
                results.append({
                    "title": r["title"],
                    "link": r["href"],
                    "snippet": r["body"]
                })
        return str(results)

    def handle_file_upload(self, files, chatbot, language):
        """if the model accepts multi modal input, implement this function"""
        status = gr.Markdown.update()
        if files:
            index = construct_index(self.api_key, file_src=files)
            assert index is not None, "获取索引失败"
            self.index = index
            status = i18n("索引构建完成")
            # Summarize the document
            logging.info(i18n("生成内容总结中……"))
            with get_openai_callback() as cb:
                os.environ["OPENAI_API_KEY"] = self.api_key
                from langchain.chains.summarize import load_summarize_chain
                from langchain.prompts import PromptTemplate
                from langchain.chat_models import ChatOpenAI
                prompt_template = "Write a concise summary of the following:\n\n{text}\n\nCONCISE SUMMARY IN " + language + ":"
                PROMPT = PromptTemplate(template=prompt_template, input_variables=["text"])
                llm = ChatOpenAI()
                chain = load_summarize_chain(llm, chain_type="map_reduce", return_intermediate_steps=True, map_prompt=PROMPT, combine_prompt=PROMPT)
                summary = chain({"input_documents": list(index.docstore.__dict__["_dict"].values())}, return_only_outputs=True)["output_text"]
                logging.info(f"Summary: {summary}")
                self.index_summary = summary
                chatbot.append((f"Uploaded {len(files)} files", summary))
            logging.info(cb)
        return gr.Files.update(), chatbot, status

    def query_index(self, query):
        if self.index is not None:
            retriever = self.index.as_retriever()
            qa = RetrievalQA.from_chain_type(llm=self.llm, chain_type="stuff", retriever=retriever)
            return qa.run(query)
        else:
            "Error during query."

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
        if text == "":
            return "URL unavailable."
        text_summary = self.summary(text)
        url_content = "webpage content summary:\n" + text_summary

        return url_content

    def ask_url(self, url, question):
        text = self.fetch_url_content(url)
        if text == "":
            return "URL unavailable."
        texts = Document(page_content=text)
        texts = self.text_splitter.split_documents([texts])
        # use embedding
        embeddings = OpenAIEmbeddings(openai_api_key=self.api_key, openai_api_base=os.environ.get("OPENAI_API_BASE", None))

        # create vectorstore
        db = FAISS.from_documents(texts, embeddings)
        retriever = db.as_retriever()
        qa = RetrievalQA.from_chain_type(llm=self.cheap_llm, chain_type="stuff", retriever=retriever)
        return qa.run(f"{question} Reply in 中文")

    def get_answer_at_once(self):
        question = self.history[-1]["content"]
        # llm=ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo")
        agent = initialize_agent(self.tools, self.llm, agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, verbose=True)
        reply = agent.run(input=f"{question} Reply in 简体中文")
        return reply, -1

    def get_answer_stream_iter(self):
        question = self.history[-1]["content"]
        it = CallbackToIterator()
        manager = BaseCallbackManager(handlers=[ChuanhuCallbackHandler(it.callback)])
        def thread_func():
            tools = self.tools
            if self.index is not None:
                    tools.append(
                        Tool.from_function(
                        func=self.query_index,
                        name="Query Knowledge Base",
                        description=f"useful when you need to know about: {self.index_summary}",
                        args_schema=WebBrowsingInput
                    )
                )
            agent = initialize_agent(self.tools, self.llm, agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, verbose=True, callback_manager=manager)
            try:
                reply = agent.run(input=f"{question} Reply in 简体中文")
            except Exception as e:
                import traceback
                traceback.print_exc()
                reply = str(e)
            it.callback(reply)
            it.finish()
        t = Thread(target=thread_func)
        t.start()
        partial_text = ""
        for value in it:
            partial_text += value
            yield partial_text
