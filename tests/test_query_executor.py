from decimal import Decimal

import duckdb
import pytest

from test_metrics import metric_db
from scripts._query_worker import hardened_connection
from scripts.data_pipeline import SCHEMAS, file_hash
from scripts.metrics import QUERY_NAMES, SQL_DIRECTORY, run_query
from scripts.query_executor import QueryError, QueryExecutor, QueryLimits


@pytest.fixture
def safe_database(metric_db, tmp_path):
    path = tmp_path / "fixture.duckdb"
    with duckdb.connect(str(path)) as target:
        for table, columns in SCHEMAS.items():
            definition = ", ".join(f'"{name}" {dtype}' for name, dtype in columns.items())
            target.execute(f'CREATE TABLE "{table}" ({definition})').fetchall()
            rows = metric_db.execute(f'SELECT * FROM "{table}"').fetchall()
            if rows:
                placeholders = ",".join("?" for _ in columns)
                target.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
        target.execute("UPDATE order_reviews SET review_comment_message='PRIVATE_REVIEW_CANARY'").fetchall()
    return path


@pytest.mark.parametrize("name", QUERY_NAMES)
def test_worker_matches_reviewed_kpi_and_keeps_source_hash(name, safe_database, metric_db):
    before = file_hash(safe_database)
    expected = run_query(metric_db, name, "2018-01-01", "2018-03-01")
    result = QueryExecutor(safe_database).execute((SQL_DIRECTORY / f"{name}.sql").read_text(encoding="utf-8"),
                                                "2018-01-01", "2018-03-01")
    assert result.rows == expected and not result.truncated
    assert result.coverage["observed_orders"] == 8 and result.coverage["delivered_orders"] == 6
    if name == "monthly_sales":
        assert result.rows[0]["merchandise_value"] == Decimal("41.00")
        assert isinstance(result.rows[0]["merchandise_value"], Decimal)
    assert file_hash(safe_database) == before


def test_private_columns_are_not_in_worker_views_and_error_is_safe(safe_database):
    with pytest.raises(QueryError) as error:
        QueryExecutor(safe_database).execute("SELECT review_comment_message FROM order_reviews",
                                             "2018-01-01", "2018-03-01")
    assert error.value.code == "binding" and error.value.retryable
    assert "PRIVATE_REVIEW_CANARY" not in str(error.value)


def test_engine_denies_writes_external_files_and_config_changes(safe_database, tmp_path):
    before = file_hash(safe_database)
    canary = tmp_path / "private.txt"
    canary.write_text("PRIVATE_FILE_CANARY", encoding="utf-8")
    with hardened_connection(str(safe_database), 32) as connection:
        with pytest.raises(duckdb.Error):
            connection.execute("DELETE FROM olist_source.main.orders")
        with pytest.raises(duckdb.Error):
            connection.execute("SELECT * FROM read_text(?)", [str(canary)]).fetchall()
        with pytest.raises(duckdb.Error):
            connection.execute("SET enable_external_access=true")
        with pytest.raises(duckdb.Error):
            connection.execute("SET memory_limit='10GB'")
        settings = dict(connection.execute("SELECT name,value FROM duckdb_settings() WHERE name IN "
                                          "('threads','memory_limit','temp_directory','enable_external_access',"
                                          "'lock_configuration','autoload_known_extensions')").fetchall())
        assert settings["threads"] == "1" and settings["enable_external_access"] == "false"
        assert settings["lock_configuration"] == "true" and settings["autoload_known_extensions"] == "false"
        assert settings["temp_directory"] == ""
    assert file_hash(safe_database) == before


def test_row_limit_fetches_at_most_one_extra_row(safe_database):
    result = QueryExecutor(safe_database, QueryLimits(max_rows=2)).execute(
        "SELECT order_id FROM orders ORDER BY order_id", "2018-01-01", "2018-03-01")
    assert len(result.rows) == 2 and result.truncated


def test_worker_timeout_terminates_and_preserves_database(safe_database):
    before = file_hash(safe_database)
    with pytest.raises(QueryError) as error:
        QueryExecutor(safe_database, QueryLimits(timeout_seconds=0.001)).execute(
            "SELECT count(*) FROM orders", "2018-01-01", "2018-03-01")
    assert error.value.code == "timeout"
    assert file_hash(safe_database) == before


def test_subprocess_environment_omits_credentials_and_pythonpath(safe_database, monkeypatch):
    import subprocess
    original_run = subprocess.run
    seen = []

    def capture(*args, **kwargs):
        seen.append(kwargs["env"])
        return original_run(*args, **kwargs)

    monkeypatch.setenv("NVIDIA_API_KEY", "PRIVATE_ENV_CANARY")
    monkeypatch.setenv("PYTHONPATH", "untrusted-location")
    monkeypatch.setattr("scripts.query_executor.subprocess.run", capture)
    QueryExecutor(safe_database).execute("SELECT count(*) FROM orders", "2018-01-01", "2018-03-01")
    assert len(seen) == 1 and "NVIDIA_API_KEY" not in seen[0] and "PYTHONPATH" not in seen[0]


def test_bounded_result_size_and_no_data_coverage(safe_database):
    executor = QueryExecutor(safe_database)
    with pytest.raises(QueryError) as error:
        executor.execute("SELECT '" + "x" * 2100 + "' AS text FROM orders", "2018-01-01", "2018-03-01")
    assert error.value.code == "result_size"
    result = executor.execute("SELECT count(*) AS total FROM orders WHERE order_purchase_timestamp >= "
                              "CAST($start_at AS TIMESTAMP) AND order_purchase_timestamp < CAST($end_at AS TIMESTAMP)",
                              "2024-01-01", "2025-01-01")
    assert result.rows == [{"total": 0}] and result.coverage["delivered_orders"] == 0


def test_engine_memory_limit_rejects_large_hash_aggregation(safe_database):
    # Trusted fixed test bypasses the application grammar to test the independent
    # engine resource boundary. Production SQL cannot call range().
    with hardened_connection(str(safe_database), 16) as connection:
        with pytest.raises(duckdb.OutOfMemoryException):
            connection.execute("SELECT count(DISTINCT i) FROM range(10000000) t(i)").fetchall()
