"""Verify the local Phase 2 environment with synthetic data and no API calls."""

from __future__ import annotations

import io
import sys
from datetime import datetime
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path


def check_environment() -> None:
    """Check isolation and the CSV/pandas/DuckDB data path in memory."""
    expected_environment = Path(__file__).resolve().parents[1] / ".venv"
    if sys.prefix == sys.base_prefix or Path(sys.prefix).resolve() != expected_environment:
        raise RuntimeError(
            "Use the project interpreter: "
            r".\.venv\Scripts\python.exe scripts/check_environment.py"
        )
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("This environment is configured for Python 3.11.x.")

    import duckdb
    import pandas as pd

    print(f"Python: {sys.version.split()[0]}")
    print(f"Environment: {sys.prefix}")
    for package in ("duckdb", "pandas", "pytest"):
        print(f"{package}: {version(package)}")

    # These rows are synthetic environment checks, not Olist data or KPI values.
    csv_text = (
        "category,amount,purchased_at\n"
        "검증,10.25,2024-01-01\n"
        "검증,2.50,2024-01-02\n"
        "다른,99.00,\n"
    )
    frame = pd.read_csv(io.StringIO(csv_text), converters={"amount": Decimal})
    frame["purchased_at"] = pd.to_datetime(frame["purchased_at"])

    with duckdb.connect(":memory:") as connection:
        connection.register("environment_rows", frame)
        actual = connection.execute(
            """
            WITH totals AS (
                SELECT category, COUNT(*) AS row_count, SUM(amount) AS total
                FROM environment_rows
                GROUP BY category
            )
            SELECT row_count, total FROM totals WHERE category = ?
            """,
            ["검증"],
        ).fetchone()
        if actual != (2, Decimal("12.75")):
            raise RuntimeError(f"Decimal/Unicode/CTE round trip failed: {actual!r}")

        dates = connection.execute(
            """
            SELECT MIN(purchased_at), COUNT(*) FILTER (WHERE purchased_at IS NULL)
            FROM environment_rows
            """
        ).fetchone()
        if dates != (datetime(2024, 1, 1), 1):
            raise RuntimeError(f"Timestamp/NULL conversion failed: {dates!r}")

        result = connection.execute(
            "SELECT COUNT(*) AS row_count FROM environment_rows"
        ).df()
        if result.shape != (1, 1) or result.loc[0, "row_count"] != 3:
            raise RuntimeError("DuckDB to pandas result conversion failed.")

    print("PASS: CSV -> pandas -> DuckDB -> pandas")
    print("PASS: Unicode, exact decimals, timestamps, NULL values, and a CTE query")


def main() -> int:
    try:
        check_environment()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
