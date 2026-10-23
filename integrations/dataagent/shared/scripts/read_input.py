"""Bounded source reads with original line ranges or exact JSON pointers."""

import json
import shlex
from pathlib import Path

from runpaths import HintParser, command, error, existing

LIMIT = 8000


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


def table_keys(names):
    """Keys as given: "t1,t3", "t1 t3" or a mix, in order."""
    names = [names] if isinstance(names, str) else names
    return [k for n in names for k in n.replace(",", " ").split()]


def render_tables(text, names):
    """Compact column listing for several linked tables in one bounded read."""
    tables = {t["key"]: t for t in json.loads(text)["tables"]}
    chosen = []
    for spec in table_keys(names):
        # "t1:41-80" reads columns 41–80 of a table too wide for one read.
        key, _, span = spec.partition(":")
        if key not in tables:
            options = "、".join(f"{k}={t['connection']}:{t['table']}" for k, t in tables.items())
            raise ValueError(f"没有编号为 {key} 的关联表；请用工作包 tables 里的 key：{options}")
        table = tables[key]
        if span:
            start, _, end = span.partition("-")
            if not (start.isdigit() and end.isdigit() and 1 <= int(start) <= int(end) <= len(table["columns"])):
                ranges = "、".join(table_specs(text, table))
                raise ValueError(f"列范围 {spec} 无效：{key} 共 {len(table['columns'])} 列；可读范围：{ranges}")
            table = {**table, "columns": table["columns"][int(start) - 1:int(end)]}
        chosen.append(table)
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


def table_specs(text, table, key=None):
    """The table whole, or column ranges ("t1:1-80") when it alone exceeds one read.

    With key, table is a column slice of that table and ranges count from 1 in
    the slice; the caller shifts them back.
    """
    whole = key is None
    key = key or table["key"]
    total = len(table["columns"])
    columns = {t["key"]: t for t in json.loads(text)["tables"]}
    doc = text if whole else json.dumps({"tables": [{**columns[key], "columns": table["columns"]}]}, ensure_ascii=False)
    if whole and (len(render_tables(text, [key]).encode()) <= LIMIT or total <= 1):
        return [key]
    specs, start = [], 1
    while start <= total:
        end = start
        while end < total and len(render_tables(doc, [f"{key}:{start}-{end + 1}"]).encode()) <= LIMIT:
            end += 1
        specs.append(f"{key}:{start}-{end}")
        start = end + 1
    return specs


def shift(spec, offset):
    key, _, span = spec.partition(":")
    start, _, end = span.partition("-")
    return f"{key}:{int(start) + offset}-{int(end) + offset}"


def table_batches(text):
    """Table keys grouped so each group's listing fits one read."""
    batches, current, size = [], [], 0
    for table in json.loads(text)["tables"]:
        for spec in table_specs(text, table):
            cost = len(render_tables(text, [spec]).encode()) + 1
            if current and size + cost > LIMIT:
                batches.append(current)
                current, size = [], 0
            current.append(spec)
            size += cost
    return batches + ([current] if current else [])


def fitting_end(text, start):
    """The last line from start whose range still fits one read."""
    total = len(text.splitlines())
    end = start
    while end < total and len(render_lines(text, start, end + 1).encode()) <= LIMIT:
        end += 1
    return end


def table_commands(path, text, names):
    """Ready reads for the requested tables, each batch within one read."""
    tables = {t["key"]: t for t in json.loads(text)["tables"]}
    specs = []
    for spec in table_keys(names):
        key, _, span = spec.partition(":")
        if span and len(render_tables(text, [spec]).encode()) > LIMIT:
            start, _, end = span.partition("-")
            narrowed = {**tables[key], "columns": tables[key]["columns"][int(start) - 1:int(end)]}
            specs += [shift(s, int(start) - 1) for s in table_specs(text, narrowed, key)]
        else:
            specs += [spec] if span else table_specs(text, tables[key])
    batches, current, size = [], [], 0
    for spec in specs:
        cost = len(render_tables(text, [spec]).encode()) + 1
        if current and size + cost > LIMIT:
            batches.append(current)
            current, size = [], 0
        current.append(spec)
        size += cost
    batches += [current] if current else []
    return [command("read_input.py", path, "--tables", ",".join(b)) for b in batches]


class PointerMiss(LookupError):
    """A JSON Pointer step that does not exist; the message names what does."""


