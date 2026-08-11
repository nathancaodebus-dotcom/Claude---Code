from core.memory import Memory


def test_append_and_history_roundtrip(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    memory.append("s1", "user", "hello")
    memory.append("s1", "assistant", "hi there")

    history = memory.history("s1")
    assert [m.role for m in history] == ["user", "assistant"]
    assert [m.content for m in history] == ["hello", "hi there"]


def test_sessions_are_isolated(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    memory.append("s1", "user", "hello")
    memory.append("s2", "user", "goodbye")

    assert [m.content for m in memory.history("s1")] == ["hello"]
    assert [m.content for m in memory.history("s2")] == ["goodbye"]


def test_facts_roundtrip(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    memory.remember_fact("favorite_color", "blue")
    memory.remember_fact("favorite_color", "green")  # overwrite

    assert memory.all_facts() == {"favorite_color": "green"}
    assert "favorite_color: green" in memory.facts_as_prompt_block()


def test_facts_prompt_block_empty_when_no_facts(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    assert memory.facts_as_prompt_block() == ""
