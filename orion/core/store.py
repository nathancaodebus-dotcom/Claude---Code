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

-- Crypto portfolio tracking. "portfolio" is a free-text label (e.g.
-- 'stable', 'risky') rather than its own table — there's nothing to manage
-- about a portfolio beyond the name it groups holdings/trades under.
-- Orion never updates crypto_holdings directly: every position change goes
-- through a proposal that the user must confirm (see tools/crypto_tools.py)
-- — this is a decision-support and paper-tracking layer, not a connection
-- to a real exchange, so nothing here places a real order on its own.
CREATE TABLE IF NOT EXISTS crypto_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio TEXT NOT NULL,
    coin TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_buy_price_usd REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(portfolio, coin)
);

CREATE TABLE IF NOT EXISTS crypto_trade_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio TEXT NOT NULL,
    action TEXT NOT NULL,
    coin TEXT NOT NULL,
    quantity REAL NOT NULL,
    price_usd REAL NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    resolved_at REAL
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


@dataclass
class CryptoHolding:
    id: int
    portfolio: str
    coin: str
    quantity: float
    avg_buy_price_usd: float


@dataclass
class CryptoTradeProposal:
    id: int
    portfolio: str
    action: str
    coin: str
    quantity: float
    price_usd: float
    reasoning: str
    status: str
    created_at: float


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

    # --- crypto portfolio (paper-tracked; see tools/crypto_tools.py for why
    # every position change goes through a proposal + explicit confirmation
    # rather than being applied directly) ---

    def propose_crypto_trade(
        self, portfolio: str, action: str, coin: str, quantity: float, price_usd: float, reasoning: str
    ) -> int:
        if action not in ("buy", "sell"):
            raise ValueError(f"action must be 'buy' or 'sell', got '{action}'.")
        if quantity <= 0:
            raise ValueError("quantity must be positive.")
        cur = self._conn.execute(
            "INSERT INTO crypto_trade_proposals "
            "(portfolio, action, coin, quantity, price_usd, reasoning, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (portfolio, action, coin.lower(), quantity, price_usd, reasoning, time.time()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_crypto_trade_proposal(self, proposal_id: int) -> CryptoTradeProposal | None:
        row = self._conn.execute(
            "SELECT id, portfolio, action, coin, quantity, price_usd, reasoning, status, created_at "
            "FROM crypto_trade_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            return None
        return CryptoTradeProposal(
            id=row[0], portfolio=row[1], action=row[2], coin=row[3],
            quantity=row[4], price_usd=row[5], reasoning=row[6], status=row[7], created_at=row[8],
        )

    def list_pending_crypto_trades(self, portfolio: str | None = None) -> list[CryptoTradeProposal]:
        query = (
            "SELECT id, portfolio, action, coin, quantity, price_usd, reasoning, status, created_at "
            "FROM crypto_trade_proposals WHERE status = 'pending'"
        )
        params: tuple = ()
        if portfolio:
            query += " AND portfolio = ?"
            params = (portfolio,)
        query += " ORDER BY created_at"
        rows = self._conn.execute(query, params).fetchall()
        return [
            CryptoTradeProposal(
                id=r[0], portfolio=r[1], action=r[2], coin=r[3],
                quantity=r[4], price_usd=r[5], reasoning=r[6], status=r[7], created_at=r[8],
            )
            for r in rows
        ]

    def confirm_crypto_trade(self, proposal_id: int) -> None:
        """Applies a pending proposal to holdings. Raises ValueError (with a
        message meant to be shown as-is) if the proposal doesn't exist, was
        already resolved, or a sell would take a holding negative — this
        method is the only path that ever changes crypto_holdings, so it's
        also the only place that needs to guard against a bad sell."""
        proposal = self.get_crypto_trade_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"No trade proposal with id {proposal_id}.")
        if proposal.status != "pending":
            raise ValueError(f"Trade proposal {proposal_id} was already {proposal.status}.")

        existing = self._conn.execute(
            "SELECT quantity, avg_buy_price_usd FROM crypto_holdings WHERE portfolio = ? AND coin = ?",
            (proposal.portfolio, proposal.coin),
        ).fetchone()

        if proposal.action == "buy":
            if existing is None:
                new_quantity, new_avg_price = proposal.quantity, proposal.price_usd
            else:
                old_quantity, old_avg_price = existing
                new_quantity = old_quantity + proposal.quantity
                new_avg_price = (
                    old_quantity * old_avg_price + proposal.quantity * proposal.price_usd
                ) / new_quantity
            self._conn.execute(
                "INSERT INTO crypto_holdings (portfolio, coin, quantity, avg_buy_price_usd, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(portfolio, coin) DO UPDATE SET "
                "quantity = excluded.quantity, avg_buy_price_usd = excluded.avg_buy_price_usd, "
                "updated_at = excluded.updated_at",
                (proposal.portfolio, proposal.coin, new_quantity, new_avg_price, time.time()),
            )
        else:  # sell
            if existing is None or existing[0] < proposal.quantity:
                held = existing[0] if existing else 0.0
                raise ValueError(
                    f"Can't sell {proposal.quantity} {proposal.coin} from '{proposal.portfolio}' — "
                    f"only {held} held."
                )
            old_quantity, old_avg_price = existing
            new_quantity = old_quantity - proposal.quantity
            if new_quantity == 0:
                self._conn.execute(
                    "DELETE FROM crypto_holdings WHERE portfolio = ? AND coin = ?",
                    (proposal.portfolio, proposal.coin),
                )
            else:
                self._conn.execute(
                    "UPDATE crypto_holdings SET quantity = ?, updated_at = ? "
                    "WHERE portfolio = ? AND coin = ?",
                    (new_quantity, time.time(), proposal.portfolio, proposal.coin),
                )

        self._conn.execute(
            "UPDATE crypto_trade_proposals SET status = 'confirmed', resolved_at = ? WHERE id = ?",
            (time.time(), proposal_id),
        )
        self._conn.commit()

    def reject_crypto_trade(self, proposal_id: int) -> None:
        proposal = self.get_crypto_trade_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"No trade proposal with id {proposal_id}.")
        if proposal.status != "pending":
            raise ValueError(f"Trade proposal {proposal_id} was already {proposal.status}.")
        self._conn.execute(
            "UPDATE crypto_trade_proposals SET status = 'rejected', resolved_at = ? WHERE id = ?",
            (time.time(), proposal_id),
        )
        self._conn.commit()

    def list_crypto_holdings(self, portfolio: str | None = None) -> list[CryptoHolding]:
        query = "SELECT id, portfolio, coin, quantity, avg_buy_price_usd FROM crypto_holdings"
        params: tuple = ()
        if portfolio:
            query += " WHERE portfolio = ?"
            params = (portfolio,)
        query += " ORDER BY portfolio, coin"
        rows = self._conn.execute(query, params).fetchall()
        return [
            CryptoHolding(id=r[0], portfolio=r[1], coin=r[2], quantity=r[3], avg_buy_price_usd=r[4])
            for r in rows
        ]
