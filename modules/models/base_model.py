from __future__ import annotations

import base64
import json
import time
import logging
import os
import shutil
import time
import traceback
from collections import deque
from enum import Enum
from io import BytesIO
from itertools import islice
from threading import Condition, Thread
from typing import Any, Dict, List, Optional
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, TypeVar, Union
from uuid import UUID
from langchain_core.outputs import ChatGenerationChunk, GenerationChunk

import colorama
import PIL
import urllib3
from duckduckgo_search import DDGS
from huggingface_hub import hf_hub_download
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chat_models.base import BaseChatModel
from langchain.schema import (AgentAction, AgentFinish, AIMessage, BaseMessage,
                              HumanMessage, SystemMessage)

from .. import shared
from ..config import retrieve_proxy
from ..index_func import *
from ..presets import *
from ..utils import *


class CallbackToIterator:
    def __init__(self):
        self.queue = deque()
        self.cond = Condition()
        self.finished = False

    def callback(self, result):
        with self.cond:
            self.queue.append(result)
            self.cond.notify()  # Wake up the generator.

    def __iter__(self):
        return self

    def __next__(self):
        with self.cond:
            # Wait for a value to be added to the queue.
            while not self.queue and not self.finished:
                self.cond.wait()
            if not self.queue:
                raise StopIteration()
            return self.queue.popleft()

    def finish(self):
        with self.cond:
            self.finished = True
            self.cond.notify()  # Wake up the generator if it's waiting.


def get_action_description(action):
    action_name = action.tool
    action_name = " ".join(action_name.split("_")).title()
    action_input = action.tool_input
    if isinstance(action_input, dict):
        action_input = " ".join(action_input.values())
    if action_name != "Final Answer":
        return f'<!-- S O PREFIX --><p class="agent-prefix">{action_name}: {action_input}\n</p><!-- E O PREFIX -->'
    else:
        return ""


