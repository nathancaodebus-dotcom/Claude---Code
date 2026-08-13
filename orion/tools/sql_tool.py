"""Query a local database in natural language — Claude writes the SQL
itself (no separate text-to-SQL model needed), this tool just executes it
against a configured connection. Defaults to read-only: write statements are
rejected unless explicitly allowed, since a misheard voice command
shouldn't be able to silently modify a database.
"""
from __future__ import annotations

import queue
import threading

from sqlalchemy import create_engine, text

from core.config import config
from tools.base import Tool

_WRITE_KEYWORDS = ("insert", "update", "delete", "drop", "alter", "create", "truncate")
DEFAULT_TIMEOUT_S = 30


class RunSqlQueryTool(Tool):
    name = "run_sql_query"
    description = (
        "Run a SQL query against the user's configured database (SQL_CONNECTION_STRING) and "
        "return the results. Read-only by default (SELECT/WITH/EXPLAIN/PRAGMA only) — pass "
        "allow_write=true explicitly for INSERT/UPDATE/DELETE/DDL, and only do so when the user "
        "clearly asked for a change, not just a lookup."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "allow_write": {"type": "boolean", "description": "Default false."},
            "max_rows": {"type": "integer", "description": "Default 50."},
            "timeout_seconds": {"type": "integer", "description": f"Default {DEFAULT_TIMEOUT_S}."},
        },
        "required": ["query"],
    }

    def run(
        self,
        query: str,
        allow_write: bool = False,
        max_rows: int = 50,
        timeout_seconds: int = DEFAULT_TIMEOUT_S,
    ) -> str:
        if not config.sql_connection_string:
            return "No database configured. Set SQL_CONNECTION_STRING in .env."

        stripped = query.strip().lower()
        if not allow_write and any(stripped.startswith(kw) for kw in _WRITE_KEYWORDS):
            return "This looks like a write query. Pass allow_write=true if that's really intended."

        # An unbounded query (a missing WHERE/LIMIT, an accidental cross
        # join) can take arbitrarily long server-side even though only
        # max_rows ever come back to the model — fetchmany() already avoids
        # pulling more than that into memory, but nothing previously stopped
        # the tool call itself from hanging until the query finished.
        # Running it on a daemon thread and giving up after timeout_seconds
        # bounds how long *this call* waits; there's no portable,
        # dialect-safe way to actually cancel an in-flight query from
        # another thread, so the query may keep running against the
        # database until it finishes on its own or the connection drops —
        # but Orion itself is no longer stuck waiting on it.
        result_queue: queue.Queue[str] = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                result_queue.put(self._execute(query, max_rows))
            except Exception as exc:  # noqa: BLE001 - surfaced to the model as the query's result
                result_queue.put(f"Error running query: {exc}")

        threading.Thread(target=worker, daemon=True).start()
        try:
            return result_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            return (
                f"Query timed out after {timeout_seconds}s without returning. Try a narrower "
                "query (add a WHERE/LIMIT clause) or a higher timeout_seconds."
            )

    def _execute(self, query: str, max_rows: int) -> str:
        engine = create_engine(config.sql_connection_string)
        with engine.connect() as conn:
            result = conn.execute(text(query))
            if not result.returns_rows:
                conn.commit()
                return f"Query executed. Rows affected: {result.rowcount}."

            columns = list(result.keys())
            rows = result.fetchmany(max_rows)

        if not rows:
            return "Query returned no rows."

        lines = [" | ".join(columns)]
        for row in rows:
            lines.append(" | ".join(str(v) for v in row))
        return "\n".join(lines)
