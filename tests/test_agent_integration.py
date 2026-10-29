import pytest

from test_metrics import metric_db
from test_query_executor import safe_database
from scripts.agent import AnalysisAgent, State
from scripts.ask import DemoClient
from scripts.metrics import QUERY_NAMES, run_query
from scripts.query_executor import QueryExecutor


@pytest.mark.parametrize("metric", QUERY_NAMES)
def test_model_fixture_to_real_worker_matches_phase3_values(metric, safe_database, metric_db):
    result = AnalysisAgent(DemoClient(metric), QueryExecutor(safe_database)).run(
        "승인된 기준 지표를 조회해줘", "2018-01-01", "2018-03-01")
    assert result.state == State.SUCCESS
    assert result.rows == run_query(metric_db, metric, "2018-01-01", "2018-03-01")
    assert result.api_attempts == 0 and result.db_executions == 1


def test_real_worker_no_data_is_terminal_not_an_invented_zero(safe_database):
    result = AnalysisAgent(DemoClient("monthly_sales"), QueryExecutor(safe_database)).run(
        "2024년 매출", "2024-01-01", "2025-01-01")
    assert result.state == State.NO_DATA and result.rows == []
    assert result.coverage["delivered_orders"] == 0
