"""Private stdin/stdout worker; only the executor supplies its trusted DB path."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

# -I removes cwd/PYTHONPATH; add only this trusted checkout for shared policy code.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

from scripts.query_executor import MAX_RESULT_BYTES, QueryLimits, encode_value
from scripts.sql_guard import SQLBlocked, TABLE_COLUMNS, validate_sql


def hardened_connection(database: str, memory_mb: int):
    connection = duckdb.connect(":memory:", config={
        "autoload_known_extensions": "false", "autoinstall_known_extensions": "false",
        "allow_community_extensions": "false", "allow_unsigned_extensions": "false",
        "allow_unredacted_secrets": "false", "memory_limit": f"{memory_mb}MB",
        "threads": "1", "max_expression_depth": "128", "temp_directory": "",
        "max_temp_directory_size": "0B",
    })
    try:
        connection.execute("SET enable_progress_bar = false").fetchall()
        connection.execute("ATTACH ? AS olist_source (READ_ONLY)", [database]).fetchall()
        for table, columns in TABLE_COLUMNS.items():
            selected = ", ".join(f'"{column}"' for column in columns)
            connection.execute(
                f'CREATE TEMP VIEW "{table}" AS SELECT {selected} FROM olist_source.main."{table}"'
            ).fetchall()
        connection.execute("SET enable_external_access = false").fetchall()
        connection.execute("SET lock_configuration = true").fetchall()
        return connection
    except Exception:
        connection.close()
        raise


def run(request: dict) -> dict:
    limits = QueryLimits(max_rows=request["max_rows"], memory_mb=request["memory_mb"])
    checked = validate_sql(request["sql"])
    parameters = {name: request["parameters"][name] for name in checked.parameters}
    with hardened_connection(request["database"], limits.memory_mb) as connection:
        # Fixed metadata query is local only, not sent to the model. It distinguishes
        # an empty period from an aggregate query returning a synthetic zero row.
        coverage_cursor = connection.execute("""
            SELECT min(order_purchase_timestamp)::VARCHAR AS first_purchase,
                max(order_purchase_timestamp)::VARCHAR AS last_purchase,
                count(*) FILTER (WHERE order_purchase_timestamp >= CAST($start_at AS TIMESTAMP)
                    AND order_purchase_timestamp < CAST($end_at AS TIMESTAMP)) AS observed_orders,
                count(*) FILTER (WHERE order_status='delivered'
                    AND order_purchase_timestamp >= CAST($start_at AS TIMESTAMP)
                    AND order_purchase_timestamp < CAST($end_at AS TIMESTAMP)) AS delivered_orders
            FROM orders
        """, {key: request["parameters"][key] for key in ("start_at", "end_at")})
        coverage = dict(zip((column[0] for column in coverage_cursor.description), coverage_cursor.fetchone()))
        candidate = checked.sql.rstrip().removesuffix(";")
        cursor = connection.execute(
            f"SELECT * FROM (\n{candidate}\n) AS bounded_result LIMIT {limits.max_rows + 1}", parameters)
        columns = [column[0] for column in cursor.description]
        types = [str(column[1]) for column in cursor.description]
        if len(columns) > 32 or len(columns) != len(set(columns)) or any(len(c) > 128 for c in columns):
            return {"status": "error", "code": "result_size"}
        values = cursor.fetchmany(limits.max_rows + 1)
        rows = []
        for row in values[:limits.max_rows]:
            if any(isinstance(cell, str) and len(cell.encode("utf-8")) > 2000
                   or isinstance(cell, float) and not math.isfinite(cell) for cell in row):
                return {"status": "error", "code": "result_size"}
            rows.append({key: encode_value(value) for key, value in zip(columns, row)})
        report = {"status": "ok", "columns": columns, "column_types": types,
                  "rows": rows, "truncated": len(values) > limits.max_rows, "coverage": coverage}
        if len(json.dumps(report, ensure_ascii=False).encode("utf-8")) > MAX_RESULT_BYTES:
            return {"status": "error", "code": "result_size"}
        return report


def main() -> int:
    try:
        data = sys.stdin.buffer.read(64_001)
        if len(data) > 64_000:
            report = {"status": "error", "code": "request_size"}
        else:
            report = run(json.loads(data))
    except SQLBlocked:
        report = {"status": "error", "code": "blocked"}
    except duckdb.BinderException:
        report = {"status": "error", "code": "binding"}
    except duckdb.OutOfMemoryException:
        report = {"status": "error", "code": "memory"}
    except Exception:
        # Raw engine exceptions may contain paths, SQL, or source values.
        report = {"status": "error", "code": "execution"}
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
