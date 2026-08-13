import sqlite3
import time

import pytest

from tools.sql_tool import RunSqlQueryTool


@pytest.fixture
def db(tmp_path):
    from core.config import config

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')")
    conn.commit()
    conn.close()

    object.__setattr__(config, "sql_connection_string", f"sqlite:///{db_path}")
    yield db_path
    object.__setattr__(config, "sql_connection_string", None)


def test_select_query(db):
    result = RunSqlQueryTool().run(query="SELECT * FROM users ORDER BY id")
    assert "Alice" in result
    assert "Bob" in result


def test_write_query_rejected_by_default(db):
    result = RunSqlQueryTool().run(query="DELETE FROM users")
    assert "allow_write" in result


def test_write_query_allowed_explicitly(db):
    result = RunSqlQueryTool().run(query="DELETE FROM users WHERE id = 1", allow_write=True)
    assert "Rows affected" in result

    remaining = RunSqlQueryTool().run(query="SELECT * FROM users")
    assert "Alice" not in remaining
    assert "Bob" in remaining


def test_no_connection_configured():
    from core.config import config

    object.__setattr__(config, "sql_connection_string", None)
    result = RunSqlQueryTool().run(query="SELECT 1")
    assert "No database configured" in result


def test_empty_result(db):
    result = RunSqlQueryTool().run(query="SELECT * FROM users WHERE id = 999")
    assert "no rows" in result


def test_query_timeout_returns_promptly_instead_of_waiting_for_a_hung_query(db, monkeypatch):
    """A missing WHERE/LIMIT (or a genuinely stuck connection) used to be
    able to hang this tool call indefinitely — _execute now runs on a
    daemon thread with a timeout, so a slow query fails fast instead of
    freezing the turn. Faked here rather than actually blocking a real
    query for the test's own sake; the tool call should return well before
    the fake query's full (2s) duration, not after it."""

    def slow_execute(self, query, max_rows):
        time.sleep(2)
        return "should never be returned"

    monkeypatch.setattr(RunSqlQueryTool, "_execute", slow_execute)

    start = time.monotonic()
    result = RunSqlQueryTool().run(query="SELECT * FROM users", timeout_seconds=1)
    elapsed = time.monotonic() - start

    assert "timed out" in result.lower()
    assert elapsed < 1.5, f"took {elapsed:.2f}s — doesn't look like it actually timed out early"
