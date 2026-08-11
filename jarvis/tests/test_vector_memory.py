"""VectorMemory itself needs sentence-transformers (a heavy, optional
dependency — see requirements-memory.txt), but its actual scoring logic,
_top_k_matches, is pure numpy over plain rows and needs neither that model
nor a database, so it's tested directly here."""
from __future__ import annotations

import numpy as np

from core.vector_memory import MemoryMatch, _top_k_matches


def _row(text: str, vec: list[float]) -> tuple[str, str, bytes]:
    return (text, "test", np.array(vec, dtype=np.float32).tobytes())


def test_returns_empty_list_for_no_rows():
    assert _top_k_matches(np.array([1.0, 0.0], dtype=np.float32), [], top_k=5) == []


def test_ranks_by_cosine_similarity_descending():
    rows = [
        _row("orthogonal", [0.0, 1.0]),
        _row("exact match", [1.0, 0.0]),
        _row("opposite", [-1.0, 0.0]),
    ]
    query = np.array([1.0, 0.0], dtype=np.float32)

    results = _top_k_matches(query, rows, top_k=3)

    assert [m.text for m in results] == ["exact match", "orthogonal", "opposite"]
    assert results[0].score > results[1].score > results[2].score


def test_respects_top_k():
    rows = [_row(f"item{i}", [1.0, float(i)]) for i in range(10)]
    query = np.array([1.0, 0.0], dtype=np.float32)

    results = _top_k_matches(query, rows, top_k=3)

    assert len(results) == 3


def test_top_k_larger_than_row_count_returns_all_rows():
    rows = [_row("only one", [1.0, 0.0])]
    query = np.array([1.0, 0.0], dtype=np.float32)

    results = _top_k_matches(query, rows, top_k=5)

    assert len(results) == 1


def test_preserves_source_field():
    rows = [("text", "obsidian_note", np.array([1.0, 0.0], dtype=np.float32).tobytes())]
    query = np.array([1.0, 0.0], dtype=np.float32)

    results = _top_k_matches(query, rows, top_k=1)

    assert results == [MemoryMatch(text="text", source="obsidian_note", score=1.0)]
