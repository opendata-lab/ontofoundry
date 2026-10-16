"""Bottom-up modeling input: describe selected source tables as a Markdown material.

A modeling run only reads materials, so tables reach DataAgent the same way a
business document does. The text names everything a mapping proposal needs
(data source, schema, table, key column, column names) and the evidence an
object or relation proposal cites (one table or column per line).
"""

from __future__ import annotations

from typing import Any

SAMPLE_ROWS = 3
MAX_SAMPLE_CHARS = 40


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|").replace("\n", " ").strip()
    return text if len(text) <= MAX_SAMPLE_CHARS else text[: MAX_SAMPLE_CHARS - 1] + "…"


def _candidates(stem: str) -> list[str]:
    return [
        stem,
        stem + "s",
        stem + "es",
        stem[:-1] + "ies" if stem.endswith("y") else stem,
    ]


def foreign_key_hints(
    tables: list[dict[str, Any]],
) -> dict[str, list[tuple[str, str, str]]]:
    """(column, target table, how) per table: declared constraints first, then
    `<name>_id` columns that name another selected table with a single-column key."""
    keys = {
        table["name"]: [c["name"] for c in table["columns"] if c.get("primary_key")]
        for table in tables
    }
    hints: dict[str, list[tuple[str, str, str]]] = {}
    for table in tables:
        found = {
            (fk["column"], fk["table"]): (fk["column"], fk["table"], "外键约束")
            for fk in table.get("foreign_keys") or []
        }
        for column in table["columns"]:
            name = column["name"]
            if column.get("primary_key") or not name.lower().endswith("_id"):
                continue
            stem = name[:-3].lower()
            target = next(
                (
                    other
                    for other in _candidates(stem)
                    if other in keys and other != table["name"] and len(keys[other]) == 1
                ),
                None,
            )
            if target and (name, target) not in found:
                found[(name, target)] = (name, target, "按命名推断")
        hints[table["name"]] = list(found.values())
    return hints


def tables_markdown(
    *,
    source: str,
    kind: str,
    database: str,
    schema: str | None,
    tables: list[dict[str, Any]],
) -> str:
    """`tables`: name, comment, row_count, columns (name, type, nullable,
    primary_key, comment), foreign_keys ({column, table}), samples (rows)."""
    keys = {
        t["name"]: [c["name"] for c in t["columns"] if c.get("primary_key")] for t in tables
    }
    hints = foreign_key_hints(tables)
    lines = [
        f"# 数据表结构：{source}",
        "",
        f"本文由 OntoFoundry 从数据连接「{source}」（{kind}，数据库 {database}）读取，"
        "用于自下而上建模：根据表结构识别业务对象、属性和关系，并建立数据映射。",
        "",
        f"- 数据源（connection_alias）：{source}",
        f"- 模式（schema_name）：{schema or database}",
        f"- 表数量：{len(tables)}",
        "",
    ]
    for table in tables:
        name = table["name"]
        lines += [f"## 表 {name}", ""]
        lines.append(f"- 表说明：{table.get('comment') or '（无）'}")
        lines.append(
            f"- 主键（key_column）：{', '.join(keys[name]) or '（无，需人工指定）'}"
        )
        if table.get("row_count") is not None:
            lines.append(f"- 行数：{table['row_count']}")
        lines += [
            "",
            "| 字段 | 类型 | 可空 | 主键 | 说明 | 样例值 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        samples = table.get("samples") or []
        for column in table["columns"]:
            values = [_cell(row.get(column["name"])) for row in samples]
            lines.append(
                f"| {column['name']} | {column['type']} | "
                f"{'是' if column.get('nullable') else '否'} | "
                f"{'是' if column.get('primary_key') else ''} | "
                f"{_cell(column.get('comment'))} | {', '.join(v for v in values if v)} |"
            )
        lines.append("")
        if hints[name]:
            lines.append("关联字段：")
            for column, target, how in hints[name]:
                target_key = keys.get(target) or ["id"]
                lines.append(f"- {name}.{column} → {target}.{target_key[0]}（{how}）")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
