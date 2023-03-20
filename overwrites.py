from __future__ import annotations
import os

import llama_index

from llama_index import (
    LLMPredictor,
    GPTTreeIndex,
    Document,
    GPTSimpleVectorIndex,
    SimpleDirectoryReader,
    RefinePrompt,
    QuestionAnswerPrompt,
    GPTListIndex,
    PromptHelper,
)
from pathlib import Path
from docx import Document as DocxDocument
from tqdm import tqdm
import re
from langchain.llms import OpenAIChat, OpenAI
from llama_index.composability import ComposableGraph
from IPython.display import Markdown, display
import json
from llama_index import Prompt
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Type

import logging
import sys

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Type
import logging
import json
import gradio as gr

# import openai
import os
import traceback
import requests

# import markdown
import csv
import mdtex2html
from pypinyin import lazy_pinyin
from presets import *
from llama_func import *
import tiktoken
from tqdm import tqdm
import colorama
import os
from llama_index import (
    GPTSimpleVectorIndex,
    GPTTreeIndex,
    GPTKeywordTableIndex,
    GPTListIndex,
)
from llama_index import SimpleDirectoryReader, download_loader
from llama_index import (
    Document,
    LLMPredictor,
    PromptHelper,
    QuestionAnswerPrompt,
    RefinePrompt,
)
from langchain.llms import OpenAIChat, OpenAI
from duckduckgo_search import ddg
import datetime

def compact_text_chunks(self, prompt: Prompt, text_chunks: List[str]) -> List[str]:
    logging.debug("Compacting text chunks...🚀🚀🚀")
    combined_str = [c.strip() for c in text_chunks if c.strip()]
    combined_str = [f"[{index+1}] {c}" for index, c in enumerate(combined_str)]
    combined_str = "\n\n".join(combined_str)
    # resplit based on self.max_chunk_overlap
    text_splitter = self.get_text_splitter_given_prompt(prompt, 1, padding=1)
    return text_splitter.split_text(combined_str)


def postprocess(
    self, y: List[Tuple[str | None, str | None]]
) -> List[Tuple[str | None, str | None]]:
    """
    Parameters:
        y: List of tuples representing the message and response pairs. Each message and response should be a string, which may be in Markdown format.
    Returns:
        List of tuples representing the message and response. Each message and response will be a string of HTML.
    """
    if y is None:
        return []
    for i, (message, response) in enumerate(y):
        y[i] = (
            # None if message is None else markdown.markdown(message),
            # None if response is None else markdown.markdown(response),
            None if message is None else message,
            None if response is None else mdtex2html.convert(response, extensions=['fenced_code','codehilite','tables']),
        )
    return y
