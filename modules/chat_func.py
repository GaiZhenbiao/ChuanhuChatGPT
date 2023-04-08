# -*- coding:utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING, List

import logging
import json
import os
import requests
import urllib3

from tqdm import tqdm
import colorama
from duckduckgo_search import ddg
import asyncio
import aiohttp


from modules.presets import *
from modules.llama_func import *
from modules.utils import *
from . import shared
from modules.config import retrieve_proxy

# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s")

if TYPE_CHECKING:
    from typing import TypedDict

    class DataframeData(TypedDict):
        headers: List[str]
        data: List[List[str | int | bool]]


initial_prompt = "You are a helpful assistant."
HISTORY_DIR = "history"
TEMPLATES_DIR = "templates"

@shared.state.switching_api_key # 在不开启多账号模式的时候，这个装饰器不会起作用
def get_response(
    openai_api_key, system_prompt, history, temperature, top_p, stream, selected_model
):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}",
    }

    history = [construct_system(system_prompt), *history]

    payload = {
        "model": selected_model,
        "messages": history,  # [{"role": "user", "content": f"{inputs}"}],
        "temperature": temperature,  # 1.0,
        "top_p": top_p,  # 1.0,
        "n": 1,
        "stream": stream,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }
    if stream:
        timeout = timeout_streaming
    else:
        timeout = timeout_all


    # 如果有自定义的api-host，使用自定义host发送请求，否则使用默认设置发送请求
    if shared.state.completion_url != COMPLETION_URL:
        logging.info(f"使用自定义API URL: {shared.state.completion_url}")

    with retrieve_proxy():
        response = requests.post(
            shared.state.completion_url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=timeout,
        )

    return response


def stream_predict(
    openai_api_key,
    system_prompt,
    history,
    inputs,
    chatbot,
    all_token_counts,
    top_p,
    temperature,
    selected_model,
    fake_input=None,
    display_append=""
):
    def get_return_value():
        return chatbot, history, status_text, all_token_counts

    logging.info("实时回答模式")
    partial_words = ""
    counter = 0
    status_text = "开始实时传输回答……"
    history.append(construct_user(inputs))
    history.append(construct_assistant(""))
    if fake_input:
        chatbot.append((fake_input, ""))
    else:
        chatbot.append((inputs, ""))
    user_token_count = 0
    if fake_input is not None:
        input_token_count = count_token(construct_user(fake_input))
    else:
        input_token_count = count_token(construct_user(inputs))
    if len(all_token_counts) == 0:
        system_prompt_token_count = count_token(construct_system(system_prompt))
        user_token_count = (
            input_token_count + system_prompt_token_count
        )
    else:
        user_token_count = input_token_count
    all_token_counts.append(user_token_count)
    logging.info(f"输入token计数: {user_token_count}")
    yield get_return_value()
    try:
        response = get_response(
            openai_api_key,
            system_prompt,
            history,
            temperature,
            top_p,
            True,
            selected_model,
        )
    except requests.exceptions.ConnectTimeout:
        status_text = (
            standard_error_msg + connection_timeout_prompt + error_retrieve_prompt
        )
        yield get_return_value()
        return
    except requests.exceptions.ReadTimeout:
        status_text = standard_error_msg + read_timeout_prompt + error_retrieve_prompt
        yield get_return_value()
        return

    yield get_return_value()
    error_json_str = ""

    if fake_input is not None:
        history[-2] = construct_user(fake_input)
    for chunk in tqdm(response.iter_lines()):
        if counter == 0:
            counter += 1
            continue
        counter += 1
        # check whether each line is non-empty
        if chunk:
            chunk = chunk.decode()
            chunklength = len(chunk)
            try:
                chunk = json.loads(chunk[6:])
            except json.JSONDecodeError:
                logging.info(chunk)
                error_json_str += chunk
                status_text = f"JSON解析错误。请重置对话。收到的内容: {error_json_str}"
                yield get_return_value()
                continue
            # decode each line as response data is in bytes
            if chunklength > 6 and "delta" in chunk["choices"][0]:
                finish_reason = chunk["choices"][0]["finish_reason"]
                status_text = construct_token_message(all_token_counts)
                if finish_reason == "stop":
                    yield get_return_value()
                    break
                try:
                    partial_words = (
                        partial_words + chunk["choices"][0]["delta"]["content"]
                    )
                except KeyError:
                    status_text = (
                        standard_error_msg
                        + "API回复中找不到内容。很可能是Token计数达到上限了。请重置对话。当前Token计数: "
                        + str(sum(all_token_counts))
                    )
                    yield get_return_value()
                    break
                history[-1] = construct_assistant(partial_words)
                chatbot[-1] = (chatbot[-1][0], partial_words+display_append)
                all_token_counts[-1] += 1
                yield get_return_value()


