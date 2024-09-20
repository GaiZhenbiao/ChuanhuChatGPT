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
from langchain.vectorstores.base import VectorStoreRetriever
from langchain_community.vectorstores import FAISS
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.human import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic.v1 import BaseModel, Field

from ..index_func import construct_index
from ..presets import SUMMARIZE_PROMPT, i18n
from ..utils import add_source_numbers
from .base_model import (BaseLLMModel, CallbackToIterator,
                         ChuanhuCallbackHandler)


class GoogleSearchInput(BaseModel):
    keywords: str = Field(description="keywords to search")


class WebBrowsingInput(BaseModel):
    url: str = Field(description="URL of a webpage")


class KnowledgeBaseQueryInput(BaseModel):
    question: str = Field(
        description="The question you want to ask the knowledge base."
    )


class WebAskingInput(BaseModel):
    url: str = Field(description="URL of a webpage")
    question: str = Field(
        description="Question that you want to know the answer to, based on the webpage's content."
    )


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
                streaming=True,
            )
        else:
            self.llm = ChatOpenAI(
                openai_api_key=openai_api_key,
                model_name="gpt-3.5-turbo",
                openai_api_base=os.environ.get("OPENAI_API_BASE", None),
                streaming=True,
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
            logging.warning("WOLFRAM_ALPHA_APPID not found, wolfram-alpha is disabled.")
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
            self.index_summary = ", ".join(
                [os.path.basename(file.name) for file in files]
            )
        return gr.update(), chatbot, status

    def prepare_inputs(
        self, real_inputs, use_websearch, files, reply_language, chatbot
    ):
        fake_inputs = real_inputs
        display_append = ""
        limited_context = False
        return limited_context, fake_inputs, display_append, real_inputs, chatbot

    def query_index(self, query):
        retriever = VectorStoreRetriever(
            vectorstore=self.index, search_type="similarity", search_kwargs={"k": 6}
        )
        relevant_documents = retriever.get_relevant_documents(query)
        reference_results = [
            [d.page_content.strip("�"), os.path.basename(d.metadata["source"])]
            for d in relevant_documents
        ]
        reference_results = add_source_numbers(reference_results)
        reference_results = "\n".join(reference_results)
        return reference_results

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
            model="text-embedding-3-large",
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

        if "Pro" in self.model_name:
            self.llm = ChatOpenAI(
                openai_api_key=self.api_key,
                model_name="gpt-4-turbo-preview",
                openai_api_base=os.environ.get("OPENAI_API_BASE", None),
                temperature=self.temperature,
                streaming=True,
            )
        else:
            self.llm = ChatOpenAI(
                openai_api_key=self.api_key,
                model_name="gpt-3.5-turbo",
                openai_api_base=os.environ.get("OPENAI_API_BASE", None),
                temperature=self.temperature,
                streaming=True,
            )

        agent_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.system_prompt),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )
        agent_prompt.input_variables = ["agent_scratchpad", "input"]

        def thread_func():
            tools = self.tools
            if self.index is not None:
                tools.append(
                    Tool.from_function(
                        func=self.query_index,
                        name="query_knowledge_base",
                        description=f"useful when you need to know about: {self.index_summary}",
                        args_schema=KnowledgeBaseQueryInput,
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
