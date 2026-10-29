"""UI service boundary: validate inputs, then reuse the bounded Phase 5 agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import duckdb

from scripts.agent import AgentLimits, AgentResult, AnalysisAgent, State
from scripts.ask import DemoClient
from scripts.llm_client import LLMError, NvidiaClient, PROJECT_ROOT, load_settings
from scripts.metrics import QUERY_NAMES
from scripts.query_executor import QueryExecutor

DEFAULT_DATABASE = PROJECT_ROOT / "data/processed/insightagent.duckdb"
METRIC_NAMES = {
    "monthly_sales": "월별 매출·주문수",
    "category_sales": "카테고리 TOP 5",
    "delivery_delays": "배송 지연 추이",
    "review_delay": "배송 지연과 평점",
}
METRIC_NOTES = {
    "monthly_sales": "배송 완료 주문의 상품금액입니다. 배송비·결제금액을 제외하고 구매 월로 집계합니다.",
    "category_sales": "같은 매출 기준의 상위 5개 카테고리입니다. 표시된 합계는 전체 매출이 아닙니다.",
    "delivery_delays": "구매 월별 배송 비교 가능 주문 중, 실제 배송 날짜가 예정 날짜보다 늦은 비율입니다.",
    "review_delay": "주문별 최신 리뷰를 먼저 선택하고 유효 평점을 비교합니다. 그룹 차이는 인과관계가 아닙니다.",
}


@dataclass(frozen=True)
class Catalog:
    first_purchase: date
    last_purchase: date
    orders: int
    delivered_orders: int


@dataclass(frozen=True)
class AnalysisRequest:
    mode: str
    metric: str
    start: date | None
    end_inclusive: date | None
    question: str = ""
    allow_repair: bool = False


@dataclass
class Snapshot:
    request: AnalysisRequest
    result: AgentResult


def read_catalog(database: Path) -> Catalog:
    if not database.is_file():
        raise ValueError("Local database unavailable")
    with duckdb.connect(str(database), read_only=True, config={
        "enable_external_access": "false", "autoload_known_extensions": "false",
        "autoinstall_known_extensions": "false", "threads": "1",
    }) as connection:
        first, last, orders, delivered = connection.execute("""
            SELECT min(order_purchase_timestamp)::DATE, max(order_purchase_timestamp)::DATE,
                count(*), count(*) FILTER (WHERE order_status='delivered') FROM orders
        """).fetchone()
    if first is None or last is None:
        raise ValueError("No observed purchase dates")
    return Catalog(first, last, orders, delivered)


def default_window(catalog: Catalog) -> tuple[date, date]:
    if catalog.first_purchase <= date(2017, 1, 1) and catalog.last_purchase >= date(2017, 12, 31):
        return date(2017, 1, 1), date(2017, 12, 31)
    return catalog.first_purchase, min(catalog.last_purchase, catalog.first_purchase + timedelta(days=364))


def api_ready() -> bool:
    try:
        load_settings()
        return True
    except LLMError:
        return False


def analyze(request: AnalysisRequest, database: Path | None = None) -> AgentResult:
    def finish(state, message, code=None):
        return AgentResult().finish(state, message, code)

    if request.mode not in {"reference", "live"} or request.metric not in QUERY_NAMES:
        return finish(State.FAILED, "분석 방식을 다시 선택하세요.", "configuration")
    if type(request.start) is not date or type(request.end_inclusive) is not date:
        return finish(State.CLARIFY, "시작일과 마지막 날짜를 모두 선택하세요.")
    if request.start > request.end_inclusive or request.end_inclusive == date.max:
        return finish(State.FAILED, "시작일은 마지막 날짜보다 늦을 수 없습니다.", "period")
    if request.mode == "live" and (not isinstance(request.question, str)
                                   or not 1 <= len(request.question.strip()) <= 2000):
        return finish(State.CLARIFY, "분석 질문을 2,000자 이내로 입력하세요.")
    start = request.start.isoformat()
    end = (request.end_inclusive + timedelta(days=1)).isoformat()
    try:
        executor = QueryExecutor(database if database is not None else DEFAULT_DATABASE)
        if request.mode == "reference":
            return AnalysisAgent(DemoClient(request.metric), executor).run(
                METRIC_NAMES[request.metric], start, end)
        # Default UI cost is one attempt. Extra repair requires a user choice.
        limits = AgentLimits(max_llm_calls=2 if request.allow_repair else 1,
                             max_sql_repairs=1 if request.allow_repair else 0,
                             max_db_executions=2 if request.allow_repair else 1)
        with NvidiaClient(load_settings()) as client:
            return AnalysisAgent(client, executor, limits).run(request.question, start, end)
    except LLMError as error:
        return finish(State.FAILED, "API 설정을 확인한 뒤 다시 실행하세요.", error.code)
    except (ValueError, OSError):
        return finish(State.FAILED, "로컬 데이터와 API 설정을 확인하세요.", "configuration")
    except Exception:
        # Never display raw SDK/engine errors, paths, headers, or credentials.
        return finish(State.FAILED, "분석을 완료하지 못했습니다. 실행 환경을 확인하세요.", "internal")
