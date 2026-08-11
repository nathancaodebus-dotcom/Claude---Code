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
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._model = SentenceTransformer(_MODEL_NAME)

    def _embed(self, text: str) -> np.ndarray:
        return self._model.encode(text, normalize_embeddings=True)

    def index(self, text: str, source: str) -> None:
        embedding = self._embed(text)
        self._conn.execute(
            "INSERT INTO memory_embeddings (text, source, embedding, created_at) VALUES (?, ?, ?, ?)",
            (text, source, embedding.astype(np.float32).tobytes(), time.time()),
        )
        self._conn.commit()

    def search(self, query: str, top_k: int = 5) -> list[MemoryMatch]:
        rows = self._conn.execute("SELECT text, source, embedding FROM memory_embeddings").fetchall()
        if not rows:
            return []
        return _top_k_matches(self._embed(query), rows, top_k)
