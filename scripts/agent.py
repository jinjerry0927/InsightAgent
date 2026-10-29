"""Explicit bounded analysis state machine. Model output never executes directly."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from scripts.analysis_context import LIMITATIONS, METRIC_COLUMNS, METRIC_LABELS, reviewed_sql, system_context
from scripts.llm_client import LLMError
from scripts.metrics import analysis_window
from scripts.query_executor import QueryError
from scripts.sql_guard import SQLBlocked, validate_sql


class State(str, Enum):
    PREFLIGHT = "preflight"
    GENERATING = "generating"
    VALIDATING = "validating"
    EXECUTING = "executing"
    REPAIRING = "repairing"
    SUCCESS = "success"
    CLARIFY = "clarify"
    UNSUPPORTED = "unsupported"
    NO_DATA = "no_data"
    BLOCKED = "blocked"
    FAILED = "failed"
    LIMIT = "limit"
    ROW_LIMIT = "row_limit"


TERMINAL = {State.SUCCESS, State.CLARIFY, State.UNSUPPORTED, State.NO_DATA,
            State.BLOCKED, State.FAILED, State.LIMIT, State.ROW_LIMIT}
TRANSITIONS = {
    State.PREFLIGHT: {State.GENERATING, State.CLARIFY, State.FAILED},
    State.GENERATING: {State.VALIDATING, State.CLARIFY, State.UNSUPPORTED, State.FAILED, State.LIMIT},
    State.VALIDATING: {State.EXECUTING, State.BLOCKED, State.FAILED, State.REPAIRING, State.LIMIT},
    State.EXECUTING: {State.SUCCESS, State.NO_DATA, State.FAILED, State.REPAIRING, State.LIMIT, State.ROW_LIMIT},
    State.REPAIRING: {State.GENERATING, State.LIMIT},
}


@dataclass(frozen=True)
class AgentLimits:
    max_llm_calls: int = 3
    max_sql_repairs: int = 1
    max_db_executions: int = 2

    def __post_init__(self):
        for value, lower, upper in ((self.max_llm_calls, 1, 3), (self.max_sql_repairs, 0, 1),
                                    (self.max_db_executions, 1, 2)):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError("Agent limits cannot exceed the approved caps")


@dataclass
class AgentResult:
    state: State = State.PREFLIGHT
    message: str = ""
    error_code: str | None = None
    metric: str | None = None
    sql: str | None = field(default=None, repr=False)
    rows: list[dict] = field(default_factory=list, repr=False)
    columns: tuple[str, ...] = ()
    coverage: dict = field(default_factory=dict)
    llm_calls: int = 0
    api_attempts: int = 0
    sql_repairs: int = 0
    db_executions: int = 0
    usage: list[dict] = field(default_factory=list)
    trace: list[str] = field(default_factory=lambda: [State.PREFLIGHT.value])
    limitations: tuple[str, ...] = LIMITATIONS
    query_elapsed_seconds: float | None = None

    def transition(self, state: State) -> None:
        if self.state in TERMINAL or state not in TRANSITIONS[self.state]:
            raise RuntimeError("Invalid agent state transition")
        self.state = state
        self.trace.append(state.value)

    def finish(self, state: State, message: str, code: str | None = None):
        self.transition(state)
        self.message, self.error_code = message, code
        return self


def parse_response(text: str) -> dict:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("Duplicate response key")
            obj[key] = value
        return obj

    payload = json.loads(text, object_pairs_hook=unique)
    if not isinstance(payload, dict):
        raise ValueError("Expected response object")
    status = payload.get("status")
    if status == "sql":
        if (set(payload) != {"status", "metric", "sql"} or payload["metric"] not in METRIC_COLUMNS
                or not isinstance(payload["sql"], str)):
            raise ValueError("Invalid SQL response")
    elif status in ("clarify", "unsupported"):
        if (set(payload) != {"status", "message"} or not isinstance(payload["message"], str)
                or not 1 <= len(payload["message"].strip()) <= 300):
            raise ValueError("Invalid scope response")
    else:
        raise ValueError("Unknown response status")
    return payload


class AnalysisAgent:
    def __init__(self, client, executor, limits: AgentLimits | None = None):
        self.client, self.executor = client, executor
        self.limits = limits or AgentLimits()

    def run(self, question: str, start: str | None = None, end: str | None = None) -> AgentResult:
        result = AgentResult()
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            return result.finish(State.CLARIFY, "분석 질문을 2,000자 이내로 입력하세요.")
        if not start or not end:
            return result.finish(State.CLARIFY, "분석 시작일과 종료일(종료일 제외)을 지정하세요.")
        try:
            start_at, end_at = analysis_window(start, end)
        except (ValueError, TypeError):
            return result.finish(State.FAILED, "분석 기간 형식을 확인하세요.", "period")
        prompt = json.dumps({"question": question, "selected_start_inclusive": start_at.isoformat(),
                             "selected_end_exclusive": end_at.isoformat()}, ensure_ascii=False)
        base_prompt = prompt
        result.transition(State.GENERATING)

        def repair(reason: str) -> bool:
            nonlocal prompt
            if (result.sql_repairs >= self.limits.max_sql_repairs
                    or result.llm_calls >= self.limits.max_llm_calls
                    or result.db_executions >= self.limits.max_db_executions):
                return False
            result.sql_repairs += 1
            result.transition(State.REPAIRING)
            # No database rows or raw database error is sent for repair.
            prompt = base_prompt + "\nRepair the previous SQL once. Safe failure code: " + reason
            prompt += "\nPrevious SQL:\n" + (result.sql or "")
            result.transition(State.GENERATING)
            return True

        while result.state not in TERMINAL:
            if result.llm_calls >= self.limits.max_llm_calls:
                return result.finish(State.LIMIT, "모델 호출 한도에 도달했습니다.", "llm_limit")
            result.llm_calls += 1
            try:
                completion = self.client.complete(prompt, system_prompt=system_context())
            except LLMError as error:
                result.api_attempts += error.attempts
                result.usage.append({"tokens": error.usage, "elapsed_seconds": error.elapsed_seconds})
                return result.finish(State.FAILED, "모델 호출 오류로 종료했습니다.", error.code)
            result.api_attempts += completion.attempts
            result.usage.append({"tokens": {"prompt_tokens": completion.prompt_tokens,
                                           "completion_tokens": completion.completion_tokens,
                                           "total_tokens": completion.total_tokens},
                                 "elapsed_seconds": completion.elapsed_seconds})
            try:
                response = parse_response(completion.content)
            except (ValueError, TypeError, RecursionError):
                return result.finish(State.FAILED, "모델 응답 형식이 올바르지 않습니다.", "model_response")
            if response["status"] in ("clarify", "unsupported"):
                return result.finish(State(response["status"]), response["message"])
            if result.metric is not None and result.metric != response["metric"]:
                return result.finish(State.FAILED, "수정 과정에서 분석 지표가 바뀌었습니다.", "metric_changed")
            result.metric, result.sql = response["metric"], response["sql"]
            result.transition(State.VALIDATING)
            try:
                checked = validate_sql(result.sql)
            except SQLBlocked as error:
                return result.finish(State.BLOCKED, str(error), error.code)
            result.sql = checked.sql
            expected = {"start_at", "end_at"} | ({"top_n"} if result.metric == "category_sales" else set())
            if set(checked.parameters) != expected:
                if repair("period_parameters"):
                    continue
                return result.finish(State.LIMIT, "기간·지표 매개변수가 승인 기준과 다릅니다.", "sql_limit")
            # Safety and KPI correctness are separate. Initially require the native
            # AST serialization to match the reviewed metric; only bound dates vary.
            if checked.sql != reviewed_sql(result.metric):
                if repair("reviewed_metric_structure"):
                    continue
                return result.finish(State.LIMIT, "생성 SQL이 승인된 KPI 계산 구조와 다릅니다.", "metric_sql")
            if result.db_executions >= self.limits.max_db_executions:
                return result.finish(State.LIMIT, "조회 실행 한도에 도달했습니다.", "db_limit")
            result.transition(State.EXECUTING)
            result.db_executions += 1
            try:
                query = self.executor.execute(result.sql, start, end)
            except QueryError as error:
                if error.retryable and repair(error.code):
                    continue
                state = State.LIMIT if error.retryable else State.FAILED
                return result.finish(state, "조회 오류로 종료했습니다.", error.code)
            result.coverage = query.coverage
            result.query_elapsed_seconds = query.elapsed_seconds
            if query.coverage["delivered_orders"] == 0 or not query.rows:
                return result.finish(State.NO_DATA, "해당 기간·상태의 관측 데이터가 없습니다.")
            monetary_types_valid = all(
                not name.endswith("merchandise_value") or dtype.startswith("DECIMAL")
                for name, dtype in zip(query.columns, query.column_types))
            if query.columns != METRIC_COLUMNS[result.metric] or not monetary_types_valid:
                if repair("metric_output_contract"):
                    continue
                return result.finish(State.LIMIT, "조회 결과가 승인 지표의 출력 계약과 다릅니다.", "metric_contract")
            result.rows, result.columns = query.rows, query.columns
            if query.truncated:
                return result.finish(State.ROW_LIMIT, "결과 행 상한에 도달했습니다. 전체 결과로 해석하지 마세요.")
            return result.finish(State.SUCCESS, METRIC_LABELS[result.metric] + " 조회 완료. SQL과 기준을 확인하세요.")
        raise RuntimeError("Agent exited without a terminal result")
