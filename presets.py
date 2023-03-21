# -*- coding:utf-8 -*-

# ChatGPT 设置
initial_prompt = "You are a helpful assistant."
API_URL = "https://api.openai.com/v1/chat/completions"
HISTORY_DIR = "history"
TEMPLATES_DIR = "templates"

# 错误信息
standard_error_msg = "☹️发生了错误："  # 错误信息的标准前缀
error_retrieve_prompt = "请检查网络连接，或者API-Key是否有效。"  # 获取对话时发生错误
connection_timeout_prompt = "连接超时，无法获取对话。"  # 连接超时
read_timeout_prompt = "读取超时，无法获取对话。"  # 读取超时
proxy_error_prompt = "代理错误，无法获取对话。"  # 代理错误
ssl_error_prompt = "SSL错误，无法获取对话。"  # SSL 错误
no_apikey_msg = "API key长度不是51位，请检查是否输入正确。"  # API key 长度不足 51 位

max_token_streaming = 3500  # 流式对话时的最大 token 数
timeout_streaming = 30  # 流式对话时的超时时间
max_token_all = 3500  # 非流式对话时的最大 token 数
timeout_all = 200  # 非流式对话时的超时时间
enable_streaming_option = True  # 是否启用选择选择是否实时显示回答的勾选框
HIDE_MY_KEY = False  # 如果你想在UI中隐藏你的 API 密钥，将此值设置为 True

SIM_K = 5
INDEX_QUERY_TEMPRATURE = 1.0

title = """<h1 align="left" style="min-width:200px; margin-top:0;">川虎ChatGPT 🚀</h1>"""
description = """\
<div align="center" style="margin:16px 0">

由Bilibili [土川虎虎虎](https://space.bilibili.com/29125536) 和 [明昭MZhao](https://space.bilibili.com/24807452)开发

访问川虎ChatGPT的 [GitHub项目](https://github.com/GaiZhenbiao/ChuanhuChatGPT) 下载最新版脚本

此App使用 `gpt-3.5-turbo` 大语言模型
</div>
"""

summarize_prompt = "你是谁？我们刚才聊了什么？"  # 总结对话时的 prompt

MODELS = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0301",
    "gpt-4",
    "gpt-4-0314",
    "gpt-4-32k",
    "gpt-4-32k-0314",
]  # 可选的模型


WEBSEARCH_PTOMPT_TEMPLATE = """\
Web search results:

{web_results}
Current date: {current_date}

Instructions: Using the provided web search results, write a comprehensive reply to the given query. Make sure to cite results using [[number](URL)] notation after the reference. If the provided search results refer to multiple subjects with the same name, write separate answers for each subject.
Query: {query}
Reply in 中文"""

PROMPT_TEMPLATE = """\
Context information is below.
---------------------
{context_str}
---------------------
Current date: {current_date}.
Using the provided context information, write a comprehensive reply to the given query.
Make sure to cite results using [number] notation after the reference.
If the provided context information refer to multiple subjects with the same name, write separate answers for each subject.
Use prior knowledge only if the given context didn't provide enough information.
Answer the question: {query_str}
Reply in 中文
"""

REFINE_TEMPLATE = """\
The original question is as follows: {query_str}
We have provided an existing answer: {existing_answer}
We have the opportunity to refine the existing answer
(only if needed) with some more context below.
------------
{context_msg}
------------
Given the new context, refine the original answer to better
Answer in the same language as the question, such as English, 中文, 日本語, Español, Français, or Deutsch.
If the context isn't useful, return the original answer.
"""
