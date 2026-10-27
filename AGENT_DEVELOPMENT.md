# Agent 维护与离线验证

Agent 使用主项目的 Python 环境与 `openai==3.22.0`，不需要第二个 SDK 环境。
运行代码集中在 `modules/agent/`；`modules/models/OpenAIAgents.py` 保留主界面模型适配职责，普通模型能力仍由 `modules/model_capabilities.py` 管理。

## 会话、历史与文件

- Agent 第一轮建立会话后，主模型选择器锁定。新建聊天或打开其他历史可以离开该会话；Agent 子模型和推理强度仍可以在下一轮更新。
- 历史记录保存模型选择与非秘密参数。切换历史会恢复模型、系统提示及参数，历史中的 API key、授权字段和连接地址不作为凭据来源。
- 服务端会话绑定仍保存在原 `agent_data/bindings.sqlite3`，模块迁移不改变已有会话身份。
- 完整终态回答先保存，再开放操作。可信完整的本轮 item.done 与匹配根轮终态按增量提交并保存后释放同对话任务槽；有已知缺口、断线或恢复时才 GET 对账，不能把当前轮误标为完整会话。文件下载使用独立的有界任务与持久收据，按服务端 session/turn 增量回填最新历史；切换或新建其他对话不受影响。旧 UI 观察器不能覆盖新会话或写回后台绑定。
- 观察回执随 worker 进度进入服务端私有绑定，记录真实根 session/turn/agent、已知消息身份与公开段最低覆盖；重连、历史重新加载和后续同 session 新轮必须携带这些约束。GET 新观察到的旧轮 item、公开段和合法文字改写也按其真实 turn/item 归属更新最低覆盖与最近有效预览；下一次 GET 缺失时保留该预览并保持同步保护，不能退回最初流文字。新发现的服务端历史轮保留覆盖约束，其 pending item 不代替本轮终态准入证明。正常完整新轮仍按本轮增量快提交，不额外 GET。完整 GET 或 item.done 可改写文字，但须满足真实归属、已知段类型/位置和类型专属状态；缺段 added/updated/done 仅合并预览，合并后的旧新段不能充当最终权威证明。
- `modules/agent/tasks.py` 的任务注册表属于单个服务进程：同 owner、同 conversation/session 原子互斥，不同对话允许并发；总计最多 8 个任务，同 owner 最多 3 个，不建立等待队列。普通模型保持原来的前台执行行为。
- 切换、新建、刷新或关闭浏览器只结束 UI 订阅。Agent 本地线程继续接收、节流保存回答，文件队列独立下载并回填原轮；后台等待授权不会自动批准工具请求。Stop 捕获具体任务的 generation/session/turn，切页不改变其目标。
- 提交前保存 intent/generation，收到 session/turn 回执和终态时强制保存；历史 JSON 使用原子替换。状态未知时禁止重复提交，服务重启后只读查询原任务并补下载，不能把缺少 session 当成未发送。
- 服务进程关闭后，本地接收和下载会停止；云端任务是否继续由供应商决定，可能继续产生 API 费用。重启后通过服务端私有绑定恢复查询。本实现不提供多服务进程的数据库租约，不承诺跨实例互斥。
- 文件任务独立于执行注册表：最多 2 个下载工作线程和 32 个等待项，溢出的任务仅存为 durable pending；加载或文件控件刷新后重新准入。重启只恢复当前授权绑定与相同连接的未完成任务。重命名跟随私有任务路径，删除收据阻止旧回填复活。文件回调不能取得模型锁或保存旧模型整份状态。
- 文件缓存按服务端用户与会话隔离。上传原件不会因清理 Agent 私有副本而删除。
- 流中已发布文件的元数据轮询与单个字节下载线程分离，慢文件不会阻塞后续文件卡片发现；按文件身份合并状态，完成/失败回执不回退为准备中。只有真实本轮终态与完整性证据释放发送，正文或下载超链接不代表结束。
- 本轮仍运行且正在等待后续输出时，在正文下保留原加载动画；公开正文流事件和可见进行中工具会隐藏动画，正文段/消息或工具完成后的等待间隙恢复，终态撤除。正文流活动为独立展示状态，不改写消息/轮次完成证据，也不使用停顿计时器。纯加载占位隐藏空 Markdown/Gradio 消息按钮，不改正文和历史。

## 结束延迟诊断

