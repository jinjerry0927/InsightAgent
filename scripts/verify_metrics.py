"""Independent CSV/Decimal checks for the reviewed baseline SQL results."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from scripts.data_pipeline import FILENAMES, file_hash, source_directory
from scripts.metrics import analysis_window


def csv_rows(source: Path, table: str):
    with (source / FILENAMES[table]).open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def stamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def source_fingerprints(connection, source: Path) -> dict[str, str]:
    """Confirm all nine original inputs match the database loading manifest."""
    source = source_directory(source)
    manifest = connection.execute("SELECT filename, sha256 FROM _source_files").fetchall()
    if {row[0] for row in manifest} != set(FILENAMES.values()):
        raise ValueError("The database source manifest is incomplete")
    for filename, expected_hash in manifest:
        if file_hash(source / filename) != expected_hash:
            raise ValueError(f"CSV does not match the loaded database: {filename}")
    return dict(manifest)


def _check(actual, expected, label: str) -> None:
    if isinstance(expected, Decimal):
        same = isinstance(actual, Decimal) and actual == expected
    elif isinstance(actual, float) or isinstance(expected, float):
        same = actual is not None and expected is not None and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    else:
        same = actual == expected
    if not same:
        raise ValueError(f"CSV reference mismatch for {label}: {actual!r} != {expected!r}")


def _check_rows(actual: list[dict], expected: list[dict], name: str) -> None:
    _check(len(actual), len(expected), f"{name}.rows")
    for number, (left, right) in enumerate(zip(actual, expected)):
        _check(set(left), set(right), f"{name}[{number}].columns")
        for field in right:
            _check(left[field], right[field], f"{name}[{number}].{field}")


def verify_against_csv(report: dict, source: Path) -> dict:
    """Compute independent reference values without SQL or pandas joins."""
    source = source_directory(source)
    start, end = analysis_window(str(report["start_inclusive"]), str(report["end_exclusive"]))
    eligible = {}
    observed = excluded = 0
    first = last = delivered_first = delivered_last = None
    for order in csv_rows(source, "orders"):
        purchased = stamp(order["order_purchase_timestamp"])
        if purchased is None:
            continue
        first = min(first, purchased) if first is not None else purchased
        last = max(last, purchased) if last is not None else purchased
        if order["order_status"] == "delivered":
            delivered_first = min(delivered_first, purchased) if delivered_first is not None else purchased
            delivered_last = max(delivered_last, purchased) if delivered_last is not None else purchased
        if not start <= purchased < end:
            continue
        observed += 1
        if order["order_status"] != "delivered":
            excluded += 1
            continue
        order["month"] = purchased.date().replace(day=1)
        eligible[order["order_id"]] = order
    _check(report["scope"], {"observed_orders": observed, "delivered_orders": len(eligible), "excluded_status_orders": excluded}, "scope")
    _check(report["coverage"], {"first_purchase": first, "last_purchase": last,
           "first_delivered_purchase": delivered_first, "last_delivered_purchase": delivered_last}, "coverage")

    monthly = {}
    delivery = {}
    for order in eligible.values():
        month = order["month"]
        if month not in monthly:
            monthly[month] = {"purchase_month": month, "order_count": 0, "item_count": 0,
                              "orders_without_items": 0, "items_without_price": 0,
                              "known_merchandise_value": None, "merchandise_value": None}
            delivery[month] = {"purchase_month": month, "delivered_orders": 0,
                               "comparable_orders": 0, "excluded_delivery_orders": 0,
                               "missing_delivery_orders": 0, "missing_estimate_orders": 0,
                               "late_orders": 0, "on_time_orders": 0, "late_rate": None}
        monthly[month]["order_count"] += 1
        d = delivery[month]
        d["delivered_orders"] += 1
        actual = stamp(order["order_delivered_customer_date"])
        estimate = stamp(order["order_estimated_delivery_date"])
        d["missing_delivery_orders"] += int(actual is None)
        d["missing_estimate_orders"] += int(estimate is None)
        if actual is None or estimate is None:
            d["excluded_delivery_orders"] += 1
            order["delivery_group"] = None
        else:
            late = actual.date() > estimate.date()
            d["comparable_orders"] += 1
            d["late_orders"] += int(late)
            d["on_time_orders"] += int(not late)
            order["delivery_group"] = "late" if late else "on_time"

    products = {p["product_id"]: p["product_category_name"] or None for p in csv_rows(source, "products")}
    translations = {t["product_category_name"]: t["product_category_name_english"] or None for t in csv_rows(source, "category_translation")}
    categories = {}
    seen_items = set()
    for item in csv_rows(source, "order_items"):
        order = eligible.get(item["order_id"])
        if order is None:
            continue
        seen_items.add(item["order_id"])
        m = monthly[order["month"]]
        code = products.get(item["product_id"])
        if code not in categories:
            categories[code] = {"category_code": code,
                                "category_name": translations.get(code) or code or "미분류",
                                "item_count": 0, "items_without_price": 0,
                                "known_merchandise_value": None, "merchandise_value": None}
        c = categories[code]
        for bucket in (m, c):
            bucket["item_count"] += 1
            if item["price"]:
                amount = Decimal(item["price"])
                previous = bucket["known_merchandise_value"]
                bucket["known_merchandise_value"] = amount if previous is None else previous + amount
            else:
                bucket["items_without_price"] += 1
    for order_id, order in eligible.items():
        monthly[order["month"]]["orders_without_items"] += int(order_id not in seen_items)
    for bucket in [*monthly.values(), *categories.values()]:
        if not bucket["items_without_price"] and not bucket.get("orders_without_items", 0):
            bucket["merchandise_value"] = bucket["known_merchandise_value"]
    for d in delivery.values():
        if d["comparable_orders"]:
            d["late_rate"] = d["late_orders"] / d["comparable_orders"]

    latest = {}
    for review in csv_rows(source, "order_reviews"):
        if review["order_id"] not in eligible:
            continue
        answer, created = stamp(review["review_answer_timestamp"]), stamp(review["review_creation_date"])
        time_key = (answer is not None, answer or datetime.min, created is not None, created or datetime.min)
        id_key = (not bool(review["review_id"]), review["review_id"])
        old = latest.get(review["order_id"])
        if old is None or time_key > old[0] or (time_key == old[0] and id_key < old[1]):
            latest[review["order_id"]] = (time_key, id_key, review["review_score"])
    groups = {}
    score_sums = defaultdict(int)
    for order_id, order in eligible.items():
        group = order["delivery_group"]
        if group is None:
            continue
        if group not in groups:
            groups[group] = {"delivery_group": group, "comparable_orders": 0,
                             "rated_orders": 0, "excluded_unrated_orders": 0,
                             "mean_review_score": None}
        g = groups[group]
        g["comparable_orders"] += 1
        selected = latest.get(order_id)
        score = int(Decimal(selected[2])) if selected is not None and selected[2] else None
        if score is not None and 1 <= score <= 5:
            g["rated_orders"] += 1
            score_sums[group] += score
        else:
            g["excluded_unrated_orders"] += 1
    for group, g in groups.items():
        if g["rated_orders"]:
            g["mean_review_score"] = score_sums[group] / g["rated_orders"]

    all_categories = sorted(categories.values(), key=lambda row: (
        row["merchandise_value"] is None,
        -row["merchandise_value"] if row["merchandise_value"] is not None else Decimal(0),
        row["category_code"] is None, row["category_code"] or "",
    ))
    expected = {
        "monthly_sales": [monthly[key] for key in sorted(monthly)],
        "delivery_delays": [delivery[key] for key in sorted(delivery)],
        "all_categories": all_categories, "category_sales": all_categories[:5],
        "review_delay": [groups[key] for key in sorted(groups)],
    }
    for name, rows in expected.items():
        _check_rows(report["results"][name], rows, name)
    known_months = [m["known_merchandise_value"] for m in monthly.values() if m["known_merchandise_value"] is not None]
    known_categories = [c["known_merchandise_value"] for c in categories.values() if c["known_merchandise_value"] is not None]
    _check(sum(known_months, Decimal(0)), sum(known_categories, Decimal(0)), "all-category reconciliation")
    return {"status": "passed", "method": "Independent raw CSV iteration and Decimal arithmetic",
            "checks": ["scope", "coverage", *expected, "all-category reconciliation"]}
