import sqlite3

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