- 缺少已观察公开段的中间 item.added/updated/done 只保留预览；之后同身份、同位置且覆盖全部已知分段的权威 item.done 可补齐该项，不再为已补齐缺口额外 GET。真正身份、位置、类型冲突、未知事件和恢复观察仍保持对账保护。
- 本地 `modules.agent.completion_timing` 日志记录单轮随机 trace、单调时钟时间点和固定原因码：公开段完成、根终态、完整性门槛、GET 对账、结果接收、持久化、任务槽释放、UI 最终帧交付。UI 时间点是服务器交付，不声称浏览器已经绘制。公开段完成也不代表根任务已结束。
- trace 不使用会话/用户/文件身份，日志不含正文、提示、文件名、密钥或令牌；不新增外部遥测连接。日志通过最多 64 条的后台队列交给已有本地日志系统，拥堵时丢弃诊断，不等待日志写入、不延迟任务释放。计时使用同一主机的单调时钟，仅内存/worker IPC 传递，不写入用户历史。
- 离线 slow_close/slow_content/不完整对账用例中的 2 秒为故意模拟的阻塞，不能当作真实供应商耗时。实际耗时须由真实运行的本地计时记录判断。

## MCP 管理员授权

普通无凭据的公网 MCP 可以独立使用，不依赖工具搜索或程序化工具调用。
应用服务器的探测会固定经验证的公网 IP，并保留原 Host 与 TLS SNI；不会跟随重定向或继承环境代理。
因此仅依赖代理或重定向才能访问的服务器需要调整部署，不能用放松地址检查替代。

凭据或私网服务必须由管理员通过服务端环境变量 `CHUANHU_AGENT_MCP_AUTHORIZATION` 绑定。
它是以服务器标签为键的 JSON 对象，例如：

```json
{
  "work-mcp": {
    "server_url": "https://mcp.example.com/mcp",
    "authorization_env": "WORK_MCP_TOKEN",
    "allowed_tools": ["read_issue"],
    "owners": ["alice"]
  }
}
```

管理员绑定仅授予权限，不会自动加入用户工具配置。用户仍需在 Agent 的 MCP 配置中填写 JSON 数组，例如：

```json
[
  {
    "server_label": "work-mcp",
    "server_url": "https://mcp.example.com/mcp",
    "authorization_env": "WORK_MCP_TOKEN",
    "allowed_tools": ["read_issue"]
  }
]
```

`WORK_MCP_TOKEN` 的实际值只由管理员设置在服务器环境中；用户界面和历史中只保存引用名，不能填写真实凭据。

`owners` 使用已认证用户名；只有显式 `shared: true` 才表示部署范围内共享，包含匿名用户。
`allowed_tools` 必须覆盖用户请求的明确工具子集。服务地址与凭据变量名必须完全匹配绑定。
只有管理员显式设置 `allow_private: true` 才允许绑定的私网目标或 HTTP 凭据端点；此设置需要评估内部服务风险。
已有授权配置如果缺少用户范围或工具范围，会安全拒绝，须由管理员补齐，不能从浏览器配置自动扩大权限。
探测地址固定仅约束本应用的请求；托管 Agent 对已批准 MCP 的后续访问仍依赖服务端和托管平台的网络行为。

## 测试

使用完整项目环境安装 `requirements.txt` 与 `requirements_tests.txt` 后，在项目根目录执行。JavaScript 验证还需要已有 Node.js：

```sh
pip install -r requirements.txt -r requirements_tests.txt
python -m pytest tests -q
node tests/javascript/model-capabilities.test.cjs
python tests/production_build_smoke.py
```

测试使用合成数据、SDK 请求形状与真实 Gradio 回调，不需要付费 API 请求，不应加入用户真实聊天、凭据或配置。
其余 JavaScript 用例由 Python 集成测试传入真实服务端标记后执行，不应直接通配启动需要标准输入的脚本。
Agent 相关用例按行为组织于 `tests/agent/`，共享模型夹具位于 `tests/agent_fixtures.py`，普通主界面测试保留在 `tests/`。
离线预览可用 `python tests/main_chat_preview.py --port 8897` 启动，用于浏览器检查；其成功不代表真实供应商端到端验证。

Windows 安全文件实现面向 Windows 10 1709+ 的本地 NTFS；网络盘、SUBST、设备路径和重解析点安全拒绝。
Windows 专属测试必须在原生 Windows 执行；Linux 上的跳过不能视为 Windows 验收通过。
