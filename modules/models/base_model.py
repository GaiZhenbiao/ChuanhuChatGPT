from __future__ import annotations
from typing import TYPE_CHECKING, List

import logging
import json
import commentjson as cjson
import os
import sys
import requests
import urllib3
import traceback
import pathlib

from tqdm import tqdm
import colorama
from duckduckgo_search import ddg
import asyncio
import aiohttp
from enum import Enum

from ..presets import *
from ..llama_func import *
from ..utils import *
from .. import shared
from ..config import retrieve_proxy


class ModelType(Enum):
    Unknown = -1
    OpenAI = 0
    ChatGLM = 1
    LLaMA = 2
    XMChat = 3
    StableLM = 4
    MOSS = 5

    @classmethod
    def get_type(cls, model_name: str):
        model_type = None
        model_name_lower = model_name.lower()
        if "gpt" in model_name_lower:
            model_type = ModelType.OpenAI
        elif "chatglm" in model_name_lower:
            model_type = ModelType.ChatGLM
        elif "llama" in model_name_lower or "alpaca" in model_name_lower:
            model_type = ModelType.LLaMA
        elif "xmchat" in model_name_lower:
            model_type = ModelType.XMChat
        elif "stablelm" in model_name_lower:
            model_type = ModelType.StableLM
        elif "moss" in model_name_lower:
            model_type = ModelType.MOSS
        else:
            model_type = ModelType.Unknown
        return model_type