def predict_all(
    openai_api_key,
    system_prompt,
    history,
    inputs,
    chatbot,
    all_token_counts,
    top_p,
    temperature,
    selected_model,
    fake_input=None,
    display_append=""
):
    logging.info("一次性回答模式")
    history.append(construct_user(inputs))
    history.append(construct_assistant(""))
    if fake_input:
        chatbot.append((fake_input, ""))
    else:
        chatbot.append((inputs, ""))
    if fake_input is not None:
        all_token_counts.append(count_token(construct_user(fake_input)))
    else:
        all_token_counts.append(count_token(construct_user(inputs)))
    try:
        response = get_response(
            openai_api_key,
            system_prompt,
            history,
            temperature,
            top_p,
            False,
            selected_model,
        )
    except requests.exceptions.ConnectTimeout:
        status_text = (
            standard_error_msg + connection_timeout_prompt + error_retrieve_prompt
        )
        return chatbot, history, status_text, all_token_counts
    except requests.exceptions.ProxyError:
        status_text = standard_error_msg + proxy_error_prompt + error_retrieve_prompt
        return chatbot, history, status_text, all_token_counts
    except requests.exceptions.SSLError:
        status_text = standard_error_msg + ssl_error_prompt + error_retrieve_prompt
        return chatbot, history, status_text, all_token_counts
    response = json.loads(response.text)
    if fake_input is not None:
        history[-2] = construct_user(fake_input)
    try:
        content = response["choices"][0]["message"]["content"]
        history[-1] = construct_assistant(content)
        chatbot[-1] = (chatbot[-1][0], content+display_append)
        total_token_count = response["usage"]["total_tokens"]
        if fake_input is not None:
            all_token_counts[-1] += count_token(construct_assistant(content))
        else:
            all_token_counts[-1] = total_token_count - sum(all_token_counts)
        status_text = construct_token_message([total_token_count])
        return chatbot, history, status_text, all_token_counts
    except KeyError:
        status_text = standard_error_msg + str(response)
        return chatbot, history, status_text, all_token_counts


def predict(
    openai_api_key,
    system_prompt,
    history,
    inputs,
    chatbot,
    all_token_counts,
    top_p,
    temperature,
    stream=False,
    selected_model=MODELS[0],
    use_websearch=False,
    files = None,
    reply_language="中文",
    should_check_token_count=True,
):  # repetition_penalty, top_k
    from llama_index.indices.vector_store.base_query import GPTVectorStoreIndexQuery
    from llama_index.indices.query.schema import QueryBundle
    from langchain.llms import OpenAIChat


    logging.info("输入为：" + colorama.Fore.BLUE + f"{inputs}" + colorama.Style.RESET_ALL)
    if should_check_token_count:
        yield chatbot+[(inputs, "")], history, "开始生成回答……", all_token_counts
    if reply_language == "跟随问题语言（不稳定）":
        reply_language = "the same language as the question, such as English, 中文, 日本語, Español, Français, or Deutsch."
    old_inputs = None
    display_reference = []
    limited_context = False
    if files:
        limited_context = True
        old_inputs = inputs
        msg = "加载索引中……（这可能需要几分钟）"
        logging.info(msg)
        yield chatbot+[(inputs, "")], history, msg, all_token_counts
        index = construct_index(openai_api_key, file_src=files)
        msg = "索引构建完成，获取回答中……"
        logging.info(msg)
        yield chatbot+[(inputs, "")], history, msg, all_token_counts
        with retrieve_proxy():
            llm_predictor = LLMPredictor(llm=OpenAIChat(temperature=0, model_name=selected_model))
            prompt_helper = PromptHelper(max_input_size = 4096, num_output = 5, max_chunk_overlap = 20, chunk_size_limit=600)
            from llama_index import ServiceContext
            service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor, prompt_helper=prompt_helper)
            query_object = GPTVectorStoreIndexQuery(index.index_struct, service_context=service_context, similarity_top_k=5, vector_store=index._vector_store, docstore=index._docstore)
            query_bundle = QueryBundle(inputs)
            nodes = query_object.retrieve(query_bundle)
        reference_results = [n.node.text for n in nodes]
        reference_results = add_source_numbers(reference_results, use_source=False)
        display_reference = add_details(reference_results)
        display_reference = "\n\n" + "".join(display_reference)
        inputs = (
            replace_today(PROMPT_TEMPLATE)
            .replace("{query_str}", inputs)
            .replace("{context_str}", "\n\n".join(reference_results))
            .replace("{reply_language}", reply_language )
        )
    elif use_websearch:
        limited_context = True
        search_results = ddg(inputs, max_results=5)
        old_inputs = inputs
        reference_results = []
        for idx, result in enumerate(search_results):
            logging.info(f"搜索结果{idx + 1}：{result}")
            domain_name = urllib3.util.parse_url(result["href"]).host
            reference_results.append([result["body"], result["href"]])
            display_reference.append(f"{idx+1}. [{domain_name}]({result['href']})\n")
        reference_results = add_source_numbers(reference_results)
        display_reference = "\n\n" + "".join(display_reference)
        inputs = (
            replace_today(WEBSEARCH_PTOMPT_TEMPLATE)
            .replace("{query}", inputs)
            .replace("{web_results}", "\n\n".join(reference_results))
            .replace("{reply_language}", reply_language )
        )
    else:
        display_reference = ""

    if len(openai_api_key) == 0 and not shared.state.multi_api_key:
        status_text = standard_error_msg + no_apikey_msg
        logging.info(status_text)
        chatbot.append((inputs, ""))
        if len(history) == 0:
            history.append(construct_user(inputs))
            history.append("")
            all_token_counts.append(0)
        else:
            history[-2] = construct_user(inputs)
        yield chatbot+[(inputs, "")], history, status_text, all_token_counts
        return
    elif len(inputs.strip()) == 0:
        status_text = standard_error_msg + no_input_msg
        logging.info(status_text)
        yield chatbot+[(inputs, "")], history, status_text, all_token_counts
        return

    if stream:
        logging.info("使用流式传输")
        iter = stream_predict(
            openai_api_key,
            system_prompt,
            history,
            inputs,
            chatbot,
            all_token_counts,
            top_p,
            temperature,
            selected_model,
            fake_input=old_inputs,
            display_append=display_reference
        )
        for chatbot, history, status_text, all_token_counts in iter:
            if shared.state.interrupted:
                shared.state.recover()
                return
            yield chatbot, history, status_text, all_token_counts
    else:
        logging.info("不使用流式传输")
        chatbot, history, status_text, all_token_counts = predict_all(
            openai_api_key,
            system_prompt,
            history,
            inputs,
            chatbot,
            all_token_counts,
            top_p,
            temperature,
            selected_model,
            fake_input=old_inputs,
            display_append=display_reference
        )
        yield chatbot, history, status_text, all_token_counts

    logging.info(f"传输完毕。当前token计数为{all_token_counts}")
    if len(history) > 1 and history[-1]["content"] != inputs:
        logging.info(
            "回答为："
            + colorama.Fore.BLUE
            + f"{history[-1]['content']}"
            + colorama.Style.RESET_ALL
        )

    if limited_context:
        history = history[-4:]
        all_token_counts = all_token_counts[-2:]
        yield chatbot, history, status_text, all_token_counts

    if stream:
        max_token = MODEL_SOFT_TOKEN_LIMIT[selected_model]["streaming"]
    else:
        max_token = MODEL_SOFT_TOKEN_LIMIT[selected_model]["all"]

    if sum(all_token_counts) > max_token and should_check_token_count:
        print(all_token_counts)
        count = 0
        while sum(all_token_counts) > max_token - 500 and sum(all_token_counts) > 0:
            count += 1
            del all_token_counts[0]
            del history[:2]
        logging.info(status_text)
        status_text = f"为了防止token超限，模型忘记了早期的 {count} 轮对话"
        yield chatbot, history, status_text, all_token_counts


