"""Validate local config; --live explicitly performs ONE small NVIDIA request."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from scripts.llm_client import LLMError, NvidiaClient, PROJECT_ROOT, load_settings

SMOKE_PROMPT = "Reply with the single word OK."
SMOKE_MAX_TOKENS = 64


def check_connection(*, live: bool = False) -> dict:
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "live": live, "attempts": 0, "automatic_retries": 0,
        "elapsed_seconds": 0, "usage": None,
    }
    try:
        settings = load_settings()
        limit = min(SMOKE_MAX_TOKENS, settings.max_tokens)
        report.update(model=settings.model, max_output_tokens=limit)
        if not live:
            return {**report, "status": "ready", "network_called": False}
        with NvidiaClient(settings) as client:
            result = client.complete(SMOKE_PROMPT, max_tokens=limit)
        report.update(
            status="ok", attempts=result.attempts, elapsed_seconds=result.elapsed_seconds,
            response_received=True, expected_reply=result.content == "OK",
            usage={"prompt_tokens": result.prompt_tokens,
                   "completion_tokens": result.completion_tokens,
                   "total_tokens": result.total_tokens},
        )
    except LLMError as exc:
        report.update(status="error", error_code=exc.code, message=str(exc),
                      attempts=exc.attempts, elapsed_seconds=exc.elapsed_seconds,
                      http_status=exc.status_code, usage=exc.usage)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="실제 API 1회, 출력 최대 64토큰")
    args = parser.parse_args()
    # No request/response debug output, even if OPENAI_LOG was set by the shell.
    for name in ("openai", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    report = check_connection(live=args.live)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.live:
        output = PROJECT_ROOT / "data/processed/nvidia_connection_check.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report["status"] in ("ready", "ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
