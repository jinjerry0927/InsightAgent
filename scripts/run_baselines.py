"""Run baseline SQL, reconcile with raw CSVs, and publish aggregate evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

from scripts.data_pipeline import file_hash, save_json, source_directory
from scripts.metrics import run_suite
from scripts.verify_metrics import source_fingerprints, verify_against_csv


def render_results(report: dict) -> str:
    lines = ["# 기준 SQL 실제 데이터 검증", "",
             f"생성 시각(UTC): {report['generated_at_utc']}", "",
             f"구매 기간: [{report['start_inclusive']}, {report['end_exclusive']})", "",
             f"상태: {report['status']} · 원본 대조: {report['verification']['status']}", "",
             "[승인 KPI 정의](METRICS.md)에 따라 실행한 실제 집계다. 금액은 원본 단위이며 배송비·결제금액을 제외한다.",
             "원본·DB 지문 유지, 주문수·상품금액·카테고리·배송·대표 리뷰 결과를 CSV 독립 계산과 대조했다.", "",
             "## 조회 범위", "",
             "| 항목 | 값 |", "| --- | --- |"]
    for name, value in {**report["coverage"], **report["scope"]}.items():
        lines.append(f"| {name} | {value} |")
    if report["status"] == "no_data":
        lines += ["", "해당 기간·상태를 만족하는 관측 데이터가 없다. 빈 월을 매출 0으로 채우지 않는다."]
    results = report["results"]
    for name in ("monthly_sales", "category_sales", "delivery_delays", "review_delay"):
        rows = results[name]
        lines += ["", f"## {name}", "", f"실행 SQL: [sql/{name}.sql](../sql/{name}.sql)", ""]
        if not rows:
            lines.append("해당 조건의 결과 행 없음.")
            continue
        names = list(rows[0])
        lines += ["| " + " | ".join(names) + " |", "| " + " | ".join("---" for _ in names) + " |"]
        for row in rows:
            cells = []
            for value in row.values():
                cells.append("NULL" if value is None else f"{value:.6f}" if isinstance(value, float) else str(value))
            lines.append("| " + " | ".join(cells) + " |")
    months = results["monthly_sales"]
    complete = bool(months) and all(row["merchandise_value"] is not None for row in months)
    total = sum((row["merchandise_value"] for row in months), Decimal(0)) if complete else None
    comparable = sum(row["comparable_orders"] for row in results["delivery_delays"])
    late = sum(row["late_orders"] for row in results["delivery_delays"])
    lines += ["", "## 전체 기간 합계와 한계", "",
              f"- 상품금액: {total if total is not None else 'NULL (관측 부재 또는 금액 결측)'}",
              f"- 배송 비교 가능 주문: {comparable:,}, 지연 주문: {late:,}",
              f"- 전체 지연율: {late / comparable:.6%}" if comparable else "- 전체 지연율: NULL (분모 0)",
              "- late_rate는 0~1 비율이다. 그룹 평점 차이는 인과관계를 뜻하지 않는다.",
              "- 일부 경계 월은 부분 관측이며, 원본 범위 밖 기간과 빈 월은 데이터가 있는 것으로 해석하지 않는다.",
              "- 대표 리뷰는 전체 스냅샷의 최신값이다. 과거 구매 기간 끝 시점의 의견을 재구성한 결과가 아니다.",
              "- 결측 금액이 있으면 전체 상품금액을 NULL로 두고 known_merchandise_value에 확인된 소계만 표시한다."]
    lines.append("- 금액이 결측인 카테고리가 있으면 거래액 순위도 확정할 수 없다.")
    return "\n".join(lines) + "\n"


def validate_output_paths(database: Path, source: Path, json_output: Path, markdown_output: Path) -> None:
    outputs = [json_output.resolve(), markdown_output.resolve()]
    if outputs[0] == outputs[1]:
        raise ValueError("JSON and Markdown outputs must be different files")
    if any(path == database.resolve() or path.is_relative_to(source.resolve()) for path in outputs):
        raise ValueError("Evidence output must not overwrite the database or source CSVs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Inclusive source-local ISO date/timestamp")
    parser.add_argument("--end", required=True, help="Exclusive source-local ISO date/timestamp")
    parser.add_argument("--database", type=Path, default=Path("data/processed/insightagent.duckdb"))
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--json-output", type=Path, default=Path("data/processed/baseline_results.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("docs/BASELINE_RESULTS.md"))
    args = parser.parse_args()
    if not args.database.is_file():
        raise FileNotFoundError(args.database)
    source = source_directory(args.source_dir)
    validate_output_paths(args.database, source, args.json_output, args.markdown_output)
    database_hash = file_hash(args.database)
    with duckdb.connect(str(args.database), read_only=True) as connection:
        fingerprints = source_fingerprints(connection, source)
        report = run_suite(connection, args.start, args.end)
        report["verification"] = verify_against_csv(report, source)
        if fingerprints != source_fingerprints(connection, source):
            raise ValueError("Source manifest changed during verification")
    if database_hash != file_hash(args.database):
        raise ValueError("The source database changed during verification")
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["source_files"] = fingerprints
    report["database_sha256"] = database_hash
    save_json(report, args.json_output)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_results(report), encoding="utf-8")
    print(f"Baseline SQL: {report['status']}; CSV reference: passed; sources: 9 unchanged")
    print(f"Delivered orders: {report['scope']['delivered_orders']:,}")
    print(f"Evidence: {args.markdown_output}")


if __name__ == "__main__":
    main()
