"""Bounded source reads with original line ranges or exact JSON pointers."""

import argparse
import json
from pathlib import Path


def render_lines(text, start=1, end=None):
    lines = text.splitlines()
    end = end or len(lines)
    if start < 1 or end < start or end > len(lines):
        raise ValueError("原行号范围不合法")
    return json.dumps(
        {
            "original_range": [start, end],
            "total_lines": len(lines),
            "unread_ranges": [
                [a, b] for a, b in ((1, start - 1), (end + 1, len(lines))) if a <= b
            ],
            "lines": [[i + 1, lines[i]] for i in range(start - 1, end)],
        },
        ensure_ascii=False,
    )


def render_tables(text, names):
    """Compact column listing for several linked tables in one bounded read."""
    tables = {t["key"]: t for t in json.loads(text)["tables"]}
    chosen = []
    for key in (n.strip() for n in names.split(",") if n.strip()):
        if key not in tables:
            options = "、".join(f"{k}={t['connection']}:{t['table']}" for k, t in tables.items())
            raise ValueError(f"没有编号为 {key} 的关联表；请用工作包 tables 里的 key：{options}")
        chosen.append(tables[key])
    lines = []
    for table in chosen:
        lines.append(
            f"## {table['key']} {table['table']}（{table['kind']}，连接 {table['connection']}，方言 {table['dialect']}）{table['comment']}"
        )
        lines.append(
            f"数据集来源：connection_id={table['connection_id']} schema_name={table['schema_name'] or '默认'} table_name={table['table_name']}"
        )
        lines.append("主键：" + (", ".join(table["primary_key"]) or "未声明"))
        for fk in table["foreign_keys"]:
            lines.append(
                f"外键：{', '.join(fk['constrained_columns'] or [])} → {fk['referred_table']}({', '.join(fk['referred_columns'] or [])})"
            )
        for column in table["columns"]:
            nullable = "可空" if column["nullable"] else "非空" if column["nullable"] is False else "可空性未知"
            lines.append(f"- {column['name']} {column['type'] or '类型未知'} {nullable} {column['comment']}".rstrip())
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--pointer")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int)
    parser.add_argument("--tables", help="逗号分隔的关联表 key（如 t1,t3），从工作包 tables_file 一次读取多张表的列")
    args = parser.parse_args()
    try:
        text = Path(args.path).read_text()
        if args.tables:
            output = render_tables(text, args.tables)
        elif args.pointer is not None:
            value = json.loads(text)
            for key in args.pointer.strip("/").split("/") if args.pointer else []:
                key = key.replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
            output = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            output = render_lines(text, args.start, args.end)
        if len(output.encode()) > 8000:
            print(
                "范围超过 8 KiB；缩小 --start/--end、--pointer 或分批 --tables，原文件完整保留，未回显内容"
            )
            return 1
        print(output)
        return 0
    except ValueError as exc:
        print(f"读取失败：{exc}" if str(exc).startswith("没有编号为") else "读取失败；检查已知路径、原行号或 JSON Pointer，禁止搜索环境和凭据")
        return 1
    except (OSError, KeyError, IndexError, TypeError):
        print("读取失败；检查已知路径、原行号或 JSON Pointer，禁止搜索环境和凭据")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