class ChuanhuCallbackHandler(BaseCallbackHandler):
    def __init__(self, callback) -> None:
        """Initialize callback handler."""
        self.callback = callback

    def on_agent_action(
        self, action: AgentAction, color: Optional[str] = None, **kwargs: Any
    ) -> Any:
        self.callback(get_action_description(action))

    def on_tool_end(
        self,
        output: str,
        color: Optional[str] = None,
        observation_prefix: Optional[str] = None,
        llm_prefix: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """If not the final action, print out observation."""
        # if observation_prefix is not None:
        #     self.callback(f"\n\n{observation_prefix}")
        # self.callback(output)
        # if llm_prefix is not None:
        #     self.callback(f"\n\n{llm_prefix}")
        if observation_prefix is not None:
            logging.info(observation_prefix)
        self.callback(output)
        if llm_prefix is not None:
            logging.info(llm_prefix)

    def on_agent_finish(
        self, finish: AgentFinish, color: Optional[str] = None, **kwargs: Any
    ) -> None:
        # self.callback(f"{finish.log}\n\n")
        logging.info(finish.log)

    def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Optional[Union[GenerationChunk, ChatGenerationChunk]] = None,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run on new LLM token. Only available when streaming is enabled.

        Args:
            token (str): The new token.
            chunk (GenerationChunk | ChatGenerationChunk): The new generated chunk,
            containing content and other information.
        """
        logging.info(f"### CHUNK ###: {chunk}")
        self.callback(token)


class ModelType(Enum):
    Unknown = -1
    OpenAI = 0
    ChatGLM = 1
    LLaMA = 2
    XMChat = 3
    StableLM = 4
    MOSS = 5
    YuanAI = 6
    Minimax = 7
    ChuanhuAgent = 8
    GooglePaLM = 9
    LangchainChat = 10
    Midjourney = 11
    Spark = 12
    OpenAIInstruct = 13
    Claude = 14
    Qwen = 15
    OpenAIVision = 16
    ERNIE = 17
    DALLE3 = 18
    GoogleGemini = 19
    GoogleGemma = 20
    Ollama = 21
    Groq = 22

    @classmethod
    def get_type(cls, model_name: str):
        # 1. get model type from model metadata (if exists)
        model_type = MODEL_METADATA[model_name]["model_type"]
        if model_type is not None:
            for member in cls:
                if member.name == model_type:
                    return member

        # 2. infer model type from model name
        model_type = None
        model_name_lower = model_name.lower()
        if "gpt" in model_name_lower:
            try:
                assert MODEL_METADATA[model_name]["multimodal"] == True
                model_type = ModelType.OpenAIVision
            except:
                if "instruct" in model_name_lower:
                    model_type = ModelType.OpenAIInstruct
                elif "vision" in model_name_lower:
                    model_type = ModelType.OpenAIVision
                else:
                    model_type = ModelType.OpenAI
        elif "chatglm" in model_name_lower:
            model_type = ModelType.ChatGLM
        elif "groq" in model_name_lower:
            model_type = ModelType.Groq
        elif "ollama" in model_name_lower:
            model_type = ModelType.Ollama
        elif "llama" in model_name_lower or "alpaca" in model_name_lower:
            model_type = ModelType.LLaMA
        elif "xmchat" in model_name_lower:
            model_type = ModelType.XMChat
        elif "stablelm" in model_name_lower:
            model_type = ModelType.StableLM
        elif "moss" in model_name_lower:
            model_type = ModelType.MOSS
        elif "yuanai" in model_name_lower:
            model_type = ModelType.YuanAI
        elif "minimax" in model_name_lower:
            model_type = ModelType.Minimax
        elif "川虎助理" in model_name_lower:
            model_type = ModelType.ChuanhuAgent
        elif "palm" in model_name_lower:
            model_type = ModelType.GooglePaLM
        elif "gemini" in model_name_lower:
            model_type = ModelType.GoogleGemini
        elif "midjourney" in model_name_lower:
            model_type = ModelType.Midjourney
        elif "azure" in model_name_lower or "api" in model_name_lower:
            model_type = ModelType.LangchainChat
        elif "讯飞星火" in model_name_lower:
            model_type = ModelType.Spark
        elif "claude" in model_name_lower:
            model_type = ModelType.Claude
        elif "qwen" in model_name_lower:
            model_type = ModelType.Qwen
        elif "ernie" in model_name_lower:
            model_type = ModelType.ERNIE
        elif "dall" in model_name_lower:
            model_type = ModelType.DALLE3
        elif "gemma" in model_name_lower:
            model_type = ModelType.GoogleGemma
        else:
            model_type = ModelType.LLaMA
        return model_type


def download(repo_id, filename, retry=10):
    if os.path.exists("./models/downloaded_models.json"):
        with open("./models/downloaded_models.json", "r") as f:
            downloaded_models = json.load(f)
        if repo_id in downloaded_models:
            return downloaded_models[repo_id]["path"]
    else:
        downloaded_models = {}
    while retry > 0:
        try:
            model_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir="models",
                resume_download=True,
            )
            downloaded_models[repo_id] = {"path": model_path}
            with open("./models/downloaded_models.json", "w") as f:
                json.dump(downloaded_models, f)
            break
        except:
            print("Error downloading model, retrying...")
            retry -= 1
    if retry == 0:
        raise Exception("Error downloading model, please try again later.")
    return model_path


class BaseLLMModel:
    def __init__(
        self,
        model_name,
        user="",
        config=None,
    ) -> None:

        if config is not None:
            temp = MODEL_METADATA[model_name].copy()
            keys_with_diff_values = {key: temp[key] for key in temp if key in DEFAULT_METADATA and temp[key] != DEFAULT_METADATA[key]}
            config.update(keys_with_diff_values)
            temp.update(config)
            config = temp
        else:
            config = MODEL_METADATA[model_name]

        self.model_name = config["model_name"]
        self.multimodal = config["multimodal"]
        self.description = config["description"]
        self.placeholder = config["placeholder"]
        self.token_upper_limit = config["token_limit"]
        self.system_prompt = config["system"]
        self.api_key = config["api_key"]
        self.api_host = config["api_host"]

        self.interrupted = False
        self.need_api_key = self.api_key is not None
        self.history = []
        self.all_token_counts = []
        self.model_type = ModelType.get_type(model_name)
        self.history_file_path = get_first_history_name(user)
        self.user_name = user
        self.chatbot = []

        self.default_single_turn = config["single_turn"]
        self.default_temperature = config["temperature"]
        self.default_top_p = config["top_p"]
        self.default_n_choices = config["n_choices"]
        self.default_stop_sequence = config["stop"]
        self.default_max_generation_token = config["max_generation"]
        self.default_presence_penalty = config["presence_penalty"]
        self.default_frequency_penalty = config["frequency_penalty"]
        self.default_logit_bias = config["logit_bias"]
        self.default_user_identifier = user

        self.single_turn = self.default_single_turn
        self.temperature = self.default_temperature
        self.top_p = self.default_top_p
        self.n_choices = self.default_n_choices
        self.stop_sequence = self.default_stop_sequence
        self.max_generation_token = self.default_max_generation_token
        self.presence_penalty = self.default_presence_penalty
        self.frequency_penalty = self.default_frequency_penalty
        self.logit_bias = self.default_logit_bias
        self.user_identifier = user

        self.metadata = config["metadata"]

    def get_answer_stream_iter(self):
        """Implement stream prediction.
        Conversations are stored in self.history, with the most recent question in OpenAI format.
        Should return a generator that yields the next word (str) in the answer.
        """
        logging.warning(
            "Stream prediction is not implemented. Using at once prediction instead."
        )
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
        # logging.warning("billing info not implemented, using default")
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

        if display_append:
            display_append = (
                '\n\n<hr class="append-display no-in-raw" />' + display_append
            )
        partial_text = ""
        token_increment = 1
        for partial_text in stream_iter:
            if type(partial_text) == tuple:
                partial_text, token_increment = partial_text
            chatbot[-1] = (chatbot[-1][0], partial_text + display_append)
            self.all_token_counts[-1] += token_increment
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

    def handle_file_upload(self, files, chatbot, language):
        """if the model accepts multi modal input, implement this function"""
        status = gr.Markdown()
        image_files = []
        other_files = []
        if files:
            for f in files:
                if f.name.endswith(IMAGE_FORMATS):
                    image_files.append(f)
                else:
                    other_files.append(f)
            if image_files:
                if self.multimodal:
                    chatbot.extend([(((image.name, None)), None) for image in image_files])
                    self.history.extend([construct_image(image.name) for image in image_files])
                else:
                    gr.Warning(i18n("该模型不支持多模态输入"))
            if other_files:
                try:
                    construct_index(self.api_key, file_src=files)
                    status = i18n("索引构建完成")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    status = i18n("索引构建失败！") + str(e)
        if other_files:
            other_files = [f.name for f in other_files]
        else:
            other_files = None
        return gr.File(value=other_files), chatbot, status

    def summarize_index(self, files, chatbot, language):
        status = gr.Markdown()
        if files:
            index = construct_index(self.api_key, file_src=files)
            status = i18n("总结完成")
            logging.info(i18n("生成内容总结中……"))
            os.environ["OPENAI_API_KEY"] = self.api_key
            from langchain.callbacks import StdOutCallbackHandler
            from langchain.chains.summarize import load_summarize_chain
            from langchain.chat_models import ChatOpenAI
            from langchain.prompts import PromptTemplate

            prompt_template = (
                "Write a concise summary of the following:\n\n{text}\n\nCONCISE SUMMARY IN "
                + language
                + ":"
            )
            PROMPT = PromptTemplate(template=prompt_template, input_variables=["text"])
            llm = ChatOpenAI()
            chain = load_summarize_chain(
                llm,
                chain_type="map_reduce",
                return_intermediate_steps=True,
                map_prompt=PROMPT,
                combine_prompt=PROMPT,
            )
            summary = chain(
                {"input_documents": list(index.docstore.__dict__["_dict"].values())},
                return_only_outputs=True,
            )["output_text"]
            print(i18n("总结") + f": {summary}")
            chatbot.append([i18n("上传了") + str(len(files)) + "个文件", summary])
        return chatbot, status

    def prepare_inputs(
        self,
        real_inputs,
        use_websearch,
        files,
        reply_language,
        chatbot,
        load_from_cache_if_possible=True,
    ):
        display_append = []
        limited_context = False
        if type(real_inputs) == list:
            fake_inputs = real_inputs[0]["text"]
        else:
            fake_inputs = real_inputs
        if files:
            from langchain.embeddings.huggingface import HuggingFaceEmbeddings
            from langchain.vectorstores.base import VectorStoreRetriever

            limited_context = True
            msg = "加载索引中……"
            logging.info(msg)
            index = construct_index(
                self.api_key,
                file_src=files,
                load_from_cache_if_possible=load_from_cache_if_possible,
            )
            assert index is not None, "获取索引失败"
            msg = "索引获取成功，生成回答中……"
            logging.info(msg)
            with retrieve_proxy():
                retriever = VectorStoreRetriever(
                    vectorstore=index, search_type="similarity", search_kwargs={"k": 6}
                )
                # retriever = VectorStoreRetriever(vectorstore=index, search_type="similarity_score_threshold", search_kwargs={
                #                                  "k": 6, "score_threshold": 0.2})
                try:
                    relevant_documents = retriever.get_relevant_documents(fake_inputs)
                except AssertionError:
                    return self.prepare_inputs(
                        fake_inputs,
                        use_websearch,
                        files,
                        reply_language,
                        chatbot,
                        load_from_cache_if_possible=False,
                    )
            reference_results = [
                [d.page_content.strip("�"), os.path.basename(d.metadata["source"])]
                for d in relevant_documents
            ]
            reference_results = add_source_numbers(reference_results)
            display_append = add_details(reference_results)
            display_append = "\n\n" + "".join(display_append)
            if type(real_inputs) == list:
                real_inputs[0]["text"] = (
                    replace_today(PROMPT_TEMPLATE)
                    .replace("{query_str}", fake_inputs)
                    .replace("{context_str}", "\n\n".join(reference_results))
                    .replace("{reply_language}", reply_language)
                )
            else:
                real_inputs = (
                    replace_today(PROMPT_TEMPLATE)
                    .replace("{query_str}", real_inputs)
                    .replace("{context_str}", "\n\n".join(reference_results))
                    .replace("{reply_language}", reply_language)
                )
        elif use_websearch:
            search_results = []
            with retrieve_proxy() as proxy:
                if proxy[0] or proxy[1]:
                    proxies = {}
                    if proxy[0]:
                        proxies["http"] = proxy[0]
                    if proxy[1]:
                        proxies["https"] = proxy[1]
                else:
                    proxies = None
                with DDGS(proxies=proxies) as ddgs:
                    ddgs_gen = ddgs.text(fake_inputs, backend="lite")
                    for r in islice(ddgs_gen, 10):
                        search_results.append(r)
            reference_results = []
            for idx, result in enumerate(search_results):
                logging.debug(f"搜索结果{idx + 1}：{result}")
                domain_name = urllib3.util.parse_url(result["href"]).host
                reference_results.append([result["body"], result["href"]])
                display_append.append(
                    # f"{idx+1}. [{domain_name}]({result['href']})\n"
                    f"<a href=\"{result['href']}\" target=\"_blank\">{idx+1}.&nbsp;{result['title']}</a>"
                )
            reference_results = add_source_numbers(reference_results)
            # display_append = "<ol>\n\n" + "".join(display_append) + "</ol>"
            display_append = (
                '<div class = "source-a">' + "".join(display_append) + "</div>"
            )
            if type(real_inputs) == list:
                real_inputs[0]["text"] = (
                    replace_today(WEBSEARCH_PTOMPT_TEMPLATE)
                    .replace("{query}", fake_inputs)
                    .replace("{web_results}", "\n\n".join(reference_results))
                    .replace("{reply_language}", reply_language)
                )
            else:
                real_inputs = (
                    replace_today(WEBSEARCH_PTOMPT_TEMPLATE)
                    .replace("{query}", fake_inputs)
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
        if type(inputs) == list:
            logging.info(
                "用户"
                + f"{self.user_name}"
                + "的输入为："
                + colorama.Fore.BLUE
                + "("
                + str(len(inputs) - 1)
                + " images) "
                + f"{inputs[0]['text']}"
                + colorama.Style.RESET_ALL
            )
        else:
            logging.info(
                "用户"
                + f"{self.user_name}"
                + "的输入为："
                + colorama.Fore.BLUE
                + f"{inputs}"
                + colorama.Style.RESET_ALL
            )
        if should_check_token_count:
            if type(inputs) == list:
                yield chatbot + [(inputs[0]["text"], "")], status_text
            else:
                yield chatbot + [(inputs, "")], status_text
        if reply_language == "跟随问题语言（不稳定）":
            reply_language = "the same language as the question, such as English, 中文, 日本語, Español, Français, or Deutsch."

        (
            limited_context,
            fake_inputs,
            display_append,
            inputs,
            chatbot,
        ) = self.prepare_inputs(
            real_inputs=inputs,
            use_websearch=use_websearch,
            files=files,
            reply_language=reply_language,
            chatbot=chatbot,
        )
        yield chatbot + [(fake_inputs, "")], status_text

        if (
            self.need_api_key
            and self.api_key is None
            and not shared.state.multi_api_key
        ):
            status_text = STANDARD_ERROR_MSG + NO_APIKEY_MSG
            logging.info(status_text)
            chatbot.append((fake_inputs, ""))
            if len(self.history) == 0:
                self.history.append(construct_user(fake_inputs))
                self.history.append("")
                self.all_token_counts.append(0)
            else:
                self.history[-2] = construct_user(fake_inputs)
            yield chatbot + [(fake_inputs, "")], status_text
            return
        elif len(fake_inputs.strip()) == 0:
            status_text = STANDARD_ERROR_MSG + NO_INPUT_MSG
            logging.info(status_text)
            yield chatbot + [(fake_inputs, "")], status_text
            return

        if self.single_turn:
            self.history = []
            self.all_token_counts = []
        if type(inputs) == list:
            self.history.append(inputs)
        else:
            self.history.append(construct_user(inputs))

        start_time = time.time()
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
            status_text = STANDARD_ERROR_MSG + beautify_err_msg(str(e))
            yield chatbot, status_text
        end_time = time.time()
        if len(self.history) > 1 and self.history[-1]["content"] != fake_inputs:
            logging.info(
                "回答为："
                + colorama.Fore.BLUE
                + f"{self.history[-1]['content']}"
                + colorama.Style.RESET_ALL
            )
            logging.info(i18n("Tokens per second：{token_generation_speed}").format(token_generation_speed=str(self.all_token_counts[-1] / (end_time - start_time))))

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

        self.chatbot = chatbot
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
        if len(self.history) > 1:
            inputs = self.history[-2]["content"]
            del self.history[-2:]
            if len(self.all_token_counts) > 0:
                self.all_token_counts.pop()
        elif len(chatbot) > 0:
            inputs = chatbot[-1][0]
            if '<div class="user-message">' in inputs:
                inputs = inputs.split('<div class="user-message">')[1]
                inputs = inputs.split("</div>")[0]
        elif len(self.history) == 1:
            inputs = self.history[-1]["content"]
            del self.history[-1]
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
        self.auto_save()

    def set_temperature(self, new_temperature):
        self.temperature = new_temperature
        self.auto_save()

    def set_top_p(self, new_top_p):
        self.top_p = new_top_p
        self.auto_save()

    def set_n_choices(self, new_n_choices):
        self.n_choices = new_n_choices
        self.auto_save()

    def set_stop_sequence(self, new_stop_sequence: str):
        new_stop_sequence = new_stop_sequence.split(",")
        self.stop_sequence = new_stop_sequence
        self.auto_save()

    def set_max_tokens(self, new_max_tokens):
        self.max_generation_token = new_max_tokens
        self.auto_save()

    def set_presence_penalty(self, new_presence_penalty):
        self.presence_penalty = new_presence_penalty
        self.auto_save()

    def set_frequency_penalty(self, new_frequency_penalty):
        self.frequency_penalty = new_frequency_penalty
        self.auto_save()

    def set_logit_bias(self, logit_bias):
        self.logit_bias = logit_bias
        self.auto_save()

    def encoded_logit_bias(self):
        if self.logit_bias is None:
            return {}
        logit_bias = self.logit_bias.split()
        bias_map = {}
        encoding = tiktoken.get_encoding("cl100k_base")
        for line in logit_bias:
            word, bias_amount = line.split(":")
            if word:
                for token in encoding.encode(word):
                    bias_map[token] = float(bias_amount)
        return bias_map

    def set_user_identifier(self, new_user_identifier):
        self.user_identifier = new_user_identifier
        self.auto_save()

    def set_system_prompt(self, new_system_prompt):
        self.system_prompt = new_system_prompt
        self.auto_save()

    def set_key(self, new_access_key):
        if "*" not in new_access_key:
            self.api_key = new_access_key.strip()
            msg = i18n("API密钥更改为了") + hide_middle_chars(self.api_key)
            logging.info(msg)
            return self.api_key, msg
        else:
            return gr.update(), gr.update()

    def set_single_turn(self, new_single_turn):
        self.single_turn = new_single_turn
        self.auto_save()

    def reset(self, remain_system_prompt=False):
        self.history = []
        self.all_token_counts = []
        self.interrupted = False
        self.history_file_path = new_auto_history_filename(self.user_name)
        history_name = self.history_file_path[:-5]
        choices = get_history_names(self.user_name)
        if history_name not in choices:
            choices.insert(0, history_name)
        system_prompt = self.system_prompt if remain_system_prompt else INITIAL_SYSTEM_PROMPT

        self.single_turn = self.default_single_turn
        self.temperature = self.default_temperature
        self.top_p = self.default_top_p
        self.n_choices = self.default_n_choices
        self.stop_sequence = self.default_stop_sequence
        self.max_generation_token = self.default_max_generation_token
        self.presence_penalty = self.default_presence_penalty
        self.frequency_penalty = self.default_frequency_penalty
        self.logit_bias = self.default_logit_bias
        self.user_identifier = self.default_user_identifier

        return (
            [],
            self.token_message([0]),
            gr.Radio(choices=choices, value=history_name),
            system_prompt,
            self.single_turn,
            self.temperature,
            self.top_p,
            self.n_choices,
            self.stop_sequence,
            self.token_upper_limit,
            self.max_generation_token,
            self.presence_penalty,
            self.frequency_penalty,
            self.logit_bias,
            self.user_identifier,
        )

    def delete_first_conversation(self):
        if self.history:
            del self.history[:2]
            del self.all_token_counts[0]
        return self.token_message()

    def delete_last_conversation(self, chatbot):
        if len(chatbot) > 0 and STANDARD_ERROR_MSG in chatbot[-1][1]:
            msg = "由于包含报错信息，只删除chatbot记录"
            chatbot = chatbot[:-1]
            return chatbot, self.history
        if len(self.history) > 0:
            self.history = self.history[:-2]
        if len(chatbot) > 0:
            msg = "删除了一组chatbot对话"
            chatbot = chatbot[:-1]
        if len(self.all_token_counts) > 0:
            msg = "删除了一组对话的token计数记录"
            self.all_token_counts.pop()
        msg = "删除了一组对话"
        self.chatbot = chatbot
        self.auto_save(chatbot)
        return chatbot, msg

    def token_message(self, token_lst=None):
        if token_lst is None:
            token_lst = self.all_token_counts
        token_sum = 0
        for i in range(len(token_lst)):
            token_sum += sum(token_lst[: i + 1])
        return (
            i18n("Token 计数: ")
            + f"{sum(token_lst)}"
            + i18n("，本次对话累计消耗了 ")
            + f"{token_sum} tokens"
        )

    def rename_chat_history(self, filename, chatbot):
        if filename == "":
            return gr.update()
        if not filename.endswith(".json"):
            filename += ".json"
        self.delete_chat_history(self.history_file_path)
        # 命名重复检测
        repeat_file_index = 2
        full_path = os.path.join(HISTORY_DIR, self.user_name, filename)
        while os.path.exists(full_path):
            full_path = os.path.join(
                HISTORY_DIR, self.user_name, f"{repeat_file_index}_{filename}"
            )
            repeat_file_index += 1
        filename = os.path.basename(full_path)

        self.history_file_path = filename
        save_file(filename, self, chatbot)
        return init_history_list(self.user_name)

    def auto_name_chat_history(
        self, name_chat_method, user_question, chatbot, single_turn_checkbox
    ):
        if len(self.history) == 2 and not single_turn_checkbox:
            user_question = self.history[0]["content"]
            if type(user_question) == list:
                user_question = user_question[0]["text"]
            filename = replace_special_symbols(user_question)[:16] + ".json"
            return self.rename_chat_history(filename, chatbot)
        else:
            return gr.update()

    def auto_save(self, chatbot=None):
        if chatbot is not None:
            save_file(self.history_file_path, self, chatbot)

    def export_markdown(self, filename, chatbot):
        if filename == "":
            return
        if not filename.endswith(".md"):
            filename += ".md"
        save_file(filename, self, chatbot)

    def load_chat_history(self, new_history_file_path=None):
        logging.debug(f"{self.user_name} 加载对话历史中……")
        if new_history_file_path is not None:
            if type(new_history_file_path) != str:
                # copy file from new_history_file_path.name to os.path.join(HISTORY_DIR, self.user_name)
                new_history_file_path = new_history_file_path.name
                shutil.copyfile(
                    new_history_file_path,
                    os.path.join(
                        HISTORY_DIR,
                        self.user_name,
                        os.path.basename(new_history_file_path),
                    ),
                )
                self.history_file_path = os.path.basename(new_history_file_path)
            else:
                self.history_file_path = new_history_file_path
        try:
            if self.history_file_path == os.path.basename(self.history_file_path):
                history_file_path = os.path.join(
                    HISTORY_DIR, self.user_name, self.history_file_path
                )
            else:
                history_file_path = self.history_file_path
            if not self.history_file_path.endswith(".json"):
                history_file_path += ".json"
            with open(history_file_path, "r", encoding="utf-8") as f:
                saved_json = json.load(f)
            try:
                if type(saved_json["history"][0]) == str:
                    logging.info("历史记录格式为旧版，正在转换……")
                    new_history = []
                    for index, item in enumerate(saved_json["history"]):
                        if index % 2 == 0:
                            new_history.append(construct_user(item))
                        else:
                            new_history.append(construct_assistant(item))
                    saved_json["history"] = new_history
                    logging.info(new_history)
            except:
                pass
            if len(saved_json["chatbot"]) < len(saved_json["history"]) // 2:
                logging.info("Trimming corrupted history...")
                saved_json["history"] = saved_json["history"][
                    -len(saved_json["chatbot"]) :
                ]
                logging.info(f"Trimmed history: {saved_json['history']}")
            logging.debug(f"{self.user_name} 加载对话历史完毕")
            self.history = saved_json["history"]
            self.single_turn = saved_json.get("single_turn", self.single_turn)
            self.temperature = saved_json.get("temperature", self.temperature)
            self.top_p = saved_json.get("top_p", self.top_p)
            self.n_choices = saved_json.get("n_choices", self.n_choices)
            self.stop_sequence = list(saved_json.get("stop_sequence", self.stop_sequence))
            self.token_upper_limit = saved_json.get(
                "token_upper_limit", self.token_upper_limit
            )
            self.max_generation_token = saved_json.get(
                "max_generation_token", self.max_generation_token
            )
            self.presence_penalty = saved_json.get(
                "presence_penalty", self.presence_penalty
            )
            self.frequency_penalty = saved_json.get(
                "frequency_penalty", self.frequency_penalty
            )
            self.logit_bias = saved_json.get("logit_bias", self.logit_bias)
            self.user_identifier = saved_json.get("user_identifier", self.user_name)
            self.metadata = saved_json.get("metadata", self.metadata)
            self.chatbot = saved_json["chatbot"]
            return (
                os.path.basename(self.history_file_path)[:-5],
                saved_json["system"],
                gr.update(value=saved_json["chatbot"]),
                self.single_turn,
                self.temperature,
                self.top_p,
                self.n_choices,
                ",".join(self.stop_sequence),
                self.token_upper_limit,
                self.max_generation_token,
                self.presence_penalty,
                self.frequency_penalty,
                self.logit_bias,
                self.user_identifier,
            )
        except:
            # 没有对话历史或者对话历史解析失败
            logging.info(f"没有找到对话历史记录 {self.history_file_path}")
            self.reset()
            return (
                os.path.basename(self.history_file_path),
                self.system_prompt,
                gr.update(value=[]),
                self.single_turn,
                self.temperature,
                self.top_p,
                self.n_choices,
                ",".join(self.stop_sequence),
                self.token_upper_limit,
                self.max_generation_token,
                self.presence_penalty,
                self.frequency_penalty,
                self.logit_bias,
                self.user_identifier,
            )

    def delete_chat_history(self, filename):
        if filename == "CANCELED":
            return gr.update(), gr.update(), gr.update()
        if filename == "":
            return i18n("你没有选择任何对话历史"), gr.update(), gr.update()
        if not filename.endswith(".json"):
            filename += ".json"
        if filename == os.path.basename(filename):
            history_file_path = os.path.join(HISTORY_DIR, self.user_name, filename)
        else:
            history_file_path = filename
        md_history_file_path = history_file_path[:-5] + ".md"
        try:
            os.remove(history_file_path)
            os.remove(md_history_file_path)
            return i18n("删除对话历史成功"), get_history_list(self.user_name), []
        except:
            logging.info(f"删除对话历史失败 {history_file_path}")
            return (
                i18n("对话历史") + filename + i18n("已经被删除啦"),
                get_history_list(self.user_name),
                [],
            )

    def auto_load(self):
        self.new_auto_history_filename()
        return self.load_chat_history()

    def new_auto_history_filename(self):
        self.history_file_path = new_auto_history_filename(self.user_name)

    def like(self):
        """like the last response, implement if needed"""
        return gr.update()

    def dislike(self):
        """dislike the last response, implement if needed"""
        return gr.update()

    def deinitialize(self):
        """deinitialize the model, implement if needed"""
        pass

    def clear_cuda_cache(self):
        import gc

        import torch
        gc.collect()
        torch.cuda.empty_cache()

    def get_base64_image(self, image_path):
        if image_path.endswith(DIRECTLY_SUPPORTED_IMAGE_FORMATS):
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        else:
            # convert to jpeg
            image = PIL.Image.open(image_path)
            image = image.convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def get_image_type(self, image_path):
        if image_path.lower().endswith(DIRECTLY_SUPPORTED_IMAGE_FORMATS):
            return os.path.splitext(image_path)[1][1:].lower()
        else:
            return "jpeg"


class Base_Chat_Langchain_Client(BaseLLMModel):
    def __init__(self, model_name, user_name=""):
        super().__init__(model_name, user=user_name)
        self.need_api_key = False
        self.model = self.setup_model()

    def setup_model(self):
        # inplement this to setup the model then return it
        pass

    def _get_langchain_style_history(self):
        history = [SystemMessage(content=self.system_prompt)]
        for i in self.history:
            if i["role"] == "user":
                history.append(HumanMessage(content=i["content"]))
            elif i["role"] == "assistant":
                history.append(AIMessage(content=i["content"]))
        return history

    def get_answer_at_once(self):
        assert isinstance(
            self.model, BaseChatModel
        ), "model is not instance of LangChain BaseChatModel"
        history = self._get_langchain_style_history()
        response = self.model.generate(history)
        return response.content, sum(response.content)

    def get_answer_stream_iter(self):
        it = CallbackToIterator()
        assert isinstance(
            self.model, BaseChatModel
        ), "model is not instance of LangChain BaseChatModel"
        history = self._get_langchain_style_history()

        def thread_func():
            self.model(
                messages=history, callbacks=[ChuanhuCallbackHandler(it.callback)]
            )
            it.finish()

        t = Thread(target=thread_func)
        t.start()
        partial_text = ""
        for value in it:
            partial_text += value
            yield partial_text
