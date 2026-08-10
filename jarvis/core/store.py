"""Structured personal data: to-dos, notes, a shopping list, and
reminders/timers. Kept separate from core/memory.py (conversation history +
free-form facts) because these have real shape — due dates, done/undone
state — that's worth querying and rendering directly instead of just
recalling as text.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from core.config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS shopping_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at REAL NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(delivered, due_at);
"""


@dataclass
class Todo:
    id: int
    text: str
    done: bool


@dataclass
class Note:
    id: int
    text: str
    created_at: float


@dataclass
class Reminder:
    id: int
    text: str
    due_at: float
    delivered: bool


class Store:
    def __init__(self, db_path: str | None = None):
        path = db_path or config.db_path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- todos ---

    def add_todo(self, text: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO todos (text, done, created_at) VALUES (?, 0, ?)", (text, time.time())
        )
        self._conn.commit()
        return cur.lastrowid

    def list_todos(self, include_done: bool = False) -> list[Todo]:
        query = "SELECT id, text, done FROM todos"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY id"
        rows = self._conn.execute(query).fetchall()
        return [Todo(id=r[0], text=r[1], done=bool(r[2])) for r in rows]

    def complete_todo(self, todo_id: int) -> bool:
        cur = self._conn.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # --- notes ---

    def add_note(self, text: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO notes (text, created_at) VALUES (?, ?)", (text, time.time())
        )
        self._conn.commit()
        return cur.lastrowid

    def list_notes(self, query: str | None = None) -> list[Note]:
        if query:
            rows = self._conn.execute(
                "SELECT id, text, created_at FROM notes WHERE text LIKE ? ORDER BY id DESC",
                (f"%{query}%",),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, text, created_at FROM notes ORDER BY id DESC"
            ).fetchall()
        return [Note(id=r[0], text=r[1], created_at=r[2]) for r in rows]

    # --- shopping list ---

    def add_shopping_item(self, text: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO shopping_items (text, created_at) VALUES (?, ?)", (text, time.time())
        )
        self._conn.commit()
        return cur.lastrowid

    def list_shopping_items(self) -> list[str]:
        rows = self._conn.execute("SELECT text FROM shopping_items ORDER BY id").fetchall()
        return [r[0] for r in rows]

    def clear_shopping_list(self) -> None:
        self._conn.execute("DELETE FROM shopping_items")
        self._conn.commit()

    # --- reminders / timers ---

    def add_reminder(self, text: str, due_at: float) -> int:
        cur = self._conn.execute(
            "INSERT INTO reminders (text, due_at, delivered, created_at) VALUES (?, ?, 0, ?)",
            (text, due_at, time.time()),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_pending_reminders(self) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT id, text, due_at, delivered FROM reminders WHERE delivered = 0 ORDER BY due_at"
        ).fetchall()
        return [Reminder(id=r[0], text=r[1], due_at=r[2], delivered=bool(r[3])) for r in rows]

    def due_reminders(self, now: float | None = None) -> list[Reminder]:
        now = now if now is not None else time.time()
        rows = self._conn.execute(
            "SELECT id, text, due_at, delivered FROM reminders WHERE delivered = 0 AND due_at <= ? "
            "ORDER BY due_at",
            (now,),
        ).fetchall()
        return [Reminder(id=r[0], text=r[1], due_at=r[2], delivered=bool(r[3])) for r in rows]

    def mark_reminder_delivered(self, reminder_id: int) -> None:
        self._conn.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (reminder_id,))
        self._conn.commit()

    def cancel_reminder(self, reminder_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self._conn.commit()
        return cur.rowcount > 0
