# -*- coding:utf-8 -*-
title = """<h1 align="center">川虎ChatGPT 🚀</h1>"""
description = """<div align=center>

由Bilibili [土川虎虎虎](https://space.bilibili.com/29125536) 和 [明昭MZhao](https://space.bilibili.com/24807452)开发

访问川虎ChatGPT的 [GitHub项目](https://github.com/GaiZhenbiao/ChuanhuChatGPT) 下载最新版脚本

此App使用 `gpt-3.5-turbo` 大语言模型
</div>
"""
customCSS = """
table {
    margin: 1em 0;
    border-collapse: collapse;
    empty-cells: show;
}
td,th {
    border: 1.2px solid var(--color-border-primary) !important;
    padding: 0.2em;
}
thead {
    background-color: rgba(175,184,193,0.2);
}
thead th {
    padding: .5em .2em;
}
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
    padding: 1rem 1.2rem 1rem;
    margin: 1em 0 1em;
    color: #FFF;
    box-shadow: inset 0px 8px 16px hsla(0, 0%, 0%, .2)
}
.codehilite .hll { background-color: #49483e }
.codehilite .c { color: #75715e } /* Comment */
.codehilite .err { color: #960050; background-color: #1e0010 } /* Error */
.codehilite .k { color: #66d9ef } /* Keyword */
.codehilite .l { color: #ae81ff } /* Literal */
.codehilite .n { color: #f8f8f2 } /* Name */
.codehilite .o { color: #f92672 } /* Operator */
.codehilite .p { color: #f8f8f2 } /* Punctuation */
.codehilite .ch { color: #75715e } /* Comment.Hashbang */
.codehilite .cm { color: #75715e } /* Comment.Multiline */
.codehilite .cp { color: #75715e } /* Comment.Preproc */
.codehilite .cpf { color: #75715e } /* Comment.PreprocFile */
.codehilite .c1 { color: #75715e } /* Comment.Single */
.codehilite .cs { color: #75715e } /* Comment.Special */
.codehilite .gd { color: #f92672 } /* Generic.Deleted */
.codehilite .ge { font-style: italic } /* Generic.Emph */
.codehilite .gi { color: #a6e22e } /* Generic.Inserted */
.codehilite .gs { font-weight: bold } /* Generic.Strong */
.codehilite .gu { color: #75715e } /* Generic.Subheading */
.codehilite .kc { color: #66d9ef } /* Keyword.Constant */
.codehilite .kd { color: #66d9ef } /* Keyword.Declaration */
.codehilite .kn { color: #f92672 } /* Keyword.Namespace */
.codehilite .kp { color: #66d9ef } /* Keyword.Pseudo */
.codehilite .kr { color: #66d9ef } /* Keyword.Reserved */
.codehilite .kt { color: #66d9ef } /* Keyword.Type */
.codehilite .ld { color: #e6db74 } /* Literal.Date */
.codehilite .m { color: #ae81ff } /* Literal.Number */
.codehilite .s { color: #e6db74 } /* Literal.String */
.codehilite .na { color: #a6e22e } /* Name.Attribute */
.codehilite .nb { color: #f8f8f2 } /* Name.Builtin */
.codehilite .nc { color: #a6e22e } /* Name.Class */
.codehilite .no { color: #66d9ef } /* Name.Constant */
.codehilite .nd { color: #a6e22e } /* Name.Decorator */
.codehilite .ni { color: #f8f8f2 } /* Name.Entity */
.codehilite .ne { color: #a6e22e } /* Name.Exception */
.codehilite .nf { color: #a6e22e } /* Name.Function */
.codehilite .nl { color: #f8f8f2 } /* Name.Label */
.codehilite .nn { color: #f8f8f2 } /* Name.Namespace */
.codehilite .nx { color: #a6e22e } /* Name.Other */
.codehilite .py { color: #f8f8f2 } /* Name.Property */
.codehilite .nt { color: #f92672 } /* Name.Tag */
.codehilite .nv { color: #f8f8f2 } /* Name.Variable */
.codehilite .ow { color: #f92672 } /* Operator.Word */
.codehilite .w { color: #f8f8f2 } /* Text.Whitespace */
.codehilite .mb { color: #ae81ff } /* Literal.Number.Bin */
.codehilite .mf { color: #ae81ff } /* Literal.Number.Float */
.codehilite .mh { color: #ae81ff } /* Literal.Number.Hex */
.codehilite .mi { color: #ae81ff } /* Literal.Number.Integer */
.codehilite .mo { color: #ae81ff } /* Literal.Number.Oct */
.codehilite .sa { color: #e6db74 } /* Literal.String.Affix */
.codehilite .sb { color: #e6db74 } /* Literal.String.Backtick */
.codehilite .sc { color: #e6db74 } /* Literal.String.Char */
.codehilite .dl { color: #e6db74 } /* Literal.String.Delimiter */
.codehilite .sd { color: #e6db74 } /* Literal.String.Doc */
.codehilite .s2 { color: #e6db74 } /* Literal.String.Double */
.codehilite .se { color: #ae81ff } /* Literal.String.Escape */
.codehilite .sh { color: #e6db74 } /* Literal.String.Heredoc */
.codehilite .si { color: #e6db74 } /* Literal.String.Interpol */
.codehilite .sx { color: #e6db74 } /* Literal.String.Other */
.codehilite .sr { color: #e6db74 } /* Literal.String.Regex */
.codehilite .s1 { color: #e6db74 } /* Literal.String.Single */
.codehilite .ss { color: #e6db74 } /* Literal.String.Symbol */
.codehilite .bp { color: #f8f8f2 } /* Name.Builtin.Pseudo */
.codehilite .fm { color: #a6e22e } /* Name.Function.Magic */
.codehilite .vc { color: #f8f8f2 } /* Name.Variable.Class */
.codehilite .vg { color: #f8f8f2 } /* Name.Variable.Global */
.codehilite .vi { color: #f8f8f2 } /* Name.Variable.Instance */
.codehilite .vm { color: #f8f8f2 } /* Name.Variable.Magic */
.codehilite .il { color: #ae81ff } /* Literal.Number.Integer.Long */
"""

summarize_prompt = "请总结以上对话，不超过100字。" # 总结对话时的 prompt

# 错误信息
standard_error_msg = "☹️发生了错误：" # 错误信息的标准前缀
error_retrieve_prompt = "请检查网络连接，或者API-Key是否有效。" # 获取对话时发生错误
connection_timeout_prompt = "连接超时，无法获取对话。" # 连接超时
read_timeout_prompt = "读取超时，无法获取对话。" # 读取超时
proxy_error_prompt = "代理错误，无法获取对话。" # 代理错误
ssl_error_prompt = "SSL错误，无法获取对话。" # SSL 错误
no_apikey_msg = "API key长度不是51位，请检查是否输入正确。" # API key 长度不足 51 位

max_token_streaming = 3500 # 流式对话时的最大 token 数
timeout_streaming = 15 # 流式对话时的超时时间
max_token_all = 3500 # 非流式对话时的最大 token 数
timeout_all = 200 # 非流式对话时的超时时间
enable_streaming_option = True  # 是否启用选择选择是否实时显示回答的勾选框
HIDE_MY_KEY = False # 如果你想在UI中隐藏你的 API 密钥，将此值设置为 True
