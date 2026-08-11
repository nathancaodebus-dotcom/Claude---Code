"""Agent.respond()/respond_streaming() share one tool-use loop with Claude,
now streamed and prompt-cached. These tests fake the anthropic client's
messages.stream() context manager (matching the real SDK's `.text_stream` /
`.get_final_message()` shape) so the loop, sentence-chunking, tool dispatch,
and cache_control placement can all be verified without a real API call."""
from __future__ import annotations

import threading
import time

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
        deltas, final_message = self._turns.pop(0)
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
