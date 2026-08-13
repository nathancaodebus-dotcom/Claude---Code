"""VectorMemory itself needs sentence-transformers (a heavy, optional
dependency — see requirements-memory.txt), but its actual scoring logic,
_top_k_matches, is pure numpy over plain rows and needs neither that model
nor a database, so it's tested directly here."""
from __future__ import annotations

import sys
import types

import numpy as np

from core.vector_memory import MemoryMatch, _top_k_matches


def _row(text: str, vec: list[float]) -> tuple[str, str, bytes]:
    return (text, "test", np.array(vec, dtype=np.float32).tobytes())


def test_uses_wal_journal_mode_for_safer_concurrent_access(tmp_path, monkeypatch):
    """VectorMemory shares its db file with Memory/Store — see their tests
    of the same name for why this matters. sentence-transformers is a heavy
    optional dependency not needed to check this, so it's faked."""

    class _FakeSentenceTransformer:
        def __init__(self, model_name):
            pass

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    from core.vector_memory import VectorMemory

    memory = VectorMemory(db_path=str(tmp_path / "test.db"))

    mode = memory._conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


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


def _make_vector_memory(tmp_path, monkeypatch, vectors: dict[str, list[float]]):
    """A fake SentenceTransformer whose encode() is a deterministic lookup
    rather than a real model — same trick as the WAL-mode test above, just
    parameterized so callers can control which text maps to which vector."""

    class _FakeSentenceTransformer:
        def __init__(self, model_name):
            pass

        def encode(self, text, normalize_embeddings=True):
            return np.array(vectors[text], dtype=np.float32)

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    from core.vector_memory import VectorMemory

    return VectorMemory(db_path=str(tmp_path / "test.db"))


def test_search_result_survives_rows_being_wiped_from_sqlite_after_caching(tmp_path, monkeypatch):
    """search() used to re-fetch every row from SQLite on every single call.
    It's now cached in memory after the first call — proven here in a
    black-box way rather than by mocking execute() (sqlite3.Connection's
    attributes are read-only, so it can't be monkeypatched directly): index
    a row, search once so the cache populates, then delete the row straight
    out of the underlying table. If search() were still re-querying, the
    next call would see zero rows and return []; since it now serves the
    cache instead, it should still find the row that's no longer in the DB."""
    vectors = {"hello": [1.0, 0.0], "query": [1.0, 0.0]}
    memory = _make_vector_memory(tmp_path, monkeypatch, vectors)
    memory.index("hello", source="test")

    first = memory.search("query")
    assert [m.text for m in first] == ["hello"]

    memory._conn.execute("DELETE FROM memory_embeddings")
    memory._conn.commit()

    second = memory.search("query")
    assert [m.text for m in second] == ["hello"]


def test_index_after_a_search_is_found_without_hitting_sqlite_again(tmp_path, monkeypatch):
    """index() appends straight to the in-memory cache rather than
    invalidating it — a newly indexed row should be searchable immediately,
    even with the underlying table wiped out from under it (same
    bypass-the-DB trick as the test above)."""
    vectors = {"first": [1.0, 0.0], "second": [0.0, 1.0], "query": [0.0, 1.0]}
    memory = _make_vector_memory(tmp_path, monkeypatch, vectors)
    memory.index("first", source="test")

    memory.search("query")  # populates the cache with just "first"
    memory.index("second", source="test")  # should append in-memory too

    memory._conn.execute("DELETE FROM memory_embeddings")
    memory._conn.commit()

    results = memory.search("query", top_k=1)
    assert results[0].text == "second"