def retry(
    openai_api_key,
    system_prompt,
    history,
    chatbot,
    token_count,
    top_p,
    temperature,
    stream=False,
    selected_model=MODELS[0],
    reply_language="中文",
):
    logging.info("重试中……")
    if len(history) == 0:
        yield chatbot, history, f"{standard_error_msg}上下文是空的", token_count
        return
    history.pop()
    inputs = history.pop()["content"]
    token_count.pop()
    iter = predict(
        openai_api_key,
        system_prompt,
        history,
        inputs,
        chatbot,
        token_count,
        top_p,
        temperature,
        stream=stream,
        selected_model=selected_model,
        reply_language=reply_language,
    )
    logging.info("重试中……")
    for x in iter:
        yield x
    logging.info("重试完毕")


def reduce_token_size(
    openai_api_key,
    system_prompt,
    history,
    chatbot,
    token_count,
    top_p,
    temperature,
    max_token_count,
    selected_model=MODELS[0],
    reply_language="中文",
):
    logging.info("开始减少token数量……")
    iter = predict(
        openai_api_key,
        system_prompt,
        history,
        summarize_prompt,
        chatbot,
        token_count,
        top_p,
        temperature,
        selected_model=selected_model,
        should_check_token_count=False,
        reply_language=reply_language,
    )
    logging.info(f"chatbot: {chatbot}")
    flag = False
    for chatbot, history, status_text, previous_token_count in iter:
        num_chat = find_n(previous_token_count, max_token_count)
        logging.info(f"previous_token_count: {previous_token_count}, keeping {num_chat} chats")
        if flag:
            chatbot = chatbot[:-1]
        flag = True
        history = history[-2*num_chat:] if num_chat > 0 else []
        token_count = previous_token_count[-num_chat:] if num_chat > 0 else []
        msg = f"保留了最近{num_chat}轮对话"
        yield chatbot, history, msg + "，" + construct_token_message(
            token_count if len(token_count) > 0 else [0],
        ), token_count
    logging.info(msg)
    logging.info("减少token数量完毕")
