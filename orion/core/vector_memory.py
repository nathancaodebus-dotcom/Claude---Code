"""Local semantic memory: a minimal RAG layer over everything Orion has
been told, so it can recall something said months ago even if the wording
was completely different from how it's asked about later.

Uses a small local sentence-transformer model (no API, no key, runs fine on
a Pi) to embed text, and a flat numpy cosine-similarity search — no vector
DB needed at this scale (a personal assistant's memory is thousands of
entries at most, not millions). Optional: only active if
sentence-transformers is installed (requirements-memory.txt).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at REAL NOT NULL
);
"""

_MODEL_NAME = "all-MiniLM-L6-v2"


@dataclass
class MemoryMatch:
    text: str
    source: str
    score: float


def _top_k_matches(
    query_vec: np.ndarray, rows: list[tuple[str, str, bytes]], top_k: int
) -> list[MemoryMatch]:
    """Scores every row against query_vec in one vectorized matrix multiply
    instead of a per-row Python loop, and uses a partial (O(n)) top-k
    selection instead of a full sort — still a flat in-memory scan (no
    vector DB / ANN index), which stays fast enough at the thousands-of-
    entries scale a personal assistant's memory actually reaches, just
    without leaving obvious performance on the table for something this
    cheap to fix."""
    if not rows:
        return []

    embeddings = np.stack([np.frombuffer(blob, dtype=np.float32) for _, _, blob in rows])
    scores = embeddings @ query_vec.astype(np.float32)  # both normalized -> dot product == cosine similarity

    top_k = min(top_k, len(rows))
    top_indices = np.argpartition(-scores, top_k - 1)[:top_k]
    top_indices = top_indices[np.argsort(-scores[top_indices])]

    return [
        MemoryMatch(text=rows[i][0], source=rows[i][1], score=float(scores[i]))
        for i in top_indices
    ]


class VectorMemory:
    def __init__(self, db_path: str | None = None):
        from sentence_transformers import SentenceTransformer

        path = db_path or config.db_path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        # See core/memory.py's __init__ for why: this file is shared across
        # several SQLite connections used from several threads at once.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._model = SentenceTransformer(_MODEL_NAME)
        # search() used to re-fetch every row from SQLite and re-decode each
        # embedding's raw bytes back into an array on every single call, even
        # for two searches back to back with nothing indexed in between —
        # all of that work is redone from scratch, unnecessarily, every time.
        # Cached in memory instead (this class already assumes one connection
        # per process, same as core/memory.py/core/store.py), populated
        # lazily on first use and kept in sync by appending in index()
        # rather than re-querying.
        self._rows_cache: list[tuple[str, str, bytes]] | None = None

    def _embed(self, text: str) -> np.ndarray:
        return self._model.encode(text, normalize_embeddings=True)

    def index(self, text: str, source: str) -> None:
        embedding = self._embed(text)
        blob = embedding.astype(np.float32).tobytes()
        self._conn.execute(
            "INSERT INTO memory_embeddings (text, source, embedding, created_at) VALUES (?, ?, ?, ?)",
            (text, source, blob, time.time()),
        )
        self._conn.commit()
        if self._rows_cache is not None:
            self._rows_cache.append((text, source, blob))

    def search(self, query: str, top_k: int = 5) -> list[MemoryMatch]:
        if self._rows_cache is None:
            self._rows_cache = self._conn.execute(
                "SELECT text, source, embedding FROM memory_embeddings"
            ).fetchall()
        if not self._rows_cache:
            return []
        return _top_k_matches(self._embed(query), self._rows_cache, top_k)
