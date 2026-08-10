"""Query a local database in natural language — Claude writes the SQL
itself (no separate text-to-SQL model needed), this tool just executes it
against a configured connection. Defaults to read-only: write statements are
rejected unless explicitly allowed, since a misheard voice command
shouldn't be able to silently modify a database.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text

from core.config import config
from tools.base import Tool

_WRITE_KEYWORDS = ("insert", "update", "delete", "drop", "alter", "create", "truncate")


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
        },
        "required": ["query"],
    }

    def run(self, query: str, allow_write: bool = False, max_rows: int = 50) -> str:
        if not config.sql_connection_string:
            return "No database configured. Set SQL_CONNECTION_STRING in .env."

        stripped = query.strip().lower()
        if not allow_write and any(stripped.startswith(kw) for kw in _WRITE_KEYWORDS):
            return "This looks like a write query. Pass allow_write=true if that's really intended."

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
