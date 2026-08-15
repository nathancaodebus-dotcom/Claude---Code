"""Wraps tools discovered from external MCP servers (core/mcp_client.py) as
Orion Tool instances, so they show up in the agent's registry alongside
every hand-written integration with no special-casing anywhere else in the
codebase -- core/agent.py's tool-use loop and dispatch already don't care
where a Tool subclass comes from."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from core.mcp_client import format_call_tool_result
from tools.base import Tool

if TYPE_CHECKING:
    from mcp.types import Tool as MCPToolSpec

    from core.mcp_client import MCPManager

_NAME_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]")
# Anthropic tool names are capped at 128 characters.
_MAX_TOOL_NAME_LENGTH = 128


def _sanitized_tool_name(server_name: str, tool_name: str) -> str:
    raw = f"mcp_{server_name}_{tool_name}"
    return _NAME_SANITIZE_RE.sub("_", raw)[:_MAX_TOOL_NAME_LENGTH]


class MCPTool(Tool):
    """A single tool exposed by one connected MCP server, dispatched back
    through the MCPManager that owns that server's live connection."""

    # An MCP server is an arbitrary external process or remote service --
    # always treated as network-dependent (and so excluded from the
    # offline fallback model, see tools/base.py) since there's no reliable
    # way to know from here whether a given one actually makes one.
    requires_network = True

    def __init__(self, manager: MCPManager, server_name: str, spec: MCPToolSpec) -> None:
        self._manager = manager
        self._server_name = server_name
        self._tool_name = spec.name
        self.name = _sanitized_tool_name(server_name, spec.name)
        self.description = (
            f"{spec.description} (MCP server: {server_name})"
            if spec.description
            else f"MCP tool '{spec.name}' from server '{server_name}'."
        )
        self.input_schema = spec.input_schema

    def run(self, **kwargs: Any) -> str:
        result = self._manager.call_tool(self._server_name, self._tool_name, kwargs)
        return format_call_tool_result(result)


def build_mcp_tools(manager: MCPManager, tools_by_server: dict[str, list[MCPToolSpec]]) -> list[MCPTool]:
    """One MCPTool per tool listed by every successfully connected server."""
    return [
        MCPTool(manager, server_name, spec)
        for server_name, specs in tools_by_server.items()
        for spec in specs
    ]
