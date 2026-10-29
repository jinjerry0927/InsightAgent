"""Fail-closed DuckDB 2.0 AST policy. Parsing never executes the candidate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import duckdb

# Only these projections are exposed to candidate SQL in the worker database.
TABLE_COLUMNS = {
    "orders": ("order_id", "order_status", "order_purchase_timestamp",
               "order_delivered_customer_date", "order_estimated_delivery_date"),
    "order_items": ("order_id", "product_id", "price"),
    "products": ("product_id", "product_category_name"),
    "category_translation": ("product_category_name", "product_category_name_english"),
    "order_reviews": ("review_id", "order_id", "review_score",
                      "review_creation_date", "review_answer_timestamp"),
}
MAX_SQL_CHARS = 12_000
ALLOWED_PARAMETERS = frozenset({"start_at", "end_at", "top_n"})
CLASSES = {"BETWEEN", "CASE", "CAST", "COLUMN_REF", "COMPARISON", "CONJUNCTION",
           "CONSTANT", "FUNCTION", "OPERATOR", "PARAMETER", "STAR", "TYPE", "WINDOW"}
NODE_TYPES = {
    "SELECT_NODE", "EMPTY", "BASE_TABLE", "JOIN", "ORDER_MODIFIER", "LIMIT_MODIFIER",
    "ASCENDING", "DESCENDING", "ORDER_DEFAULT", "CASE_EXPR", "COLUMN_REF",
    "COMPARE_BETWEEN", "COMPARE_NOT_BETWEEN", "COMPARE_EQUAL", "COMPARE_NOTEQUAL",
    "COMPARE_GREATERTHAN", "COMPARE_GREATERTHANOREQUALTO", "COMPARE_LESSTHAN",
    "COMPARE_LESSTHANOREQUALTO", "CONJUNCTION_AND", "CONJUNCTION_OR", "FUNCTION",
    "OPERATOR_CAST", "OPERATOR_COALESCE", "OPERATOR_IS_NOT_NULL", "OPERATOR_IS_NULL",
    "OPERATOR_NOT", "STAR", "TYPE", "VALUE_CONSTANT", "VALUE_PARAMETER", "WINDOW_ROW_NUMBER",
}
FUNCTIONS = {"sum", "avg", "min", "max", "count", "count_star", "date_trunc", "nullif",
             "row_number", "+", "-", "*", "/"}
CAST_TYPES = {"DATE", "TIMESTAMP", "DECIMAL", "DOUBLE", "FLOAT", "BIGINT", "INTEGER",
              "VARCHAR", "BOOLEAN"}


class SQLBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__("허용된 조회 SQL 정책을 만족하지 않아 실행을 차단했습니다.")
        self.code = code


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str = field(repr=False)
    parameters: tuple[str, ...]
    tables: tuple[str, ...]


def objects(value):
    pending = [value]
    count = 0
    while pending:
        current = pending.pop()
        count += 1
        if count > 10_000:
            raise SQLBlocked("complexity")
        if isinstance(current, dict):
            yield current
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


def scoped_tables(query: dict, inherited: frozenset[str] = frozenset()) -> set[str]:
    visible, used = set(inherited), set()
    for entry in query["cte_map"]["map"]:
        name = entry["key"].lower()
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", name) or name in TABLE_COLUMNS:
            raise SQLBlocked("cte")
        used.update(scoped_tables(entry["value"]["query_node"], frozenset(visible)))
        visible.add(name)
    for node in objects({key: value for key, value in query.items() if key != "cte_map"}):
        if node.get("type") == "BASE_TABLE":
            name = node["table_name"].lower()
            if name not in visible and name not in TABLE_COLUMNS:
                raise SQLBlocked("table")
            if name in TABLE_COLUMNS:
                used.add(name)
    return used


def validate_sql(sql: str) -> ValidatedSQL:
    if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL_CHARS:
        raise SQLBlocked("input_size")
    if duckdb.__version__ != "2.0.0":
        raise SQLBlocked("engine_version")
    try:
        with duckdb.connect(":memory:", config={
            "enable_external_access": "false", "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false", "max_expression_depth": "128",
            "memory_limit": "32MB", "threads": "1",
        }) as parser:
            serialized = parser.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
            tree = json.loads(serialized)
            if tree.get("error") or len(tree.get("statements", [])) != 1:
                raise SQLBlocked("statement")
            statement = tree["statements"][0]
            if statement["node"]["type"] != "SELECT_NODE":
                raise SQLBlocked("statement")
            nodes = list(objects(tree))
            used_tables = scoped_tables(statement["node"])
            parameters = set()
            for node in nodes:
                if "class" in node and node["class"] not in CLASSES:
                    raise SQLBlocked("expression")
                if "type" in node and node["type"] not in NODE_TYPES:
                    raise SQLBlocked("syntax")
                if node.get("sample") is not None or node.get("at_clause") is not None:
                    raise SQLBlocked("syntax")
                if node.get("schema") or node.get("catalog"):
                    raise SQLBlocked("qualified_access")
                if "function_name" in node:
                    function = node["function_name"].lower()
                    if function not in FUNCTIONS or node.get("export_state"):
                        raise SQLBlocked("function")
                    if node.get("qualified_name", {}).get("path", [function]) != [node["function_name"]]:
                        raise SQLBlocked("qualified_access")
                if node.get("type") == "BASE_TABLE":
                    table = node["table_name"].lower()
                    if node.get("schema_name") or node.get("catalog_name"):
                        raise SQLBlocked("qualified_access")
                if node.get("class") == "TYPE" and node["type_name"].upper() not in CAST_TYPES:
                    raise SQLBlocked("cast")
                if node.get("class") == "COLUMN_REF" and len(node["column_names"]) > 2:
                    raise SQLBlocked("qualified_access")
                if node.get("class") == "PARAMETER":
                    name = node["identifier"]
                    if name not in ALLOWED_PARAMETERS:
                        raise SQLBlocked("parameter")
                    parameters.add(name)
                if node.get("type") == "JOIN":
                    if (node.get("ref_type") != "REGULAR" or node.get("is_implicit")
                            or not node.get("condition") and not node.get("using_columns")):
                        raise SQLBlocked("join")
                if node.get("class") == "STAR":
                    if (node.get("columns") or node.get("expr") or node.get("replace_list")
                            or node.get("rename_list") or node.get("exclude_list")):
                        raise SQLBlocked("star")
            if not used_tables:
                raise SQLBlocked("table")
            # Execute a serialization of the checked AST, never the original model text.
            canonical = parser.execute("SELECT json_deserialize_sql(?)", [serialized]).fetchone()[0]
            return ValidatedSQL(canonical, tuple(sorted(parameters)), tuple(sorted(used_tables)))
    except SQLBlocked:
        raise
    except (duckdb.Error, ValueError, KeyError, TypeError, RecursionError):
        raise SQLBlocked("parse") from None
