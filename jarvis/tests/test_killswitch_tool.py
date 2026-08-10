import pytest

from tools.killswitch_tool import EmergencyWipeTool


@pytest.fixture(autouse=True)
def kill_switch(tmp_path, monkeypatch):
    from core.config import config

    monkeypatch.chdir(tmp_path)
    object.__setattr__(config, "kill_switch_phrase", "burn it down")
    object.__setattr__(config, "db_path", str(tmp_path / "jarvis.db"))
    yield
    object.__setattr__(config, "kill_switch_phrase", None)


def test_wrong_phrase_does_not_wipe():
    result = EmergencyWipeTool().run(confirmation_phrase="wrong phrase")
    assert "does not match" in result


def test_not_configured_returns_message():
    from core.config import config

    object.__setattr__(config, "kill_switch_phrase", None)
    result = EmergencyWipeTool().run(confirmation_phrase="anything")
    assert "not configured" in result


def test_correct_phrase_wipes_memory_and_store():
    from core.config import config
    from core.memory import Memory
    from core.store import Store

    memory = Memory()
    memory.append("s1", "user", "hello")
    memory.remember_fact("k", "v")

    store = Store()
    store.add_todo("buy milk")

    result = EmergencyWipeTool().run(confirmation_phrase="burn it down")
    assert "Wiped" in result

    assert Memory().history("s1") == []
    assert Memory().all_facts() == {}
    assert Store().list_todos() == []
