import json
from decimal import Decimal

import pytest

from scripts.agent import AgentLimits, AgentResult, AnalysisAgent, State
from scripts.analysis_context import METRIC_COLUMNS, system_context
from scripts.llm_client import CompletionResult, LLMError
from scripts.metrics import SQL_DIRECTORY
from scripts.query_executor import QueryError, QueryResult


def sql_response(name="monthly_sales", sql=None):
    return json.dumps({"status": "sql", "metric": name,
                       "sql": sql if sql is not None else (SQL_DIRECTORY / f"{name}.sql").read_text(encoding="utf-8")})


class FakeClient:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def complete(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return CompletionResult(response, "offline", 0.1, 10, 2, 12, attempts=0)


def query_result(*, delivered=6, truncated=False, columns=None, money_type="DECIMAL(38,2)"):
    columns = columns or METRIC_COLUMNS["monthly_sales"]
    row = {name: Decimal("41.00") if name.endswith("merchandise_value") else 1 for name in columns}
    return QueryResult(columns, tuple(money_type if name.endswith("merchandise_value") else "BIGINT"
                                      for name in columns), [row], {"delivered_orders": delivered}, truncated, 0.1)


class FakeExecutor:
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def run(client, executor, limits=None, question="월별 매출과 주문수", start="2018-01-01", end="2018-03-01"):
    return AnalysisAgent(client, executor, limits).run(question, start, end)


def test_normal_flow_and_context_contains_no_raw_data_or_credentials():
    client, executor = FakeClient(sql_response()), FakeExecutor(query_result())
    result = run(client, executor)
    assert result.state == State.SUCCESS and result.rows[0]["merchandise_value"] == Decimal("41.00")
    assert (result.llm_calls, result.api_attempts, result.sql_repairs, result.db_executions) == (1, 0, 0, 1)
    assert result.trace == ["preflight", "generating", "validating", "executing", "success"]
    context = client.calls[0][1]["system_prompt"]
    assert "DECIMAL" in context and "$start_at" in context and "METRIC review_delay" in context
    assert all(value not in context for value in ("review_comment_message", "customer_unique_id", "NVIDIA_API_KEY"))


@pytest.mark.parametrize("question,start,end,state", [
    ("", "2018-01-01", "2018-03-01", State.CLARIFY),
    ("질문", None, None, State.CLARIFY),
    ("질문", "2018-01-01", None, State.CLARIFY),
    ("질문", "bad", "2018-01-01", State.FAILED),
    ("질문", "2019-01-01", "2018-01-01", State.FAILED),
])
def test_preflight_has_no_calls(question, start, end, state):
    client, executor = FakeClient(), FakeExecutor()
    result = run(client, executor, question=question, start=start, end=end)
    assert result.state == state and not client.calls and not executor.calls


@pytest.mark.parametrize("code", ["authentication", "quota", "timeout", "connection", "server", "output_limit"])
def test_api_errors_stop_immediately_without_repair(code):
    client = FakeClient(LLMError(code, "safe public error", attempts=1))
    executor = FakeExecutor()
    result = run(client, executor)
    assert result.state == State.FAILED and result.error_code == code
    assert (result.llm_calls, result.api_attempts, result.sql_repairs, result.db_executions) == (1, 1, 0, 0)
    assert len(client.calls) == 1 and not executor.calls


def test_dangerous_sql_is_blocked_before_db_with_no_model_repair():
    client, executor = FakeClient(sql_response(sql="SELECT * FROM read_text('.env')")), FakeExecutor()
    result = run(client, executor)
    assert result.state == State.BLOCKED and result.db_executions == 0 and result.sql_repairs == 0
    assert len(client.calls) == 1 and not executor.calls


def test_binding_error_gets_one_repair_and_only_safe_error_context():
    client = FakeClient(sql_response(), sql_response())
    executor = FakeExecutor(QueryError("binding", retryable=True), query_result())
    result = run(client, executor)
    assert result.state == State.SUCCESS
    assert (result.llm_calls, result.sql_repairs, result.db_executions) == (2, 1, 2)
    assert result.trace.count("repairing") == 1 and "binding" in client.calls[1][0]
    assert "41.00" not in client.calls[1][0]


def test_repeated_error_and_lowered_limits_never_create_a_third_execution():
    for limits, expected_calls in ((AgentLimits(), 2), (AgentLimits(max_llm_calls=1), 1),
                                   (AgentLimits(max_db_executions=1), 1), (AgentLimits(max_sql_repairs=0), 1)):
        client = FakeClient(sql_response(), sql_response())
        executor = FakeExecutor(QueryError("binding", retryable=True), QueryError("binding", retryable=True))
        result = run(client, executor, limits)
        assert result.state == State.LIMIT
        assert result.llm_calls == result.db_executions == expected_calls
        assert result.sql_repairs <= 1 and len(client.calls) == expected_calls


@pytest.mark.parametrize("code", ["timeout", "memory", "execution", "database_changed"])
def test_resource_or_integrity_failure_never_retries(code):
    result = run(FakeClient(sql_response()), FakeExecutor(QueryError(code)))
    assert result.state == State.FAILED and result.error_code == code
    assert result.llm_calls == result.db_executions == 1 and result.sql_repairs == 0


@pytest.mark.parametrize("text", [
    "not JSON", "```sql\nSELECT 1;\n```", "[]", '{"status":"sql","status":"unsupported"}',
    '{"status":"sql","metric":"unapproved","sql":"SELECT 1"}',
    '{"status":"sql","metric":[],"sql":"SELECT 1"}',
    '{"status":"unsupported","message":"reason","extra":"field"}',
])
def test_invalid_model_contract_does_not_execute(text):
    executor = FakeExecutor()
    result = run(FakeClient(text), executor)
    assert result.state == State.FAILED and result.error_code == "model_response" and not executor.calls


@pytest.mark.parametrize("status", ["clarify", "unsupported"])
def test_scope_responses_terminate_without_db(status):
    executor = FakeExecutor()
    result = run(FakeClient(json.dumps({"status": status, "message": "분석 범위를 확인하세요."})), executor)
    assert result.state.value == status and result.db_executions == 0


def test_no_data_does_not_publish_zero_or_fabricated_statistics():
    result = run(FakeClient(sql_response()), FakeExecutor(query_result(delivered=0)))
    assert result.state == State.NO_DATA and result.rows == [] and result.coverage["delivered_orders"] == 0


def test_row_limit_and_money_type_contract_are_explicit():
    result = run(FakeClient(sql_response()), FakeExecutor(query_result(truncated=True)))
    assert result.state == State.ROW_LIMIT
    result = run(FakeClient(sql_response()), FakeExecutor(query_result(money_type="DOUBLE")), AgentLimits(max_sql_repairs=0))
    assert result.state == State.LIMIT and result.error_code == "metric_contract" and not result.rows


def test_missing_period_parameters_repair_before_execution_and_metric_stays_fixed():
    client = FakeClient(sql_response(sql="SELECT count(*) FROM orders"), sql_response())
    executor = FakeExecutor(query_result())
    result = run(client, executor)
    assert result.state == State.SUCCESS and result.sql_repairs == 1 and result.db_executions == 1
    client = FakeClient(sql_response(), sql_response("category_sales"))
    result = run(client, FakeExecutor(QueryError("binding", retryable=True)))
    assert result.state == State.FAILED and result.error_code == "metric_changed" and result.db_executions == 1


def test_caps_and_terminal_states_cannot_be_overridden():
    for kwargs in ({"max_llm_calls":4}, {"max_sql_repairs":2}, {"max_db_executions":3}):
        with pytest.raises(ValueError):
            AgentLimits(**kwargs)
    result = AgentResult()
    result.finish(State.CLARIFY, "missing period")
    with pytest.raises(RuntimeError):
        result.transition(State.GENERATING)


def test_safe_but_wrong_kpi_sql_is_not_executed_and_can_be_repaired_once():
    original = (SQL_DIRECTORY / "monthly_sales.sql").read_text(encoding="utf-8")
    wrong = original.replace("order_status = 'delivered'", "order_status = 'canceled'")
    client, executor = FakeClient(sql_response(sql=wrong), sql_response()), FakeExecutor(query_result())
    result = run(client, executor)
    assert result.state == State.SUCCESS and result.llm_calls == 2 and result.db_executions == 1
    assert result.sql_repairs == 1 and "reviewed_metric_structure" in client.calls[1][0]
    executor = FakeExecutor()
    result = run(FakeClient(sql_response(sql=wrong)), executor, AgentLimits(max_sql_repairs=0))
    assert result.state == State.LIMIT and result.error_code == "metric_sql" and not executor.calls
