"""End-to-end coverage for tools/registry_builder.py's MCP block: with
MCP_SERVERS_CONFIG_PATH unset, nothing MCP-related should even be
attempted; with it pointing at a real config, the fixture MCP server's
tools should show up in the registry and actually dispatch through it."""
from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

import pytest

from core.config import config
from core.memory import Memory
from core.store import Store
from tools.registry_builder import build_registry

pytest.importorskip("mcp")

_FIXTURE_SERVER = str(Path(__file__).parent / "fixtures" / "mcp_echo_server.py")


def _set_mcp_config_path(value):
    object.__setattr__(config, "mcp_servers_config_path", value)


@pytest.fixture(autouse=True)
def _restore_mcp_config_path():
    original = config.mcp_servers_config_path
    yield
    _set_mcp_config_path(original)


def test_build_registry_registers_no_mcp_tools_when_unconfigured():
    _set_mcp_config_path(None)
    registry = build_registry(Memory(db_path=":memory:"), Store(db_path=":memory:"))

    assert not any(t.name.startswith("mcp_") for t in registry.all())


def test_build_registry_connects_configured_server_and_registers_its_tools(tmp_path):
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({
        "mcpServers": {"echo": {"command": sys.executable, "args": [_FIXTURE_SERVER]}}
    }))
    _set_mcp_config_path(str(config_path))

    registry = build_registry(Memory(db_path=":memory:"), Store(db_path=":memory:"))

    assert registry.get("mcp_echo_echo") is not None
    assert registry.get("mcp_echo_fail") is not None

    result = registry.dispatch("mcp_echo_echo", {"text": "hello from the registry"})
    assert result == "echo: hello from the registry"


def test_build_registry_survives_the_mcp_package_itself_being_missing(monkeypatch, tmp_path):
    """Mirrors test_registry_builder_resilience.py's plotly simulation: MCP
    support is an optional dependency (requirements-mcp.txt) and a missing
    `mcp` package should disable only the MCP tool group, never the rest
    of the registry."""
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({
        "mcpServers": {"echo": {"command": sys.executable, "args": [_FIXTURE_SERVER]}}
    }))
    _set_mcp_config_path(str(config_path))

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("No module named 'mcp'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    registry = build_registry(Memory(db_path=":memory:"), Store(db_path=":memory:"))

    assert not any(t.name.startswith("mcp_") for t in registry.all())
    # The rest of the registry is unaffected.
    assert registry.get("get_weather") is not None
