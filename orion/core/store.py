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

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    text TEXT NOT NULL,
    due_at REAL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS failed_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    error TEXT NOT NULL,
    created_at REAL NOT NULL
);
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


@dataclass
class Document:
    id: int
    kind: str
    name: str
    path: str


@dataclass
class Project:
    id: int
    name: str


@dataclass
class Milestone:
    id: int
    project_id: int
    text: str
    due_at: float | None
    done: bool


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

    # --- documents (generated PowerPoint/Word/Excel files, tracked by name so
    # a later voice command like 'add a slide about X' can find the file again) ---

    def register_document(self, kind: str, name: str, path: str) -> Document | None:
        """Create or overwrite the document record for `name`. Returns the record
        it replaced (if any) so callers can warn when a name collision crosses
        kinds (e.g. a spreadsheet named 'budget' replacing a presentation of the
        same name) — kind and path are always updated together so the row can
        never end up pointing at a path of a different kind than it claims."""
        previous = self.get_document(name)
        now = time.time()
        self._conn.execute(
            "INSERT INTO documents (kind, name, path, created_at, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET kind = excluded.kind, path = excluded.path, "
            "updated_at = excluded.updated_at",
            (kind, name, path, now, now),
        )
        self._conn.commit()
        return previous

    def touch_document(self, name: str) -> None:
        self._conn.execute(
            "UPDATE documents SET updated_at = ? WHERE name = ?", (time.time(), name)
        )
        self._conn.commit()

    def get_document(self, name: str) -> Document | None:
        row = self._conn.execute(
            "SELECT id, kind, name, path FROM documents WHERE name = ?", (name,)
        ).fetchone()
        return Document(id=row[0], kind=row[1], name=row[2], path=row[3]) if row else None

    def list_documents(self, kind: str | None = None) -> list[Document]:
        if kind:
            rows = self._conn.execute(
                "SELECT id, kind, name, path FROM documents WHERE kind = ? ORDER BY updated_at DESC",
                (kind,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, kind, name, path FROM documents ORDER BY updated_at DESC"
            ).fetchall()
        return [Document(id=r[0], kind=r[1], name=r[2], path=r[3]) for r in rows]

    # --- projects / milestones ---

    def create_project(self, name: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO projects (name, created_at) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET name = excluded.name",
            (name, time.time()),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
        return row[0]

    def get_project(self, name: str) -> Project | None:
        row = self._conn.execute("SELECT id, name FROM projects WHERE name = ?", (name,)).fetchone()
        return Project(id=row[0], name=row[1]) if row else None

    def list_projects(self) -> list[Project]:
        rows = self._conn.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
        return [Project(id=r[0], name=r[1]) for r in rows]

    def add_milestone(self, project_id: int, text: str, due_at: float | None) -> int:
        cur = self._conn.execute(
            "INSERT INTO milestones (project_id, text, due_at, done, created_at) VALUES (?, ?, ?, 0, ?)",
            (project_id, text, due_at, time.time()),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_milestones(self, project_id: int, include_done: bool = False) -> list[Milestone]:
        query = "SELECT id, project_id, text, due_at, done FROM milestones WHERE project_id = ?"
        if not include_done:
            query += " AND done = 0"
        query += " ORDER BY due_at IS NULL, due_at"
        rows = self._conn.execute(query, (project_id,)).fetchall()
        return [Milestone(id=r[0], project_id=r[1], text=r[2], due_at=r[3], done=bool(r[4])) for r in rows]

    def upcoming_milestones(self, within_seconds: float) -> list[Milestone]:
        cutoff = time.time() + within_seconds
        rows = self._conn.execute(
            "SELECT id, project_id, text, due_at, done FROM milestones "
            "WHERE done = 0 AND due_at IS NOT NULL AND due_at <= ? ORDER BY due_at",
            (cutoff,),
        ).fetchall()
        return [Milestone(id=r[0], project_id=r[1], text=r[2], due_at=r[3], done=bool(r[4])) for r in rows]

    def complete_milestone(self, milestone_id: int) -> bool:
        cur = self._conn.execute("UPDATE milestones SET done = 1 WHERE id = ?", (milestone_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # --- failed command log ---

    def log_failed_command(self, tool_name: str, error: str) -> None:
        self._conn.execute(
            "INSERT INTO failed_commands (tool_name, error, created_at) VALUES (?, ?, ?)",
            (tool_name, error, time.time()),
        )
        self._conn.commit()

    def recent_failed_commands(self, limit: int = 20) -> list[tuple[str, str, float]]:
        rows = self._conn.execute(
            "SELECT tool_name, error, created_at FROM failed_commands ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return rows
