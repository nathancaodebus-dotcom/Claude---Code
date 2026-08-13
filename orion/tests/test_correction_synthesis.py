from core.correction_synthesis import KEEP_RECENT, SYNTHESIZE_THRESHOLD, CorrectionSynthesizer
from core.memory import Memory


def _fill_corrections(memory: Memory, count: int) -> None:
    for i in range(count):
        memory.log_correction("tool_usage", f"mistake {i}", f"correction {i}")


def test_no_synthesis_below_threshold(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    _fill_corrections(memory, SYNTHESIZE_THRESHOLD)

    calls = []
    synthesizer = CorrectionSynthesizer(memory, summarize=lambda prev, new: calls.append(new) or "digest")
    synthesizer.maybe_synthesize()

    assert calls == []
    assert memory.get_corrections_digest() == ""


def test_synthesizes_overflow_and_keeps_recent_window(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    total = SYNTHESIZE_THRESHOLD + 10
    _fill_corrections(memory, total)

    captured = {}

    def fake_summarize(previous, new_corrections):
        captured["previous"] = previous
        captured["new_corrections"] = new_corrections
        return "concise lessons"

    synthesizer = CorrectionSynthesizer(memory, summarize=fake_summarize)
    synthesizer.maybe_synthesize()

    assert memory.get_corrections_digest() == "concise lessons"
    assert captured["previous"] == ""
    assert len(captured["new_corrections"]) == total - KEEP_RECENT

    marker = memory.get_corrections_consolidated_through()
    remaining = memory.corrections_after(marker)
    assert len(remaining) == KEEP_RECENT


def test_synthesis_is_idempotent_until_more_overflow_accumulates(tmp_path):
    memory = Memory(db_path=str(tmp_path / "test.db"))
    _fill_corrections(memory, SYNTHESIZE_THRESHOLD + 5)

    calls = {"count": 0}

    def counting_summarize(previous, new_corrections):
        calls["count"] += 1
        return f"digest v{calls['count']}"

    synthesizer = CorrectionSynthesizer(memory, summarize=counting_summarize)
    synthesizer.maybe_synthesize()
    synthesizer.maybe_synthesize()  # no new overflow yet — should not re-synthesize

    assert calls["count"] == 1

    _fill_corrections(memory, SYNTHESIZE_THRESHOLD)  # push it over the threshold again
    synthesizer.maybe_synthesize()

    assert calls["count"] == 2
    assert memory.get_corrections_digest() == "digest v2"
