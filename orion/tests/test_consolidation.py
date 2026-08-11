from core.consolidation import CONSOLIDATE_THRESHOLD, KEEP_RECENT, Consolidator
from core.memory import Memory


def _fill_history(memory: Memory, session_id: str, count: int) -> None:
    for i in range(count):
        memory.append(session_id, "user" if i % 2 == 0 else "assistant", f"message {i}")


def test_no_consolidation_below_threshold(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    _fill_history(memory, "s1", CONSOLIDATE_THRESHOLD)

    calls = []
    consolidator = Consolidator(memory, summarize=lambda prev, new: calls.append(new) or "summary")
    consolidator.maybe_consolidate("s1")

    assert calls == []
    assert memory.get_summary("s1") == ""


def test_consolidates_overflow_and_keeps_recent_window(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    total = CONSOLIDATE_THRESHOLD + 10
    _fill_history(memory, "s1", total)

    captured = {}

    def fake_summarize(previous, new_messages):
        captured["previous"] = previous
        captured["new_messages"] = new_messages
        return "concise digest"

    consolidator = Consolidator(memory, summarize=fake_summarize)
    consolidator.maybe_consolidate("s1")

    assert memory.get_summary("s1") == "concise digest"
    assert captured["previous"] == ""
    # everything except the most recent KEEP_RECENT messages got summarized
    assert len(captured["new_messages"]) == total - KEEP_RECENT

    marker = memory.get_consolidated_through("s1")
    remaining = memory.messages_after("s1", marker)
    assert len(remaining) == KEEP_RECENT


def test_consolidation_is_idempotent_until_more_overflow_accumulates(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    _fill_history(memory, "s1", CONSOLIDATE_THRESHOLD + 5)

    calls = {"count": 0}

    def counting_summarize(previous, new_messages):
        calls["count"] += 1
        return f"digest v{calls['count']}"

    consolidator = Consolidator(memory, summarize=counting_summarize)
    consolidator.maybe_consolidate("s1")
    consolidator.maybe_consolidate("s1")  # no new overflow yet — should not re-summarize

    assert calls["count"] == 1

    _fill_history(memory, "s1", CONSOLIDATE_THRESHOLD)  # push it over the threshold again
    consolidator.maybe_consolidate("s1")

    assert calls["count"] == 2
    assert memory.get_summary("s1") == "digest v2"


def test_summary_as_prompt_block_empty_when_no_summary(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    assert memory.summary_as_prompt_block("s1") == ""


def test_summary_as_prompt_block_includes_summary(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    memory.set_summary("s1", "user is planning a trip to Japan", consolidated_through_id=5)
    assert "user is planning a trip to Japan" in memory.summary_as_prompt_block("s1")
