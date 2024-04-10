import hashlib
import logging
import os

import PyPDF2
from langchain_community.chat_models import ChatOpenAI
from langchain_community.embeddings.huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from tqdm import tqdm

from modules.config import local_embedding
from modules.presets import *
from modules.utils import *


def get_documents(file_src):
    from langchain.schema import Document
    from langchain.text_splitter import TokenTextSplitter

    text_splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=30)

    documents = []
    logging.debug("Loading documents...")
    logging.debug(f"file_src: {file_src}")
    for file in file_src:
        filepath = file.name
        filename = os.path.basename(filepath)
        file_type = os.path.splitext(filename)[1]
        logging.info(f"loading file: {filename}")
        texts = None
        try:
            if file_type == ".pdf":
                logging.debug("Loading PDF...")
                try:
                    from modules.config import advance_docs
                    from modules.pdf_func import parse_pdf

                    two_column = advance_docs["pdf"].get("two_column", False)
                    pdftext = parse_pdf(filepath, two_column).text
                except:
                    pdftext = ""
                    with open(filepath, "rb") as pdfFileObj:
                        pdfReader = PyPDF2.PdfReader(pdfFileObj)
                        for page in tqdm(pdfReader.pages):
                            pdftext += page.extract_text()
                texts = [Document(page_content=pdftext, metadata={"source": filepath})]
            elif file_type == ".docx":
                logging.debug("Loading Word...")
                from langchain.document_loaders import \
                    UnstructuredWordDocumentLoader

                loader = UnstructuredWordDocumentLoader(filepath)
                texts = loader.load()
            elif file_type == ".pptx":
                logging.debug("Loading PowerPoint...")
                from langchain.document_loaders import \
                    UnstructuredPowerPointLoader

                loader = UnstructuredPowerPointLoader(filepath)
                texts = loader.load()
            elif file_type == ".epub":
                logging.debug("Loading EPUB...")
                from langchain.document_loaders import UnstructuredEPubLoader

                loader = UnstructuredEPubLoader(filepath)
                texts = loader.load()
            elif file_type == ".xlsx":
                logging.debug("Loading Excel...")
                text_list = excel_to_string(filepath)
                texts = []
                for elem in text_list:
                    texts.append(
                        Document(page_content=elem, metadata={"source": filepath})
                    )
            elif file_type in [
                ".jpg",
                ".jpeg",
                ".png",
                ".heif",
                ".heic",
                ".webp",
                ".bmp",
                ".gif",
                ".tiff",
                ".tif",
            ]:
                raise gr.Warning(
                    i18n("不支持的文件: ")
                    + filename
                    + i18n("，请使用 .pdf, .docx, .pptx, .epub, .xlsx 等文档。")
                )
            else:
                logging.debug("Loading text file...")
                from langchain.document_loaders import TextLoader

                loader = TextLoader(filepath, "utf8")
                texts = loader.load()
        except Exception as e:
            import traceback

            logging.error(f"Error loading file: {filename}")
            traceback.print_exc()

        if texts is not None:
            texts = text_splitter.split_documents(texts)
            documents.extend(texts)
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
    load_from_cache_if_possible=True,
):
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    else:
        # 由于一个依赖的愚蠢的设计，这里必须要有一个API KEY
        os.environ["OPENAI_API_KEY"] = "sk-xxxxxxx"
    logging.debug(f"api base: {os.environ.get('OPENAI_API_BASE', None)}")
    chunk_size_limit = None if chunk_size_limit == 0 else chunk_size_limit
    embedding_limit = None if embedding_limit == 0 else embedding_limit
    separator = " " if separator == "" else separator

    index_name = get_file_hash(file_src)
    index_path = f"./index/{index_name}"
    if local_embedding:
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/distiluse-base-multilingual-cased-v2"
        )
    else:
        if os.environ.get("OPENAI_API_TYPE", "openai") == "openai":
            embeddings = OpenAIEmbeddings(
                openai_api_base=os.environ.get("OPENAI_API_BASE", None),
                openai_api_key=os.environ.get("OPENAI_EMBEDDING_API_KEY", api_key),
                model="text-embedding-3-large",
            )
        else:
            embeddings = OpenAIEmbeddings(
                deployment=os.environ["AZURE_EMBEDDING_DEPLOYMENT_NAME"],
                openai_api_key=os.environ["AZURE_OPENAI_API_KEY"],
                model=os.environ["AZURE_EMBEDDING_MODEL_NAME"],
                openai_api_base=os.environ["AZURE_OPENAI_API_BASE_URL"],
                openai_api_type="azure",
            )
    if os.path.exists(index_path) and load_from_cache_if_possible:
        logging.info(i18n("找到了缓存的索引文件，加载中……"))
        return FAISS.load_local(
            index_path, embeddings, allow_dangerous_deserialization=True
        )
    else:
        documents = get_documents(file_src)
        logging.debug(i18n("构建索引中……"))
        if documents:
            with retrieve_proxy():
                index = FAISS.from_documents(documents, embeddings)
        else:
            raise Exception(i18n("没有找到任何支持的文档。"))
        logging.debug(i18n("索引构建完成！"))
        os.makedirs("./index", exist_ok=True)
        index.save_local(index_path)
        logging.debug(i18n("索引已保存至本地!"))
        return index
