"""Regression test for a real bug: tools/system_tool.py used to `import
psutil` unconditionally at module level. psutil hard-refuses to install on
Android/Termux ('platform android is not supported'), which meant that
importing this module — and therefore registry_builder.py, which imports
names from it unconditionally — crashed the entire tool registry, not just
the psutil-dependent tools. Simulates that environment by faking psutil's
absence rather than actually uninstalling it."""
import builtins
import importlib

import pytest


@pytest.fixture
def system_tool_without_psutil(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("No module named 'psutil'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    import tools.system_tool as system_tool_module

    module = importlib.reload(system_tool_module)
    yield module
    importlib.reload(module)  # restore the real psutil-backed module for other tests


def test_module_imports_without_psutil(system_tool_without_psutil):
    assert system_tool_without_psutil.psutil is None


def test_system_status_degrades_gracefully(system_tool_without_psutil):
    result = system_tool_without_psutil.SystemStatusTool().run()
    assert "psutil is not installed" in result


def test_list_processes_degrades_gracefully(system_tool_without_psutil):
    result = system_tool_without_psutil.ListProcessesTool().run()
    assert "psutil is not installed" in result


def test_set_process_priority_degrades_gracefully(system_tool_without_psutil):
    result = system_tool_without_psutil.SetProcessPriorityTool().run(pid=1, nice_level=5)
    assert "psutil is not installed" in result


def test_list_failed_commands_unaffected_by_missing_psutil(system_tool_without_psutil, tmp_path):
    from core.store import Store

    store = Store(db_path=str(tmp_path / "test.db"))
    result = system_tool_without_psutil.ListFailedCommandsTool(store).run()
    assert "No failed commands logged." == result


def test_registry_builder_imports_cleanly_without_psutil(system_tool_without_psutil):
    import importlib

    import tools.registry_builder as registry_builder_module

    importlib.reload(registry_builder_module)  # must not raise ImportError
