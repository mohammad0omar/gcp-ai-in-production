from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp
from sqlglot.executor import execute

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def read(name):
    return (SQL_DIR / name).read_text()


def test_sql_files_parse():
    files = sorted(SQL_DIR.glob("*.sql"))
    assert len(files) == 6
    for path in files:
        parsed = sqlglot.parse(path.read_text(), dialect="bigquery")
        assert parsed and all(parsed), path.name


def test_cost_query_shape():
    text = read("02_cost_from_billing.sql")
    assert "gcp_billing_export_resource_v1_" in text
    assert "BILLING_EXPORT_PROJECT" in text and "WORKLOAD_PROJECT" in text
    assert "service.id = 'SERVICE_ID'" in text and "sku.id IN" in text
    assert text.count("LEFT JOIN UNNEST(labels)") == 2  # missing labels stay visible
    assert "'unlabelled'" in text and "UNNEST(credits)" in text
    assert "'feature'" in text and "'customer'" in text


def test_tokens_query_reads_hash_field_and_event():
    text = read("01_tokens_from_logs.sql")
    assert "jsonPayload.customer_id AS customer_hash" in text
    assert "jsonPayload.event = 'ai_usage'" in text


def test_join_keeps_matched_billing_only_and_log_only_rows():
    view = sqlglot.parse_one(
        read("03_cost_per_customer_feature.sql"), dialect="bigquery"
    )
    select = view.expression
    assert isinstance(select, exp.Select)
    # Run the SELECT on fixtures with the python engine; tables swapped to plain names.
    select = select.transform(
        lambda n: (
            exp.to_table("t" if n.name == "tokens_daily" else "c")
            if isinstance(n, exp.Table) and n.name in ("tokens_daily", "cost_daily")
            else n
        )
    )
    tables = {
        "t": [
            {
                "usage_date": "d1",
                "customer_hash": "a",
                "feature": "f",
                "calls": 10,
                "prompt_tokens": 1,
                "output_tokens": 1,
                "cached_tokens": 0,
                "thoughts_tokens": 0,
            },
            {
                "usage_date": "d1",
                "customer_hash": "log_only",
                "feature": "f",
                "calls": 4,
                "prompt_tokens": 1,
                "output_tokens": 1,
                "cached_tokens": 0,
                "thoughts_tokens": 0,
            },
        ],
        "c": [
            {"usage_date": "d1", "customer_hash": "a", "feature": "f", "cost": 2.0},
            {
                "usage_date": "d1",
                "customer_hash": "bill_only",
                "feature": "f",
                "cost": 3.0,
            },
        ],
    }
    sql = select.sql(dialect="bigquery").replace(
        "SAFE_DIVIDE(c.cost, t.calls)", "c.cost / t.calls"
    )
    rows = {r[1]: r for r in execute(sql, tables=tables).rows}
    assert set(rows) == {"a", "log_only", "bill_only"}
    cost = {k: v[8] for k, v in rows.items()}
    assert cost["a"] == 2.0 and cost["bill_only"] == 3.0
    assert cost["log_only"] is None  # not 0: billing has not arrived
    assert rows["a"][9] == pytest.approx(0.2)


def test_discovery_and_reconcile_scoped_to_project_and_service():
    assert "project.id = 'WORKLOAD_PROJECT'" in read("00_discover_skus.sql")
    text = read("05_reconcile.sql")
    assert "cost_missing_from_filter" in text and "service.id = 'SERVICE_ID'" in text


def test_reconcile_is_rolling_and_uses_credits():
    text = read("05_reconcile.sql")
    assert (
        "2027" not in text and "INTERVAL 30 DAY" in text and "UNNEST(credits)" in text
    )


def test_terraform_authorizes_all_four_views():
    tf = (SQL_DIR.parent / "terraform" / "main.tf").read_text()
    for table in (
        "tokens_daily",
        "cost_daily",
        "cost_per_customer_feature",
        "dashboard",
    ):
        assert f'table_id   = "{table}"' in tf
