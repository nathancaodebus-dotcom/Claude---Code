"""Agent.respond()/respond_streaming() share one tool-use loop with Claude,
now streamed and prompt-cached. These tests fake the anthropic client's
messages.stream() context manager (matching the real SDK's `.text_stream` /
`.get_final_message()` shape) so the loop, sentence-chunking, tool dispatch,
and cache_control placement can all be verified without a real API call."""
from __future__ import annotations

import threading
import time

import anthropic
import httpx

from core.agent import Agent
from core.memory import Memory
from tools.base import Tool, ToolRegistry


class _TextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, id: str, name: str, input: dict):  # noqa: A002
        self.id = id
        self.name = name
        self.input = input


class _FakeMessage:
    def __init__(self, content: list, stop_reason: str):
        self.content = content
        self.stop_reason = stop_reason


class _FakeStreamContext:
    def __init__(self, deltas: list[str], final_message: _FakeMessage):
        self._deltas = deltas
        self._final_message = final_message

    @property
    def text_stream(self):
        return iter(self._deltas)

    def get_final_message(self) -> _FakeMessage:
        return self._final_message

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeMessagesAPI:
    def __init__(self, turns: list[tuple[list[str], _FakeMessage]]):
        self._turns = list(turns)
        self.stream_calls: list[dict] = []

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        turn = self._turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        deltas, final_message = turn
        return _FakeStreamContext(deltas, final_message)


class _FakeClient:
    def __init__(self, turns: list[tuple[list[str], _FakeMessage]]):
        self.messages = _FakeMessagesAPI(turns)


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes back the given text."
    input_schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def __init__(self):
        self.calls: list[str] = []

    def run(self, text: str) -> str:
        self.calls.append(text)
        return f"echoed: {text}"


def _make_agent(turns: list[tuple[list[str], _FakeMessage]], registry: ToolRegistry | None = None):
    memory = Memory(db_path=":memory:")
    agent = Agent(memory, registry or ToolRegistry())
    agent._client = _FakeClient(turns)
    return agent, memory


def test_respond_returns_full_streamed_text():
    final = _FakeMessage([_TextBlock("Hello there.")], "end_turn")
    agent, memory = _make_agent([(["Hello ", "there."], final)])

    reply = agent.respond("s1", "hi")

    assert reply == "Hello there."
    history = memory.history("s1")
    assert [m.content for m in history] == ["hi", "Hello there."]


def test_consolidation_runs_in_background_and_does_not_block_the_response():
    """maybe_consolidate makes a real Claude call once a session crosses the
    threshold — respond() must return the user's answer without waiting for
    that, or every response landing on the threshold would silently eat a
    whole extra API round trip's worth of latency."""
    final = _FakeMessage([_TextBlock("ok")], "end_turn")
    agent, _ = _make_agent([(["ok"], final)])

    consolidation_started = threading.Event()
    consolidation_may_finish = threading.Event()

    def slow_maybe_consolidate(session_id: str) -> None:
        consolidation_started.set()
        consolidation_may_finish.wait(timeout=2)

    agent._consolidator.maybe_consolidate = slow_maybe_consolidate

    start = time.perf_counter()
    reply = agent.respond("s1", "hi")
    elapsed = time.perf_counter() - start

    assert reply == "ok"
    assert elapsed < 1.0, "respond() waited for the consolidator instead of backgrounding it"
    assert consolidation_started.wait(timeout=1), "background consolidation never ran"
    consolidation_may_finish.set()  # let the background thread exit cleanly before the test ends


def test_respond_streaming_calls_on_sentence_per_complete_sentence():
    final = _FakeMessage([_TextBlock("First one. Second one? Third.")], "end_turn")
    agent, _ = _make_agent([(["First one. Second ", "one? Third."], final)])

    seen = []
    reply = agent.respond_streaming("s1", "hi", on_sentence=seen.append)

    assert seen == ["First one.", "Second one?", "Third."]
    assert reply == "First one. Second one? Third."


def test_respond_streaming_flushes_trailing_text_without_terminal_punctuation():
    final = _FakeMessage([_TextBlock("No punctuation at the end")], "end_turn")
    agent, _ = _make_agent([(["No punctuation ", "at the end"], final)])

    seen = []
    agent.respond_streaming("s1", "hi", on_sentence=seen.append)

    assert seen == ["No punctuation at the end"]


