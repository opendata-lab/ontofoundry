"""One line per linked table, plus the column hints the expander and the agent share.

Hints are candidates only: link candidates come from declared foreign keys or a
column named after another table's single-column key; value candidates from a
comment such as "状态：营业/装修/闭店". The agent confirms both (design
2026-11-15 MS-03, MS-05).
"""

import json
import re
from pathlib import Path

LIST_LIMIT = 6000
VALUES = re.compile(r"[：:]\s*([^，,；;。（(]+)")
SPLIT = re.compile(r"[/／、]")
FLAG = re.compile(r"1\s*[:：=]?\s*是.{0,4}0\s*[:：=]?\s*否")
# A key named "id" says nothing about which table a column points at.
GENERIC_KEYS = {"id", "code", "no", "key", "uuid"}
NOISE = re.compile(r"(^|_)(tmp|temp|bak|backup|ods|log|sync)(_|$|\d)", re.IGNORECASE)


def load_tables(path):
    data = json.loads(Path(path).read_bytes())
    return data.get("tables", []) if isinstance(data, dict) else []


def comment_values(comment):
    """Listed values in a column comment, or None when it lists fewer than two."""
    match = VALUES.search(comment or "")
    if not match:
        return None
    values = [v.strip() for v in SPLIT.split(match.group(1)) if v.strip()]
    return values if len(values) >= 2 and len(values) <= 20 and all(len(v) <= 20 for v in values) else None


def is_flag(column):
    """An integer yes/no column, e.g. "是否生鲜：1 是 0 否"."""
    comment = column.get("comment") or ""
    return bool(FLAG.search(comment)) or comment.startswith("是否") and "INT" in str(column.get("type") or "").upper()


def single_keys(tables):
    """Column name of each single-column primary key -> table keys owning it."""
    owners = {}
    for table in tables:
        pk = table.get("primary_key") or []
        if len(pk) == 1:
            owners.setdefault(pk[0], []).append(table["key"])
    return owners


def link_candidates(table, owners, by_name=None):
    """(column, [table keys]) pairs: declared foreign keys first, then name matches."""
    found = {}
    by_name = by_name or {}
    for fk in table.get("foreign_keys") or []:
        target = by_name.get(fk.get("referred_table"))
        for column in fk.get("constrained_columns") or []:
            if target:
                found.setdefault(column, [target])
    pk = set(table.get("primary_key") or [])
    for column in table.get("columns") or []:
        name = column["name"]
        if name in found:
            continue
        keys = [
            k for key_name, ks in owners.items() for k in ks
            if k != table["key"] and key_name.lower() not in GENERIC_KEYS
            and (name == key_name and pk != {name} or name.endswith("_" + key_name))
        ]
        if keys:
            found[name] = keys
    return found


def table_line(table, owners, by_name):
    pk = ",".join(table.get("primary_key") or []) or "未声明"
    parts = [f"{table['key']} {table.get('table_name') or table.get('table')} {table.get('comment') or ''}".rstrip(),
             f"PK {pk}", f"{len(table.get('columns') or [])} 列"]
    links = link_candidates(table, owners, by_name)
    if links:
        parts.append("关联候选 " + "，".join(
            f"{c}→{'/'.join(ks[:2])}{'等' if len(ks) > 2 else ''}" for c, ks in links.items()))
    values = [c["name"] for c in table.get("columns") or [] if comment_values(c.get("comment"))]
    if values:
        parts.append("取值候选 " + "，".join(values))
    flags = [c["name"] for c in table.get("columns") or [] if is_flag(c)]
    if flags:
        parts.append("布尔候选 " + "，".join(flags))
    if NOISE.search(table.get("table_name") or ""):
        parts.append("名称像技术表或备份，按材料判断是否建模")
    return " · ".join(parts)


def summary_lines(tables, limit=LIST_LIMIT):
    owners = single_keys(tables)
    by_name = {t.get("table_name"): t["key"] for t in tables}
    lines, size = [], 0
    for n, table in enumerate(tables):
        line = table_line(table, owners, by_name)
        size += len(line.encode()) + 1
        if size > limit:
            lines.append(f"…其余 {len(tables) - n} 张未列出，用 --search-tables 按业务词检索")
            break
        lines.append(line)
    return lines
