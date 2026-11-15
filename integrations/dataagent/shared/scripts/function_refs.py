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


def function_errors(fragment):
    """(client_ref, field, name) for each rejected function; metric expressions are aggregates and skipped."""
    found = []

    def walk(value, ref):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in REJECTED and isinstance(child, str):
                    found.extend((ref, key, name) for name in sorted(called(child) & REJECTED[key]))
                else:
                    walk(child, ref)
        elif isinstance(value, list):
            for child in value:
                walk(child, ref)

    for item in fragment:
        if isinstance(item, dict) and item.get("target_kind") != "metric" and isinstance(item.get("after"), dict):
            walk(item["after"], item.get("client_ref") or "?")
    return found


def function_messages(fragment):
    where = {"expression": "表达式", "query_sql": "查询 SQL"}
    return [f"[FUNCTION_UNSUPPORTED] {ref}：{where[field]}用了平台不支持的函数 {name}；改用支持的写法（如 CASE）或写进说明"
            for ref, field, name in function_errors(fragment)]