def test_remembered_fact_reaches_the_next_turns_system_prompt_end_to_end():
    """Regression test for a real bug reported against a comparable project
    (OpenJarvis #721): auto-captured facts were written successfully but
    never actually reached the prompt-injection path, so recall silently
    didn't work despite the write appearing to succeed. Exercises the real
    path start to finish — dispatching remember_fact through the registry
    exactly as Claude's tool_use block would, not calling memory.remember_fact()
    directly — then checks the *next* turn's system block actually contains it."""
    from tools.memory_tool import RememberFactTool

    registry = ToolRegistry()
    memory = Memory(db_path=":memory:")
    registry.register(RememberFactTool(memory))

    remember_round = _FakeMessage(
        [_ToolUseBlock("call_1", "remember_fact", {"key": "dog_name", "value": "Rex"})], "tool_use"
    )
    ack_round = _FakeMessage([_TextBlock("Got it, I'll remember that.")], "end_turn")
    agent = Agent(memory, registry)
    agent._client = _FakeClient([([], remember_round), (["Got it, I'll remember that."], ack_round)])

    agent.respond("s1", "My dog's name is Rex.")

    next_turn_system_blocks = agent._system_blocks("s1")
    dynamic_block_text = "\n\n".join(b["text"] for b in next_turn_system_blocks if "cache_control" not in b)
    assert "dog_name" in dynamic_block_text
    assert "Rex" in dynamic_block_text


def test_respond_dispatches_tool_use_round_then_returns_final_answer():
    tool = _EchoTool()
    registry = ToolRegistry()
    registry.register(tool)

    tool_round = _FakeMessage(
        [_ToolUseBlock("call_1", "echo", {"text": "ping"})], "tool_use"
    )
    final_round = _FakeMessage([_TextBlock("Done: echoed: ping")], "end_turn")
    agent, _ = _make_agent(
        [([], tool_round), (["Done: echoed: ping"], final_round)], registry
    )

    reply = agent.respond("s1", "please echo ping")

    assert tool.calls == ["ping"]
    assert reply == "Done: echoed: ping"
    assert len(agent._client.messages.stream_calls) == 2


def test_tool_call_survives_alongside_streamed_text_in_the_same_turn():
    """Regression test for a real bug reported against a comparable project
    (OpenJarvis #707): function calls got dropped specifically when text was
    also being streamed in the same response. core/agent.py extracts both
    text *and* tool_use blocks from the fully-assembled get_final_message()
    result, never from the incremental .text_stream deltas, so a tool call
    should never be at risk of being lost just because prose was streamed
    alongside it in the same turn — this locks that in."""
    tool = _EchoTool()
    registry = ToolRegistry()
    registry.register(tool)

    mixed_round = _FakeMessage(
        [_TextBlock("Let me check that for you."), _ToolUseBlock("call_1", "echo", {"text": "ping"})],
        "tool_use",
    )
    final_round = _FakeMessage([_TextBlock("Done: echoed: ping")], "end_turn")
    agent, _ = _make_agent(
        [(["Let me check ", "that for you."], mixed_round), (["Done: echoed: ping"], final_round)], registry
    )

    reply = agent.respond("s1", "please echo ping")

    assert tool.calls == ["ping"], "the tool_use block alongside streamed text was dropped"
    assert reply == "Done: echoed: ping"


def test_system_blocks_mark_static_instructions_as_cacheable():
    agent, _ = _make_agent([])

    blocks = agent._system_blocks("s1")

    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "second self" in blocks[0]["text"]
    # No facts/summary recorded yet for a fresh in-memory session, so there's
    # nothing dynamic to append.
    assert len(blocks) == 1


def test_system_blocks_append_uncached_dynamic_block_when_facts_exist():
    agent, memory = _make_agent([])
    memory.remember_fact("favorite_color", "blue")

    blocks = agent._system_blocks("s1")

    assert len(blocks) == 2
    assert "cache_control" not in blocks[1]
    assert "blue" in blocks[1]["text"]


def test_cached_tool_schemas_marks_only_the_last_schema():
    registry = ToolRegistry()
    registry.register(_EchoTool())
    agent, _ = _make_agent([], registry)

    schemas = agent._cached_tool_schemas()

    assert len(schemas) == 1
    assert schemas[-1]["cache_control"] == {"type": "ephemeral"}


