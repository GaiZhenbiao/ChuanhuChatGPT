import os
import logging

from llama_index import GPTSimpleVectorIndex
from llama_index import download_loader
from llama_index import (
    Document,
    LLMPredictor,
    PromptHelper,
    QuestionAnswerPrompt,
    RefinePrompt,
)
from langchain.llms import OpenAI
import colorama


from modules.presets import *
from modules.utils import *


def get_documents(file_src):
    documents = []
    index_name = ""
    logging.debug("Loading documents...")
    logging.debug(f"file_src: {file_src}")
    for file in file_src:
        logging.debug(f"file: {file.name}")
        index_name += file.name
        if os.path.splitext(file.name)[1] == ".pdf":
            logging.debug("Loading PDF...")
            CJKPDFReader = download_loader("CJKPDFReader")
            loader = CJKPDFReader()
            documents += loader.load_data(file=file.name)
        elif os.path.splitext(file.name)[1] == ".docx":
            logging.debug("Loading DOCX...")
            DocxReader = download_loader("DocxReader")
            loader = DocxReader()
            documents += loader.load_data(file=file.name)
        elif os.path.splitext(file.name)[1] == ".epub":
            logging.debug("Loading EPUB...")
            EpubReader = download_loader("EpubReader")
            loader = EpubReader()
            documents += loader.load_data(file=file.name)
        else:
            logging.debug("Loading text file...")
            with open(file.name, "r", encoding="utf-8") as f:
                text = add_space(f.read())
                documents += [Document(text)]
    index_name = sha1sum(index_name)
    return documents, index_name


def construct_index(
    api_key,
    file_src,
    max_input_size=4096,
    num_outputs=1,
    max_chunk_overlap=20,
    chunk_size_limit=600,
    embedding_limit=None,
    separator=" ",
    num_children=10,
    max_keywords_per_chunk=10,
):
    os.environ["OPENAI_API_KEY"] = api_key
    chunk_size_limit = None if chunk_size_limit == 0 else chunk_size_limit
    embedding_limit = None if embedding_limit == 0 else embedding_limit
    separator = " " if separator == "" else separator

    llm_predictor = LLMPredictor(
        llm=OpenAI(model_name="gpt-3.5-turbo-0301", openai_api_key=api_key)
    )
    prompt_helper = PromptHelper(
        max_input_size,
        num_outputs,
        max_chunk_overlap,
        embedding_limit,
        chunk_size_limit,
        separator=separator,
    )
    documents, index_name = get_documents(file_src)
    if os.path.exists(f"./index/{index_name}.json"):
        logging.info("找到了缓存的索引文件，加载中……")
        return GPTSimpleVectorIndex.load_from_disk(f"./index/{index_name}.json")
    else:
        try:
            logging.debug("构建索引中……")
            index = GPTSimpleVectorIndex(
                documents, llm_predictor=llm_predictor, prompt_helper=prompt_helper
            )
            os.makedirs("./index", exist_ok=True)
            index.save_to_disk(f"./index/{index_name}.json")
            return index
        except Exception as e:
            print(e)
            return None


def chat_ai(
    api_key,
    index,
    question,
    context,
    chatbot,
    reply_language,
):
    os.environ["OPENAI_API_KEY"] = api_key

    logging.info(f"Question: {question}")

    response, chatbot_display, status_text = ask_ai(
        api_key,
        index,
        question,
        replace_today(PROMPT_TEMPLATE),
        REFINE_TEMPLATE,
        SIM_K,
        INDEX_QUERY_TEMPRATURE,
        context,
        reply_language,
    )
    if response is None:
        status_text = "查询失败，请换个问法试试"
        return context, chatbot
    response = response

    context.append({"role": "user", "content": question})
    context.append({"role": "assistant", "content": response})
    chatbot.append((question, chatbot_display))

    os.environ["OPENAI_API_KEY"] = ""
    return context, chatbot, status_text


def ask_ai(
    api_key,
    index,
    question,
    prompt_tmpl,
    refine_tmpl,
    sim_k=1,
    temprature=0,
    prefix_messages=[],
    reply_language="中文",
):
    os.environ["OPENAI_API_KEY"] = api_key

    logging.debug("Index file found")
    logging.debug("Querying index...")
    llm_predictor = LLMPredictor(
        llm=OpenAI(
            temperature=temprature,
            model_name="gpt-3.5-turbo-0301",
            prefix_messages=prefix_messages,
        )
    )

    response = None  # Initialize response variable to avoid UnboundLocalError
    qa_prompt = QuestionAnswerPrompt(prompt_tmpl.replace("{reply_language}", reply_language))
    rf_prompt = RefinePrompt(refine_tmpl.replace("{reply_language}", reply_language))
    response = index.query(
        question,
        llm_predictor=llm_predictor,
        similarity_top_k=sim_k,
        text_qa_template=qa_prompt,
        refine_template=rf_prompt,
        response_mode="compact",
    )

    if response is not None:
        logging.info(f"Response: {response}")
        ret_text = response.response
        nodes = []
        for index, node in enumerate(response.source_nodes):
            brief = node.source_text[:25].replace("\n", "")
            nodes.append(
                f"<details><summary>[{index+1}]\t{brief}...</summary><p>{node.source_text}</p></details>"
            )
        new_response = ret_text + "\n----------\n" + "\n\n".join(nodes)
        logging.info(
            f"Response: {colorama.Fore.BLUE}{ret_text}{colorama.Style.RESET_ALL}"
        )
        os.environ["OPENAI_API_KEY"] = ""
        return ret_text, new_response, f"查询消耗了{llm_predictor.last_token_usage} tokens"
    else:
        logging.warning("No response found, returning None")
        os.environ["OPENAI_API_KEY"] = ""
        return None


def add_space(text):
    punctuations = {"，": "， ", "。": "。 ", "？": "？ ", "！": "！ ", "：": "： ", "；": "； "}
    for cn_punc, en_punc in punctuations.items():
        text = text.replace(cn_punc, en_punc)
    return text
