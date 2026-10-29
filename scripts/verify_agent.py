"""Offline comparison: full agent/worker pipeline against reviewed Phase 3 SQL."""

from __future__ import annotations

from datetime import datetime, timezone
import json

import duckdb

from scripts.agent import AnalysisAgent, State
from scripts.ask import DemoClient
from scripts.data_pipeline import file_hash
from scripts.llm_client import PROJECT_ROOT
from scripts.metrics import QUERY_NAMES, run_query
from scripts.query_executor import QueryExecutor


def main() -> int:
    database = PROJECT_ROOT / "data/processed/insightagent.duckdb"
    fingerprint = file_hash(database)
    start, end = "2016-09-01", "2018-11-01"
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "mode": "offline_fixture",
              "api_attempts": 0, "start_inclusive": start, "end_exclusive": end, "metrics": {}}
    with duckdb.connect(str(database), read_only=True) as connection:
        executor = QueryExecutor(database)
        for metric in QUERY_NAMES:
            expected = run_query(connection, metric, start, end)
            result = AnalysisAgent(DemoClient(metric), executor).run("승인된 기준 지표 조회", start, end)
            if result.state != State.SUCCESS or result.rows != expected:
                raise RuntimeError("Agent result does not match reviewed Phase 3 SQL")
            report["metrics"][metric] = {"matches_phase3": True, "rows": len(result.rows),
                                          "db_executions": result.db_executions, "trace": result.trace}
    report["database_unchanged"] = file_hash(database) == fingerprint
    if not report["database_unchanged"]:
        raise RuntimeError("Database fingerprint changed")
    report["status"] = "ok"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (PROJECT_ROOT / "data/processed/phase5_offline_verification.json").write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
