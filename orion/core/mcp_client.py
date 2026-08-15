"""MCP (Model Context Protocol) client support: lets Orion connect to
external MCP servers configured in a JSON file and use their tools
alongside the hand-written tools/registry_builder.py registry, inspired by
OpenJarvis's mcp_adapter.py (github.com/open-jarvis/OpenJarvis).

Each configured server is either a local subprocess speaking MCP over
stdio (most third-party MCP servers -- npx/uvx-launched filesystem, git,
Slack, ... servers) or a remote server speaking MCP over Streamable HTTP
(a plain url). The config file uses the same "mcpServers" shape as Claude
Desktop/Cursor/etc., so an existing config from another MCP client can
usually be pointed at directly -- see mcp_servers.example.json.

The MCP SDK's ClientSession is async-only and expects a long-lived
connection: list_tools() once, then call_tool() many times over the same
session, not a fresh connection per call (slow -- a new subprocess/
handshake every time -- and wrong for any server that keeps state between
calls). Every tool call in this codebase is synchronous, though
(ToolRegistry.dispatch calls tool.run() directly, from a worker thread via
core/agent.py's ThreadPoolExecutor) -- so MCPManager runs one background
thread with its own event loop for the process's lifetime, connects to
every configured server once, and exposes synchronous connect_all()/
call_tool() methods that hand work to that loop and block for the result.
"""
from __future__ import annotations

import asyncio
import atexit
import json
import logging
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp import ClientSession
    from mcp.types import CallToolResult, Tool as MCPToolSpec

logger = logging.getLogger("orion.mcp")

# Connecting means launching a subprocess (or an HTTP handshake) plus an
# MCP initialize + list_tools round trip -- generous relative to a normal
# tool call, but this only happens once at startup, not per turn.
_CONNECT_TIMEOUT_S = 20.0
_CALL_TOOL_TIMEOUT_S = 60.0


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    url: str | None = None


def load_mcp_server_configs(path: str) -> list[MCPServerConfig]:
    """Reads a Claude-Desktop-style {"mcpServers": {...}} JSON file. Never
    raises -- a missing file, unreadable file, or malformed entry just
    means fewer (or zero) MCP servers get configured, since MCP support is
    entirely opt-in and shouldn't be able to crash startup."""
    file = Path(path)
    if not file.is_file():
        return []

    try:
        raw = json.loads(file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Couldn't read MCP server config %s: %s", path, exc)
        return []

    servers = raw.get("mcpServers", {})
    if not isinstance(servers, dict):
        logger.warning("MCP config %s: 'mcpServers' must be an object, got %r", path, servers)
        return []

    configs = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            logger.warning("Skipping MCP server '%s': expected an object, got %r", name, spec)
            continue
        url = spec.get("url")
        command = spec.get("command")
        if not url and not command:
            logger.warning(
                "Skipping MCP server '%s': needs either 'command' (stdio) or 'url' (HTTP)", name
            )
            continue
        configs.append(
            MCPServerConfig(name=name, command=command, args=list(spec.get("args", [])), env=spec.get("env"), url=url)
        )
    return configs


class MCPManager:
    """Owns the background event loop and one persistent connection per
    configured MCP server."""

    def __init__(self, configs: list[MCPServerConfig]) -> None:
        self._configs = configs
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, list[MCPToolSpec]] = {}

    def connect_all(self) -> dict[str, list[MCPToolSpec]]:
        """Starts the background loop and connects to every configured
        server, blocking until each has either connected and listed its
        tools or failed/timed out. Returns {server_name: [tools]} for the
        servers that connected successfully -- a server that fails (bad
        command, unreachable URL, timeout) is logged and skipped, never
        blocking the others, matching tools/registry_builder.py's
        per-integration resilience elsewhere in this project."""
        if not self._configs:
            return {}
        self._ensure_loop_running()
        future = asyncio.run_coroutine_threadsafe(self._connect_all_async(), self._loop)
        try:
            return future.result(timeout=_CONNECT_TIMEOUT_S * len(self._configs))
        except Exception as exc:
            logger.warning("MCP: connecting to servers timed out or failed: %s", exc)
            return dict(self._tools)

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
        if self._loop is None:
            raise RuntimeError("MCP manager has no servers connected")
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(server_name, tool_name, arguments), self._loop
        )
        return future.result(timeout=_CALL_TOOL_TIMEOUT_S)

    def shutdown(self) -> None:
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown_async(), self._loop).result(timeout=10)
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup, never block process exit on it
            logger.debug("MCP: error while shutting down: %s", exc)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop = None

    def _ensure_loop_running(self) -> None:
        if self._loop is not None:
            return
        ready = threading.Event()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_run, name="orion-mcp", daemon=True)
        self._thread.start()
        ready.wait(timeout=5)

    async def _connect_all_async(self) -> dict[str, list[MCPToolSpec]]:
        self._stack = AsyncExitStack()
        results = await asyncio.gather(
            *(self._connect_one(cfg) for cfg in self._configs), return_exceptions=True
        )
        for cfg, result in zip(self._configs, results):
            if isinstance(result, Exception):
                logger.warning("MCP: server '%s' failed to connect: %s", cfg.name, result)
        return dict(self._tools)

    async def _connect_one(self, cfg: MCPServerConfig) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        if cfg.url:
            from mcp.client.streamable_http import streamable_http_client

            read, write = await self._stack.enter_async_context(streamable_http_client(cfg.url))
        else:
            params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env)
            read, write = await self._stack.enter_async_context(stdio_client(params))

        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listing = await session.list_tools()
        self._sessions[cfg.name] = session
        self._tools[cfg.name] = list(listing.tools)

    async def _call_tool_async(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
        session = self._sessions.get(server_name)
        if session is None:
            raise RuntimeError(f"MCP server '{server_name}' isn't connected")
        return await session.call_tool(tool_name, arguments)

    async def _shutdown_async(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()


def format_call_tool_result(result: CallToolResult) -> str:
    """Flattens an MCP CallToolResult down to the plain string every other
    tool in this project returns to Claude -- text blocks joined together,
    non-text content (images, embedded resources, ...) noted by type since
    there's no multimodal tool-result channel back to Claude here, and an
    is_error result prefixed so the model can see and self-correct instead
    of it silently looking like a normal answer."""
    parts = []
    for block in result.content:
        if block.type == "text":
            parts.append(block.text)
        else:
            parts.append(f"[MCP {block.type} content omitted]")
    text = "\n".join(parts).strip() or "(empty result)"
    return f"Error: {text}" if result.is_error else text
