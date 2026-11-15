"""Column references checked locally against this run's tables, before the platform.

Table datasets no longer list columns (design 2026-11-15 MS-02), so a wrong
column name in a metric, filter, mapping or link table would only surface as a
platform rejection that costs a repair round. Seen in the 2026-11-15
regression: a refund metric used "amount" for refund_amount, and query
datasets copied schema_name from the generated table datasets.
"""

import json

from runpaths import PARTS
from table_summary import load_tables


def part_items():
    items = []
    for path in sorted(PARTS.glob("*.json")):
        try:
            value = json.loads(path.read_bytes())
        except (OSError, ValueError):
            continue
        if isinstance(value, list):
            items += [i for i in value if isinstance(i, dict)]
    return items


def dataset_columns(items, tables):
    """client_ref -> column names, for datasets whose columns are known locally."""
    by_name = {}
    for table in tables:
        by_name.setdefault(table.get("table_name"), []).append(table)
    known = {}
    for item in items:
        after = item.get("after") if isinstance(item.get("after"), dict) else {}
        if item.get("target_kind") != "dataset" or not item.get("client_ref"):
            continue
        if after.get("source_kind", "table") == "table":
            candidates = [t for t in by_name.get(after.get("table_name"), [])
                          if not after.get("schema_name") or t.get("schema_name") in (None, after.get("schema_name"))]
            if len(candidates) == 1:
                known[item["client_ref"]] = {c["name"] for c in candidates[0].get("columns") or []}
        elif after.get("columns"):
            known[item["client_ref"]] = {c.get("name") for c in after["columns"] if isinstance(c, dict)}
    return known


def column_errors(fragment, known):
    """(where, column, dataset, valid columns) for each reference to a missing column."""
    found = []

    def check(ref, column, where):
        dataset = ref.get("client_ref") if isinstance(ref, dict) else None
        if dataset in known and column not in known[dataset]:
            found.append((where, column, dataset, sorted(known[dataset])))

    def walk(value, where):
        if isinstance(value, dict):
            if isinstance(value.get("dataset_id"), dict) and isinstance(value.get("column"), str):
                check(value["dataset_id"], value["column"], where)
            if value.get("kind") == "mapping_table" and isinstance(value.get("dataset_id"), dict):
                for column in [*(value.get("source_columns") or []), *(value.get("target_columns") or [])]:
                    check(value["dataset_id"], column, where)
            for key, child in value.items():
                walk(child, f"{where}/{key}")
        elif isinstance(value, list):
            for n, child in enumerate(value):
                walk(child, f"{where}/{n}")

    for item in fragment:
        after = item.get("after") if isinstance(item.get("after"), dict) else None
        if after is None:
            continue
        where = item.get("client_ref") or "?"
        walk(after, where)
        if item.get("target_kind") == "mapping":
            sources = {s.get("id"): s.get("dataset_id") for s in after.get("sources") or [] if isinstance(s, dict)}
            for source in after.get("sources") or []:
                for column in source.get("key_columns") or []:
                    check(source.get("dataset_id"), column, f"{where}/key_columns")
            for name, field in (after.get("fields") or {}).items():
                if isinstance(field, dict) and field.get("kind") == "column":
                    check(sources.get(field.get("source_id")), field.get("column"), f"{where}/fields/{name}")
    return found


def query_location_errors(fragment):
    """A query dataset names no table location; the platform rejects schema_name or table_name on it."""
    return [item.get("client_ref") or "?" for item in fragment
            if item.get("target_kind") == "dataset" and isinstance(item.get("after"), dict)
            and item["after"].get("source_kind") == "query"
            and (item["after"].get("schema_name") is not None or item["after"].get("table_name") is not None)]


def local_column_messages(fragment, tables_file):
    """Error lines for check_part; empty when the tables file is unavailable."""
    lines = [f"[QUERY_DATASET_LOCATION] 查询数据集 {ref} 不能写 schema_name 或 table_name（表位置写在 SQL 里）；删去这两项"
             for ref in query_location_errors(fragment)]
    if not tables_file:
        return lines
    try:
        tables = load_tables(tables_file)
    except (OSError, ValueError):
        return lines
    known = dataset_columns(part_items() + list(fragment), tables)
    for where, column, dataset, valid in column_errors(fragment, known):
        shown = "、".join(valid[:30]) + ("等" if len(valid) > 30 else "")
        lines.append(f"[COLUMN_UNKNOWN] {where}：数据集 {dataset} 没有列 {column}；可用：{shown}")
    return lines
