"""Local Streamlit UI. Analysis runs only inside explicit form submission."""

from __future__ import annotations

from datetime import date
import logging
from pathlib import Path

import streamlit as st

from scripts import charts, dashboard
from scripts.agent import State


@st.cache_data(show_spinner=False)
def catalog_for_revision(database: str, revision: tuple[int, int]):
    return dashboard.read_catalog(Path(database))


ERROR_HELP = {
    "authentication": "API 키와 이용 권한을 확인한 후 직접 다시 실행하세요.",
    "quota": "API 사용 한도를 확인하세요. 자동으로 재호출하지 않습니다.",
    "timeout": "시간 제한으로 종료했습니다. 자동으로 재실행하지 않습니다.",
    "connection": "네트워크 연결을 확인한 후 직접 다시 실행하세요.",
    "metric_sql": "승인된 계산 구조와 달라 종료했습니다. 질문을 지원 범위에 맞게 표현해 주세요.",
    "configuration": "로컬 데이터와 .env 설정을 확인하세요. 키는 화면이나 채팅에 입력하지 마세요.",
    "output_limit": "모델 답변이 토큰 제한으로 잘려 사용하지 않았습니다.",
}


def render_snapshot(snapshot: dashboard.Snapshot):
    request, result = snapshot.request, snapshot.result
    st.divider()
    st.subheader("마지막 실행 결과")
    mode = "기준 분석 · API 미사용" if request.mode == "reference" else "AI 질문 · NVIDIA"
    start = request.start.isoformat() if type(request.start) is date else "미지정"
    end = request.end_inclusive.isoformat() if type(request.end_inclusive) is date else "미지정"
    st.caption(f"{mode}  |  {start} ~ {end} (양끝 날짜 포함)")
    if request.mode == "live":
        st.text(request.question)
    if result.state == State.SUCCESS:
        st.success(result.message)
    elif result.state in {State.NO_DATA, State.CLARIFY, State.UNSUPPORTED, State.ROW_LIMIT}:
        st.warning(result.message)
    else:
        st.error(result.message)
    if result.error_code in ERROR_HELP:
        st.info(ERROR_HELP[result.error_code])
    if result.state == State.SUCCESS and result.rows:
        summaries = charts.cards(result.metric, result.rows)
        for offset in range(0, len(summaries), 2):
            row = summaries[offset:offset + 2]
            for column, (label, value) in zip(st.columns(len(row)), row):
                column.metric(label, value, border=True)
        st.caption(dashboard.METRIC_NOTES[result.metric])
    elif result.state == State.ROW_LIMIT:
        st.caption("표·그래프는 표시된 일부 행입니다. 전체 기간 합계 카드는 표시하지 않습니다.")
    chart_tab, table_tab, sql_tab, info_tab = st.tabs(["차트", "집계 표", "SQL·계산 기준", "실행 정보"])
    with chart_tab:
        if result.state in {State.SUCCESS, State.ROW_LIMIT} and result.rows:
            for index, (title, figure) in enumerate(charts.figures(result.metric, result.rows)):
                st.markdown(f"#### {title}")
                st.plotly_chart(figure, key=f"chart_{index}", width="stretch", on_select="ignore",
                                config={"displaylogo": False}, alt=title)
            st.caption("관측이 없는 월·결측은 0으로 채우지 않습니다. 정확한 금액은 집계 표·카드에서 확인하세요.")
        else:
            st.info("표시할 집계 결과가 없습니다. 질문·기간 또는 오류 안내를 확인하세요.")
    with table_tab:
        if result.rows:
            st.dataframe(charts.table(result.rows, result.columns), hide_index=True, width="stretch")
            st.caption("—는 결측입니다. 확인된 상품금액 소계와 완전한 상품금액을 구분합니다.")
        else:
            st.info("집계 결과 없음 · 임의로 0이나 수치를 만들지 않습니다.")
    with sql_tab:
        if result.sql:
            st.code(result.sql, language="sql")
        st.caption("기간은 시작 포함·종료 제외 값으로 안전하게 바인딩됩니다. 화면의 마지막 날짜는 포함합니다.")
        for note in result.limitations:
            st.write("• " + note)
        if result.coverage:
            st.caption(f"전체 구매 관측 범위: {result.coverage.get('first_purchase', '미확인')} ~ "
                       f"{result.coverage.get('last_purchase', '미확인')}")
    with info_tab:
        token_count = charts.usage_totals(result.usage)
        tokens = "미사용" if result.api_attempts == 0 else "미제공" if token_count is None else f"{token_count:,}"
        model_seconds = sum(event.get("elapsed_seconds", 0) for event in result.usage)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("API 요청", f"{result.api_attempts}회")
        col2.metric("사용 토큰", tokens)
        col3.metric("모델 시간", "미사용" if result.api_attempts == 0 else f"{model_seconds:.2f}초")
        col4.metric("조회 시간", "—" if result.query_elapsed_seconds is None else f"{result.query_elapsed_seconds:.2f}초")
        st.caption(f"SQL 수정 {result.sql_repairs}회 · 후보 DB 조회 {result.db_executions}회 · 자동 SDK 재시도 없음")
        if result.api_attempts:
            for index, event in enumerate(result.usage, 1):
                counts = event.get("tokens") or {}
                text = lambda name: "미제공" if counts.get(name) is None else f"{counts[name]:,}"
                st.caption(f"요청 {index}: 입력 {text('prompt_tokens')} · 출력 {text('completion_tokens')} "
                           f"· 합계 {text('total_tokens')} 토큰")
        st.code(" → ".join(result.trace), language="text")
        if result.error_code:
            st.text("종료 코드: " + result.error_code)


