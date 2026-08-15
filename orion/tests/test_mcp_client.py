"""core/mcp_client.py connects Orion to external MCP servers. The config
parsing tests are pure unit tests; the MCPManager tests spawn a real,
tiny MCP server (tests/fixtures/mcp_echo_server.py) over stdio so the
actual SDK integration -- connect, list_tools, call_tool, shutdown -- is
exercised end to end rather than mocked."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.mcp_client import (
    MCPManager,
    MCPServerConfig,
    format_call_tool_result,
    load_mcp_server_configs,
)

pytest.importorskip("mcp")

_FIXTURE_SERVER = str(Path(__file__).parent / "fixtures" / "mcp_echo_server.py")


def _echo_server_config(name: str = "echo") -> MCPServerConfig:
    return MCPServerConfig(name=name, command=sys.executable, args=[_FIXTURE_SERVER])


# --- load_mcp_server_configs ------------------------------------------------


def test_load_mcp_server_configs_missing_file_returns_empty(tmp_path):
    assert load_mcp_server_configs(str(tmp_path / "does_not_exist.json")) == []


def test_load_mcp_server_configs_malformed_json_returns_empty(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text("{not valid json")

    assert load_mcp_server_configs(str(path)) == []


def test_load_mcp_server_configs_skips_server_missing_command_and_url(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"broken": {"args": ["--foo"]}}}))

    assert load_mcp_server_configs(str(path)) == []


def test_load_mcp_server_configs_parses_stdio_and_http_servers(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({
        "mcpServers": {
            "local": {"command": "npx", "args": ["-y", "some-server"], "env": {"FOO": "bar"}},
            "remote": {"url": "https://example.com/mcp"},
        }
    }))

    configs = load_mcp_server_configs(str(path))

    by_name = {c.name: c for c in configs}
    assert by_name["local"].command == "npx"
    assert by_name["local"].args == ["-y", "some-server"]
    assert by_name["local"].env == {"FOO": "bar"}
    assert by_name["remote"].url == "https://example.com/mcp"


# --- format_call_tool_result -------------------------------------------------


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeCallToolResult:
    def __init__(self, content, is_error=False):
        self.content = content
        self.is_error = is_error


def test_format_call_tool_result_joins_text_blocks():
    result = _FakeCallToolResult([_FakeTextBlock("hello"), _FakeTextBlock("world")])
    assert format_call_tool_result(result) == "hello\nworld"


def test_format_call_tool_result_prefixes_errors():
    result = _FakeCallToolResult([_FakeTextBlock("boom")], is_error=True)
    assert format_call_tool_result(result) == "Error: boom"


def test_format_call_tool_result_handles_empty_content():
    assert format_call_tool_result(_FakeCallToolResult([])) == "(empty result)"


# --- MCPManager (real subprocess server) ------------------------------------


@pytest.fixture
def manager():
    mgr = MCPManager([_echo_server_config()])
    yield mgr
    mgr.shutdown()


def test_manager_connects_and_lists_tools(manager):
    tools_by_server = manager.connect_all()

    assert set(tools_by_server.keys()) == {"echo"}
    tool_names = {t.name for t in tools_by_server["echo"]}
    assert tool_names == {"echo", "fail"}


def test_manager_call_tool_returns_text_result(manager):
    manager.connect_all()

    result = manager.call_tool("echo", "echo", {"text": "hi there"})

    assert format_call_tool_result(result) == "echo: hi there"


def test_manager_call_tool_marks_errors(manager):
    manager.connect_all()

    result = manager.call_tool("echo", "fail", {"message": "kaboom"})

    assert result.is_error is True
    assert "kaboom" in format_call_tool_result(result)


def test_manager_with_no_configs_connects_to_nothing():
    mgr = MCPManager([])
    assert mgr.connect_all() == {}


def test_manager_skips_a_server_that_fails_to_connect_without_blocking_others(tmp_path):
    broken = MCPServerConfig(name="broken", command=str(tmp_path / "no-such-binary"), args=[])
    mgr = MCPManager([broken, _echo_server_config("echo")])
    try:
        tools_by_server = mgr.connect_all()
        assert "echo" in tools_by_server
        assert "broken" not in tools_by_server
    finally:
        mgr.shutdown()
