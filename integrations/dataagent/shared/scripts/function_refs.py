"""Functions the platform rejects, found locally before a submission round is spent.

The name lists are generated from the platform code by generate_output_schemas.py
(platform_functions.json), so this check follows the platform instead of skill text.
Only names the platform is known to reject are reported; anything else is left to it.
"""

import json
import re
from pathlib import Path

LISTS = json.loads((Path(__file__).resolve().parent / "platform_functions.json").read_bytes())
REJECTED = {field: frozenset(LISTS[field]) for field in ("expression", "query_sql")}
# Strings, quoted identifiers and comments never hold a call.
SKIP = re.compile(r"'(?:''|\\.|[^'\\])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|--[^\n]*|/\*[\s\S]*?\*/")
CALL = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\s*\(")


def called(text):
    return {name.upper() for name in CALL.findall(SKIP.sub(" ", text))}


def executable_fields(item):
    """(field, text) for the contract fields the platform parses; literal values elsewhere are data."""
    after = item.get("after") if isinstance(item.get("after"), dict) else {}
    kind = item.get("target_kind")
    if kind == "rule":
        yield "expression", after.get("expression")
    elif kind == "dataset":
        yield "query_sql", after.get("query_sql")
    elif kind == "object_type":
        for branch in after.get("derived_by") or []:
            if isinstance(branch, dict):
                yield "expression", branch.get("expression")
    elif kind == "mapping":
        for field in (after.get("fields") or {}).values():
            if isinstance(field, dict):
                yield "expression", field.get("expression")


def function_errors(fragment):
    """(client_ref, field, name) for each rejected function; metric expressions are aggregates, not checked."""
    found = []
    for item in fragment:
        if not isinstance(item, dict):
            continue
        for field, text in executable_fields(item):
            if isinstance(text, str):
                found.extend((item.get("client_ref") or "?", field, name) for name in sorted(called(text) & REJECTED[field]))
    return found


def function_messages(fragment):
    where = {"expression": "表达式", "query_sql": "查询 SQL"}
    return [f"[FUNCTION_UNSUPPORTED] {ref}：{where[field]}用了平台不支持的函数 {name}；改用支持的写法（如 CASE）或写进说明"
            for ref, field, name in function_errors(fragment)]
