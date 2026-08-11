import time

from core.tool_cache import ToolResultCache
from tools.base import Tool, ToolRegistry


def test_get_returns_none_for_uncacheable_tool():
    cache = ToolResultCache()
    cache_result = cache.get("echo", {"text": "hi"})
    assert cache_result is None


def test_set_then_get_returns_cached_result_for_cacheable_tool():
    cache = ToolResultCache()
    cache.set("web_search", {"query": "Orion"}, "cached results")

    assert cache.get("web_search", {"query": "Orion"}) == "cached results"


def test_set_is_a_noop_for_uncacheable_tool():
    cache = ToolResultCache()
    cache.set("echo", {"text": "hi"}, "should not be stored")

    assert cache.get("echo", {"text": "hi"}) is None


def test_different_arguments_are_different_cache_entries():
    cache = ToolResultCache()
    cache.set("web_search", {"query": "Orion"}, "result A")

    assert cache.get("web_search", {"query": "Nathan"}) is None


def test_entry_expires_after_its_ttl(monkeypatch):
    cache = ToolResultCache()
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    cache.set("web_search", {"query": "Orion"}, "fresh result")

    monkeypatch.setattr(time, "time", lambda: now + 301)  # web_search TTL is 300s
    assert cache.get("web_search", {"query": "Orion"}) is None


def test_unhashable_argument_does_not_crash_get_or_set():
    cache = ToolResultCache()
    cache.set("web_search", {"query": ["not", "hashable"]}, "result")
    assert cache.get("web_search", {"query": ["not", "hashable"]}) is None


class _CountingTool(Tool):
    name = "web_search"  # a real cacheable tool name, to exercise the cache path
    description = "test double"
    input_schema = {"type": "object", "properties": {"query": {"type": "string"}}}

    def __init__(self):
        self.call_count = 0

    def run(self, query: str) -> str:
        self.call_count += 1
        return f"result for {query} (call {self.call_count})"


def test_dispatch_only_calls_the_tool_once_for_repeated_identical_calls():
    registry = ToolRegistry()
    tool = _CountingTool()
    registry.register(tool)

    first = registry.dispatch("web_search", {"query": "Orion"})
    second = registry.dispatch("web_search", {"query": "Orion"})

    assert first == second
    assert tool.call_count == 1


def test_dispatch_calls_the_tool_again_for_different_arguments():
    registry = ToolRegistry()
    tool = _CountingTool()
    registry.register(tool)

    registry.dispatch("web_search", {"query": "Orion"})
    registry.dispatch("web_search", {"query": "Nathan"})

    assert tool.call_count == 2


class _FailingCacheableTool(Tool):
    name = "get_weather"  # also a cacheable tool name

    description = "test double that always raises"
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        raise RuntimeError("network is down")


def test_dispatch_does_not_cache_a_raised_exception():
    registry = ToolRegistry()
    registry.register(_FailingCacheableTool())

    first = registry.dispatch("get_weather", {})
    assert "network is down" in first

    # A second, identical call should try again (and fail again) rather
    # than serve a cached error — errors are likely transient.
    second = registry.dispatch("get_weather", {})
    assert "network is down" in second
