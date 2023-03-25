from __future__ import annotations
import logging

from llama_index import Prompt
from typing import List, Tuple
import mdtex2html

from modules.presets import *
from modules.llama_func import *


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
    user, bot = y[-1]
    if not detect_converted_mark(user):
        user = convert_asis(user)
    if not detect_converted_mark(bot):
        bot = convert_mdtext(bot)
    y[-1] = (user, bot)
    return y

with open("./assets/custom.js", "r", encoding="utf-8") as f, open("./assets/Kelpy-Codos.js", "r", encoding="utf-8") as f2:
    customJS = f.read()
    kelpyCodos = f2.read()

def reload_javascript():
    print("Reloading javascript...")
    js = f'<script>{customJS}</script><script>{kelpyCodos}</script>'
    def template_response(*args, **kwargs):
        res = GradioTemplateResponseOriginal(*args, **kwargs)
        res.body = res.body.replace(b'</html>', f'{js}</html>'.encode("utf8"))
        res.init_headers()
        return res

    gr.routes.templates.TemplateResponse = template_response

GradioTemplateResponseOriginal = gr.routes.templates.TemplateResponse