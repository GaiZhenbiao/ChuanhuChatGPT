# 在 ChuanhuChat 中使用 OpenAI Agent

这是可选的真实界面能力，不是把普通 Chat Completions 改名为 Agent。启用后，侧边栏工具箱出现 **OpenAI Agent 任务** Tab，用户发送任务，官方托管沙箱执行多步工作，界面显示进度、结果、session/turn，并提供继续、停止、恢复与产物下载。

## 独立运行环境

核心仍使用 `openai==1.16.2`、Gradio 4.29、Pydantic 2.5.2。本功能通过独立子进程使用验证过的 `openai==3.13.0`，Python 3.10+；新 SDK 的 anyio 4.10+、httpx2 与 Pydantic 依赖不会升级核心环境。

在项目根目录建立专用环境：

```sh
python3.11 -m venv .agents-runtime
.agents-runtime/bin/python -m pip install -r optional/agents/requirements.txt
```

Windows 使用 `.agents-runtime\Scripts\python.exe`。自定义已安装的解释器可设置服务器环境变量 `CHUANHU_AGENT_PYTHON`，不通过网页接收解释器路径。

用户在项目根目录 `.env.agents` 自行填写 **CHUANHU_AGENT_API_KEY**；本文件被 Git 忽略，不应提交或在聊天中发送其内容。也可由服务器进程专门提供同名环境变量（优先于文件）。插件不读取 `config.json.openai_api_key` 或通用 OPENAI_API_KEY，不使用第三方 base，不提供 provider fallback。

客户端固定 `https://api.openai.com/v1`，拒绝重定向，不继承代理/组织/project/endpoint 设置，SDK 自动带 `OpenAI-Beta: agents=v1`，自动重试关闭。专用密钥需具有 `api.agents.read`、`api.agents.write`、`api.responses.write` 权限，以及所选模型访问权限；401/403 会显示可理解的错误，不会偷偷换接口。模型 ID 由用户明确选择，默认值来自官方 quickstart，不能推断所有项目都能访问。

## 启用与一个完整任务

1. 设置 → 插件，启用 `openai_agents`，重启应用。
2. 打开工具箱 → OpenAI Agent 任务，填写明确任务、官方模型 ID。
3. 根据任务需要选择可选的 text_statistics 工具。勾选本次官方发送/沙箱授权后点击 **发送任务 / 继续**。此操作会产生实际 API 费用。
4. 等待进度与目标 turn 结果。例：

   > 使用 Python 标准库生成一份 12 个月合成销售数据，计算总额与月均值，写入 `/workspace/report.md` 和 `/workspace/sales.csv`，运行计算并报告实际结果。不要访问网络。

5. 再发送“给报告增加最大/最小月份并保存更新后的文件”，沿用同一 session。继续任务锁定该 session 初次选择的模型和工具授权；要更换先保存产物、清理，然后新建。
6. 点击 **取回产物** 下载。查看 **恢复 / 对账状态** 可列出官方保存的产物名称。
7. 确认所需产物已经保存，勾选清理确认并点击 **清理 session 并开始新任务**。只删除当前浏览器所管理的 session，不批量清理账户资源。

## 工具与数据边界

- Agent 只能在官方 `openai_hosted` 环境运行，沙箱网络强制 disabled，子 Agent disabled；不挂载本机文件、配置或密钥。
- 托管环境提供代码执行/文件操作；官方沙箱隔离与本机 Python 插件的信任边界不同。
- 唯一可选的应用函数为 `text_statistics`：只接受 `{ "text": "..." }`，最多 20000 字符，不允许额外属性、读文件或联网。函数结果按当前 turn_id/call_id 回传，最多 10 次函数调用，未知名称/审批动作停止并要求恢复。
- 不自动把 legacy hook、插件 Python 函数、MCP、网页搜索或本机 shell 暴露给模型。
- 当前版本不支持本机文件上传、任意工具注册、浏览器登录审批或跨浏览器自动迁移；可以将不敏感数据作为任务文字发送。
- 产物经固定官方 SDK 端点下载，不跟随模型提供的下载 URL；最多 20 个、每个 10 MiB、总计 50 MiB，落地随机临时目录后通过当前 Gradio 会话 File 返回。文本展示最多 100000 字符。

## 停止、断流与恢复

**停止远程任务** 会提交 `agent.session.input.cancel`，不是只停浏览器流。点击发生在 session/turn 标识尚未到达时会记录停止意图，标识到达后取消新任务；发送尚未发生时不发新请求。停止已提交不等于停止已确认，请恢复状态检查真正的 turn 状态。

浏览器关闭、插件禁用或网络断开不会自动取消官方 session。未确认结局时发送按钮会阻止重复输入；先停止或对账。读取官方 turn 状态与已保存 items 进行恢复，不以 `idle`、EOF、子 Agent 完成或旧 turn 完成当本次成功；继续前记录已有 turn ID 排除旧事件。服务端按 owner 锁预留任务，按 generation 丢弃迟到操作，双击不会创建两个付费 session。

本地只在 `plugin_data/agents` 保存 owner 摘要、run/session/turn ID、状态、模型和工具授权；不保存密钥、任务文字或回答。这是服务器管理员的恢复记录，禁止浏览器直接读取。新 session 创建结果不明时，用本次随机 run ID 对账最近 100 个官方 session，绝不自动重发输入。找不到时保留记录交由管理员核对；不能据此断言远端未执行。

浏览器关闭后，当前 UI session 状态不承诺跨浏览器/重启恢复。管理员可根据私有记录，用隔离运行器中的 `inspect_saved` / `cancel_session` 管理记录中的特定资源。不要删除无归属的用户 session。

每次连接本地等待有界，默认任务约 90 秒、HTTP 等待 45 秒、子进程最长 150 秒；超过预算时不会宣称任务成功，也不会自动重试。远端运行预算不是账单硬上限，及时显式停止。应用不显示精确费用估算或承诺免费；优先用离线验收检查改动。

## 验证与文档来源

真实能力已用一个无私人数据的合成任务验证：创建 session，目标 turn 完成，沙箱报告创建并读回测试文件，之后删除该测试 session。没有追加任务、重试或再开计费 session。最终 UI 的继续、函数工具、取消、恢复与产物下载经模拟 SDK / 真实 Gradio HTTP 验收，尚未逐项付费验证。usage/token 金额未保留，不能报告实际费用。

官方契约核对时间：2026-10-01。

- [官方 quickstart](https://developers.openai.com/api/docs/guides/agents-api/quickstart)
- [事件与 items](https://developers.openai.com/api/docs/guides/agents-api/sessions/events)
- [API streaming events](https://developers.openai.com/api/reference/resources/beta/subresources/agents/streaming-events)
- [文件与产物](https://developers.openai.com/api/docs/guides/agents-api/environments/files)

这项集成面向 beta.agents namespace；它与 Agents SDK（应用内编排框架）、Responses API、旧 Assistants API 是不同接口。此次选择独立托管 session，不修改已有普通 provider，也不升级全项目到新 SDK。
