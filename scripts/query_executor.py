"""Bounded worker requests. No NVIDIA credentials are passed to the subprocess."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from scripts.data_pipeline import file_hash
from scripts.metrics import analysis_window
from scripts.sql_guard import validate_sql

WORKER = Path(__file__).with_name("_query_worker.py")
MAX_RESULT_BYTES = 128_000


class QueryError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__("조회가 제한 또는 오류로 종료되었습니다.")
        self.code, self.retryable = code, retryable


@dataclass(frozen=True)
class QueryLimits:
    max_rows: int = 200
    timeout_seconds: float = 10
    memory_mb: int = 256

    def __post_init__(self):
        if (type(self.max_rows) is not int or not 1 <= self.max_rows <= 200
                or type(self.memory_mb) is not int or not 16 <= self.memory_mb <= 256
                or isinstance(self.timeout_seconds, bool)
                or not isinstance(self.timeout_seconds, (int, float))
                or not 0 < self.timeout_seconds <= 10):
            raise ValueError("Invalid query limits")


def encode_value(value):
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    return value


def decode_value(value):
    if isinstance(value, dict):
        if set(value) == {"$decimal"}:
            return Decimal(value["$decimal"])
        if set(value) == {"$date"}:
            return date.fromisoformat(value["$date"])
        if set(value) == {"$datetime"}:
            return datetime.fromisoformat(value["$datetime"])
        raise QueryError("worker_protocol")
    return value


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    column_types: tuple[str, ...]
    rows: list[dict]
    coverage: dict
    truncated: bool
    elapsed_seconds: float


class QueryExecutor:
    def __init__(self, database: Path, limits: QueryLimits | None = None):
        self.database = Path(database).resolve()
        if not self.database.is_file() or self.database.suffix != ".duckdb":
            raise ValueError("An existing local .duckdb file is required")
        self.limits = limits or QueryLimits()

    def execute(self, sql: str, start: str, end: str, *, top_n: int = 5) -> QueryResult:
        checked = validate_sql(sql)
        start_at, end_at = analysis_window(start, end)
        if type(top_n) is not int or not 1 <= top_n <= 5:
            raise ValueError("top_n must be between 1 and 5")
        parameters = {"start_at": start_at.isoformat(), "end_at": end_at.isoformat(), "top_n": top_n}
        payload = json.dumps({
            "database": str(self.database), "sql": checked.sql,
            "parameters": parameters, "max_rows": self.limits.max_rows,
            "memory_mb": self.limits.memory_mb,
        }).encode("utf-8")
        # Isolated Python ignores PYTHONPATH/user site. The environment omits API keys.
        env = {key: value for key, value in os.environ.items()
               if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"}}
        fingerprint = file_hash(self.database)
        started = perf_counter()
        try:
            process = subprocess.run(
                [sys.executable, "-I", "-X", "utf8", str(WORKER)], input=payload,
                capture_output=True, timeout=self.limits.timeout_seconds, env=env, check=False,
            )
        except subprocess.TimeoutExpired:
            raise QueryError("timeout") from None
        except OSError:
            raise QueryError("worker_start") from None
        finally:
            if file_hash(self.database) != fingerprint:
                raise QueryError("database_changed")
        elapsed = perf_counter() - started
        if process.returncode != 0 or len(process.stdout) > MAX_RESULT_BYTES:
            raise QueryError("worker_failure")
        try:
            report = json.loads(process.stdout)
            if report["status"] != "ok":
                code = report["code"]
                raise QueryError(code, retryable=code == "binding")
            columns = tuple(report["columns"])
            rows = [{key: decode_value(value) for key, value in row.items()} for row in report["rows"]]
            if len(rows) > self.limits.max_rows or len(columns) > 32:
                raise QueryError("worker_protocol")
            return QueryResult(columns, tuple(report["column_types"]), rows,
                               report["coverage"], report["truncated"], elapsed)
        except (KeyError, TypeError, ValueError):
            raise QueryError("worker_protocol") from None
