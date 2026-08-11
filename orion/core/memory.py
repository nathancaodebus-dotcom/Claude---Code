"""Persistent memory: conversation history, long-term facts about the user,
and rolling per-session summaries of conversation that's aged out of the
active context window (see core/consolidation.py) — so older exchanges get
assimilated into a durable digest instead of just disappearing.

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

CREATE TABLE IF NOT EXISTS conversation_summaries (
    session_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    consolidated_through_id INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);
"""


@dataclass
class Message:
    role: str
    content: str
    id: int = 0


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
            "SELECT id, role, content FROM messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [Message(id=i, role=r, content=c) for i, r, c in reversed(rows)]

    def clear(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._conn.commit()

    def message_count(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0]

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

    # --- conversation consolidation (older history assimilated into a summary) ---

    def messages_after(self, session_id: str, after_id: int) -> list[Message]:
        rows = self._conn.execute(
            "SELECT id, role, content FROM messages WHERE session_id = ? AND id > ? ORDER BY id",
            (session_id, after_id),
        ).fetchall()
        return [Message(id=i, role=r, content=c) for i, r, c in rows]

    def get_summary(self, session_id: str) -> str:
        row = self._conn.execute(
            "SELECT summary FROM conversation_summaries WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else ""

    def get_consolidated_through(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT consolidated_through_id FROM conversation_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else 0

    def set_summary(self, session_id: str, summary: str, consolidated_through_id: int) -> None:
        self._conn.execute(
            "INSERT INTO conversation_summaries (session_id, summary, consolidated_through_id, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
            "summary = excluded.summary, consolidated_through_id = excluded.consolidated_through_id, "
            "updated_at = excluded.updated_at",
            (session_id, summary, consolidated_through_id, time.time()),
        )
        self._conn.commit()

    def summary_as_prompt_block(self, session_id: str) -> str:
        summary = self.get_summary(session_id)
        if not summary:
            return ""
        return f"Summary of earlier conversation in this session (older messages have scrolled out of context):\n{summary}"
