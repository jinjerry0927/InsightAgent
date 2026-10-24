"""Run reviewed repository SQL only; this is not an LLM SQL safety validator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


SQL_DIRECTORY = Path(__file__).resolve().parents[1] / "sql"
QUERY_NAMES = ("monthly_sales", "category_sales", "delivery_delays", "review_delay")


def analysis_window(start: str, end: str) -> tuple[datetime, datetime]:
    start_at, end_at = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if start_at.tzinfo is not None or end_at.tzinfo is not None:
        raise ValueError("Use timezone-naive dates/timestamps matching the source data")
    if start_at >= end_at:
        raise ValueError("The start must be earlier than the exclusive end")
    return start_at, end_at


def records(connection, sql: str, parameters: dict | None = None) -> list[dict]:
    cursor = connection.execute(sql, parameters or {})
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def run_query(connection, name: str, start: str, end: str, top_n: int | None = 5) -> list[dict]:
    if name not in QUERY_NAMES:
        raise ValueError(f"Unknown baseline query: {name}")
    if top_n is not None and (isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1):
        raise ValueError("top_n must be a positive integer or None for all categories")
    start_at, end_at = analysis_window(start, end)
    parameters = {"start_at": start_at, "end_at": end_at}
    if name == "category_sales":
        parameters["top_n"] = top_n
    return records(connection, (SQL_DIRECTORY / f"{name}.sql").read_text(encoding="utf-8"), parameters)


def run_suite(connection, start: str, end: str) -> dict:
    start_at, end_at = analysis_window(start, end)
    coverage = records(connection, """
        SELECT MIN(order_purchase_timestamp) AS first_purchase,
            MAX(order_purchase_timestamp) AS last_purchase,
            MIN(order_purchase_timestamp) FILTER (WHERE order_status='delivered') AS first_delivered_purchase,
            MAX(order_purchase_timestamp) FILTER (WHERE order_status='delivered') AS last_delivered_purchase
        FROM orders
    """)[0]
    scope = records(connection, """
        SELECT COUNT(*) AS observed_orders,
            COUNT(*) FILTER (WHERE order_status='delivered') AS delivered_orders,
            COUNT(*) FILTER (WHERE order_status IS DISTINCT FROM 'delivered') AS excluded_status_orders
        FROM orders WHERE order_purchase_timestamp >= $start_at AND order_purchase_timestamp < $end_at
    """, {"start_at": start_at, "end_at": end_at})[0]
    results = {name: run_query(connection, name, start, end) for name in QUERY_NAMES}
    results["all_categories"] = run_query(connection, "category_sales", start, end, top_n=None)
    return {
        "start_inclusive": start_at, "end_exclusive": end_at,
        "status": "ok" if scope["delivered_orders"] else "no_data",
        "coverage": coverage, "scope": scope, "results": results,
        "limitations": [
            "Item merchandise value excludes freight/payments and is not accounting net revenue.",
            "Boundary months may contain partial observations; empty months are not filled with zero.",
            "Latest reviews use the full source snapshot, not an as-of reconstruction at the period end.",
            "Review score differences are associations, not evidence of causation.",
        ],
    }
