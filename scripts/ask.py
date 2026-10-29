"""Run one analysis; explicit --demo or --live prevents accidental paid calls."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

from scripts.agent import AgentLimits, AnalysisAgent, State
from scripts.llm_client import CompletionResult, LLMError, NvidiaClient, PROJECT_ROOT, load_settings
from scripts.metrics import QUERY_NAMES, SQL_DIRECTORY
from scripts.query_executor import QueryExecutor, encode_value


class DemoClient:
    """Fixed reviewed SQL, NOT a natural-language model or language quality test."""

    def __init__(self, metric: str):
        self.metric = metric

    def complete(self, prompt: str, **kwargs) -> CompletionResult:
        text = json.dumps({"status": "sql", "metric": self.metric,
                           "sql": (SQL_DIRECTORY / f"{self.metric}.sql").read_text(encoding="utf-8")})
        return CompletionResult(text, "offline-fixture", 0, None, None, None, attempts=0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true", help="고정 SQL·실제 로컬 DB, API 요청 없음")
    mode.add_argument("--live", action="store_true", help="실제 NVIDIA 모델 사용")
    parser.add_argument("question")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/processed/insightagent.duckdb")
    parser.add_argument("--metric", choices=QUERY_NAMES, default="monthly_sales", help="demo 전용 고정 지표")
    parser.add_argument("--max-llm-calls", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--max-sql-repairs", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    for name in ("openai", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        executor = QueryExecutor(args.database)
        limits = AgentLimits(max_llm_calls=args.max_llm_calls, max_sql_repairs=args.max_sql_repairs)
        if args.demo:
            result = AnalysisAgent(DemoClient(args.metric), executor, limits).run(args.question, args.start, args.end)
        else:
            with NvidiaClient(load_settings()) as client:
                result = AnalysisAgent(client, executor, limits).run(args.question, args.start, args.end)
    except (ValueError, LLMError):
        print(json.dumps({"state": "failed", "error_code": "configuration",
                          "message": "로컬 DB 경로·API 설정·실행 옵션을 확인하세요."}, ensure_ascii=False))
        return 2
    report = {"mode": "offline_fixture" if args.demo else "live",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "start_inclusive": args.start, "end_exclusive": args.end, **asdict(result)}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=encode_value, allow_nan=False))
    return 0 if result.state in (State.SUCCESS, State.NO_DATA, State.CLARIFY, State.UNSUPPORTED) else 2


if __name__ == "__main__":
    raise SystemExit(main())
