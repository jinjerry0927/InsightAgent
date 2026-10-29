"""Deterministic presentation of verified rows; floats are only for chart geometry."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go

BLUE, ORANGE = "#2563EB", "#E68A2E"
COLUMN_LABELS = {
    "purchase_month": "구매 월", "order_count": "주문수", "item_count": "상품 행수",
    "orders_without_items": "상품 누락 주문", "items_without_price": "가격 결측 상품 행",
    "known_merchandise_value": "확인된 상품금액(소계)", "merchandise_value": "상품금액",
    "category_code": "카테고리 코드", "category_name": "카테고리",
    "delivered_orders": "배송 완료 주문", "comparable_orders": "배송 비교 가능 주문",
    "excluded_delivery_orders": "배송 비교 제외", "missing_delivery_orders": "실제 배송일 결측",
    "missing_estimate_orders": "예정 배송일 결측", "late_orders": "지연 주문",
    "on_time_orders": "정상 배송 주문", "late_rate": "지연율",
    "delivery_group": "배송 그룹", "rated_orders": "유효 평점 주문",
    "excluded_unrated_orders": "평점 제외 주문", "mean_review_score": "평균 평점",
}


def money(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def percentage(numerator: int, denominator: int) -> str:
    return "—" if not denominator else f"{Decimal(numerator) * 100 / Decimal(denominator):.2f}%"


def complete_money(rows: list[dict]) -> Decimal | None:
    values = [row["merchandise_value"] for row in rows]
    return sum(values, Decimal(0)) if values and all(value is not None for value in values) else None


def cards(metric: str, rows: list[dict]) -> list[tuple[str, str]]:
    total = lambda name: sum(row[name] for row in rows)
    if metric == "monthly_sales":
        return [("상품금액 · 원본 단위", money(complete_money(rows))),
                ("배송 완료 주문", f"{total('order_count'):,}건"),
                ("상품 행수", f"{total('item_count'):,}행"),
                ("가격 결측 상품 행", f"{total('items_without_price'):,}행")]
    if metric == "category_sales":
        return [("표시된 TOP 5 상품금액", money(complete_money(rows))),
                ("표시 카테고리", f"{len(rows)}개"),
                ("가격 결측 상품 행", f"{total('items_without_price'):,}행")]
    if metric == "delivery_delays":
        return [("배송 비교 가능 주문", f"{total('comparable_orders'):,}건"),
                ("지연 주문", f"{total('late_orders'):,}건"),
                ("기간 전체 지연율", percentage(total('late_orders'), total('comparable_orders'))),
                ("배송 비교 제외", f"{total('excluded_delivery_orders'):,}건")]
    groups = {row["delivery_group"]: row for row in rows}
    score = lambda group: ("—" if groups.get(group, {}).get("mean_review_score") is None
                           else f"{groups[group]['mean_review_score']:.2f} / 5")
    return [("유효 평점 주문", f"{total('rated_orders'):,}건"),
            ("지연 그룹 평균 평점", score("late")), ("정상 그룹 평균 평점", score("on_time")),
            ("평점 제외 주문", f"{total('excluded_unrated_orders'):,}건")]


def table(rows: list[dict], columns: tuple[str, ...]) -> pd.DataFrame:
    def display(name, value):
        if value is None:
            return "—"
        if isinstance(value, Decimal):
            return money(value)
        if isinstance(value, date):
            return value.isoformat()
        if name == "late_rate":
            return f"{value:.2%}"
        if name == "mean_review_score":
            return f"{value:.2f}"
        if name == "delivery_group":
            return {"late": "지연", "on_time": "정상 배송"}.get(value, value)
        return value
    return pd.DataFrame([{COLUMN_LABELS[name]: display(name, row[name]) for name in columns}
                         for row in rows], columns=[COLUMN_LABELS[name] for name in columns])


def monthly_points(rows: list[dict], field: str):
    observed = {row["purchase_month"]: row[field] for row in rows}
    current, last = min(observed), max(observed)
    dates, values = [], []
    while current <= last:
        dates.append(current)
        values.append(observed.get(current))  # Absence is a gap, never a zero.
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return dates, values


def figures(metric: str, rows: list[dict]) -> list[tuple[str, go.Figure]]:
    output = []
    if metric in {"monthly_sales", "delivery_delays"}:
        series = (("상품금액 추이", "merchandise_value", "상품금액 · 원본 단위"),
                  ("주문수 추이", "order_count", "주문수")) if metric == "monthly_sales" else (
                      ("배송 지연율 추이", "late_rate", "지연율 (%)"),)
        for title, field, axis in series:
            dates, values = monthly_points(rows, field)
            geometry = [None if value is None else float(value) * (100 if field == "late_rate" else 1)
                        for value in values]
            exact = ["미관측·결측" if value is None else money(value) if isinstance(value, Decimal)
                     else f"{value:.2%}" if field == "late_rate" else f"{value:,}" for value in values]
            figure = go.Figure(go.Scatter(x=dates, y=geometry, customdata=exact, mode="lines+markers",
                                         connectgaps=False, line={"color": BLUE, "width": 3},
                                         hovertemplate="%{x|%Y-%m}<br>%{customdata}<extra></extra>"))
            figure.update_layout(xaxis_title="구매 월", yaxis_title=axis)
            figure.update_xaxes(tickformat="%Y-%m")
            output.append((title, figure))
    elif metric == "category_sales":
        labels = [f"{row['category_name']} · {row['category_code']}" if row["category_code"] is not None
                  else f"{row['category_name']} · 미분류" for row in rows]
        figure = go.Figure(go.Bar(y=labels,
                                 x=[None if row["merchandise_value"] is None else float(row["merchandise_value"])
                                    for row in rows], orientation="h", marker_color=BLUE,
                                 customdata=[money(row["merchandise_value"]) for row in rows],
                                 hovertemplate="%{y}<br>%{customdata}<extra></extra>"))
        figure.update_layout(xaxis_title="상품금액 · 원본 단위", yaxis={"autorange": "reversed"})
        output.append(("상품 카테고리 TOP 5", figure))
    else:
        labels = ["지연" if row["delivery_group"] == "late" else "정상 배송" for row in rows]
        figure = go.Figure(go.Bar(x=labels, y=[row["mean_review_score"] for row in rows],
                                 customdata=[row["rated_orders"] for row in rows],
                                 marker_color=[ORANGE if row["delivery_group"] == "late" else BLUE for row in rows],
                                 hovertemplate="%{x}<br>평점 %{y:.2f} · 표본 %{customdata:,}건<extra></extra>"))
        figure.update_layout(yaxis={"title": "평균 평점", "range": [0, 5]})
        output.append(("배송 그룹별 평점과 표본", figure))
    for _, figure in output:
        figure.update_layout(template="plotly_white", height=340, margin={"l": 12, "r": 20, "t": 12, "b": 30},
                             font={"family": "sans-serif", "color": "#172235"}, showlegend=False)
    return output


def usage_totals(events: list[dict]) -> int | None:
    values = [(event.get("tokens") or {}).get("total_tokens") for event in events]
    return sum(values) if values and all(value is not None for value in values) else None
