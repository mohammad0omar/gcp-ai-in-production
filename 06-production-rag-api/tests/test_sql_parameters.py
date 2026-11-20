"""Run the real query code with a fake cursor: SQL text stays constant, values travel as parameters."""

from unittest.mock import MagicMock

import pytest
from rag import bootstrap, search

EVIL = "x'; DROP TABLE chunks; --"


@pytest.fixture
def cursor(monkeypatch):
    cur = MagicMock()
    cur.fetchall.return_value = [("fire-code-7", "text", 0.1)]
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(search, "connect", lambda: conn)
    return cur


def test_search_keeps_user_values_out_of_the_sql_text(cursor):
    search.search_chunks([0.1, 0.2], 5, EVIL)
    for call in cursor.execute.call_args_list:
        assert EVIL not in call.args[0]
    query, params = cursor.execute.call_args_list[1].args
    assert query is search.SEARCH_SQL
    assert params == ("[0.1,0.2]", EVIL, EVIL, "[0.1,0.2]", 5)


def test_search_sets_a_statement_timeout(cursor):
    search.search_chunks([0.1], 5)
    sql, params = cursor.execute.call_args_list[0].args
    assert "statement_timeout" in sql
    assert params == ("5000",)


def test_grant_sql_text_is_exact_and_valid_for_the_driver():
    from pg8000.dbapi import convert_paramstyle

    assert bootstrap.GRANT_API_SQL == (
        "SELECT 'GRANT SELECT ON chunks TO ' || quote_ident(CAST(%s AS text))"
    )
    # The driver turns %s into $1 and must leave nothing else behind (no stray % tokens).
    sent, _ = convert_paramstyle("format", bootstrap.GRANT_API_SQL, ("rag-api@p.iam",))
    assert sent == "SELECT 'GRANT SELECT ON chunks TO ' || quote_ident(CAST($1 AS text))"
    sent, _ = convert_paramstyle("format", bootstrap.GRANT_INGEST_SQL, ("x",))
    assert "%" not in sent


def test_grant_passes_the_role_as_a_parameter():
    cur = MagicMock()
    cur.fetchone.return_value = ('GRANT SELECT ON chunks TO "rag-api@p.iam"',)
    bootstrap.grant(cur, bootstrap.GRANT_API_SQL, EVIL)
    assert cur.execute.call_args_list[0].args == (bootstrap.GRANT_API_SQL, (EVIL,))
    assert cur.execute.call_args_list[1].args == ('GRANT SELECT ON chunks TO "rag-api@p.iam"',)
    assert EVIL not in bootstrap.GRANT_API_SQL


def test_api_user_only_gets_select():
    assert "INSERT" not in bootstrap.GRANT_API_SQL and "DELETE" not in bootstrap.GRANT_API_SQL
    assert "INSERT" in bootstrap.GRANT_INGEST_SQL


def test_bootstrap_applies_each_schema_statement(tmp_path):
    schema = tmp_path / "s.sql"
    schema.write_text("CREATE EXTENSION IF NOT EXISTS vector;\nCREATE TABLE IF NOT EXISTS t (a int);\n")
    cur = MagicMock()
    bootstrap.apply_schema(cur, schema)
    assert cur.execute.call_count == 2
