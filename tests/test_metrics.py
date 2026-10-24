"""Hand-calculated business examples, edge cases, and an independent CSV oracle."""

import copy
import csv
from datetime import date
from decimal import Decimal

import duckdb
import pytest

from scripts.data_pipeline import FILENAMES, SCHEMAS, file_hash
from scripts.metrics import analysis_window, run_query, run_suite
from scripts.run_baselines import render_results, validate_output_paths
from scripts.verify_metrics import source_fingerprints, verify_against_csv


START, END = "2018-01-01", "2018-03-01"


def insert(connection, table, **values):
    columns = ", ".join(f'"{key}"' for key in values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', list(values.values())).fetchall()


@pytest.fixture
def metric_db():
    with duckdb.connect(":memory:") as connection:
        for table, columns in SCHEMAS.items():
            definition = ", ".join(f'"{column}" {dtype}' for column, dtype in columns.items())
            connection.execute(f'CREATE TABLE "{table}" ({definition})').fetchall()
        orders = [
            ("a", "delivered", "2018-01-01 00:00:00", "2018-01-10 23:59:59", "2018-01-10"),
            ("b", "delivered", "2018-01-31 23:59:59", "2018-02-02", "2018-02-01"),
            ("c", "delivered", "2018-02-01", None, "2018-02-10"),
            ("d", "canceled", "2018-01-15", "2018-01-20", "2018-01-18"),
            ("e", "shipped", "2018-01-20", None, "2018-01-30"),
            ("f", "delivered", "2018-01-25", "2018-01-25", "2018-01-20"),
            ("g", "delivered", "2018-02-15", "2018-02-20", "2018-02-20"),
            ("h", "delivered", "2018-02-28", "2018-03-02", "2018-03-01"),
        ]
        for order_id, status, purchased, actual, estimate in orders:
            insert(connection, "orders", order_id=order_id, order_status=status,
                   order_purchase_timestamp=purchased, order_delivered_customer_date=actual,
                   order_estimated_delivery_date=estimate)
        for product_id, category in [("pa", "alpha"), ("pb", "beta"), ("pu", "pt_code"), ("pm", None)]:
            insert(connection, "products", product_id=product_id, product_category_name=category)
        for code, english in [("alpha", "Alpha"), ("beta", "Beta")]:
            insert(connection, "category_translation", product_category_name=code, product_category_name_english=english)
        for order_id, product_id, amount in [
            ("a", "pa", "10.25"), ("a", "pb", "20.75"),
            ("b", "pa", "4.00"), ("b", "pu", "6.00"), ("f", "pa", "0.00"),
            ("c", "pm", "7.50"), ("g", "pm", "8.00"), ("h", "missing-product", "2.50"),
            ("d", "pa", "999.00"), ("e", "pa", "500.00"),
        ]:
            insert(connection, "order_items", order_id=order_id, product_id=product_id, price=Decimal(amount), freight_value=Decimal("100.00"))
        for order_id in ("a", "b"):
            for seq in (1, 2):
                insert(connection, "order_payments", order_id=order_id, payment_sequential=seq, payment_value=Decimal("500.00"))
        for order_id, review_id, score, created, answered in [
            ("a", "shared", 4, "2018-01-11", "2018-01-12"),
            ("b", "old", 1, "2018-02-02", "2018-02-03"),
            ("b", "shared", 5, "2018-02-04", "2018-02-05"),
            ("c", "c-review", 5, "2018-02-11", "2018-02-12"),
            ("d", "d-review", 1, "2018-01-22", "2018-01-25"),
            ("g", "g-review", 3, "2018-02-22", "2018-02-25"),
            ("h", "h-review", 2, "2018-03-03", "2018-03-05"),
        ]:
            insert(connection, "order_reviews", order_id=order_id, review_id=review_id,
                   review_score=score, review_creation_date=created, review_answer_timestamp=answered)
        yield connection


def test_monthly_sales_are_exact_and_ignore_freight_payments_reviews(metric_db):
    rows = run_query(metric_db, "monthly_sales", START, END)
    assert [(r["purchase_month"], r["order_count"], r["item_count"], r["merchandise_value"]) for r in rows] == [
        (date(2018, 1, 1), 3, 5, Decimal("41.00")),
        (date(2018, 2, 1), 3, 3, Decimal("18.00")),
    ]
    assert all(r["orders_without_items"] == r["items_without_price"] == 0 for r in rows)
    assert all(isinstance(r["merchandise_value"], Decimal) for r in rows)
    insert(metric_db, "order_payments", order_id="a", payment_value=Decimal("999999.99"))
    insert(metric_db, "order_reviews", order_id="a", review_id="another", review_score=1)
    assert run_query(metric_db, "monthly_sales", START, END) == rows


def test_inclusive_start_exclusive_end(metric_db):
    rows = run_query(metric_db, "monthly_sales", START, "2018-02-01")
    assert len(rows) == 1 and rows[0]["merchandise_value"] == Decimal("41.00")
    assert run_query(metric_db, "monthly_sales", "2018-02-01", "2018-02-02")[0]["merchandise_value"] == Decimal("7.50")


def test_categories_keep_unknown_null_and_missing_product_amounts(metric_db):
    rows = run_query(metric_db, "category_sales", START, END)
    assert [(r["category_code"], r["category_name"], r["merchandise_value"]) for r in rows] == [
        ("beta", "Beta", Decimal("20.75")), (None, "미분류", Decimal("18.00")),
        ("alpha", "Alpha", Decimal("14.25")), ("pt_code", "pt_code", Decimal("6.00")),
    ]
    assert sum(r["merchandise_value"] for r in rows) == Decimal("59.00")


def test_top_five_has_stable_code_ties_and_does_not_merge_translated_names(metric_db):
    for code in ("t6", "t4", "t2", "t5", "t1", "t3"):
        insert(metric_db, "products", product_id=code, product_category_name=code)
        insert(metric_db, "category_translation", product_category_name=code, product_category_name_english="same name")
        insert(metric_db, "order_items", order_id="a", product_id=code, price=Decimal("100.00"))
    rows = run_query(metric_db, "category_sales", START, END)
    assert [r["category_code"] for r in rows] == ["t1", "t2", "t3", "t4", "t5"]
    assert len(run_query(metric_db, "category_sales", START, END, top_n=None)) == 10


def test_delivery_uses_calendar_days_and_excludes_missing_dates(metric_db):
    january, february = run_query(metric_db, "delivery_delays", START, END)
    assert (january["delivered_orders"], january["comparable_orders"], january["late_orders"], january["on_time_orders"]) == (3, 3, 2, 1)
    assert january["late_rate"] == pytest.approx(2 / 3)
    assert (february["delivered_orders"], february["comparable_orders"], february["excluded_delivery_orders"], february["missing_delivery_orders"]) == (3, 2, 1, 1)
    assert february["late_rate"] == 0.5


def test_zero_delivery_denominator_is_null(metric_db):
    row = run_query(metric_db, "delivery_delays", "2018-02-01", "2018-02-02")[0]
    assert row["comparable_orders"] == row["late_orders"] == 0
    assert row["late_rate"] is None


def test_reviews_choose_latest_per_order_even_with_reused_review_id(metric_db):
    late, on_time = run_query(metric_db, "review_delay", START, END)
    assert late == {"delivery_group": "late", "comparable_orders": 3, "rated_orders": 2,
                    "excluded_unrated_orders": 1, "mean_review_score": 3.5}
    assert on_time == {"delivery_group": "on_time", "comparable_orders": 2, "rated_orders": 2,
                       "excluded_unrated_orders": 0, "mean_review_score": 3.5}


def test_review_ties_use_creation_then_id_and_null_times_last(metric_db):
    for review_id, score, created, answered in [
        ("early", 1, "2018-04-01", "2018-04-02"),
        ("zzz", 2, "2018-04-02", "2018-04-02"),
        ("aaa", 4, "2018-04-02", "2018-04-02"),
        ("null-time", 1, "2018-05-01", None),
    ]:
        insert(metric_db, "order_reviews", order_id="b", review_id=review_id, review_score=score,
               review_creation_date=created, review_answer_timestamp=answered)
    late = run_query(metric_db, "review_delay", START, END)[0]
    assert late["mean_review_score"] == 3.0  # b=4 and h=2; f remains unrated.


def test_invalid_latest_review_is_excluded_without_using_an_older_score(metric_db):
    insert(metric_db, "order_reviews", order_id="b", review_id="latest", review_score=None,
           review_creation_date="2018-04-01", review_answer_timestamp="2018-04-02")
    late = run_query(metric_db, "review_delay", START, END)[0]
    assert late["rated_orders"] == 1 and late["excluded_unrated_orders"] == 2
    assert late["mean_review_score"] == 2.0


def test_observed_zero_money_is_distinct_from_no_data(metric_db):
    zero = run_suite(metric_db, "2018-01-25", "2018-01-26")
    assert zero["status"] == "ok"
    assert zero["results"]["monthly_sales"][0]["merchandise_value"] == Decimal("0.00")
    absent = run_suite(metric_db, "2025-01-01", "2025-02-01")
    assert absent["status"] == "no_data"
    assert all(not rows for rows in absent["results"].values())


def test_missing_items_or_prices_are_not_filled_with_zero(metric_db):
    insert(metric_db, "orders", order_id="no-items", order_status="delivered", order_purchase_timestamp="2018-01-12")
    insert(metric_db, "order_items", order_id="c", product_id="pa", price=None)
    january, february = run_query(metric_db, "monthly_sales", START, END)
    assert january["orders_without_items"] == 1 and january["merchandise_value"] is None
    assert january["known_merchandise_value"] == Decimal("41.00")
    assert february["items_without_price"] == 1 and february["merchandise_value"] is None
    assert february["known_merchandise_value"] == Decimal("18.00")


@pytest.mark.parametrize("start,end", [
    ("2018-01-01", "2018-01-01"), ("2019-01-01", "2018-01-01"),
    ("not-a-date", END), ("2018-01-01T00:00:00+09:00", END),
])
def test_invalid_windows_are_rejected(start, end):
    with pytest.raises(ValueError):
        analysis_window(start, end)


@pytest.mark.parametrize("top_n", [0, -1, 1.5, True])
def test_invalid_category_limits_are_rejected(metric_db, top_n):
    with pytest.raises(ValueError):
        run_query(metric_db, "category_sales", START, END, top_n=top_n)


def test_only_fixed_repository_queries_are_exposed(metric_db):
    with pytest.raises(ValueError, match="Unknown baseline"):
        run_query(metric_db, "../../unreviewed", START, END)


@pytest.fixture
def csv_source(metric_db, tmp_path):
    source = tmp_path / "raw"
    source.mkdir()
    for table, columns in SCHEMAS.items():
        rows = metric_db.execute(f'SELECT * FROM "{table}"').fetchall()
        with (source / FILENAMES[table]).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
    return source


def test_csv_oracle_agrees_with_hand_checked_results_and_detects_changed_sql(metric_db, csv_source):
    report = run_suite(metric_db, START, END)
    assert verify_against_csv(report, csv_source)["status"] == "passed"
    modified = copy.deepcopy(report)
    modified["results"]["monthly_sales"][0]["merchandise_value"] += Decimal("0.01")
    with pytest.raises(ValueError, match="CSV reference mismatch"):
        verify_against_csv(modified, csv_source)
    modified = copy.deepcopy(report)
    modified["results"]["monthly_sales"][0]["merchandise_value"] = 41.0
    with pytest.raises(ValueError, match="CSV reference mismatch"):
        verify_against_csv(modified, csv_source)
    report["verification"] = {"status": "passed"}
    report["generated_at_utc"] = "synthetic-test"
    assert "59.00" in render_results(report)


def test_changed_original_files_are_rejected(metric_db, csv_source):
    metric_db.execute("CREATE TABLE _source_files (filename VARCHAR, sha256 VARCHAR)").fetchall()
    metric_db.executemany("INSERT INTO _source_files VALUES (?, ?)",
                         [(name, file_hash(csv_source / name)) for name in FILENAMES.values()]).fetchall()
    assert len(source_fingerprints(metric_db, csv_source)) == 9
    with (csv_source / FILENAMES["orders"]).open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="does not match"):
        source_fingerprints(metric_db, csv_source)


def test_evidence_paths_cannot_overwrite_inputs(tmp_path):
    source, database = tmp_path / "raw", tmp_path / "input.duckdb"
    with pytest.raises(ValueError, match="overwrite"):
        validate_output_paths(database, source, source / "orders.csv", tmp_path / "report.md")
    with pytest.raises(ValueError, match="overwrite"):
        validate_output_paths(database, source, database, tmp_path / "report.md")
    with pytest.raises(ValueError, match="different files"):
        validate_output_paths(database, source, tmp_path / "same", tmp_path / "same")
