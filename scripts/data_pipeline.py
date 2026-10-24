"""Typed Olist loading and descriptive quality checks; no business KPI logic."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import duckdb


SCHEMAS = {
    "customers": {
        "customer_id": "VARCHAR", "customer_unique_id": "VARCHAR",
        "customer_zip_code_prefix": "VARCHAR", "customer_city": "VARCHAR",
        "customer_state": "VARCHAR",
    },
    "geolocation": {
        "geolocation_zip_code_prefix": "VARCHAR", "geolocation_lat": "DOUBLE",
        "geolocation_lng": "DOUBLE", "geolocation_city": "VARCHAR",
        "geolocation_state": "VARCHAR",
    },
    "order_items": {
        "order_id": "VARCHAR", "order_item_id": "BIGINT", "product_id": "VARCHAR",
        "seller_id": "VARCHAR", "shipping_limit_date": "TIMESTAMP",
        "price": "DECIMAL(18,2)", "freight_value": "DECIMAL(18,2)",
    },
    "order_payments": {
        "order_id": "VARCHAR", "payment_sequential": "BIGINT", "payment_type": "VARCHAR",
        "payment_installments": "BIGINT", "payment_value": "DECIMAL(18,2)",
    },
    "order_reviews": {
        "review_id": "VARCHAR", "order_id": "VARCHAR", "review_score": "BIGINT",
        "review_comment_title": "VARCHAR", "review_comment_message": "VARCHAR",
        "review_creation_date": "TIMESTAMP", "review_answer_timestamp": "TIMESTAMP",
    },
    "orders": {
        "order_id": "VARCHAR", "customer_id": "VARCHAR", "order_status": "VARCHAR",
        "order_purchase_timestamp": "TIMESTAMP", "order_approved_at": "TIMESTAMP",
        "order_delivered_carrier_date": "TIMESTAMP",
        "order_delivered_customer_date": "TIMESTAMP",
        "order_estimated_delivery_date": "TIMESTAMP",
    },
    "products": {
        "product_id": "VARCHAR", "product_category_name": "VARCHAR",
        "product_name_lenght": "BIGINT", "product_description_lenght": "BIGINT",
        "product_photos_qty": "BIGINT", "product_weight_g": "BIGINT",
        "product_length_cm": "BIGINT", "product_height_cm": "BIGINT",
        "product_width_cm": "BIGINT",
    },
    "sellers": {
        "seller_id": "VARCHAR", "seller_zip_code_prefix": "VARCHAR",
        "seller_city": "VARCHAR", "seller_state": "VARCHAR",
    },
    "category_translation": {
        "product_category_name": "VARCHAR", "product_category_name_english": "VARCHAR",
    },
}

FILENAMES = {
    name: f"olist_{name}_dataset.csv" for name in SCHEMAS
    if name != "category_translation"
}
FILENAMES["category_translation"] = "product_category_name_translation.csv"

TABLE_ROLES = {
    "customers": "주문용 고객 ID와 고유 고객 ID·지역 연결",
    "geolocation": "우편번호 접두사별 여러 좌표·지역명",
    "order_items": "주문 내 상품 행·판매자·상품금액·배송비",
    "order_payments": "주문 내 결제 순번·수단·금액",
    "order_reviews": "주문별 리뷰 이벤트·평점·텍스트",
    "orders": "주문 상태·고객 연결·구매·배송 시각",
    "products": "상품 ID·카테고리·물리적 속성",
    "sellers": "판매자 ID·지역",
    "category_translation": "상품 카테고리 원문과 영어 이름 연결",
}

# These are candidates to measure, not constraints that silently drop bad rows.
KEY_CANDIDATES = {
    "customers": [("customer_id",), ("customer_unique_id",)],
    "geolocation": [("geolocation_zip_code_prefix",)],
    "order_items": [("order_id", "order_item_id")],
    "order_payments": [("order_id", "payment_sequential")],
    "order_reviews": [("review_id",), ("review_id", "order_id")],
    "orders": [("order_id",)], "products": [("product_id",)],
    "sellers": [("seller_id",)],
    "category_translation": [("product_category_name",)],
}

RELATIONSHIPS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("order_payments", "order_id", "orders", "order_id"),
    ("order_reviews", "order_id", "orders", "order_id"),
    ("products", "product_category_name", "category_translation", "product_category_name"),
]


def source_directory(path: Path) -> Path:
    """Accept CSVs directly or in exactly one immediate archive subdirectory."""
    path = path.resolve()
    if not path.is_dir():
        raise ValueError(f"Source directory does not exist: {path}")
    candidates = [path, *sorted(p for p in path.iterdir() if p.is_dir())]
    complete = [p for p in candidates if all((p / f).is_file() for f in FILENAMES.values())]
    if len(complete) != 1:
        raise ValueError(
            f"Expected exactly one directory with all {len(FILENAMES)} Olist CSV files; "
            f"found {len(complete)} under {path}"
        )
    return complete[0]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_headers(source: Path) -> None:
    for table, columns in SCHEMAS.items():
        with (source / FILENAMES[table]).open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        if header != list(columns):
            raise ValueError(f"Unexpected CSV header: {FILENAMES[table]}")


def build_database(source: Path, output: Path) -> dict:
    """Build a new database without modifying source files or existing output."""
    source = source_directory(source)
    validate_headers(source)
    output = output.resolve()
    if output.suffix != ".duckdb" or output.is_relative_to(source):
        raise ValueError("Output must be a .duckdb file outside the source directory")
    if output.exists():
        raise FileExistsError(f"Output already exists; choose a new output path: {output}")
    manifest = {
        name: {"filename": filename, "sha256": file_hash(source / filename)}
        for name, filename in FILENAMES.items()
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}-{uuid4().hex}.duckdb")
    try:
        with duckdb.connect(str(temporary)) as connection:
            connection.execute("BEGIN TRANSACTION")
            for table, columns in SCHEMAS.items():
                # Use the tested SQL reader; materialize once before validation/casting.
                connection.execute(
                    "CREATE OR REPLACE TEMP TABLE _raw_import AS SELECT * FROM "
                    "read_csv(?, header=true, all_varchar=true, strict_mode=true)",
                    [str(source / FILENAMES[table])],
                ).fetchall()
                for column, dtype in columns.items():
                    if dtype == "VARCHAR":
                        continue
                    invalid = f'TRY_CAST("{column}" AS {dtype}) IS NULL'
                    if dtype.startswith("DECIMAL"):
                        invalid += (
                            f' OR NOT regexp_full_match("{column}", '
                            "'[+-]?[0-9]+(\\.[0-9]{1,2})?')"
                        )
                    elif dtype == "BIGINT":
                        invalid += (
                            f' OR TRY_CAST("{column}" AS DOUBLE) '
                            f'!= trunc(TRY_CAST("{column}" AS DOUBLE))'
                        )
                    count = connection.execute(
                        f'SELECT COUNT(*) FROM _raw_import WHERE "{column}" IS NOT NULL '
                        f"AND ({invalid})"
                    ).fetchall()[0][0]
                    if count:
                        raise ValueError(f"{table}.{column}: {count} invalid or lossy {dtype} values")
                selections = ", ".join(
                    f'CAST("{column}" AS {dtype}) AS "{column}"'
                    for column, dtype in columns.items()
                )
                connection.execute(f'CREATE TABLE "{table}" AS SELECT {selections} FROM _raw_import')
                raw_count = connection.execute("SELECT COUNT(*) FROM _raw_import").fetchall()[0][0]
                typed_count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchall()[0][0]
                if raw_count != typed_count:
                    raise ValueError(f"Row count changed during conversion: {table}")
                manifest[table]["rows"] = typed_count
            connection.execute(
                "CREATE TABLE _source_files "
                "(table_name VARCHAR PRIMARY KEY, filename VARCHAR, sha256 VARCHAR, row_count BIGINT)"
            )
            connection.executemany(
                "INSERT INTO _source_files VALUES (?, ?, ?, ?)",
                [(name, m["filename"], m["sha256"], m["rows"]) for name, m in manifest.items()],
            )
            for name, info in manifest.items():
                if file_hash(source / info["filename"]) != info["sha256"]:
                    raise ValueError(f"Source changed during loading: {name}")
            connection.execute("COMMIT")
        if output.exists():
            raise FileExistsError(f"Output appeared during loading: {output}")
        temporary.rename(output)
    finally:
        # Only remove task-created temporary files within the verified output folder.
        for path in (temporary, temporary.with_suffix(".duckdb.wal")):
            if path.resolve().parent != output.parent:
                raise RuntimeError("Unexpected temporary file location")
            path.unlink(missing_ok=True)
    return manifest


def _records(connection, sql: str) -> list[dict]:
    cursor = connection.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def profile_database(database: Path) -> dict:
    """Measure quality without dropping duplicates, imputing, or defining KPIs."""
    if not database.is_file():
        raise FileNotFoundError(database)
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "tables": {}}
    with duckdb.connect(str(database), read_only=True) as connection:
        report["source_files"] = _records(connection, "SELECT * FROM _source_files ORDER BY table_name")
        for table, columns in SCHEMAS.items():
            rows = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            unique = connection.execute(f'SELECT COUNT(*) FROM (SELECT DISTINCT * FROM "{table}")').fetchone()[0]
            stats = {"rows": rows, "duplicate_rows": rows - unique, "columns": {}, "keys": {}}
            for column, dtype in columns.items():
                nulls, distinct = connection.execute(
                    f'SELECT COUNT(*) FILTER (WHERE "{column}" IS NULL), '
                    f'COUNT(DISTINCT "{column}") FROM "{table}"'
                ).fetchone()
                info = {"type": dtype, "nulls": nulls, "distinct_non_null": distinct}
                if dtype != "VARCHAR":
                    minimum, maximum = connection.execute(
                        f'SELECT MIN("{column}"), MAX("{column}") FROM "{table}"'
                    ).fetchone()
                    info.update(minimum=minimum, maximum=maximum)
                stats["columns"][column] = info
            for key in KEY_CANDIDATES[table]:
                quoted = ", ".join(f'"{col}"' for col in key)
                present = " AND ".join(f'"{col}" IS NOT NULL' for col in key)
                non_null = connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {present}').fetchone()[0]
                unique = connection.execute(
                    f'SELECT COUNT(*) FROM (SELECT DISTINCT {quoted} FROM "{table}" WHERE {present})'
                ).fetchone()[0]
                stats["keys"][", ".join(key)] = {
                    "null_key_rows": rows - non_null, "distinct_keys": unique,
                    "duplicate_key_rows": non_null - unique,
                }
            report["tables"][table] = stats

        report["relationships"] = []
        for child, child_key, parent, parent_key in RELATIONSHIPS:
            missing = connection.execute(
                f'SELECT COUNT(*) FROM "{child}" c WHERE c."{child_key}" IS NOT NULL '
                f'AND NOT EXISTS (SELECT 1 FROM "{parent}" p WHERE p."{parent_key}" = c."{child_key}")'
            ).fetchone()[0]
            report["relationships"].append({
                "child": f"{child}.{child_key}", "parent": f"{parent}.{parent_key}",
                "unmatched_non_null_rows": missing,
            })

        report["order_statuses"] = _records(connection, """
            SELECT order_status, COUNT(*) AS rows,
                COUNT(*) FILTER (WHERE order_delivered_customer_date IS NULL) AS missing_delivery,
                COUNT(*) FILTER (WHERE order_approved_at IS NULL) AS missing_approval
            FROM orders GROUP BY order_status ORDER BY rows DESC
        """)
        report["purchase_months"] = _records(connection, """
            SELECT strftime(order_purchase_timestamp, '%Y-%m') AS month, COUNT(*) AS rows
            FROM orders GROUP BY 1 ORDER BY 1
        """)
        report["fanout"] = _records(connection, """
            WITH i AS (SELECT order_id, COUNT(*) AS n FROM order_items GROUP BY order_id),
                 p AS (SELECT order_id, COUNT(*) AS n FROM order_payments GROUP BY order_id),
                 r AS (SELECT order_id, COUNT(*) AS n FROM order_reviews GROUP BY order_id)
            SELECT COUNT(*) AS orders,
                COUNT(*) FILTER (WHERE i.n > 1) AS multiple_items,
                COUNT(*) FILTER (WHERE p.n > 1) AS multiple_payments,
                COUNT(*) FILTER (WHERE r.n > 1) AS multiple_reviews,
                SUM(greatest(coalesce(i.n, 0), 1) * greatest(coalesce(p.n, 0), 1)
                    * greatest(coalesce(r.n, 0), 1)) AS predicted_left_join_rows
            FROM orders o LEFT JOIN i USING (order_id)
            LEFT JOIN p USING (order_id) LEFT JOIN r USING (order_id)
        """)[0]
        actual_join = connection.execute("""
            SELECT COUNT(*) FROM orders o LEFT JOIN order_items i USING (order_id)
            LEFT JOIN order_payments p USING (order_id) LEFT JOIN order_reviews r USING (order_id)
        """).fetchone()[0]
        report["fanout"]["actual_left_join_rows"] = actual_join
        if actual_join != report["fanout"]["predicted_left_join_rows"]:
            raise ValueError("Join fanout counts do not agree")
        report["review_text"] = _records(connection, """
            SELECT COUNT(*) AS rows,
                COUNT(*) FILTER (WHERE nullif(trim(review_comment_title), '') IS NOT NULL) AS with_title,
                COUNT(*) FILTER (WHERE nullif(trim(review_comment_message), '') IS NOT NULL) AS with_message,
                COUNT(*) FILTER (WHERE nullif(trim(review_comment_title), '') IS NOT NULL
                    OR nullif(trim(review_comment_message), '') IS NOT NULL) AS with_any_text
            FROM order_reviews
        """)[0]
        report["review_scores"] = _records(connection,
            "SELECT review_score, COUNT(*) AS rows FROM order_reviews GROUP BY review_score ORDER BY review_score")
        report["delivery_anomalies"] = _records(connection, """
            SELECT COUNT(*) FILTER (WHERE order_delivered_customer_date < order_purchase_timestamp)
                AS delivered_before_purchase FROM orders
        """)[0]
    return report


def save_json(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def render_profile(report: dict) -> str:
    """Render aggregate-only evidence; never publish individual IDs or review text."""
    lines = [
        "# Olist 데이터 실측 보고서", "",
        f"생성 시각(UTC): {report['generated_at_utc']}", "",
        "`python -m scripts.profile_data`로 생성한 로컬 실측 결과다. 원본 행을 삭제·중복 제거·보정하지 않았다.",
        "KPI 계산 기준은 [METRICS.md](METRICS.md)의 승인 대기 초안을 참조한다.", "",
        "## 테이블·파일 근거", "",
        "| 테이블 | 역할 | 파일 | 행 수 | 타입 변환 후 전체 컬럼 중복 행(초과분) |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for source in report["source_files"]:
        table = source["table_name"]
        lines.append(f"| {table} | {TABLE_ROLES[table]} | {source['filename']} | {report['tables'][table]['rows']:,} | {report['tables'][table]['duplicate_rows']:,} |")
    lines += ["", "## 컬럼 타입·결측·범위", "",
              "빈 CSV 필드는 NULL로 적재했다. 식별자·우편번호는 VARCHAR, 금액은 DECIMAL(18,2)이다.",
              "TIMESTAMP는 원본의 시간대 없는 값을 보존한다. 아래 날짜 범위가 모든 기간에 데이터가 존재함을 뜻하지는 않는다."]
    for table, stats in report["tables"].items():
        lines += ["", f"### {table}", "", "| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |", "| --- | --- | ---: | ---: | --- | --- |"]
        for name, col in stats["columns"].items():
            lines.append(f"| {name} | {col['type']} | {col['nulls']:,} | {col['distinct_non_null']:,} | {col.get('minimum', '—')} | {col.get('maximum', '—')} |")
    lines += ["", "## 키 후보 검증", "", "고유 고객 식별자와 우편번호의 반복은 기본키로 쓸 수 없다는 근거다. 반복 자체를 오류로 삭제하지 않는다.", "",
              "| 테이블 | 후보 키 | NULL 키 행 | 고유 키 수 | 중복 키 행(초과분) |", "| --- | --- | ---: | ---: | ---: |"]
    for table, stats in report["tables"].items():
        for key, info in stats["keys"].items():
            lines.append(f"| {table} | {key} | {info['null_key_rows']:,} | {info['distinct_keys']:,} | {info['duplicate_key_rows']:,} |")
    lines += ["", "## 연결 키 검사", "", "NULL인 자식 키는 별도 컬럼 결측 표에서 확인한다.", "",
              "| 자식 | 부모 | NULL 제외 연결되지 않는 행 |", "| --- | --- | ---: |"]
    for relation in report["relationships"]:
        lines.append(f"| {relation['child']} | {relation['parent']} | {relation['unmatched_non_null_rows']:,} |")
    lines += ["", "## 주문 상태·배송 결측", "", "| 상태 | 행 수 | 고객 배송일 NULL | 승인일 NULL |", "| --- | ---: | ---: | ---: |"]
    for status in report["order_statuses"]:
        lines.append(f"| {status['order_status']} | {status['rows']:,} | {status['missing_delivery']:,} | {status['missing_approval']:,} |")
    lines += ["", "## 구매 월별 원본 행 분포", "", "전체 상태의 원본 주문 행 수다. 승인된 주문수 KPI가 아니다. 표에 없는 월은 관측 행이 없다.", "",
              "| 구매 월 | 원본 주문 행 수 |", "| --- | ---: |"]
    for month in report["purchase_months"]:
        lines.append(f"| {month['month']} | {month['rows']:,} |")
    f = report["fanout"]
    lines += ["", "## 다중 연결 집계 위험", "",
              f"- 원본 주문 행: {f['orders']:,}",
              f"- 상품이 여러 행인 주문: {f['multiple_items']:,}",
              f"- 결제가 여러 행인 주문: {f['multiple_payments']:,}",
              f"- 리뷰가 여러 행인 주문: {f['multiple_reviews']:,}",
              f"- 주문→상품→결제→리뷰 LEFT JOIN 예상 행 수: {f['predicted_left_join_rows']:,}",
              f"- 실제 동일 JOIN의 COUNT(*) 검증: {f['actual_left_join_rows']:,}",
              "- JOIN 전 상품·결제·리뷰를 필요한 단위로 먼저 집계해야 한다. 이 검사는 매출 KPI 구현이 아니다.",
              "", "## 리뷰 텍스트", ""]
    for label, count in report["review_text"].items():
        lines.append(f"- {label}: {count:,}")
    lines += ["", "| 평점 | 행 수 |", "| --- | ---: |"]
    for score in report["review_scores"]:
        lines.append(f"| {score['review_score']} | {score['rows']:,} |")
    lines += ["", "## 날짜 이상값", "",
              f"- 구매보다 이른 고객 배송일: {report['delivery_anomalies']['delivered_before_purchase']:,}행", "",
              "## 로컬 원본 SHA-256", "", "공식 배포 체크섬과 비교한 인증값이 아니라, 이번 로컬 입력의 재현용 지문이다.", "",
              "| 파일 | SHA-256 |", "| --- | --- |"]
    for source in report["source_files"]:
        lines.append(f"| {source['filename']} | {source['sha256']} |")
    return "\n".join(lines) + "\n"
