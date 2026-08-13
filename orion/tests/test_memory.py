from core.memory import Memory


def test_uses_wal_journal_mode_for_safer_concurrent_access(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))

    mode = memory._conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


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


def test_log_correction_and_recent_corrections_roundtrip(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    memory.log_correction("tone", "was too formal", "use a casual tone", context="chat reply")

    corrections = memory.recent_corrections()
    assert len(corrections) == 1
    assert corrections[0].category == "tone"
    assert corrections[0].mistake == "was too formal"
    assert corrections[0].correction == "use a casual tone"
    assert corrections[0].context == "chat reply"


def test_corrections_as_prompt_block_empty_when_none_logged(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    assert memory.corrections_as_prompt_block() == ""


def test_corrections_as_prompt_block_includes_recent_raw_corrections(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    memory.log_correction("tool_usage", "used the wrong calendar", "use the work calendar for meetings")

    block = memory.corrections_as_prompt_block()
    assert "used the wrong calendar" in block
    assert "use the work calendar for meetings" in block


def test_corrections_as_prompt_block_includes_digest_and_only_unfolded_recent(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    first_id = memory.log_correction("tone", "too formal", "be casual")
    memory.log_correction("tone", "still formal", "really, be casual")
    memory.set_corrections_digest("Always use a casual tone.", consolidated_through_id=first_id)

    block = memory.corrections_as_prompt_block()
    assert "Always use a casual tone." in block
    assert "still formal" in block
    # The first correction was folded into the digest, so it shouldn't also
    # still appear in the raw "recent" tail.
    recent_section = block.split("Recent corrections")[-1]
    assert "too formal" not in recent_section
