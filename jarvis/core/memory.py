"""Persistent memory: conversation history + long-term facts about the user.

Backed by SQLite so it survives restarts and works identically on a
Raspberry Pi or a phone-adjacent server with zero extra setup.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from core.config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS facts (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


@dataclass
class Message:
    role: str
    content: str


class Memory:
    """One SQLite connection per process; safe for the single-user, single-process use case."""

    def __init__(self, db_path: str | None = None):
        path = db_path or config.db_path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def append(self, session_id: str, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )
        self._conn.commit()

    def history(self, session_id: str, limit: int = 40) -> list[Message]:
        rows = self._conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [Message(role=r, content=c) for r, c in reversed(rows)]

    def clear(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._conn.commit()

    def remember_fact(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO facts (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, time.time()),
        )
        self._conn.commit()

    def all_facts(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM facts").fetchall()
        return dict(rows)

    def facts_as_prompt_block(self) -> str:
        facts = self.all_facts()
        if not facts:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in facts.items())
        return f"Things you know about the user:\n{lines}"

    def facts_json(self) -> str:
        return json.dumps(self.all_facts(), ensure_ascii=False, indent=2)