def resolve_pointer(path, text, pointer):
    """The value at a JSON Pointer, or an error naming what does exist there."""
    value = json.loads(text)
    walked = ""
    for raw in pointer.strip("/").split("/") if pointer else []:
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not (key.isdigit() and int(key) < len(value)):
                raise PointerMiss(f"JSON Pointer {pointer} 在 {walked or '文档根'} 处无效：这里是 {len(value)} 项的数组，有效下标 0–{len(value) - 1}")
            value = value[int(key)]
        elif isinstance(value, dict):
            if key not in value:
                keys = "、".join(list(value)[:15]) + ("…" if len(value) > 15 else "")
                raise PointerMiss(f"JSON Pointer {pointer} 在 {walked or '文档根'} 处没有键 {key}；现有键：{keys}")
            value = value[key]
        else:
            raise PointerMiss(f"JSON Pointer {pointer} 在 {walked} 处已是标量，不能再往下取")
        walked += "/" + raw
    return value


def main():
    parser = HintParser(description="按原行号读材料、按 JSON Pointer 读片段，或用 --tables 读关联表的列")
    parser.add_argument("path")
    parser.add_argument("--pointer")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int)
    parser.add_argument("--tables", nargs="+", help="关联表 key，逗号或空格分隔（如 t1,t3）；过宽的表按列范围读（如 t1:1-80）")
    args = parser.parse_args()
    path = args.path
    if not Path(path).is_file():
        folder = Path(path).parent
        print(error("FILE_NOT_FOUND", f"工作区文件 {path} 不存在", f"{folder}/ 现有：{existing(folder)}",
                    "路径照 init_workflow 打印的本轮路径或工作包复制"))
        return 1
    try:
        text = Path(path).read_text()
    except (OSError, UnicodeDecodeError) as exc:
        print(error("READ_FAILED", f"无法读取 {path}：{type(exc).__name__}", "未读取任何内容", retry=False))
        return 1
    try:
        if args.tables:
            output = render_tables(text, args.tables)
        elif args.pointer is not None:
            output = json.dumps(resolve_pointer(path, text, args.pointer), ensure_ascii=False, separators=(",", ":"))
        else:
            total = len(text.splitlines())
            end = args.end or total
            if not 1 <= args.start <= end <= total:
                fixed = command("read_input.py", path, "--start", str(min(max(args.start, 1), total)), "--end", str(total))
                print(error("INVALID_ARGUMENT", f"行范围 {args.start}–{end} 无效，{path} 共 {total} 行", "未读取任何内容", fixed))
                return 1
            output = render_lines(text, args.start, end)
    except json.JSONDecodeError as exc:
        print(error("JSON_INVALID", f"{path} 第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}", "未读取任何内容",
                    f"不带 --pointer/--tables 按行读原文：{command('read_input.py', path, '--start', str(max(exc.lineno - 2, 1)), '--end', str(min(exc.lineno + 2, len(text.splitlines()))))}"))
        return 1
    except LookupError as exc:
        print(error("INVALID_ARGUMENT", str(exc), "未读取任何内容", "按上面列出的键或下标改正 --pointer"))
        return 1
    except ValueError as exc:
        print(error("INVALID_ARGUMENT", str(exc), "未读取任何内容", "按上面列出的 key 或列范围改正 --tables"))
        return 1
    size = len(output.encode())
    if size > LIMIT:
        reason = f"输出 {size} 字节，超过单次 {LIMIT} 字节上限"
        state = f"未回显内容，{path} 未改动"
        if args.tables:
            commands = table_commands(path, text, args.tables)
            step = f"分 {len(commands)} 批读，每批一次：" + "；".join(commands)
        elif args.pointer is not None:
            step = f"改读更小的子路径，例如 {command('read_input.py', path, '--pointer', args.pointer.rstrip('/') + '/0')}（数组）或其中一个键"
        else:
            first = render_lines(text, args.start, args.start)
            if len(first.encode()) > LIMIT:
                line = text.splitlines()[args.start - 1]
                cut = 2500  # characters; at 3 bytes each a piece stays under the limit
                pieces = (len(line) + cut - 1) // cut
                step = (f"第 {args.start} 行单行就有 {len(line.encode())} 字节，按字符分 {pieces} 段读："
                        f"sed -n '{args.start}p' {shlex.quote(path)} | cut -c 1-{cut}，下一段 cut -c {cut + 1}-{2 * cut}，依此类推")
            else:
                last = fitting_end(text, args.start)
                step = command("read_input.py", path, "--start", str(args.start), "--end", str(last))
                if last < (args.end or len(text.splitlines())):
                    step += f"，之后从 --start {last + 1} 接着读"
        print(error("OUTPUT_TOO_LARGE", reason, state, step))
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
