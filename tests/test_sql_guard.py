from pathlib import Path

import pytest

from scripts.metrics import QUERY_NAMES, SQL_DIRECTORY
from scripts.sql_guard import MAX_SQL_CHARS, SQLBlocked, validate_sql


@pytest.mark.parametrize("name", QUERY_NAMES)
def test_reviewed_cte_queries_round_trip_and_preserve_parameters(name):
    checked = validate_sql((SQL_DIRECTORY / f"{name}.sql").read_text(encoding="utf-8"))
    assert set(checked.parameters) == {"start_at", "end_at"} | ({"top_n"} if name == "category_sales" else set())
    assert validate_sql(checked.sql) == checked


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders", "DELETE FROM orders", "INSERT INTO orders DEFAULT VALUES",
    "COPY orders TO 'leak.csv'", "ATTACH 'other.duckdb' AS other", "SET enable_external_access=true",
    "INSTALL httpfs", "LOAD httpfs", "PRAGMA database_list", "CALL checkpoint()",
    "SELECT * FROM orders; DELETE FROM orders", "SELECT * FROM orders; SELECT * FROM order_items",
    "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
    "SELECT * FROM read_csv('local.csv')", "SELECT * FROM read_parquet('https://example.test/data')",
    "SELECT * FROM read_text('.env')", "SELECT * FROM query('DELETE FROM orders')",
    "SELECT * FROM query_table('orders')", "SELECT * FROM glob('*')",
    "SELECT * FROM duckdb_secrets()", "SELECT * FROM duckdb_tables()",
    "SELECT * FROM information_schema.tables", "SELECT * FROM olist_source.main.orders",
    "SELECT * FROM main.orders", "SELECT * FROM _source_files", "SELECT * FROM 'local.csv'",
    "SELECT current_setting('access_mode') FROM orders", "SELECT getenv('NVIDIA_API_KEY') FROM orders",
    "SELECT read_blob('.env') FROM orders", "SELECT main.sum(price) FROM order_items",
    "SELECT repeat(order_id, 1000000000) FROM orders", "SELECT md5(order_id) FROM orders",
    "SELECT count(*) FROM orders, order_items", "SELECT count(*) FROM orders CROSS JOIN order_items",
    "SELECT * FROM range(1000000000000)", "VALUES (1)",
    "WITH RECURSIVE x AS (SELECT 1 AS n UNION ALL SELECT n+1 FROM x) SELECT * FROM x",
    "SELECT order_id FROM orders UNION ALL SELECT order_id FROM orders",
    "SELECT CAST(order_id AS BLOB) FROM orders", "SELECT * REPLACE ('x' AS order_id) FROM orders",
    "SELECT $api_key FROM orders", "SELECT FROM", "", "-- only a comment",
    "SELECT 1", "SELECT lead(order_id) OVER() FROM orders",
    "WITH x AS (WITH hidden AS (SELECT * FROM orders) SELECT * FROM hidden) SELECT * FROM hidden",
    'WITH x AS (WITH "private.csv" AS (SELECT * FROM orders) SELECT * FROM "private.csv") SELECT * FROM "private.csv"',
])
def test_rejects_dangerous_unknown_or_unsupported_syntax(sql):
    with pytest.raises(SQLBlocked):
        validate_sql(sql)


def test_comments_and_literals_are_not_executed_or_keyword_filtered():
    checked = validate_sql("/* DELETE; ATTACH */ SELECT 'DROP TABLE x;' AS note, count(*) FROM orders -- LOAD httpfs")
    assert checked.tables == ("orders",)
    assert "/*" not in checked.sql and "DROP TABLE x;" in checked.sql


def test_oversized_and_engine_drift_fail_closed(monkeypatch):
    with pytest.raises(SQLBlocked):
        validate_sql(" " * (MAX_SQL_CHARS + 1))
    monkeypatch.setattr("scripts.sql_guard.duckdb.__version__", "unreviewed-version")
    with pytest.raises(SQLBlocked) as error:
        validate_sql("SELECT count(*) FROM orders")
    assert error.value.code == "engine_version"
