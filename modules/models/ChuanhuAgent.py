import logging
import os
from itertools import islice
from threading import Thread

import gradio as gr
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from langchain.agents import (AgentExecutor, AgentType,
                              create_openai_tools_agent, initialize_agent,
                              load_tools)
from langchain.callbacks.base import BaseCallbackManager
from langchain.chains import RetrievalQA
from langchain.chains.summarize import load_summarize_chain
from langchain.docstore.document import Document
from langchain.text_splitter import TokenTextSplitter
from langchain.tools import StructuredTool, Tool
from langchain_community.callbacks import get_openai_callback
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.human import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic.v1 import BaseModel, Field

from ..config import default_chuanhu_assistant_model
from ..index_func import construct_index
from ..presets import SUMMARIZE_PROMPT, i18n
from .base_model import (BaseLLMModel, CallbackToIterator,
                         ChuanhuCallbackHandler)


class GoogleSearchInput(BaseModel):
    keywords: str = Field(description="keywords to search")


class WebBrowsingInput(BaseModel):
    url: str = Field(description="URL of a webpage")


class WebAskingInput(BaseModel):
    url: str = Field(description="URL of a webpage")
    question: str = Field(
        description="Question that you want to know the answer to, based on the webpage's content."
    )


agent_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant"),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)
agent_prompt.input_variables = ['agent_scratchpad', 'input']


