"""Run with python -m unittest discover -s tests -v.

Uses the installed LangChain runtime. UI, document indexing, model inference and
unrelated tool loading are isolated so this suite needs no GPU or API keys.
"""

import asyncio
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import httpx
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.language_models.fake import FakeListLLM
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from modules import parallel_search


QUERY = {"objective": "Find Chuanhu Chat documentation", "search_queries": ["Chuanhu Chat documentation"]}
SOURCE = '{"results":[{"url":"https://example.org/docs?a=1&b=2","excerpts":["Chuanhu documentation"]}]}'
REAL_CLIENT = httpx.AsyncClient


def load_agent_module():
    """Import the real agent without the app's unrelated UI/indexing setup."""
    class BaseModel:
        def __init__(self, model_name, user):
            self.model_name = model_name

    stubs = {}
    for name, attrs in {
        "gradio": {},
        "modules.index_func": {"construct_index": Mock()},
        "modules.presets": {"SUMMARIZE_PROMPT": "{text}", "i18n": lambda value: value},
        "modules.utils": {"add_source_numbers": Mock()},
        "modules.models.base_model": {
            "BaseLLMModel": BaseModel,
            "CallbackToIterator": Mock(),
            "ChuanhuCallbackHandler": Mock(),
        },
    }.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        stubs[name] = module
    with patch.dict(sys.modules, stubs):
        return importlib.import_module("modules.models.ChuanhuAgent")


agent_module = load_agent_module()


def make_agent(environment):
    # Execute the actual constructor and provider-selection code. No inference
    # request or default-provider network call is made during registration.
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment, clear=True))
        stack.enter_context(patch.object(agent_module, "ChatOpenAI", return_value=Mock()))
        stack.enter_context(patch.object(agent_module, "TokenTextSplitter"))
        stack.enter_context(patch.object(agent_module, "load_summarize_chain"))
        loaded = stack.enter_context(patch.object(agent_module, "load_tools", return_value=[]))
        agent = agent_module.ChuanhuAgent_Client("川虎助理", "inference-test-key")
        return agent, loaded.call_args.args[0]


class MCPServer:
    def __init__(self, sse=False, failure=None):
        self.requests = []
        self.sse = sse
        self.failure = failure

    async def handle(self, request):
        self.requests.append(request)
        payload = json.loads(request.content)
        method = payload["method"]
        if self.failure and method == "tools/call":
            if isinstance(self.failure, Exception):
                raise self.failure
            return self.failure
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {"protocolVersion": parallel_search.PROTOCOL_VERSION}
        elif method == "tools/list":
            result = {"tools": [{"name": "web_search"}]}
        else:
            result = {"content": [{"type": "text", "text": SOURCE}]}
        message = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        headers = {"mcp-session-id": "transport-session"} if method == "initialize" else {}
        if self.sse:
            # Include a notification and multiline data to exercise framing.
            notification = 'data: {"jsonrpc":"2.0","method":"notifications/message"}\n\n'
            text = json.dumps(message, indent=2)
            data = notification + "\n".join("data: " + line for line in text.splitlines()) + "\n\n"
            return httpx.Response(200, text=data, headers={**headers, "content-type": "text/event-stream"})
        return httpx.Response(200, json=message, headers=headers)

    def client(self, **kwargs):
        return REAL_CLIENT(transport=httpx.MockTransport(self.handle), **kwargs)


