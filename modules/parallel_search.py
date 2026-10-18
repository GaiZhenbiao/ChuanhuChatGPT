"""Opt-in Parallel Search MCP tool for ChuanhuAgent."""

import asyncio
import json
from typing import List

import httpx
from langchain.tools import StructuredTool
from langchain_core.tools import ToolException
from pydantic.v1 import BaseModel, Field


MCP_URL = "https://search.parallel.ai/mcp"
USER_AGENT = "ChuanhuChat (https://github.com/GaiZhenbiao/ChuanhuChatGPT)"
PROTOCOL_VERSION = "2025-03-26"
MAX_RESPONSE_BYTES = 1024 * 1024
CALL_TIMEOUT = 45


class ParallelSearchInput(BaseModel):
    objective: str = Field(min_length=1, description="What you want to learn from the web.")
    search_queries: List[str] = Field(
        min_items=1, description="Related keyword queries for this objective."
    )


async def _rpc(client, method, params=None, request_id=None):
    payload = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if request_id is not None:
        payload["id"] = request_id
    async with client.stream("POST", MCP_URL, json=payload) as response:
        response.raise_for_status()
        if method == "initialize":
            session = response.headers.get("mcp-session-id")
            if session:
                client.headers["Mcp-Session-Id"] = session
        if request_id is None:
            return None
        size = 0
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if content_type == "text/event-stream":
            # Stop after our response, even if the server keeps the stream open.
            data = []
            buffer = b""
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError("MCP response is too large")
                buffer += chunk
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    line = raw_line.rstrip(b"\r").decode("utf-8")
                    if line.startswith("data:"):
                        value = line[5:]
                        data.append(value[1:] if value.startswith(" ") else value)
                    elif not line and data:
                        message = json.loads("\n".join(data))
                        data = []
                        if not isinstance(message, dict):
                            raise ValueError("Invalid MCP event")
                        if message.get("id") == request_id:
                            return _result(message, request_id)
            raise ValueError("MCP stream ended without a matching response")
        if content_type != "application/json":
            raise ValueError("Unexpected MCP response type")
        chunks = []
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("MCP response is too large")
            chunks.append(chunk)
        return _result(json.loads(b"".join(chunks)), request_id)


def _result(message, request_id):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or message.get("id") != request_id:
        raise ValueError("Invalid MCP response")
    if "error" in message:
        raise ToolException("Parallel Search MCP error: " + str(message["error"]))
    if not isinstance(message.get("result"), dict):
        raise ValueError("Missing MCP result")
    return message["result"]


def create_parallel_search_tool(session_id=None):
    # Bind an immutable caller-owned context, never a model-wide mutable ID.
    # Hosts without a conversation lifecycle leave this optional field absent.

    async def search(objective, search_queries):
        async def call():
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/event-stream",
            }
            async with httpx.AsyncClient(headers=headers, timeout=30) as client:
                initialized = await _rpc(client, "initialize", {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "ChuanhuChat", "version": "1.0"},
                }, 1)
                version = initialized.get("protocolVersion")
                if version != PROTOCOL_VERSION:
                    raise ValueError("Unsupported MCP protocol version")
                client.headers["MCP-Protocol-Version"] = version
                await _rpc(client, "notifications/initialized")
                discovered = await _rpc(client, "tools/list", {}, 2)
                tools = discovered.get("tools")
                if not isinstance(tools, list) or not any(isinstance(tool, dict) and tool.get("name") == "web_search" for tool in tools):
                    raise ValueError("MCP server does not advertise web_search")
                arguments = {
                    "objective": objective,
                    "search_queries": search_queries,
                }
                if session_id is not None:
                    arguments["session_id"] = session_id
                result = await _rpc(client, "tools/call", {
                    "name": "web_search",
                    "arguments": arguments,
                }, 3)
                content = result.get("content")
                if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
                    raise ValueError("Invalid MCP search content")
                texts = [item["text"] for item in content if item.get("type") == "text"]
                text = "\n".join(texts)
                if result.get("isError"):
                    raise ToolException("Parallel Search MCP: " + text)
                if not text:
                    raise ValueError("MCP search returned no text")
                return text

        try:
            return await asyncio.wait_for(call(), timeout=CALL_TIMEOUT)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise ToolException("Parallel search timed out. Try a narrower query.") from exc
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ToolException("Parallel search failed: " + str(exc)) from exc

    def search_sync(objective, search_queries):
        return asyncio.run(search(objective, search_queries))

    return StructuredTool.from_function(
        func=search_sync,
        coroutine=search,
        name="parallel_search",
        description="Search the web for current information using Parallel. Returns source URLs and excerpts for citations. Group related keyword queries in one call.",
        args_schema=ParallelSearchInput,
        handle_tool_error=True,
    )
