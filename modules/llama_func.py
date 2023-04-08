import os
import logging

from llama_index import download_loader
from llama_index import (
    Document,
    LLMPredictor,
    PromptHelper,
    QuestionAnswerPrompt,
    RefinePrompt,
)
import colorama
import PyPDF2
from tqdm import tqdm

from modules.presets import *
from modules.utils import *
from modules.config import local_embedding


def get_index_name(file_src):
    file_paths = [x.name for x in file_src]
    file_paths.sort(key=lambda x: os.path.basename(x))

    md5_hash = hashlib.md5()
    for file_path in file_paths:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                md5_hash.update(chunk)

    return md5_hash.hexdigest()


def block_split(text):
    blocks = []
    while len(text) > 0:
        blocks.append(Document(text[:1000]))
        text = text[1000:]
    return blocks


def get_documents(file_src):
    documents = []
    logging.debug("Loading documents...")
    logging.debug(f"file_src: {file_src}")
    for file in file_src:
        filepath = file.name
        filename = os.path.basename(filepath)
        file_type = os.path.splitext(filepath)[1]
        logging.info(f"loading file: {filename}")
        try:
            if file_type == ".pdf":
                logging.debug("Loading PDF...")
                try:
                    from modules.pdf_func import parse_pdf
                    from modules.config import advance_docs

                    two_column = advance_docs["pdf"].get("two_column", False)
                    pdftext = parse_pdf(filepath, two_column).text
                except:
                    pdftext = ""
                    with open(filepath, "rb") as pdfFileObj:
                        pdfReader = PyPDF2.PdfReader(pdfFileObj)
                        for page in tqdm(pdfReader.pages):
                            pdftext += page.extract_text()
                text_raw = pdftext
            elif file_type == ".docx":
                logging.debug("Loading Word...")
                DocxReader = download_loader("DocxReader")
                loader = DocxReader()
                text_raw = loader.load_data(file=filepath)[0].text
            elif file_type == ".epub":
                logging.debug("Loading EPUB...")
                EpubReader = download_loader("EpubReader")
                loader = EpubReader()
                text_raw = loader.load_data(file=filepath)[0].text
            elif file_type == ".xlsx":
                logging.debug("Loading Excel...")
                text_list = excel_to_string(filepath)
                for elem in text_list:
                    documents.append(Document(elem))
                continue
            else:
                logging.debug("Loading text file...")
                with open(filepath, "r", encoding="utf-8") as f:
                    text_raw = f.read()
        except Exception as e:
            logging.error(f"Error loading file: {filename}")
            pass
        text = add_space(text_raw)
        # text = block_split(text)
        # documents += text
        documents += [Document(text)]
    logging.debug("Documents loaded.")
    return documents


def construct_index(
    api_key,
    file_src,
    max_input_size=4096,
    num_outputs=5,
    max_chunk_overlap=20,
    chunk_size_limit=600,
    embedding_limit=None,
    separator=" ",
):
    from langchain.chat_models import ChatOpenAI
    from langchain.embeddings.huggingface import HuggingFaceEmbeddings
    from llama_index import GPTSimpleVectorIndex, ServiceContext, LangchainEmbedding, OpenAIEmbedding

    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    chunk_size_limit = None if chunk_size_limit == 0 else chunk_size_limit
    embedding_limit = None if embedding_limit == 0 else embedding_limit
    separator = " " if separator == "" else separator

    llm_predictor = LLMPredictor(
        llm=ChatOpenAI(model_name="gpt-3.5-turbo-0301", openai_api_key=api_key)
    )
    prompt_helper = PromptHelper(
        max_input_size=max_input_size,
        num_output=num_outputs,
        max_chunk_overlap=max_chunk_overlap,
        embedding_limit=embedding_limit,
        chunk_size_limit=600,
        separator=separator,
    )
    index_name = get_index_name(file_src)
    if os.path.exists(f"./index/{index_name}.json"):
        logging.info("找到了缓存的索引文件，加载中……")
        return GPTSimpleVectorIndex.load_from_disk(f"./index/{index_name}.json")
    else:
        try:
            documents = get_documents(file_src)
            if local_embedding:
                embed_model = LangchainEmbedding(HuggingFaceEmbeddings())
            else:
                embed_model = OpenAIEmbedding()
            logging.info("构建索引中……")
            with retrieve_proxy():
                service_context = ServiceContext.from_defaults(
                    llm_predictor=llm_predictor,
                    prompt_helper=prompt_helper,
                    chunk_size_limit=chunk_size_limit,
                    embed_model=embed_model,
                )
                index = GPTSimpleVectorIndex.from_documents(
                    documents, service_context=service_context
                )
            logging.debug("索引构建完成！")
            os.makedirs("./index", exist_ok=True)
            index.save_to_disk(f"./index/{index_name}.json")
            logging.debug("索引已保存至本地!")
            return index

        except Exception as e:
            logging.error("索引构建失败！", e)
            print(e)
            return None


def add_space(text):
    punctuations = {"，": "， ", "。": "。 ", "？": "？ ", "！": "！ ", "：": "： ", "；": "； "}
    for cn_punc, en_punc in punctuations.items():
        text = text.replace(cn_punc, en_punc)
    return text