def test_cached_tool_schemas_handles_empty_registry():
    agent, _ = _make_agent([], ToolRegistry())

    assert agent._cached_tool_schemas() == []


# --- offline fallback ---


def _fake_httpx_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _fake_httpx_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_fake_httpx_request())


class _FakeOfflineAgent:
    def __init__(self, reply: str = "offline reply"):
        self.reply = reply
        self.calls: list[str] = []

    def respond(self, user_message: str) -> str:
        self.calls.append(user_message)
        return self.reply


def test_connection_error_falls_back_to_offline_agent(monkeypatch):
    agent, memory = _make_agent([anthropic.APIConnectionError(request=_fake_httpx_request())])
    monkeypatch.setattr("core.agent.is_ollama_reachable", lambda host: True)
    agent._offline = _FakeOfflineAgent("offline reply")

    reply = agent.respond("s1", "hi")

    assert reply == "offline reply"
    assert agent._offline.calls == ["hi"]
    assert [m.content for m in memory.history("s1")] == ["hi", "offline reply"]


def test_rate_limit_error_falls_back_to_offline_agent(monkeypatch):
    error = anthropic.RateLimitError("rate limited", response=_fake_httpx_response(429), body=None)
    agent, _ = _make_agent([error])
    monkeypatch.setattr("core.agent.is_ollama_reachable", lambda host: True)
    agent._offline = _FakeOfflineAgent("offline reply")

    assert agent.respond("s1", "hi") == "offline reply"


def test_internal_server_error_falls_back_to_offline_agent(monkeypatch):
    error = anthropic.InternalServerError("outage", response=_fake_httpx_response(500), body=None)
    agent, _ = _make_agent([error])
    monkeypatch.setattr("core.agent.is_ollama_reachable", lambda host: True)
    agent._offline = _FakeOfflineAgent("offline reply")

    assert agent.respond("s1", "hi") == "offline reply"


def test_credit_balance_error_falls_back_to_offline_agent(monkeypatch):
    error = anthropic.BadRequestError(
        "Your credit balance is too low to access the Anthropic API.",
        response=_fake_httpx_response(400),
        body=None,
    )
    agent, _ = _make_agent([error])
    monkeypatch.setattr("core.agent.is_ollama_reachable", lambda host: True)
    agent._offline = _FakeOfflineAgent("offline reply")

    assert agent.respond("s1", "hi") == "offline reply"


def test_unrelated_bad_request_error_does_not_fall_back():
    error = anthropic.BadRequestError("max_tokens is too large.", response=_fake_httpx_response(400), body=None)
    agent, _ = _make_agent([error])
    agent._offline = _FakeOfflineAgent("offline reply")

    try:
        agent.respond("s1", "hi")
        assert False, "expected the BadRequestError to propagate"
    except anthropic.BadRequestError:
        pass
    assert agent._offline.calls == []


def test_authentication_error_does_not_fall_back():
    """A bad API key is a real misconfiguration the user needs to see and
    fix -- silently degrading to a local model would hide it instead."""
    error = anthropic.AuthenticationError("invalid x-api-key", response=_fake_httpx_response(401), body=None)
    agent, _ = _make_agent([error])
    agent._offline = _FakeOfflineAgent("offline reply")

    try:
        agent.respond("s1", "hi")
        assert False, "expected the AuthenticationError to propagate"
    except anthropic.AuthenticationError:
        pass
    assert agent._offline.calls == []


def test_falls_back_gracefully_when_ollama_also_unreachable(monkeypatch):
    agent, _ = _make_agent([anthropic.APIConnectionError(request=_fake_httpx_request())])
    monkeypatch.setattr("core.agent.is_ollama_reachable", lambda host: False)
    agent._offline = _FakeOfflineAgent("should not be used")

    reply = agent.respond("s1", "hi")

    assert "can't reach Claude" in reply
    assert "Ollama" in reply
    assert agent._offline.calls == []  # never actually called — unreachable check happens first


def test_offline_reply_reaches_on_sentence_callback(monkeypatch):
    agent, _ = _make_agent([anthropic.APIConnectionError(request=_fake_httpx_request())])
    monkeypatch.setattr("core.agent.is_ollama_reachable", lambda host: True)
    agent._offline = _FakeOfflineAgent("offline reply")

    seen = []
    agent.respond_streaming("s1", "hi", on_sentence=seen.append)

    assert seen == ["offline reply"]
