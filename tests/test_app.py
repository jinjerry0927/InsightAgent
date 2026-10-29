from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from test_metrics import metric_db
from test_query_executor import safe_database
from scripts import dashboard
from scripts.agent import AgentResult, State

APP = Path(__file__).resolve().parents[1] / "app.py"


def open_app(monkeypatch, database):
    monkeypatch.setattr(dashboard, "DEFAULT_DATABASE", database)
    monkeypatch.setattr(dashboard, "api_ready", lambda: True)
    return AppTest.from_file(str(APP), default_timeout=25).run()


def test_initial_render_does_not_analyze(safe_database, monkeypatch):
    def unexpected(*args):
        pytest.fail("Initial render must not run analysis")
    monkeypatch.setattr(dashboard, "analyze", unexpected)
    at = open_app(monkeypatch, safe_database)
    assert not at.exception and not at.error and len(at.get("plotly_chart")) == 0
    assert at.button[0].label == "분석 실행"


@pytest.mark.parametrize("metric,charts", [("monthly_sales", 2), ("category_sales", 1),
                                            ("delivery_delays", 1), ("review_delay", 1)])
def test_four_real_reference_results_render_table_and_graph(metric, charts, safe_database, monkeypatch):
    at = open_app(monkeypatch, safe_database)
    at.selectbox[0].select(metric).run()
    at.button[0].click().run()
    assert not at.exception and not at.error
    assert len(at.get("plotly_chart")) == charts and len(at.dataframe) == 1
    result = at.session_state["last_analysis"].result
    assert result.state == State.SUCCESS and result.api_attempts == 0
    if metric == "monthly_sales":
        assert at.dataframe[0].value.iloc[0]["상품금액"] == "41.00"


def test_reruns_and_mode_changes_keep_snapshot_without_new_calls(safe_database, monkeypatch):
    calls = []
    original = dashboard.analyze

    def capture(request):
        calls.append(request)
        return original(request, safe_database)

    monkeypatch.setattr(dashboard, "analyze", capture)
    at = open_app(monkeypatch, safe_database)
    at.button[0].click().run()
    at.run()
    at.radio[0].set_value("AI 질문").run()
    assert len(calls) == 1 and not at.exception
    assert at.session_state["last_analysis"].request.mode == "reference"
    assert any("기준 분석 · API 미사용" in caption.value for caption in at.caption)


@pytest.mark.parametrize("state", [State.NO_DATA, State.BLOCKED, State.FAILED, State.CLARIFY, State.UNSUPPORTED, State.LIMIT])
def test_terminal_states_have_no_charts_or_fabricated_statistics(state, safe_database, monkeypatch):
    calls = []
    def result(request):
        calls.append(request)
        return AgentResult(state=state, message="안전하게 종료했습니다.", error_code="quota" if state == State.FAILED else None)
    monkeypatch.setattr(dashboard, "analyze", result)
    at = open_app(monkeypatch, safe_database)
    at.button[0].click().run()
    assert not at.exception and len(calls) == 1 and len(at.dataframe) == len(at.get("plotly_chart")) == 0
    assert at.warning or at.error


def test_real_no_data_period_and_inverted_dates(safe_database, monkeypatch):
    at = open_app(monkeypatch, safe_database)
    at.date_input[0].set_value(date(2024, 1, 1))
    at.date_input[1].set_value(date(2024, 1, 31))
    at.button[0].click().run()
    assert at.session_state["last_analysis"].result.state == State.NO_DATA
    at.date_input[0].set_value(date(2024, 3, 1))
    at.button[0].click().run()
    assert at.session_state["last_analysis"].result.error_code == "period" and not at.exception


def test_ai_submit_runs_only_once_and_shows_unknown_usage(safe_database, monkeypatch):
    calls = []
    def analyze(request):
        calls.append(request)
        return AgentResult(state=State.FAILED, message="모델 호출 오류로 종료했습니다.", error_code="quota",
                           api_attempts=1, llm_calls=1, usage=[{"tokens": None, "elapsed_seconds": 0.1}])
    monkeypatch.setattr(dashboard, "analyze", analyze)
    at = open_app(monkeypatch, safe_database)
    at.radio[0].set_value("AI 질문").run()
    assert not calls
    at.text_area[0].set_value("월별 매출")
    at.button[0].click().run()
    at.run()
    assert len(calls) == 1 and calls[0].mode == "live" and not calls[0].allow_repair
    assert next(m.value for m in at.metric if m.label == "사용 토큰") == "미제공"
    assert not at.exception


def test_missing_database_displays_safe_setup_message(tmp_path, monkeypatch):
    at = open_app(monkeypatch, tmp_path / "PRIVATE_PATH_CANARY.duckdb")
    assert len(at.error) == 1 and not at.exception and not at.button
    assert "PRIVATE_PATH_CANARY" not in at.error[0].value


def test_row_limit_does_not_present_partial_sum_as_a_period_total(safe_database, monkeypatch):
    result = dashboard.analyze(dashboard.AnalysisRequest("reference", "monthly_sales",
                               date(2018, 1, 1), date(2018, 2, 28)), safe_database)
    result.state = State.ROW_LIMIT
    result.message = "결과 상한에 도달했습니다."
    monkeypatch.setattr(dashboard, "analyze", lambda request: result)
    at = open_app(monkeypatch, safe_database)
    at.button[0].click().run()
    assert not at.exception and len(at.dataframe) == 1 and at.warning
    assert not any(metric.label == "상품금액 · 원본 단위" for metric in at.metric)