class ChuanhuAgent_Client(BaseLLMModel):
    def __init__(self, model_name, openai_api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        self.text_splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=30)
        self.api_key = openai_api_key
        self.cheap_llm = ChatOpenAI(
            openai_api_key=openai_api_key,
            temperature=0,
            model_name="gpt-3.5-turbo",
            openai_api_base=os.environ.get("OPENAI_API_BASE", None),
        )
        PROMPT = PromptTemplate(template=SUMMARIZE_PROMPT, input_variables=["text"])
        self.summarize_chain = load_summarize_chain(
            self.cheap_llm,
            chain_type="map_reduce",
            return_intermediate_steps=True,
            map_prompt=PROMPT,
            combine_prompt=PROMPT,
        )
        self.index_summary = None
        self.index = None
        self.tools = []
        if "Pro" in self.model_name:
            self.llm = ChatOpenAI(
                openai_api_key=openai_api_key,
                model_name="gpt-4-turbo-preview",
                openai_api_base=os.environ.get("OPENAI_API_BASE", None),
            )
        else:
            self.llm = ChatOpenAI(
                openai_api_key=openai_api_key,
                model_name="gpt-3.5-turbo",
                openai_api_base=os.environ.get("OPENAI_API_BASE", None),
            )
        tools_to_enable = ["llm-math", "arxiv", "wikipedia"]
        # if exists GOOGLE_CSE_ID and GOOGLE_API_KEY, enable google-search-results-json
        if (
            os.environ.get("GOOGLE_CSE_ID", None) is not None
            and os.environ.get("GOOGLE_API_KEY", None) is not None
        ):
            tools_to_enable.append("google-search-results-json")
        else:
            logging.warning(
                "GOOGLE_CSE_ID and/or GOOGLE_API_KEY not found, using DuckDuckGo instead."
            )
            self.tools.append(
                Tool.from_function(
                    func=self.google_search_simple,
                    name="ddg_search_json",
                    description="useful when you need to search the web.",
                    args_schema=GoogleSearchInput,
                )
            )
        # if exists WOLFRAM_ALPHA_APPID, enable wolfram-alpha
        if os.environ.get("WOLFRAM_ALPHA_APPID", None) is not None:
            tools_to_enable.append("wolfram-alpha")
        else:
            logging.warning(
                "WOLFRAM_ALPHA_APPID not found, wolfram-alpha is disabled."
            )
        # if exists SERPAPI_API_KEY, enable serpapi
        if os.environ.get("SERPAPI_API_KEY", None) is not None:
            tools_to_enable.append("serpapi")
        else:
            logging.warning("SERPAPI_API_KEY not found, serpapi is disabled.")
        self.tools += load_tools(tools_to_enable, llm=self.llm)

        self.tools.append(
            Tool.from_function(
                func=self.summary_url,
                name="summary_webpage",
                description="useful when you need to know the overall content of a webpage.",
                args_schema=WebBrowsingInput,
            )
        )

        self.tools.append(
            StructuredTool.from_function(
                func=self.ask_url,
                name="ask_webpage",
                description="useful when you need to ask detailed questions about a webpage.",
                args_schema=WebAskingInput,
            )
        )

    def google_search_simple(self, query):
        results = []
        with DDGS() as ddgs:
            ddgs_gen = ddgs.text(query, backend="lite")
            for r in islice(ddgs_gen, 10):
                results.append(
                    {"title": r["title"], "link": r["href"], "snippet": r["body"]}
                )
        return str(results)

    def handle_file_upload(self, files, chatbot, language):
        """if the model accepts multi modal input, implement this function"""
        status = gr.Markdown()
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
                from langchain.chat_models import ChatOpenAI
                from langchain.prompts import PromptTemplate

                prompt_template = (
                    "Write a concise summary of the following:\n\n{text}\n\nCONCISE SUMMARY IN "
                    + language
                    + ":"
                )
                PROMPT = PromptTemplate(
                    template=prompt_template, input_variables=["text"]
                )
                llm = ChatOpenAI()
                chain = load_summarize_chain(
                    llm,
                    chain_type="map_reduce",
                    return_intermediate_steps=True,
                    map_prompt=PROMPT,
                    combine_prompt=PROMPT,
                )
                summary = chain(
                    {
                        "input_documents": list(
                            index.docstore.__dict__["_dict"].values()
                        )
                    },
                    return_only_outputs=True,
                )["output_text"]
                logging.info(f"Summary: {summary}")
                self.index_summary = summary
                chatbot.append((f"Uploaded {len(files)} files", summary))
            logging.info(cb)
        return gr.update(), chatbot, status

    def query_index(self, query):
        if self.index is not None:
            retriever = self.index.as_retriever()
            qa = RetrievalQA.from_chain_type(
                llm=self.llm, chain_type="stuff", retriever=retriever
            )
            return qa.run(query)
        else:
            "Error during query."

    def summary(self, text):
        texts = Document(page_content=text)
        texts = self.text_splitter.split_documents([texts])
        return self.summarize_chain(
            {"input_documents": texts}, return_only_outputs=True
        )["output_text"]

    def fetch_url_content(self, url):
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        # 提取所有的文本
        text = "".join(s.getText() for s in soup.find_all("p"))
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
        embeddings = OpenAIEmbeddings(
            openai_api_key=self.api_key,
            openai_api_base=os.environ.get("OPENAI_API_BASE", None),
        )

        # create vectorstore
        db = FAISS.from_documents(texts, embeddings)
        retriever = db.as_retriever()
        qa = RetrievalQA.from_chain_type(
            llm=self.cheap_llm, chain_type="stuff", retriever=retriever
        )
        return qa.run(f"{question} Reply in 中文")

    def get_answer_at_once(self):
        question = self.history[-1]["content"]
        # llm=ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo")
        agent = initialize_agent(
            self.tools,
            self.llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
        )
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
                        args_schema=WebBrowsingInput,
                    )
                )
            agent = create_openai_tools_agent(self.llm, tools, agent_prompt)
            agent_executor = AgentExecutor(
                agent=agent, tools=tools, callback_manager=manager, verbose=True
            )
            messages = []
            for msg in self.history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
                else:
                    logging.warning(f"Unknown role: {msg['role']}")
            try:
                reply = agent_executor.invoke(
                    {"input": question, "chat_history": messages}
                )["output"]
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
