# 川虎助理的 Parallel 联网搜索

川虎助理可使用 [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp)
搜索实时信息，并将来源 URL 与摘录提供给模型用于引用。匿名搜索免费，无需账号或
Parallel API Key，搜索使用 Fast 模式，有服务端用量限制。

在 `config.json` 的顶层加入以下配置，然后重启川虎 Chat，重新选择川虎助理模型：

```json
"CHUANHU_PARALLEL_SEARCH": "true"
```

也可以在启动前设置环境变量 `CHUANHU_PARALLEL_SEARCH=true`。如果 `config.json`
包含此项，以配置文件为准，与其他川虎助理设置一致。删除此项或设为字符串 `"false"`
即可关闭此工具。该设置只作用于川虎助理，不影响普通聊天的联网搜索开关。

启用后，助理可调用 `parallel_search` 工具。DuckDuckGo 默认搜索、已配置的 Google
和 SerpAPI 工具仍然可用。搜索失败会向助理返回错误，不会自动切换提供方重试。
只有助理实际调用此工具时，搜索目标和关键词才会发送至
`https://search.parallel.ai/mcp`；未启用时不会连接该服务。

同一对话中的后续提问、流式回答和重试会沿用同一个会话 ID，重置对话或开始独立的
单轮任务时会生成新的 ID。保存的历史记录会保留该 ID；不含 ID 的旧历史记录在加载时
会建立新的会话上下文，再次保存后即可保留。

## Parallel search in ChuanhuAgent

Set the string `"CHUANHU_PARALLEL_SEARCH": "true"` in `config.json`, or set the
environment variable `CHUANHU_PARALLEL_SEARCH=true` before starting the app.
Restart and select a ChuanhuAgent model. The config file takes precedence when
the setting is present. Set it to the string `"false"` or remove the opt-in to
disable it.

The agent can choose the `parallel_search` tool for current information and cite
its source URLs and excerpts. Existing DuckDuckGo, Google and SerpAPI tools stay
available. Ordinary chat's web-search checkbox is unchanged. No Parallel account
or API key is needed; search uses Fast mode and anonymous service limits apply.
Requests have a 45-second
overall timeout, and failures are returned to the agent without automatic provider
fallback. Async tool calls support cancellation. The existing webpage summary
and question-answering tools remain available for reading pages.

Search calls share a conversation ID across follow-up turns, retries and webpage
reads, including streaming turns. Resetting the chat or starting a new independent
single-turn run creates a new ID. Saved histories retain their ID when loaded;
older histories receive a new ID on load and retain it when saved again.
For callers using the model directly, append to the current `history` to continue
a chat; assign a plain list to start an independent context. A captured
`ConversationHistory` can be restored to resume that chat. Each execution binds
its own search tool to that context, so interleaved chats cannot overwrite its ID.
