"""registry_builder.py wraps every tool group's import in _register_safe so
that any single missing dependency (very common on Termux/Android, where
many PyPI packages have no prebuilt wheel) disables only that group, never
the whole registry. These tests simulate that directly against
_register_safe rather than uninstalling real packages."""
import builtins
import logging

from tools.base import ToolRegistry
from tools.registry_builder import _register_safe


def test_register_safe_swallows_import_error(caplog):
    registry = ToolRegistry()

    def failing_group():
        raise ImportError("No module named 'does_not_exist'")

    with caplog.at_level(logging.WARNING):
        _register_safe(registry, "test group", failing_group)

    assert registry.all() == []
    assert "test group" in caplog.text
    assert "does_not_exist" in caplog.text


def test_register_safe_registers_on_success():
    registry = ToolRegistry()
    calls = []

    def working_group():
        calls.append("ran")

    _register_safe(registry, "test group", working_group)

    assert calls == ["ran"]


def test_register_safe_does_not_swallow_other_exceptions():
    registry = ToolRegistry()

    def broken_group():
        raise ValueError("this is a real bug, not a missing dependency")

    try:
        _register_safe(registry, "test group", broken_group)
        assert False, "expected ValueError to propagate"
    except ValueError:
        pass


def test_build_registry_survives_a_missing_dependency(monkeypatch):
    """Simulates one group's dependency being absent and checks the rest of
    the registry still builds — the actual failure mode hit live on Termux."""
    import sys

    import tools.registry_builder as registry_builder_module
    from core.memory import Memory
    from core.store import Store

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "plotly.graph_objects" or name == "plotly":
            raise ImportError("No module named 'plotly'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # An earlier test may have already imported tools.chart_tool (and plotly),
    # in which case Python would just return the cached module without ever
    # calling fake_import — force a fresh import so the simulated ImportError
    # actually takes effect.
    for module_name in list(sys.modules):
        if module_name == "tools.chart_tool" or module_name.startswith("plotly"):
            monkeypatch.delitem(sys.modules, module_name)

    memory = Memory(db_path=":memory:")
    store = Store(db_path=":memory:")
    registry = registry_builder_module.build_registry(memory, store)

    # The rest of the registry (dozens of unrelated tools) is still there.
    assert registry.get("get_weather") is not None
    assert registry.get("calculate") is not None
    assert registry.get("add_todo") is not None
    # Only the plotly-dependent tool is gone.
    assert registry.get("generate_chart") is None