class BaseLLMModel:
    def __init__(
        self,
        model_name,
        system_prompt="",
        temperature=1.0,
        top_p=1.0,
        n_choices=1,
        stop=None,
        max_generation_token=None,
        presence_penalty=0,
        frequency_penalty=0,
        logit_bias=None,
        user="",
    ) -> None:
        self.history = []
        self.all_token_counts = []
        self.model_name = model_name
        self.model_type = ModelType.get_type(model_name)
        try:
            self.token_upper_limit = MODEL_TOKEN_LIMIT[model_name]
        except KeyError:
            self.token_upper_limit = DEFAULT_TOKEN_LIMIT
        self.interrupted = False
        self.system_prompt = system_prompt
        self.api_key = None
        self.need_api_key = False
        self.single_turn = False

        self.temperature = temperature
        self.top_p = top_p
        self.n_choices = n_choices
        self.stop_sequence = stop
        self.max_generation_token = None
        self.presence_penalty = presence_penalty
        self.frequency_penalty = frequency_penalty
        self.logit_bias = logit_bias
        self.user_identifier = user

    def get_answer_stream_iter(self):
        """stream predict, need to be implemented
        conversations are stored in self.history, with the most recent question, in OpenAI format
        should return a generator, each time give the next word (str) in the answer
        """
        logging.warning("stream predict not implemented, using at once predict instead")
        response, _ = self.get_answer_at_once()
        yield response

    def get_answer_at_once(self):
        """predict at once, need to be implemented
        conversations are stored in self.history, with the most recent question, in OpenAI format
        Should return:
        the answer (str)
        total token count (int)
        """
        logging.warning("at once predict not implemented, using stream predict instead")
        response_iter = self.get_answer_stream_iter()
        count = 0
        for response in response_iter:
            count += 1
        return response, sum(self.all_token_counts) + count

    def billing_info(self):
        """get billing infomation, inplement if needed"""
        logging.warning("billing info not implemented, using default")
        return BILLING_NOT_APPLICABLE_MSG

    def count_token(self, user_input):
        """get token count from input, implement if needed"""
        # logging.warning("token count not implemented, using default")
        return len(user_input)

    def stream_next_chatbot(self, inputs, chatbot, fake_input=None, display_append=""):
        def get_return_value():
            return chatbot, status_text

        status_text = i18n("开始实时传输回答……")
        if fake_input:
            chatbot.append((fake_input, ""))
        else:
            chatbot.append((inputs, ""))

        user_token_count = self.count_token(inputs)
        self.all_token_counts.append(user_token_count)
        logging.debug(f"输入token计数: {user_token_count}")

        stream_iter = self.get_answer_stream_iter()

        for partial_text in stream_iter:
            chatbot[-1] = (chatbot[-1][0], partial_text + display_append)
            self.all_token_counts[-1] += 1
            status_text = self.token_message()
            yield get_return_value()
            if self.interrupted:
                self.recover()
                break
        self.history.append(construct_assistant(partial_text))

    def next_chatbot_at_once(self, inputs, chatbot, fake_input=None, display_append=""):
        if fake_input:
            chatbot.append((fake_input, ""))
        else:
            chatbot.append((inputs, ""))
        if fake_input is not None:
            user_token_count = self.count_token(fake_input)
        else:
            user_token_count = self.count_token(inputs)
        self.all_token_counts.append(user_token_count)
        ai_reply, total_token_count = self.get_answer_at_once()
        self.history.append(construct_assistant(ai_reply))
        if fake_input is not None:
            self.history[-2] = construct_user(fake_input)
        chatbot[-1] = (chatbot[-1][0], ai_reply + display_append)
        if fake_input is not None:
            self.all_token_counts[-1] += count_token(construct_assistant(ai_reply))
        else:
            self.all_token_counts[-1] = total_token_count - sum(self.all_token_counts)
        status_text = self.token_message()
        return chatbot, status_text

    def handle_file_upload(self, files, chatbot):
        """if the model accepts multi modal input, implement this function"""
        status = gr.Markdown.update()
        if files:
            construct_index(self.api_key, file_src=files)
            status = "索引构建完成"
        return gr.Files.update(), chatbot, status

    def prepare_inputs(self, real_inputs, use_websearch, files, reply_language, chatbot):
        fake_inputs = None
        display_append = []
        limited_context = False
        fake_inputs = real_inputs
        if files:
            from llama_index.indices.vector_store.base_query import GPTVectorStoreIndexQuery
            from llama_index.indices.query.schema import QueryBundle
            from langchain.embeddings.huggingface import HuggingFaceEmbeddings
            from langchain.chat_models import ChatOpenAI
            from llama_index import (
                GPTSimpleVectorIndex,
                ServiceContext,
                LangchainEmbedding,
                OpenAIEmbedding,
            )
            limited_context = True
            msg = "加载索引中……"
            logging.info(msg)
            # yield chatbot + [(inputs, "")], msg
            index = construct_index(self.api_key, file_src=files)
            assert index is not None, "获取索引失败"
            msg = "索引获取成功，生成回答中……"
            logging.info(msg)
            if local_embedding or self.model_type != ModelType.OpenAI:
                embed_model = LangchainEmbedding(HuggingFaceEmbeddings(model_name = "sentence-transformers/distiluse-base-multilingual-cased-v2"))
            else:
                embed_model = OpenAIEmbedding()
            # yield chatbot + [(inputs, "")], msg
            with retrieve_proxy():
                prompt_helper = PromptHelper(
                    max_input_size=4096,
                    num_output=5,
                    max_chunk_overlap=20,
                    chunk_size_limit=600,
                )
                from llama_index import ServiceContext

                service_context = ServiceContext.from_defaults(
                    prompt_helper=prompt_helper, embed_model=embed_model
                )
                query_object = GPTVectorStoreIndexQuery(
                    index.index_struct,
                    service_context=service_context,
                    similarity_top_k=5,
                    vector_store=index._vector_store,
                    docstore=index._docstore,
                    response_synthesizer=None
                )
                query_bundle = QueryBundle(real_inputs)
                nodes = query_object.retrieve(query_bundle)
            reference_results = [n.node.text for n in nodes]
            reference_results = add_source_numbers(reference_results, use_source=False)
            display_append = add_details(reference_results)
            display_append = "\n\n" + "".join(display_append)
            real_inputs = (
                replace_today(PROMPT_TEMPLATE)
                .replace("{query_str}", real_inputs)
                .replace("{context_str}", "\n\n".join(reference_results))
                .replace("{reply_language}", reply_language)
            )
        elif use_websearch:
            limited_context = True
            search_results = ddg(real_inputs, max_results=5)
            reference_results = []
            for idx, result in enumerate(search_results):
                logging.debug(f"搜索结果{idx + 1}：{result}")
                domain_name = urllib3.util.parse_url(result["href"]).host
                reference_results.append([result["body"], result["href"]])
                display_append.append(
                    # f"{idx+1}. [{domain_name}]({result['href']})\n"
                    f"<li><a href=\"{result['href']}\" target=\"_blank\">{domain_name}</a></li>\n"
                )
            reference_results = add_source_numbers(reference_results)
            display_append = "<ol>\n\n" + "".join(display_append) + "</ol>"
            real_inputs = (
                replace_today(WEBSEARCH_PTOMPT_TEMPLATE)
                .replace("{query}", real_inputs)
                .replace("{web_results}", "\n\n".join(reference_results))
                .replace("{reply_language}", reply_language)
            )
        else:
            display_append = ""
        return limited_context, fake_inputs, display_append, real_inputs, chatbot

    def predict(
        self,
        inputs,
        chatbot,
        stream=False,
        use_websearch=False,
        files=None,
        reply_language="中文",
        should_check_token_count=True,
    ):  # repetition_penalty, top_k

        status_text = "开始生成回答……"
        logging.info(
            "输入为：" + colorama.Fore.BLUE + f"{inputs}" + colorama.Style.RESET_ALL
        )
        if should_check_token_count:
            yield chatbot + [(inputs, "")], status_text
        if reply_language == "跟随问题语言（不稳定）":
            reply_language = "the same language as the question, such as English, 中文, 日本語, Español, Français, or Deutsch."

        limited_context, fake_inputs, display_append, inputs, chatbot = self.prepare_inputs(real_inputs=inputs, use_websearch=use_websearch, files=files, reply_language=reply_language, chatbot=chatbot)
        yield chatbot + [(fake_inputs, "")], status_text

        if (
            self.need_api_key and
            self.api_key is None
            and not shared.state.multi_api_key
        ):
            status_text = STANDARD_ERROR_MSG + NO_APIKEY_MSG
            logging.info(status_text)
            chatbot.append((inputs, ""))
            if len(self.history) == 0:
                self.history.append(construct_user(inputs))
                self.history.append("")
                self.all_token_counts.append(0)
            else:
                self.history[-2] = construct_user(inputs)
            yield chatbot + [(inputs, "")], status_text
            return
        elif len(inputs.strip()) == 0:
            status_text = STANDARD_ERROR_MSG + NO_INPUT_MSG
            logging.info(status_text)
            yield chatbot + [(inputs, "")], status_text
            return

        if self.single_turn:
            self.history = []
            self.all_token_counts = []
        self.history.append(construct_user(inputs))

        try:
            if stream:
                logging.debug("使用流式传输")
                iter = self.stream_next_chatbot(
                    inputs,
                    chatbot,
                    fake_input=fake_inputs,
                    display_append=display_append,
                )
                for chatbot, status_text in iter:
                    yield chatbot, status_text
            else:
                logging.debug("不使用流式传输")
                chatbot, status_text = self.next_chatbot_at_once(
                    inputs,
                    chatbot,
                    fake_input=fake_inputs,
                    display_append=display_append,
                )
                yield chatbot, status_text
        except Exception as e:
            traceback.print_exc()
            status_text = STANDARD_ERROR_MSG + str(e)
            yield chatbot, status_text

        if len(self.history) > 1 and self.history[-1]["content"] != inputs:
            logging.info(
                "回答为："
                + colorama.Fore.BLUE
                + f"{self.history[-1]['content']}"
                + colorama.Style.RESET_ALL
            )

        if limited_context:
            # self.history = self.history[-4:]
            # self.all_token_counts = self.all_token_counts[-2:]
            self.history = []
            self.all_token_counts = []

        max_token = self.token_upper_limit - TOKEN_OFFSET

        if sum(self.all_token_counts) > max_token and should_check_token_count:
            count = 0
            while (
                sum(self.all_token_counts)
                > self.token_upper_limit * REDUCE_TOKEN_FACTOR
                and sum(self.all_token_counts) > 0
            ):
                count += 1
                del self.all_token_counts[0]
                del self.history[:2]
            logging.info(status_text)
            status_text = f"为了防止token超限，模型忘记了早期的 {count} 轮对话"
            yield chatbot, status_text

        self.auto_save(chatbot)

    def retry(
        self,
        chatbot,
        stream=False,
        use_websearch=False,
        files=None,
        reply_language="中文",
    ):
        logging.debug("重试中……")
        if len(self.history) > 0:
            inputs = self.history[-2]["content"]
            del self.history[-2:]
            self.all_token_counts.pop()
        elif len(chatbot) > 0:
            inputs = chatbot[-1][0]
        else:
            yield chatbot, f"{STANDARD_ERROR_MSG}上下文是空的"
            return

        iter = self.predict(
            inputs,
            chatbot,
            stream=stream,
            use_websearch=use_websearch,
            files=files,
            reply_language=reply_language,
        )
        for x in iter:
            yield x
        logging.debug("重试完毕")

    # def reduce_token_size(self, chatbot):
    #     logging.info("开始减少token数量……")
    #     chatbot, status_text = self.next_chatbot_at_once(
    #         summarize_prompt,
    #         chatbot
    #     )
    #     max_token_count = self.token_upper_limit * REDUCE_TOKEN_FACTOR
    #     num_chat = find_n(self.all_token_counts, max_token_count)
    #     logging.info(f"previous_token_count: {self.all_token_counts}, keeping {num_chat} chats")
    #     chatbot = chatbot[:-1]
    #     self.history = self.history[-2*num_chat:] if num_chat > 0 else []
    #     self.all_token_counts = self.all_token_counts[-num_chat:] if num_chat > 0 else []
    #     msg = f"保留了最近{num_chat}轮对话"
    #     logging.info(msg)
    #     logging.info("减少token数量完毕")
    #     return chatbot, msg + "，" + self.token_message(self.all_token_counts if len(self.all_token_counts) > 0 else [0])

    def interrupt(self):
        self.interrupted = True

    def recover(self):
        self.interrupted = False

    def set_token_upper_limit(self, new_upper_limit):
        self.token_upper_limit = new_upper_limit
        print(f"token上限设置为{new_upper_limit}")

    def set_temperature(self, new_temperature):
        self.temperature = new_temperature

    def set_top_p(self, new_top_p):
        self.top_p = new_top_p

    def set_n_choices(self, new_n_choices):
        self.n_choices = new_n_choices

    def set_stop_sequence(self, new_stop_sequence: str):
        new_stop_sequence = new_stop_sequence.split(",")
        self.stop_sequence = new_stop_sequence

    def set_max_tokens(self, new_max_tokens):
        self.max_generation_token = new_max_tokens

    def set_presence_penalty(self, new_presence_penalty):
        self.presence_penalty = new_presence_penalty

    def set_frequency_penalty(self, new_frequency_penalty):
        self.frequency_penalty = new_frequency_penalty

    def set_logit_bias(self, logit_bias):
        logit_bias = logit_bias.split()
        bias_map = {}
        encoding = tiktoken.get_encoding("cl100k_base")
        for line in logit_bias:
            word, bias_amount = line.split(":")
            if word:
                for token in encoding.encode(word):
                    bias_map[token] = float(bias_amount)
        self.logit_bias = bias_map

    def set_user_identifier(self, new_user_identifier):
        self.user_identifier = new_user_identifier

    def set_system_prompt(self, new_system_prompt):
        self.system_prompt = new_system_prompt

    def set_key(self, new_access_key):
        self.api_key = new_access_key.strip()
        msg = i18n("API密钥更改为了") + hide_middle_chars(self.api_key)
        logging.info(msg)
        return self.api_key, msg

    def set_single_turn(self, new_single_turn):
        self.single_turn = new_single_turn

    def reset(self):
        self.history = []
        self.all_token_counts = []
        self.interrupted = False
        pathlib.Path(os.path.join(HISTORY_DIR, self.user_identifier, new_auto_history_filename(os.path.join(HISTORY_DIR, self.user_identifier)))).touch()
        return [], self.token_message([0])

    def delete_first_conversation(self):
        if self.history:
            del self.history[:2]
            del self.all_token_counts[0]
        return self.token_message()

    def delete_last_conversation(self, chatbot):
        if len(chatbot) > 0 and STANDARD_ERROR_MSG in chatbot[-1][1]:
            msg = "由于包含报错信息，只删除chatbot记录"
            chatbot.pop()
            return chatbot, self.history
        if len(self.history) > 0:
            self.history.pop()
            self.history.pop()
        if len(chatbot) > 0:
            msg = "删除了一组chatbot对话"
            chatbot.pop()
        if len(self.all_token_counts) > 0:
            msg = "删除了一组对话的token计数记录"
            self.all_token_counts.pop()
        msg = "删除了一组对话"
        return chatbot, msg

    def token_message(self, token_lst=None):
        if token_lst is None:
            token_lst = self.all_token_counts
        token_sum = 0
        for i in range(len(token_lst)):
            token_sum += sum(token_lst[: i + 1])
        return i18n("Token 计数: ") + f"{sum(token_lst)}" + i18n("，本次对话累计消耗了 ") + f"{token_sum} tokens"

    def save_chat_history(self, filename, chatbot, user_name):
        if filename == "":
            return
        if not filename.endswith(".json"):
            filename += ".json"
        return save_file(filename, self.system_prompt, self.history, chatbot, user_name)

    def auto_save(self, chatbot):
        history_file_path = get_history_filepath(self.user_identifier)
        save_file(history_file_path, self.system_prompt, self.history, chatbot, self.user_identifier)

    def export_markdown(self, filename, chatbot, user_name):
        if filename == "":
            return
        if not filename.endswith(".md"):
            filename += ".md"
        return save_file(filename, self.system_prompt, self.history, chatbot, user_name)

    def load_chat_history(self, filename, user_name):
        logging.debug(f"{user_name} 加载对话历史中……")
        logging.info(f"filename: {filename}")
        if type(filename) != str and filename is not None:
            filename = filename.name
        try:
            if "/" not in filename:
                history_file_path = os.path.join(HISTORY_DIR, user_name, filename)
            else:
                history_file_path = filename
            with open(history_file_path, "r") as f:
                json_s = json.load(f)
            try:
                if type(json_s["history"][0]) == str:
                    logging.info("历史记录格式为旧版，正在转换……")
                    new_history = []
                    for index, item in enumerate(json_s["history"]):
                        if index % 2 == 0:
                            new_history.append(construct_user(item))
                        else:
                            new_history.append(construct_assistant(item))
                    json_s["history"] = new_history
                    logging.info(new_history)
            except:
                pass
            logging.debug(f"{user_name} 加载对话历史完毕")
            self.history = json_s["history"]
            return os.path.basename(filename), json_s["system"], json_s["chatbot"]
        except:
            # 没有对话历史或者对话历史解析失败
            logging.info(f"没有找到对话历史记录 {filename}")
            return gr.update(), self.system_prompt, gr.update()

    def auto_load(self):
        if self.user_identifier == "":
            self.reset()
            return self.system_prompt, gr.update()
        history_file_path = get_history_filepath(self.user_identifier)
        filename, system_prompt, chatbot = self.load_chat_history(history_file_path, self.user_identifier)
        return system_prompt, chatbot


    def like(self):
        """like the last response, implement if needed
        """
        return gr.update()

    def dislike(self):
        """dislike the last response, implement if needed
        """
        return gr.update()
