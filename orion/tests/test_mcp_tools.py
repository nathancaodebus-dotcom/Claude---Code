"""tools/mcp_tools.py wraps tools discovered from external MCP servers as
Orion Tool instances. Uses plain fake stand-ins for the MCP SDK's Tool spec
and CallToolResult (see tests/test_mcp_client.py for the real-subprocess
integration test of the SDK layer these sit on top of) so this file stays
fast and independent of the `mcp` package being installed."""
from __future__ import annotations

from tools.mcp_tools import MCPTool, _sanitized_tool_name, build_mcp_tools


class _FakeToolSpec:
    def __init__(self, name: str, description: str | None, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeCallToolResult:
    def __init__(self, content, is_error=False):
        self.content = content
        self.is_error = is_error


class _FakeManager:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.next_result = _FakeCallToolResult([_FakeTextBlock("ok")])

    def call_tool(self, server_name: str, tool_name: str, arguments: dict):
        self.calls.append((server_name, tool_name, arguments))
        return self.next_result


def test_sanitized_tool_name_strips_unsafe_characters():
    assert _sanitized_tool_name("my server!", "do-thing.v2") == "mcp_my_server__do-thing_v2"


def test_sanitized_tool_name_truncates_to_max_length():
    name = _sanitized_tool_name("s", "t" * 200)
    assert len(name) == 128


def test_mcp_tool_carries_over_name_description_and_schema():
    manager = _FakeManager()
    spec = _FakeToolSpec("search", "Searches things.", {"type": "object", "properties": {}})

    tool = MCPTool(manager, "my-server", spec)

    assert tool.name == "mcp_my-server_search"
    assert "Searches things." in tool.description
    assert "my-server" in tool.description
    assert tool.input_schema == {"type": "object", "properties": {}}


def test_mcp_tool_without_description_falls_back_to_a_generic_one():
    manager = _FakeManager()
    spec = _FakeToolSpec("search", None, {"type": "object"})

    tool = MCPTool(manager, "my-server", spec)

    assert "search" in tool.description
    assert "my-server" in tool.description


def test_mcp_tool_run_dispatches_through_the_manager_and_formats_the_result():
    manager = _FakeManager()
    manager.next_result = _FakeCallToolResult([_FakeTextBlock("42")])
    spec = _FakeToolSpec("calc", "Calculates.", {"type": "object"})
    tool = MCPTool(manager, "my-server", spec)

    result = tool.run(x=1, y=2)

    assert result == "42"
    assert manager.calls == [("my-server", "calc", {"x": 1, "y": 2})]


def test_mcp_tool_run_surfaces_error_results():
    manager = _FakeManager()
    manager.next_result = _FakeCallToolResult([_FakeTextBlock("bad input")], is_error=True)
    spec = _FakeToolSpec("calc", "Calculates.", {"type": "object"})
    tool = MCPTool(manager, "my-server", spec)

    result = tool.run(x=1)

    assert result == "Error: bad input"


def test_build_mcp_tools_creates_one_tool_per_server_tool():
    manager = _FakeManager()
    tools_by_server = {
        "server-a": [_FakeToolSpec("a1", "d", {}), _FakeToolSpec("a2", "d", {})],
        "server-b": [_FakeToolSpec("b1", "d", {})],
    }

    tools = build_mcp_tools(manager, tools_by_server)

    assert {t.name for t in tools} == {"mcp_server-a_a1", "mcp_server-a_a2", "mcp_server-b_b1"}


def test_build_mcp_tools_with_no_servers_returns_empty():
    assert build_mcp_tools(_FakeManager(), {}) == []