def main():
    st.set_page_config(page_title="InsightAgent · Olist 분석", page_icon="📊", layout="wide")
    for name in ("openai", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    st.title("InsightAgent")
    st.caption("질문에서 근거까지 · Olist 이커머스 분석")
    try:
        database = dashboard.DEFAULT_DATABASE
        stat = database.stat()
        catalog = catalog_for_revision(str(database), (stat.st_mtime_ns, stat.st_size))
    except Exception:
        st.error("로컬 분석 데이터가 준비되지 않았습니다. README의 데이터 구축 안내를 확인하세요.")
        return
    with st.sidebar:
        st.header("분석 설정")
        mode_label = st.radio("분석 방식", ["기준 분석", "AI 질문"], key="mode",
                              captions=["API 없이 검증된 지표 조회", "NVIDIA 모델로 자연어 질문"])
        mode = "reference" if mode_label == "기준 분석" else "live"
        metric = "monthly_sales"
        if mode == "reference":
            metric = st.selectbox("분석 지표", list(dashboard.METRIC_NAMES),
                                  format_func=dashboard.METRIC_NAMES.get, key="metric")
        if mode == "live":
            st.caption("질문에서 지원 지표 4개 중 하나를 선택합니다.")
            st.caption("API 설정 준비됨" if dashboard.api_ready() else "API 설정이 필요합니다. 로컬 .env를 확인하세요.")
        st.divider()
        st.markdown("**사용 가능한 데이터**")
        st.caption(f"구매일 {catalog.first_purchase} ~ {catalog.last_purchase}")
        st.metric("관측 주문", f"{catalog.orders:,}건")
        st.caption(f"배송 완료 {catalog.delivered_orders:,}건 · 과거 공개 데이터")
        st.caption("지원: 승인 지표 4개·기간 변경. 원본 고객·리뷰 조회는 지원하지 않습니다.")
    first, last = dashboard.default_window(catalog)
    with st.form("analysis", enter_to_submit=False):
        st.subheader("데이터에 질문하기" if mode == "live" else "기준 지표 살펴보기")
        if mode == "live":
            question = st.text_area("분석 질문", value="선택 기간의 월별 매출과 주문수를 보여줘.",
                                    max_chars=2000, key="question")
            allow_repair = st.checkbox("응답 수정 1회 허용", value=False, key="allow_repair",
                                       help="추가 API 사용량이 발생할 수 있습니다. 인증·한도·위험 SQL 오류는 재시도하지 않습니다.")
        else:
            question, allow_repair = "", False
            st.caption(dashboard.METRIC_NOTES[metric])
        col1, col2 = st.columns(2)
        start = col1.date_input("시작일", value=first, key="start", format="YYYY-MM-DD")
        end = col2.date_input("마지막 날짜 (포함)", value=last, key="end", format="YYYY-MM-DD")
        st.caption("구매일 기준입니다. 관측 범위를 벗어난 기간에는 데이터가 없을 수 있습니다.")
        submitted = st.form_submit_button("분석 실행", type="primary", width="stretch")
    if submitted:
        request = dashboard.AnalysisRequest(mode, metric, start, end, question, allow_repair)
        with st.spinner("SQL을 확인하고 읽기 전용으로 조회하고 있습니다…"):
            result = dashboard.analyze(request)
        st.session_state["last_analysis"] = dashboard.Snapshot(request, result)
    if "last_analysis" in st.session_state:
        render_snapshot(st.session_state["last_analysis"])
    else:
        st.info("지표와 기간을 선택해 분석을 실행하세요. AI 질문도 버튼을 누를 때만 API를 사용합니다.")


if __name__ == "__main__":
    main()
