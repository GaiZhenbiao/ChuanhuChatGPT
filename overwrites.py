from __future__ import annotations
import logging

from llama_index import Prompt
from typing import List, Tuple
import mdtex2html

from presets import *
from llama_func import *


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
    if y is None or y == []:
        return []
    tag_regex = re.compile(r"^<\w+>[^<]+</\w+>")
    if tag_regex.search(y[-1][1]):
        y[-1] = (y[-1][0].replace("\n", "<br>"), y[-1][1])
    else:
        y[-1] = (y[-1][0].replace("\n", "<br>"), convert_mdtext(y[-1][1]))
    return y
