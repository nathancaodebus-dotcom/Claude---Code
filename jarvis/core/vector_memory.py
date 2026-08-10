"""Local semantic memory: a minimal RAG layer over everything Jarvis has
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

        query_vec = self._embed(query)
        scored = []
        for text, source, blob in rows:
            vec = np.frombuffer(blob, dtype=np.float32)
            score = float(np.dot(query_vec, vec))  # both normalized -> dot product == cosine similarity
            scored.append(MemoryMatch(text=text, source=source, score=score))

        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]
