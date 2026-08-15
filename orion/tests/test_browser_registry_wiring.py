"""Coverage for tools/registry_builder.py's browser automation block --
mirrors tests/test_mcp_registry_wiring.py and
tests/test_registry_builder_resilience.py's plotly simulation: a missing
`playwright` package should disable only the browser tool group, never the
rest of the registry."""
from __future__ import annotations

import builtins

import pytest

from core.memory import Memory
from core.store import Store
from tools.registry_builder import build_registry

pytest.importorskip("playwright")


def test_build_registry_registers_the_browser_tools():
    registry = build_registry(Memory(db_path=":memory:"), Store(db_path=":memory:"))

    assert registry.get("browser_navigate") is not None
    assert registry.get("browser_click") is not None
    assert registry.get("browser_fill") is not None
    assert registry.get("browser_get_text") is not None
    assert registry.get("browser_screenshot") is not None


def test_build_registry_survives_the_playwright_package_itself_being_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright" or name.startswith("playwright."):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    registry = build_registry(Memory(db_path=":memory:"), Store(db_path=":memory:"))

    assert registry.get("browser_navigate") is None
    assert registry.get("browser_click") is None
    # The rest of the registry is unaffected.
    assert registry.get("get_weather") is not None
