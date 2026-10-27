# Agent 模型推理兼容规则

核对日期：2026-10-06。能力表位于 `modules/agent/reasoning.py`，UI 与创建、更新、运行入口共用该表。

| 精确模型标识 | 可显式选择的 effort | 来源 |
| --- | --- | --- |
| gpt-6-astra | low、medium、high、xhigh、max | [官方模型页](https://developers.openai.com/api/docs/models/gpt-6-astra) |
| gpt-6-sol | none、low、medium、high、xhigh、max | [官方模型页](https://developers.openai.com/api/docs/models/gpt-6-sol) |
| gpt-6.1-sol | low、medium、high、xhigh、max | [官方模型页](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |

各模型另有“模型默认”，创建时省略 reasoning，更新时用 effort=null。合法的显式选择保持原值，包括 GPT-6 Sol 的 none；不把默认、medium 或其他合法值一律改成 low。已知型号的旧 minimal（以及不支持的 none）按已授权的兼容策略调整为 low，选框同步显示 low，现有状态区域显示调整说明。旧云端 session 的生效设置在更新确认前保持原值，下一轮输入提交前完成兼容更新。

这是基于官方可验证文档的静态能力表，未声称从远端动态发现能力，也未添加探测请求。实际安装的 OpenAI SDK 3.22.0 中，`types/model.py` 仅声明 id、created、object、owned_by、shutdown_date；Agent / AgentSession 的 reasoning 是当前配置或解析后的默认值；`types/beta/agent_reasoning.py` 的 effort 是全模型联合枚举。上述类型没有声明每个模型的 supported_efforts，不能将联合枚举或当前值当成远端能力清单。

未知或自定义模型（包括未核实的版本标识）不借用其他型号的支持列表：下拉框只列出模型默认及已保存的 SDK 合法当前值，允许按服务商说明输入 effort，并显示“尚无已核实的推理选项”的说明。服务端保留合法枚举内的显式值，将具体兼容性留给供应商判定；不静默改为 low。SDK 枚举外的值在任何 HTTP 调用前拒绝。新增型号或版本必须先核对其官方约束再添加精确标识，不使用名称前缀猜测能力。

HTTP 400 表示请求被拒绝，提示检查模型和请求参数；不据此推断 API 地址改变或不支持 Agents API。诊断仅保存封闭允许的 HTTP 状态、error type/code、参数字段、请求阶段和 request id。索引工具字段只接受限定格式与字段名。日志和私有绑定不记录异常原文、响应正文、用户输入、连接 URL 或凭据。确定拒绝后仍不自动重发。附件准备阶段独立保存 `last_request_phase`，清除提交不确定标记不会丢失失败位置。

离线回归 `tests/agent/test_reasoning_compatibility.py` 使用实际 SDK 的 MockTransport 并禁止 socket 连接，覆盖继承、恢复、切模型、合法低强度保留、未知模型、SDK 序列化、更新确认、创建/更新/附件错误阶段，以及下拉框回执的访问目标和版本检查。该回归不验证远端服务的实际可用性。
