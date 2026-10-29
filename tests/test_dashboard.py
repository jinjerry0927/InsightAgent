from datetime import date
from decimal import Decimal
import json

import pytest

from test_metrics import metric_db
from test_query_executor import safe_database
from scripts import dashboard
from scripts.agent import State
from scripts.llm_client import CompletionResult
from scripts.metrics import SQL_DIRECTORY


def request(**changes):
    values = dict(mode="reference", metric="monthly_sales", start=date(2018, 1, 1),
                  end_inclusive=date(2018, 1, 31))
    return dashboard.AnalysisRequest(**{**values, **changes})


def test_catalog_and_inclusive_date_boundary_match_actual_rows(safe_database):
    catalog = dashboard.read_catalog(safe_database)
    assert (catalog.orders, catalog.delivered_orders) == (8, 6)
    result = dashboard.analyze(request(), safe_database)
    assert result.state == State.SUCCESS and len(result.rows) == 1
    assert result.rows[0]["order_count"] == 3  # Jan 31 at 23:59:59 is included.
    assert result.rows[0]["merchandise_value"] == Decimal("41.00")
    assert result.api_attempts == 0


@pytest.mark.parametrize("changes,state", [
    ({"start": None}, State.CLARIFY), ({"end_inclusive": None}, State.CLARIFY),
    ({"start": date(2018, 3, 1)}, State.FAILED),
    ({"mode": "live", "question": ""}, State.CLARIFY),
    ({"mode": "live", "question": "x" * 2001}, State.CLARIFY),
    ({"metric": "../../private"}, State.FAILED),
])
def test_invalid_inputs_have_no_model_or_db_execution(changes, state, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Preflight must not initialize the database or model")
    monkeypatch.setattr(dashboard, "QueryExecutor", unexpected)
    monkeypatch.setattr(dashboard, "load_settings", unexpected)
    result = dashboard.analyze(request(**changes))
    assert result.state == state and result.api_attempts == result.db_executions == 0


@pytest.mark.parametrize("repair,caps", [(False, (1, 0, 1)), (True, (2, 1, 2))])
def test_ui_repair_choice_controls_budget_and_never_passes_rows_to_model(safe_database, monkeypatch, repair, caps):
    seen = []
    original = dashboard.AnalysisAgent

    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def complete(self, prompt, **kwargs):
            seen.append(prompt)
            return CompletionResult(json.dumps({"status": "sql", "metric": "monthly_sales",
                "sql": (SQL_DIRECTORY / "monthly_sales.sql").read_text(encoding="utf-8")}),
                "offline-http-fixture", 0.1, 10, 2, 12, 1)

    def agent(client, executor, limits):
        assert (limits.max_llm_calls, limits.max_sql_repairs, limits.max_db_executions) == caps
        return original(client, executor, limits)

    monkeypatch.setattr(dashboard, "load_settings", lambda: object())
    monkeypatch.setattr(dashboard, "NvidiaClient", lambda settings: Client())
    monkeypatch.setattr(dashboard, "AnalysisAgent", agent)
    result = dashboard.analyze(request(mode="live", question="월별 매출", allow_repair=repair), safe_database)
    assert result.state == State.SUCCESS and len(seen) == 1
    assert "PRIVATE_REVIEW_CANARY" not in seen[0] and "41.00" not in seen[0]


def test_unexpected_exception_does_not_expose_credentials_or_paths(safe_database, monkeypatch):
    def failure():
        raise RuntimeError("PRIVATE_KEY_AND_PATH_CANARY")
    monkeypatch.setattr(dashboard, "load_settings", failure)
    result = dashboard.analyze(request(mode="live", question="월별 매출"), safe_database)
    assert result.state == State.FAILED and result.error_code == "internal"
    assert "CANARY" not in result.message
