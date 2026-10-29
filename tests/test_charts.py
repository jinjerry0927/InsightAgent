from datetime import date
from decimal import Decimal

from scripts import charts


def test_money_zero_missing_and_large_decimal_remain_distinct():
    assert charts.complete_money([{"merchandise_value": Decimal("0.00")}]) == Decimal("0.00")
    assert charts.complete_money([{"merchandise_value": None}, {"merchandise_value": Decimal("10.00")}]) is None
    exact = Decimal("9007199254740993.01")
    display = charts.table([{"merchandise_value": exact}], ("merchandise_value",))
    assert display.iloc[0, 0] == "9,007,199,254,740,993.01"
    assert charts.money(None) == "—"


def test_missing_month_is_a_gap_and_hover_keeps_exact_money():
    rows = [
        {"purchase_month": date(2018, 1, 1), "merchandise_value": Decimal("10.25"), "order_count": 2},
        {"purchase_month": date(2018, 3, 1), "merchandise_value": Decimal("0.00"), "order_count": 1},
    ]
    figure = charts.figures("monthly_sales", rows)[0][1]
    assert list(figure.data[0].y) == [10.25, None, 0.0]
    assert figure.data[0].connectgaps is False
    assert figure.data[0].customdata[0] == "10.25" and figure.data[0].customdata[2] == "0.00"


def test_delivery_summary_uses_weighted_denominator_and_empty_rate_is_unknown():
    rows = [
        {"comparable_orders": 10, "late_orders": 2, "excluded_delivery_orders": 1},
        {"comparable_orders": 90, "late_orders": 9, "excluded_delivery_orders": 3},
    ]
    values = dict(charts.cards("delivery_delays", rows))
    assert values["기간 전체 지연율"] == "11.00%"  # Not (20%+10%)/2.
    assert charts.percentage(0, 0) == "—"


def test_categories_with_same_translation_keep_distinct_codes_and_null_amount():
    rows = [{"category_name": "Same", "category_code": "a", "merchandise_value": Decimal("10.00")},
            {"category_name": "Same", "category_code": "b", "merchandise_value": None}]
    figure = charts.figures("category_sales", rows)[0][1]
    assert len(set(figure.data[0].y)) == 2
    assert list(figure.data[0].x) == [10.0, None]


def test_review_chart_exposes_sample_sizes_without_zero_filling_missing_score():
    rows = [{"delivery_group": "late", "mean_review_score": None, "rated_orders": 0},
            {"delivery_group": "on_time", "mean_review_score": 4.25, "rated_orders": 20}]
    figure = charts.figures("review_delay", rows)[0][1]
    assert list(figure.data[0].y) == [None, 4.25]
    assert list(figure.data[0].customdata) == [0, 20]


def test_incomplete_usage_is_unknown_instead_of_a_partial_total():
    assert charts.usage_totals([{"tokens": {"total_tokens": 12}}, {"tokens": None}]) is None
    assert charts.usage_totals([{"tokens": {"total_tokens": 12}}, {"tokens": {"total_tokens": 7}}]) == 19
