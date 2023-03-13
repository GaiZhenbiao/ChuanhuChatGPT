import argparse

# -*- coding:utf-8 -*-
title = """<h1 align="center">川虎ChatGPT 🚀</h1>"""
description = """<div align=center>

由Bilibili [土川虎虎虎](https://space.bilibili.com/29125536) 和 [明昭MZhao](https://space.bilibili.com/24807452)开发

访问川虎ChatGPT的 [GitHub项目](https://github.com/GaiZhenbiao/ChuanhuChatGPT) 下载最新版脚本

此App使用 `gpt-3.5-turbo` 大语言模型
</div>
"""
customCSS = """
code {
    display: inline;
    white-space: break-spaces;
    border-radius: 6px;
    margin: 0 2px 0 2px;
    padding: .2em .4em .1em .4em;
    background-color: rgba(175,184,193,0.2);
}
pre code {
    display: block;
    white-space: pre;
    background-color: hsla(0, 0%, 0%, 72%);
    border: solid 5px var(--color-border-primary) !important;
    border-radius: 10px;
    padding: 0 1.2rem 1.2rem;
    margin-top: 1em !important;
    color: #FFF;
    box-shadow: inset 0px 8px 16px hsla(0, 0%, 0%, .2)
}
"""

standard_error_msg = "☹️发生了错误：" # 错误信息的标准前缀
error_retrieve_prompt = "连接超时，无法获取对话。请检查网络连接，或者API-Key是否有效。" # 获取对话时发生错误
summarize_prompt = "请总结以上对话，不超过100字。" # 总结对话时的 prompt

my_api_key = ""    # 在这里输入你的 API 密钥

parser = argparse.ArgumentParser()
parser.add_argument("--authentication", action="store_true", default=False, help="是否开启登录")
parser.add_argument("--input_key", action="store_true", default=False, help="是否由用户输入API-Key")
parser.add_argument("--share", action="store_true", default=False, help="是否创建gradio公开链接")
parser.add_argument("--use_stream", type=int, default=1, choices=[0, 1, 2], help="0实时传输回答，1一次性返回答案，2在ui中增加传输模式选项")
parser.add_argument("--timeout_all", type=int, default=200, help="非流式对话时的超时时间")
parser.add_argument("--max_token_all", type=int, default=3000, help="非流式对话时的最大 token 数")
parser.add_argument("--timeout_streaming", type=int, default=5, help="流式对话时的超时时间")
parser.add_argument("--max_token_streaming", type=int, default=3000, help="流式对话时的最大 token 数")

args = parser.parse_args()

