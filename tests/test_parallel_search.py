"""Run with python -m unittest discover -s tests -v.

Uses the installed LangChain runtime. UI, document indexing, model inference and
unrelated tool loading are isolated so this suite needs no GPU or API keys.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

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
    global base_module, utils_module
    stubs = {}
    for name, attrs in {
        "gradio": {"themes": MagicMock(), "Radio": Mock(), "DownloadButton": Mock(),
                   "update": lambda **kwargs: kwargs},
        "gradio.utils": {"get_upload_folder": lambda: tempfile.gettempdir()},
        "gradio.processing_utils": {"save_file_to_cache": lambda path, cache: path},
        "modules.index_func": {"construct_index": Mock()},
        "modules.config": {"retrieve_proxy": Mock(), "auth_list": [],
                           "hide_history_when_not_logged_in": False, "admin_list": []},
    }.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        stubs[name] = module
    with patch.dict(sys.modules, stubs):
        # Keep the real BaseLLMModel lifecycle, history loader, serializer and
        # callback iterator. Only UI/cache/indexing/config startup is isolated.
        agent = importlib.import_module("modules.models.ChuanhuAgent")
        base_module = sys.modules["modules.models.base_model"]
        utils_module = sys.modules["modules.utils"]
        return agent


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
        stack.enter_context(patch.object(base_module, "get_first_history_name", return_value="test"))
        # config.py normally merges these defaults during app startup.
        config = {**base_module.DEFAULT_METADATA, **base_module.MODEL_METADATA["川虎助理"]}
        stack.enter_context(patch.dict(base_module.MODEL_METADATA, {"川虎助理": config}))
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


class RecordingModel(FakeListLLM):
    prompts: list = []

    def _call(self, prompt, stop=None, run_manager=None, **kwargs):
        self.prompts.append(prompt)
        return super()._call(prompt, stop=stop, run_manager=run_manager, **kwargs)


def research_model(label="research", streaming=False):
    query = {**QUERY, "objective": label}
    if streaming:
        return FakeMessagesListChatModel(responses=[
            AIMessage(content="", additional_kwargs={"tool_calls": [{
                "id": "call_search", "type": "function", "function": {
                    "name": "parallel_search", "arguments": json.dumps(query),
                },
            }]}),
            AIMessage(content="", additional_kwargs={"tool_calls": [{
                "id": "call_followup", "type": "function", "function": {
                    "name": "parallel_search", "arguments": json.dumps(query),
                },
            }]}),
            AIMessage(content="See https://example.org/docs?a=1&b=2"),
        ])
    action = 'Action:\n```json\n' + json.dumps({
        "action": "parallel_search", "action_input": query,
    }) + '\n```'
    return RecordingModel(responses=[action, action, 'Action:\n```json\n' + json.dumps({
        "action": "Final Answer", "action_input": "See https://example.org/docs?a=1&b=2",
    }) + '\n```'])


def search_arguments(server):
    return [json.loads(request.content)["params"]["arguments"]
            for request in server.requests
            if json.loads(request.content)["method"] == "tools/call"]


class ConversationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.agent, _ = make_agent({"CHUANHU_PARALLEL_SEARCH": "true"})
        self.agent.history.append({"role": "user", "content": "Research this topic"})
        self.server = MCPServer()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(parallel_search.httpx, "AsyncClient", side_effect=self.server.client))
        self.stack.enter_context(patch.object(self.agent, "token_message", return_value="tokens"))

    def answer(self, label="research"):
        self.agent.llm = research_model(label)
        reply, _ = self.agent.get_answer_at_once()
        self.assertIn(SOURCE, self.agent.llm.prompts[-1])
        self.assertIn("https://example.org/docs", reply)
        return search_arguments(self.server)[-1]["session_id"]

    def test_followups_webpage_read_and_retries_keep_conversation(self):
        first = self.answer()
        self.agent.history.extend([
            {"role": "assistant", "content": "Found sources"},
            {"role": "user", "content": "Follow up on those sources"},
        ])
        # Existing webpage tools use requests, not MCP web_fetch. Reading a
        # source must not change the research context used by the next search.
        with patch.object(agent_module.requests, "get", return_value=Mock(text="<p>A source</p>")), \
                patch.object(self.agent, "summary", return_value="A source"):
            webpage = next(tool for tool in self.agent.tools if tool.name == "summary_webpage")
            self.assertIn("A source", webpage.invoke({"url": "https://example.org/docs"}))
        self.assertEqual(self.answer(), first)
        # Deleting/trimming a turn must not turn a follow-up into a new chat.
        self.agent.history = self.agent.history[-1:]
        self.assertEqual(self.answer(), first)
        with patch.object(self.agent, "auto_save"), patch.object(base_module, "count_token", return_value=1):
            self.agent.stream = False
            list(self.agent.retry([]))
        self.assertEqual({args["session_id"] for args in search_arguments(self.server)}, {first})

    def test_reset_new_and_replaced_history_are_independent(self):
        first = self.answer()
        with patch.object(base_module, "new_auto_history_filename", return_value="new.json"), \
                patch.object(base_module, "get_history_names", return_value=[]):
            self.agent.reset()
        self.agent.history.append({"role": "user", "content": "Independent chat"})
        second = self.answer()
        self.assertNotEqual(first, second)
        self.agent.history = [{"role": "user", "content": "Independent research run"}]
        third = self.answer()
        self.assertNotIn(third, {first, second})
        self.assertEqual(self.answer(), third)

    def test_saved_loaded_and_legacy_histories(self):
        first = self.answer()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(utils_module, "HISTORY_DIR", directory), \
                patch.object(base_module, "HISTORY_DIR", directory):
            saved = utils_module.save_file(str(Path(directory, "saved.json")), self.agent)
            data = json.loads(Path(saved).read_text())
            self.assertEqual(data["conversation_id"], first)
            self.agent.history = [{"role": "user", "content": "Unrelated chat"}]
            unrelated = self.answer()
            self.agent.load_chat_history(saved)
            self.assertEqual(self.answer(), first)
            self.agent.load_chat_history(saved)
            self.assertEqual(self.answer(), first)
            for identity in [None, "invalid identity"]:
                data.pop("conversation_id", None)
                if identity is not None:
                    data["conversation_id"] = identity
                Path(saved).write_text(json.dumps(data))
                self.agent.load_chat_history(saved)
                legacy = self.answer()
                self.assertNotIn(legacy, {first, unrelated})
                self.assertEqual(self.answer(), legacy)
                # Saving a legacy context establishes an identity for reloads.
                utils_module.save_file(saved, self.agent)
                self.agent.load_chat_history(saved)
                self.assertEqual(self.answer(), legacy)

    def test_single_turn_new_runs_and_retry_boundaries(self):
        self.agent.single_turn = True
        self.agent.stream = False
        self.agent.llm = research_model()
        with patch.object(self.agent, "auto_save"), patch.object(base_module, "count_token", return_value=1):
            list(self.agent.predict("First independent run", []))
            first = search_arguments(self.server)[-1]["session_id"]
            list(self.agent.retry([]))
            self.assertEqual(search_arguments(self.server)[-1]["session_id"], first)
            list(self.agent.predict("Next independent run", []))
            second = search_arguments(self.server)[-1]["session_id"]
        self.assertNotEqual(first, second)
        self.assertEqual([a["session_id"] for a in search_arguments(self.server)],
                         [first] * 4 + [second] * 2)

    def test_failure_and_cancellation_retry_keep_run_then_new_run_rotates(self):
        for failure in [httpx.Response(503, text="temporary failure"), asyncio.CancelledError()]:
            with self.subTest(failure=type(failure).__name__):
                self.agent.history = [{"role": "user", "content": "Retry this run"}]
                self.agent.llm = research_model()
                original_handle = self.server.handle
                failed = False

                async def fail_once(request):
                    nonlocal failed
                    if not failed and json.loads(request.content)["method"] == "tools/call":
                        failed = True
                        self.server.requests.append(request)
                        if isinstance(failure, BaseException):
                            raise failure
                        return failure
                    return await original_handle(request)

                with patch.object(self.server, "handle", side_effect=fail_once):
                    if isinstance(failure, asyncio.CancelledError):
                        with self.assertRaises(asyncio.CancelledError):
                            self.agent.get_answer_at_once()
                    else:
                        self.agent.get_answer_at_once()
                failed_id = search_arguments(self.server)[-1]["session_id"]
                self.agent.llm = research_model()
                self.agent.stream = False
                with patch.object(self.agent, "auto_save"), patch.object(base_module, "count_token", return_value=1):
                    list(self.agent.retry([]))
                self.assertEqual(search_arguments(self.server)[-1]["session_id"], failed_id)
                self.agent.history = [{"role": "user", "content": "New run after retry"}]
                self.assertNotEqual(self.answer(), failed_id)

    def test_interleaved_independent_runs_and_resumption_on_one_model(self):
        for streaming in [False, True]:
            with self.subTest(streaming=streaming):
                self.server.requests.clear()
                self.agent.history = [{"role": "user", "content": "Conversation A"}]
                history_a = self.agent.history
                model_a = research_model("A", streaming)
                model_b = research_model("B", streaming)
                entered, release = Event(), Event()
                original_handle = self.server.handle

                async def interleave(request):
                    payload = json.loads(request.content)
                    if (payload["method"] == "tools/call"
                            and payload["params"]["arguments"]["objective"] == "A"
                            and not entered.is_set()):
                        entered.set()
                        if not release.wait(5):
                            raise RuntimeError("Second conversation did not complete")
                    return await original_handle(request)

                def answer():
                    if streaming:
                        return "".join(self.agent.get_answer_stream_iter())
                    return self.agent.get_answer_at_once()[0]

                self.agent.llm = model_a
                initial_tools = list(self.agent.tools)
                with patch.object(self.server, "handle", side_effect=interleave), \
                        patch.object(agent_module, "ChatOpenAI", side_effect=[model_a, model_b]), \
                        ThreadPoolExecutor(max_workers=2) as pool:
                    future_a = pool.submit(answer)
                    try:
                        self.assertTrue(entered.wait(5))
                        self.agent.history = [{"role": "user", "content": "Conversation B"}]
                        history_b = self.agent.history
                        self.agent.llm = model_b
                        future_b = pool.submit(answer)
                        self.assertIn("https://example.org/docs", future_b.result(5))
                    finally:
                        release.set()
                    self.assertIn("https://example.org/docs", future_a.result(5))
                grouped = {label: [a["session_id"] for a in search_arguments(self.server)
                                   if a["objective"] == label] for label in ["A", "B"]}
                self.assertEqual(grouped["A"], [history_a.conversation_id] * 2)
                self.assertEqual(grouped["B"], [history_b.conversation_id] * 2)
                self.assertNotEqual(grouped["A"][0], grouped["B"][0])
                self.assertEqual(self.agent.tools, initial_tools)
                # Switching back to a captured conversation resumes its identity.
                for history in [history_a, history_b]:
                    self.agent.history = history
                    self.agent.history.extend([
                        {"role": "assistant", "content": "Sources found"},
                        {"role": "user", "content": "Follow up"},
                    ])
                    if streaming:
                        with patch.object(agent_module, "ChatOpenAI", return_value=research_model(streaming=True)):
                            self.assertIn("https://example.org/docs", answer())
                        self.assertEqual(search_arguments(self.server)[-1]["session_id"], history.conversation_id)
                    else:
                        self.assertEqual(self.answer(), history.conversation_id)


class ParallelSearchTests(unittest.TestCase):
    def test_tool_without_host_context_omits_optional_session_id(self):
        server = MCPServer()
        tool = parallel_search.create_parallel_search_tool()
        with patch.object(parallel_search.httpx, "AsyncClient", side_effect=server.client):
            self.assertEqual(tool.invoke(QUERY), SOURCE)
        self.assertNotIn("session_id", search_arguments(server)[0])

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
                tool = next(tool for tool in agent._tools_for_conversation(agent.history) if tool.name == "parallel_search")
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