class ParallelSearchTests(unittest.TestCase):
    def test_saved_config_overrides_environment_for_enable_and_disable(self):
        import modules

        presets = types.ModuleType("modules.presets")
        presets.i18n = lambda value: value
        presets.MODEL_METADATA = {}
        presets.DEFAULT_METADATA = {}
        presets.MODELS = ["GPT-4o-mini"]
        shared = types.ModuleType("modules.shared")
        shared.state = Mock()
        config_path = Path(__file__).resolve().parents[1] / "modules" / "config.py"
        for saved, env in [("true", "false"), ("false", "true")]:
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                Path(directory, "config.json").write_text(json.dumps({"CHUANHU_PARALLEL_SEARCH": saved}))
                stack.enter_context(patch.dict(os.environ, {"CHUANHU_PARALLEL_SEARCH": env}, clear=True))
                stack.enter_context(patch.dict(sys.modules, {"modules.presets": presets, "modules.shared": shared}))
                stack.enter_context(patch.object(modules, "presets", presets, create=True))
                stack.enter_context(patch.object(modules, "shared", shared, create=True))
                previous_directory = os.getcwd()
                try:
                    os.chdir(directory)
                    spec = importlib.util.spec_from_file_location("modules.config_under_test", config_path)
                    config = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(config)
                finally:
                    os.chdir(previous_directory)
                self.assertEqual(os.environ["CHUANHU_PARALLEL_SEARCH"], saved)
                agent, _ = make_agent(dict(os.environ))
                self.assertEqual("parallel_search" in [tool.name for tool in agent.tools], saved == "true")

    def test_default_and_explicit_disable_make_no_mcp_requests(self):
        for env in [{}, {"CHUANHU_PARALLEL_SEARCH": "false"}, {"CHUANHU_PARALLEL_SEARCH": "0"}]:
            with self.subTest(env=env), patch.object(parallel_search.httpx, "AsyncClient") as client:
                agent, loaded = make_agent(env)
                self.assertIn("ddg_search_json", [tool.name for tool in agent.tools])
                self.assertNotIn("parallel_search", [tool.name for tool in agent.tools])
                self.assertNotIn("google-search-results-json", loaded)
                client.assert_not_called()

    def test_opt_in_preserves_default_and_configured_tools(self):
        for env in [
            {"CHUANHU_PARALLEL_SEARCH": "true"},
            {"CHUANHU_PARALLEL_SEARCH": "1", "GOOGLE_CSE_ID": "cse", "GOOGLE_API_KEY": "key", "SERPAPI_API_KEY": "serp"},
        ]:
            with self.subTest(env=env), patch.object(parallel_search.httpx, "AsyncClient") as client:
                agent, loaded = make_agent(env)
                names = [tool.name for tool in agent.tools]
                self.assertIn("parallel_search", names)
                self.assertIn("summary_webpage", names)
                self.assertIn("ask_webpage", names)
                self.assertEqual("ddg_search_json" in names, "GOOGLE_API_KEY" not in env)
                self.assertEqual("google-search-results-json" in loaded, "GOOGLE_API_KEY" in env)
                self.assertEqual("serpapi" in loaded, "SERPAPI_API_KEY" in env)
                client.assert_not_called()

    def test_registered_tool_json_sse_and_request_headers(self):
        for sse in [False, True]:
            with self.subTest(sse=sse):
                server = MCPServer(sse=sse)
                agent, _ = make_agent({"CHUANHU_PARALLEL_SEARCH": "true"})
                tool = next(tool for tool in agent.tools if tool.name == "parallel_search")
                with patch.object(parallel_search.httpx, "AsyncClient", side_effect=server.client):
                    self.assertEqual(tool.invoke(QUERY), SOURCE)
                    self.assertEqual(tool.invoke(QUERY), SOURCE)
                conversation_ids = []
                for request in server.requests:
                    self.assertEqual(str(request.url), parallel_search.MCP_URL)
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(request.headers["User-Agent"], parallel_search.USER_AGENT)
                    self.assertNotIn("authorization", request.headers)
                    payload = json.loads(request.content)
                    if payload["method"] != "initialize":
                        self.assertEqual(request.headers["Mcp-Session-Id"], "transport-session")
                        self.assertEqual(request.headers["MCP-Protocol-Version"], parallel_search.PROTOCOL_VERSION)
                    if payload["method"] == "tools/call":
                        args = payload["params"]["arguments"]
                        self.assertEqual(args["objective"], QUERY["objective"])
                        self.assertEqual(args["search_queries"], QUERY["search_queries"])
                        conversation_ids.append(args["session_id"])
                self.assertEqual(len(conversation_ids), 2)
                self.assertEqual(conversation_ids[0], conversation_ids[1])

    def test_real_langchain_agent_consumes_search_observation(self):
        # Scripted model responses, real constructor/tool/AgentExecutor. This is
        # an agent-dispatch test, not a claim about live model search decisions.
        server = MCPServer()
        agent, _ = make_agent({"CHUANHU_PARALLEL_SEARCH": "true"})
        model = FakeMessagesListChatModel(responses=[
            AIMessage(content="", additional_kwargs={"tool_calls": [{
                "id": "call_search", "type": "function", "function": {
                    "name": "parallel_search", "arguments": json.dumps(QUERY),
                },
            }]}),
            AIMessage(content="See https://example.org/docs?a=1&b=2"),
        ])
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Use sources to answer."), ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        executable = create_openai_tools_agent(model, agent.tools, prompt)
        executor = AgentExecutor(agent=executable, tools=agent.tools, return_intermediate_steps=True)
        with patch.object(parallel_search.httpx, "AsyncClient", side_effect=server.client):
            result = executor.invoke({"input": "Find Chuanhu documentation"})
        self.assertEqual(result["intermediate_steps"][0][1], SOURCE)
        self.assertIn("https://example.org/docs?a=1&b=2", result["output"])
        self.assertEqual(len(server.requests), 4)

    def test_actual_agent_entrypoint_consumes_tool_result(self):
        class RecordingModel(FakeListLLM):
            prompts: list = []

            def _call(self, prompt, stop=None, run_manager=None, **kwargs):
                self.prompts.append(prompt)
                return super()._call(prompt, stop=stop, run_manager=run_manager, **kwargs)

        model = RecordingModel(responses=[
            'Action:\n```json\n' + json.dumps({"action": "parallel_search", "action_input": QUERY}) + '\n```',
            'Action:\n```json\n' + json.dumps({"action": "Final Answer", "action_input": "See https://example.org/docs?a=1&b=2"}) + '\n```',
        ])
        server = MCPServer()
        agent, _ = make_agent({"CHUANHU_PARALLEL_SEARCH": "true"})
        agent.llm = model
        agent.history = [{"role": "user", "content": "Find Chuanhu documentation"}]
        with patch.object(parallel_search.httpx, "AsyncClient", side_effect=server.client):
            reply, token_count = agent.get_answer_at_once()
        self.assertIn(SOURCE, model.prompts[1])
        self.assertIn("https://example.org/docs?a=1&b=2", reply)
        self.assertEqual(token_count, -1)
        self.assertEqual(len(server.requests), 4)

    def test_errors_are_tool_observations_without_provider_fallback(self):
        failures = [
            httpx.Response(429, text="quota exceeded"),
            httpx.Response(403, text="forbidden"),
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "error": {"message": "bad request"}}),
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": {"isError": True, "content": [{"type": "text", "text": "quota exceeded"}]}}),
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 99, "result": {}}),
            httpx.Response(200, text="not json", headers={"content-type": "application/json"}),
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": {"content": []}}),
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": {"content": [None]}}),
            httpx.Response(302, headers={"location": "https://example.org/redirect"}),
            httpx.Response(200, text=" " * (parallel_search.MAX_RESPONSE_BYTES + 1), headers={"content-type": "application/json"}),
            httpx.ReadTimeout("slow provider"),
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                server = MCPServer(failure=failure)
                with patch.object(parallel_search.httpx, "AsyncClient", side_effect=server.client):
                    result = parallel_search.create_parallel_search_tool().invoke(QUERY)
                self.assertTrue(result.startswith("Parallel"), result)
                self.assertNotEqual(result, SOURCE)
                self.assertEqual(len(server.requests), 4)

    def test_invalid_arguments_do_not_send_requests(self):
        with patch.object(parallel_search.httpx, "AsyncClient") as client:
            with self.assertRaises(ValueError):
                parallel_search.create_parallel_search_tool().invoke({"objective": "", "search_queries": []})
            client.assert_not_called()


class AsyncSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_dispatch(self):
        server = MCPServer()
        with patch.object(parallel_search.httpx, "AsyncClient", side_effect=server.client):
            self.assertEqual(await parallel_search.create_parallel_search_tool().ainvoke(QUERY), SOURCE)

    async def test_cancellation_closes_transport_and_is_not_swallowed(self):
        entered = asyncio.Event()
        closed = asyncio.Event()
        server = MCPServer()

        class BlockingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                entered.set()
                await asyncio.Event().wait()
                yield b""

            async def aclose(self):
                closed.set()

        async def handle(request):
            if json.loads(request.content)["method"] != "tools/call":
                return await server.handle(request)
            return httpx.Response(200, stream=BlockingStream(), headers={"content-type": "application/json"})

        def client(**kwargs):
            return REAL_CLIENT(transport=httpx.MockTransport(handle), **kwargs)

        with patch.object(parallel_search.httpx, "AsyncClient", side_effect=client):
            task = asyncio.create_task(parallel_search.create_parallel_search_tool().ainvoke(QUERY))
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(closed.is_set())

    async def test_overall_deadline(self):
        server = MCPServer()

        async def handle(request):
            if json.loads(request.content)["method"] == "tools/call":
                await asyncio.Event().wait()
            return await server.handle(request)

        def client(**kwargs):
            return REAL_CLIENT(transport=httpx.MockTransport(handle), **kwargs)

        with patch.object(parallel_search.httpx, "AsyncClient", side_effect=client), patch.object(parallel_search, "CALL_TIMEOUT", 0.02):
            result = await parallel_search.create_parallel_search_tool().ainvoke(QUERY)
        self.assertIn("timed out", result)


if __name__ == "__main__":
    unittest.main()
