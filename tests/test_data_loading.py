"""Offline tests for conversion, source preservation, and aggregation hazards."""

import csv
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from scripts.data_pipeline import (
    FILENAMES, SCHEMAS, build_database, file_hash, profile_database,
    render_profile, save_json, source_directory,
)


def write_rows(source: Path, table: str, rows: list[dict]) -> None:
    with (source / FILENAMES[table]).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SCHEMAS[table])
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def source(tmp_path):
    source = tmp_path / "raw" / "archive"
    source.mkdir(parents=True)
    for table, columns in SCHEMAS.items():
        row = {}
        for column, dtype in columns.items():
            if dtype == "TIMESTAMP":
                row[column] = "2018-01-01 12:30:00"
            elif dtype.startswith("DECIMAL"):
                row[column] = "10.25"
            elif dtype in ("BIGINT", "DOUBLE"):
                row[column] = "1"
            elif "zip_code" in column:
                row[column] = "00123"
            elif column in ("customer_city", "seller_city", "geolocation_city"):
                row[column] = "São Paulo"
            else:
                row[column] = "one"
        if table == "orders":
            row["order_status"] = "delivered"
        if table == "order_reviews":
            row["review_comment_title"] = "ótimo"
            row["review_comment_message"] = ""
            row["review_score"] = "5"
        write_rows(source, table, [row])
    return source


def read_rows(source: Path, table: str) -> list[dict]:
    with (source / FILENAMES[table]).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_round_trip_preserves_sources_types_and_quality_report(source, tmp_path):
    before = {path.name: file_hash(path) for path in source.glob("*.csv")}
    database = tmp_path / "analysis.duckdb"
    manifest = build_database(source.parent, database)
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("SELECT customer_zip_code_prefix, customer_city FROM customers").fetchone() == ("00123", "São Paulo")
        assert connection.execute("SELECT price FROM order_items").fetchone() == (Decimal("10.25"),)
        assert connection.execute("SELECT review_comment_message FROM order_reviews").fetchone() == (None,)
        assert connection.execute("SELECT COUNT(*) FROM _source_files").fetchone() == (9,)
    report = profile_database(database)
    assert all(info["rows"] == 1 for info in manifest.values())
    assert report["tables"]["orders"]["columns"]["order_purchase_timestamp"]["minimum"].year == 2018
    assert report["review_text"]["with_message"] == 0
    assert report["review_text"]["with_any_text"] == 1
    assert all(link["unmatched_non_null_rows"] == 0 for link in report["relationships"])
    assert before == {path.name: file_hash(path) for path in source.glob("*.csv")}
    save_json(report, tmp_path / "profile.json")
    assert '"10.25"' in (tmp_path / "profile.json").read_text(encoding="utf-8")
    assert "order_purchase_timestamp" in render_profile(report)


@pytest.mark.parametrize("table,column,bad_value", [
    ("orders", "order_purchase_timestamp", "not-a-date"),
    ("order_items", "price", "10.255"),
    ("order_items", "price", "not-money"),
    ("order_items", "order_item_id", "1.5"),
])
def test_lossy_or_invalid_conversions_fail_without_publishing_database(source, tmp_path, table, column, bad_value):
    rows = read_rows(source, table)
    rows[0][column] = bad_value
    write_rows(source, table, rows)
    database = tmp_path / "invalid.duckdb"
    with pytest.raises(ValueError, match="invalid or lossy"):
        build_database(source, database)
    assert not database.exists()
    assert not list(tmp_path.glob(".invalid-*.duckdb*"))


def test_existing_output_is_preserved(source, tmp_path):
    database = tmp_path / "existing.duckdb"
    database.write_bytes(b"keep existing output")
    with pytest.raises(FileExistsError):
        build_database(source, database)
    assert database.read_bytes() == b"keep existing output"


def test_missing_csv_fails_before_database_creation(source, tmp_path):
    (source / FILENAMES["orders"]).rename(source / "orders.not-csv")
    database = tmp_path / "missing.duckdb"
    with pytest.raises(ValueError, match="exactly one directory"):
        build_database(source, database)
    assert not database.exists()


def test_unexpected_column_fails_before_database_creation(source, tmp_path):
    file = source / FILENAMES["customers"]
    file.write_text(file.read_text(encoding="utf-8").replace("customer_city", "unknown_city"), encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected CSV header"):
        build_database(source, tmp_path / "invalid.duckdb")


def test_duplicate_rows_and_non_unique_customer_identifiers_are_reported(source, tmp_path):
    customers = read_rows(source, "customers")
    second = dict(customers[0], customer_id="two")
    write_rows(source, "customers", [*customers, second])
    reviews = read_rows(source, "order_reviews")
    write_rows(source, "order_reviews", [*reviews, *reviews])
    database = tmp_path / "duplicates.duckdb"
    build_database(source, database)
    report = profile_database(database)
    assert report["tables"]["customers"]["keys"]["customer_id"]["duplicate_key_rows"] == 0
    assert report["tables"]["customers"]["keys"]["customer_unique_id"]["duplicate_key_rows"] == 1
    assert report["tables"]["order_reviews"]["rows"] == 2
    assert report["tables"]["order_reviews"]["duplicate_rows"] == 1


def test_multiple_children_expand_join_and_missing_foreign_keys_are_visible(source, tmp_path):
    for table, key in [("order_items", "order_item_id"), ("order_payments", "payment_sequential"), ("order_reviews", "review_id")]:
        rows = read_rows(source, table)
        second = dict(rows[0])
        second[key] = "2" if table != "order_reviews" else "two"
        if table == "order_items":
            second["product_id"] = "missing-product"
        write_rows(source, table, [*rows, second])
    database = tmp_path / "fanout.duckdb"
    build_database(source, database)
    report = profile_database(database)
    assert report["fanout"]["orders"] == 1
    assert report["fanout"]["multiple_items"] == 1
    assert report["fanout"]["multiple_payments"] == 1
    assert report["fanout"]["multiple_reviews"] == 1
    assert report["fanout"]["predicted_left_join_rows"] == 8
    assert report["fanout"]["actual_left_join_rows"] == 8
    missing = next(link for link in report["relationships"] if link["child"] == "order_items.product_id")
    assert missing["unmatched_non_null_rows"] == 1


def test_multiple_complete_input_folders_are_rejected(source):
    other = source.parent / "second"
    other.mkdir()
    for file in source.glob("*.csv"):
        (other / file.name).write_bytes(file.read_bytes())
    with pytest.raises(ValueError, match="found 2"):
        source_directory(source.parent)
