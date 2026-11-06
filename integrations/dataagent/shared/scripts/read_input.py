"""Bounded, readable source views with stable refs and physical source lines."""

import bisect
import csv
import io
import json
import re
from pathlib import Path

from runpaths import HintParser, command, error, existing
from table_format import clean, column_line, table_header, table_lines

LIMIT = 8000
SEARCH_LIMIT = 4000
SCAN_ROWS = 10000


def clip(value, limit=900):
    text = str(value)
    if len(text.encode()) <= limit:
        return text
    return text.encode()[:limit].decode("utf-8", "ignore") + "…[超长内容已截断]"


def fit_lines(lines, limit=LIMIT):
    """Bound a non-pageable summary without emitting partial references."""
    output = []
    for line in lines:
        line = clip(line, 1500)
        if len(("\n".join([*output, line]) + "\n").encode()) > limit - 120:
            output.append("…概览已截断；请按路径、列或关键词定点读取")
            break
        output.append(line)
    return "\n".join(output)


def render_lines(text, start=1, end=None):
    lines = text.splitlines()
    if not lines:
        return "空文件"
    end = len(lines) if end is None else end
    if not 1 <= start <= end <= len(lines):
        raise ValueError("原行号范围不合法")
    return "\n".join(f"{i}→{clip(lines[i - 1])}" for i in range(start, end + 1))


def text_page(path, text, start=1, end=None):
    lines = text.splitlines()
    if not lines:
        return "空文件"
    end = len(lines) if end is None else end
    if not 1 <= start <= end <= len(lines):
        raise ValueError(f"原行号范围不合法；共 {len(lines)} 行")
    output, last = [], start - 1
    reserve = len(command("read_input.py", path, "--start", str(end)).encode()) + 250
    for i in range(start, end + 1):
        line = f"{i}→{clip(lines[i - 1])}"
        if len("\n".join([*output, line]).encode()) > LIMIT - reserve:
            break
        output.append(line)
        last = i
    unread = [f"{a}–{b}" for a, b in ((1, start - 1), (last + 1, len(lines))) if a <= b]
    output.append("未读范围：" + ("、".join(unread) or "无"))
    if last < len(lines):
        output.append(
            "下一页：" + command("read_input.py", path, "--start", str(last + 1))
        )
    return "\n".join(output)


def table_keys(names):
    names = [names] if isinstance(names, str) else names
    return [k for n in names for k in n.replace(",", " ").split()]


def render_tables(text, names, col_query=None, path="<tables_file>"):
    tables = {t["key"]: t for t in json.loads(text)["tables"]}
    specs = table_keys(names)
    if len(specs) > 10:
        raise ValueError("一次最多描述 10 张表")
    lines = []
    for spec in specs:
        key, _, span = spec.partition(":")
        if key not in tables:
            raise ValueError(f"未知引用 {key}；请先 --search-tables 检索有效引用")
        table = tables[key]
        columns = table["columns"]
        total = len(columns)
        start, end = 1, min(total, 60)
        if span:
            match = re.fullmatch(r"(\d+)-(\d+)", span)
            if not match or not 1 <= int(match[1]) <= int(match[2]) <= total:
                raise ValueError(f"无效列范围 {spec}；共 {total} 列")
            start, end = int(match[1]), int(match[2])
        elif total > 60:
            # Stable priority order is used by every page, including explicit ranges.
            foreign = {
                c
                for fk in table.get("foreign_keys") or []
                for c in fk.get("constrained_columns") or []
            }
            primary = set(table.get("primary_key") or [])
            columns = sorted(
                columns,
                key=lambda c: (
                    0
                    if c["name"] in primary
                    else 1
                    if c["name"] in foreign
                    else 2
                    if c.get("comment")
                    else 3
                ),
            )
        if span and total > 60:
            foreign = {
                c
                for fk in table.get("foreign_keys") or []
                for c in fk.get("constrained_columns") or []
            }
            primary = set(table.get("primary_key") or [])
            columns = sorted(
                columns,
                key=lambda c: (
                    0
                    if c["name"] in primary
                    else 1
                    if c["name"] in foreign
                    else 2
                    if c.get("comment")
                    else 3
                ),
            )
        if col_query:
            columns = [
                c
                for c in columns
                if all(
                    w.casefold() in (c["name"] + " " + c.get("comment", "")).casefold()
                    for w in col_query.split()
                )
            ]
            total = len(columns)
            if not span:
                end = min(total, 60)
        header = table_lines(table, [])
        if len("\n".join([*lines, *header]).encode()) > LIMIT - 1000:
            rest = specs[specs.index(spec) :]
            lines.append(
                "其余表："
                + command("read_input.py", path, "--describe-tables", ",".join(rest))
            )
            break
        lines.extend(header)
        last = start - 1
        # Reserve space for exact continuation commands and later table headers.
        reserve = 500 + len(
            command("read_input.py", path, "--describe-tables", key).encode()
        )
        for i in range(start, min(end, total) + 1):
            line = clip(column_line(table, columns[i - 1]), 1600)
            if len("\n".join([*lines, line]).encode()) > LIMIT - reserve:
                break
            lines.append(line)
            last = i
        if last < total:
            args = ["--describe-tables", f"{key}:{last + 1}-{min(last + 60, total)}"]
            if col_query:
                args += ["--col-query", col_query]
            lines.append(
                "列按主键、外键、注释优先；续读："
                + command("read_input.py", path, *args)
            )
        if len("\n".join(lines).encode()) > LIMIT - 600:
            rest = specs[specs.index(spec) + 1 :]
            if rest:
                lines.append(
                    "其余表："
                    + command(
                        "read_input.py", path, "--describe-tables", ",".join(rest)
                    )
                )
            break
    return "\n".join(lines)


def paged(units, page, per_page, limit, next_command):
    if page < 1:
        raise ValueError("页码必须从 1 开始")
    pages, current = [], []
    for unit in units:
        unit = clip(unit, min(limit // 2, 2000))
        if current and (
            len(current) >= per_page
            or len("\n".join([*current, unit]).encode()) > limit - 600
        ):
            pages.append(current)
            current = []
        current.append(unit)
    pages.append(current)
    if page > len(pages):
        raise ValueError(f"页码超出范围；共 {len(pages)} 页")
    output = pages[page - 1] or ["无匹配结果"]
    footer = f"第 {page}/{len(pages)} 页 · 共 {len(units)} 项"
    if page < len(pages):
        footer += "\n下一页：" + next_command(page + 1)
    return "\n".join([*output, footer])


def search_tables(
    text,
    words="",
    connection=None,
    schema=None,
    kind=None,
    page=1,
    path="<tables_file>",
):
    units = []
    words = words.casefold().split()
    for table in json.loads(text)["tables"]:
        if (
            (connection is not None and table["connection"] != connection)
            or (schema is not None and (table.get("schema_name") or "") != schema)
            or (kind and table.get("kind") != kind)
        ):
            continue
        columns = table["columns"]
        body = " ".join(
            [
                table["table"],
                table["connection"],
                table.get("schema_name") or "",
                table.get("comment") or "",
                *[c["name"] + " " + (c.get("comment") or "") for c in columns],
            ]
        ).casefold()
        if not all(w in body for w in words):
            continue
        matched = [
            c
            for c in columns
            if words
            and any(
                w in (c["name"] + " " + (c.get("comment") or "")).casefold()
                for w in words
            )
        ]
        units.append(
            clip(table_header(table), 650)
            + (
                "｜匹配列 "
                + clip(
                    "、".join(
                        f"{c['name']}({clean(c.get('comment'))})" for c in matched
                    ),
                    350,
                )
                if matched
                else ""
            )
        )

    def next_cmd(n):
        args = ["--search-tables", " ".join(words), "--page", str(n)]
        for flag, value in (
            ("--connection", connection),
            ("--schema", schema),
            ("--kind", kind),
        ):
            if value is not None:
                args += [flag, value]
        return command("read_input.py", path, *args)

    return paged(units, page, 30, SEARCH_LIMIT, next_cmd)


class PointerMiss(LookupError):
    """A JSON Pointer step does not exist."""


class JsonSource:
    """Parse positions alongside values; repeated text never aliases source spans."""

    def __init__(self, text):
        self.text = text
        self.value = json.loads(text)
        self.nodes = {}
        self.newlines = [i for i, c in enumerate(text) if c == "\n"]
        self._scan(0, "")

    def _scan(self, offset, pointer):
        text = self.text
        offset = re.compile(r"\s*").match(text, offset).end()
        start = offset
        value, end = json.JSONDecoder().raw_decode(text, offset)
        self.nodes[pointer] = (value, start, end)
        if isinstance(value, (dict, list)):
            offset += 1
            index = 0
            while True:
                offset = re.compile(r"\s*").match(text, offset).end()
                if text[offset] in "}]":
                    break
                if isinstance(value, dict):
                    key, offset = json.JSONDecoder().raw_decode(text, offset)
                    offset = re.compile(r"\s*:\s*").match(text, offset).end()
                else:
                    key = index
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                offset = self._scan(offset, pointer + "/" + escaped)
                offset = re.compile(r"\s*,?\s*").match(text, offset).end()
                index += 1
        return end

    def tag(self, pointer, ref):
        _, start, end = self.nodes[pointer]
        a = bisect.bisect_left(self.newlines, start) + 1
        b = bisect.bisect_left(self.newlines, max(start, end - 1)) + 1
        return f"[ref: {ref}#{pointer} · L{a}–{b}]"

    def select(self, pointer):
        if pointer in self.nodes:
            return [pointer]
        parent, _, tail = pointer.rpartition("/")
        match = re.fullmatch(r"(\d+)-(\d+)", tail)
        node = self.nodes.get(parent, (None,))[0]
        if (
            match
            and isinstance(node, list)
            and 0 <= int(match[1]) <= int(match[2]) < len(node)
        ):
            return [
                parent + "/" + str(i) for i in range(int(match[1]), int(match[2]) + 1)
            ]
        raise PointerMiss(f"JSON Pointer {pointer} 不存在；请 --outline 查看有效路径")


def resolve_pointer(path, text, pointer):
    source = JsonSource(text)
    found = source.select(pointer)
    return (
        source.nodes[found[0]][0]
        if len(found) == 1
        else [source.nodes[p][0] for p in found]
    )


def value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "number" if isinstance(value, (int, float)) else "string"


def summary(value):
    if isinstance(value, dict):
        return "对象；键：" + "、".join(value)
    if isinstance(value, list):
        result = f"数组 {len(value)} 项"
        if value and all(isinstance(v, dict) for v in value):
            fields = {tuple(sorted(v)) for v in value}
            if len(fields) == 1:
                result += "；字段：" + "、".join(
                    k + ":" + "/".join(sorted({value_type(v[k]) for v in value}))
                    for k in value[0]
                )
        if value:
            sample = value[0]
            if isinstance(sample, dict):
                result += "；示例：" + "；".join(
                    k + "=" + clean(v) for k, v in sample.items()
                )
            else:
                result += "；示例：" + clean(sample)
        return result
    return value_type(value) + " · " + clean(value)


def json_view(path, text, ref, outline=False, pointer=None, query=None, page=1):
    source = JsonSource(text)
    if query is not None:
        key, sep, expected = query.partition("=")
        if sep:
            found = [
                p
                for p, (v, _, _) in source.nodes.items()
                if isinstance(v, dict)
                and key in v
                and (
                    json.dumps(v[key])
                    if v[key] is None or isinstance(v[key], bool)
                    else str(v[key])
                )
                == expected
            ]
        else:
            found = [
                p
                for p, (v, _, _) in source.nodes.items()
                if not isinstance(v, (dict, list))
                and query.casefold() in (p + " " + str(v)).casefold()
            ]
    elif pointer is not None:
        found = source.select(pointer)
    else:
        found = []

        def visit(p):
            found.append(p)
            value = source.nodes[p][0]
            if isinstance(value, dict):
                for key in value:
                    visit(p + "/" + key.replace("~", "~0").replace("/", "~1"))
            elif isinstance(value, list) and value:
                visit(p + "/0")

        visit("")
    units = []
    for p in found:
        value, start, end = source.nodes[p]
        if outline or query is not None or pointer is None:
            units.append(source.tag(p, ref) + " " + clip(summary(value), 1300))
        else:
            # Source text retains exact values, indentation and real physical lines.
            fragment = text[start:end].splitlines()
            first = bisect.bisect_left(source.newlines, start) + 1
            chunk = [source.tag(p, ref)]
            for i, line in enumerate(fragment):
                numbered = f"{first + i}→{clip(line)}"
                if (
                    len("\n".join([*chunk, numbered]).encode()) > 1800
                    and len(chunk) > 1
                ):
                    units.append("\n".join(chunk))
                    chunk = [source.tag(p, ref)]
                chunk.append(numbered)
            units.append("\n".join(chunk))
    args = (
        ["--query", query]
        if query is not None
        else ["--pointer", pointer]
        if pointer is not None
        else ["--outline"]
    )
    return paged(
        units,
        page,
        20 if query is not None else 100000,
        LIMIT,
        lambda n: command("read_input.py", path, *args, "--ref", ref, "--page", str(n)),
    )


def csv_source(text):
    reader = csv.reader(
        io.StringIO(text, newline="") if isinstance(text, str) else text
    )
    header = next(reader, [])
    records = []
    previous = reader.line_num
    for number, row in enumerate(reader, 1):
        records.append((number, previous + 1, reader.line_num, row))
        previous = reader.line_num
        if number >= SCAN_ROWS:
            # Look ahead without consuming the rest of an enormous file.
            return header, records, next(reader, None) is not None
    return header, records, False


def cell_type(value):
    if value.casefold() in {"true", "false"}:
        return "boolean"
    try:
        float(value)
        return "number"
    except ValueError:
        return "string"


def csv_view(path, text, ref, rows=None, cols=None, query=None, page=1):
    header, records, capped = csv_source(text)
    chosen = header if not cols else cols.split(",")
    if any(c not in header for c in chosen):
        raise ValueError("未知列；有效列：" + "、".join(header))

    def row_line(record):
        number, start, end, values = record
        location = f"L{start}" + (f"–{end}" if end != start else "")
        cells = [
            (c, values[i] if i < len(values) else "")
            for i, c in enumerate(header)
            if c in chosen
        ]
        return f"[ref: {ref}#row:{number} · {location}] " + " · ".join(
            f"{c}={clip(clean(v), 300)}" for c, v in cells
        )

    note = (
        f"扫描上限 {SCAN_ROWS} 行；后续行未扫描，统计为扫描范围"
        if capped
        else f"数据共 {len(records)} 行"
    )
    if rows is None and query is None:
        lines = ["CSV 表头（L1）：" + "、".join(header), note]
        for index, col in enumerate(header):
            values = [
                r[3][index] for r in records if index < len(r[3]) and r[3][index] != ""
            ]
            distinct = set()
            for value in values:
                distinct.add(value)
                if len(distinct) > 1000:
                    break
            lines.append(
                f"列 {col} · {'/'.join(sorted({cell_type(v) for v in values})) or '未知'} · 非空 {len(values)} · 不同值 {'≥1001（封顶）' if len(distinct) > 1000 else len(distinct)} · 示例 "
                + "、".join(
                    clip(clean(v), 100) for v in dict.fromkeys(values[:20]) if v
                )[:300]
            )
        lines += [row_line(r) for r in records[:3]]
        lines.append("读取：" + command("read_input.py", path, "--rows", "1-20"))
        return paged(
            lines,
            page,
            100000,
            LIMIT,
            lambda n: command(
                "read_input.py", path, "--outline", "--ref", ref, "--page", str(n)
            ),
        )
    if rows:
        match = re.fullmatch(r"(\d+)-(\d+)", rows)
        if not match or not 1 <= int(match[1]) <= int(match[2]):
            raise ValueError("行范围须为 1-20 形式")
        records = [r for r in records if int(match[1]) <= r[0] <= int(match[2])]
    if query is not None:
        key, sep, value = query.partition("=")
        if sep and key not in header:
            raise ValueError("未知查询列；有效列：" + "、".join(header))
        if sep:
            records = [
                r
                for r in records
                if len(r[3]) > header.index(key) and r[3][header.index(key)] == value
            ]
        else:
            records = [
                r for r in records if query.casefold() in " ".join(r[3]).casefold()
            ]
    args = ["--query", query] if query is not None else ["--rows", rows]
    if cols:
        args += ["--cols", cols]
    return (
        note
        + "\n"
        + paged(
            [row_line(r) for r in records],
            page,
            20,
            LIMIT - len(note.encode()) - 1,
            lambda n: command(
                "read_input.py", path, *args, "--ref", ref, "--page", str(n)
            ),
        )
    )


def main():
    parser = HintParser(description="按原行号、表引用、JSON 路径或 CSV 行列有界读取")
    parser.add_argument("path")
    parser.add_argument("--ref", help="材料引用编号，如 m1；默认取文件名")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int)
    parser.add_argument("--page", type=int, default=1)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--search-tables", nargs="?", const="")
    modes.add_argument("--describe-tables", "--tables", nargs="+")
    modes.add_argument("--outline", action="store_true")
    modes.add_argument("--pointer")
    modes.add_argument("--rows")
    modes.add_argument("--query")
    parser.add_argument("--col-query")
    parser.add_argument("--cols")
    parser.add_argument("--connection")
    parser.add_argument("--schema")
    parser.add_argument("--kind", choices=["table", "view"])
    args = parser.parse_args()
    path = Path(args.path)
    if not path.is_file():
        print(
            error(
                "FILE_NOT_FOUND",
                f"工作区文件 {path} 不存在",
                "未读取内容",
                f"现有文件：{existing(path.parent)}",
            )
        )
        return 1
    try:
        text = "" if path.suffix.lower() == ".csv" else path.read_text(encoding="utf-8")
        ref = args.ref or path.stem
        if args.search_tables is not None:
            output = search_tables(
                text,
                args.search_tables,
                args.connection,
                args.schema,
                args.kind,
                args.page,
                str(path),
            )
        elif args.describe_tables:
            output = render_tables(
                text, args.describe_tables, args.col_query, str(path)
            )
        elif path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8", newline="") as source:
                output = csv_view(
                    str(path), source, ref, args.rows, args.cols, args.query, args.page
                )
        elif (
            args.outline
            or args.pointer is not None
            or args.query is not None
            or (
                path.suffix.lower() == ".json"
                and len(text.encode()) > LIMIT
                and args.start == 1
                and args.end is None
            )
        ):
            output = json_view(
                str(path), text, ref, args.outline, args.pointer, args.query, args.page
            )
        else:
            output = text_page(str(path), text, args.start, args.end)
        if len(output.encode()) > LIMIT:
            raise ValueError("输出超限；请缩小路径、表或列范围")
    except json.JSONDecodeError as exc:
        print(
            error(
                "JSON_INVALID",
                f"{path} 第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}",
                "未回显内容",
                command(
                    "read_input.py",
                    str(path),
                    "--start",
                    str(max(1, exc.lineno - 2)),
                    "--end",
                    str(min(len(text.splitlines()), exc.lineno + 2)),
                ),
            )
        )
        return 1
    except (ValueError, LookupError, OSError, csv.Error, RecursionError) as exc:
        print(
            error(
                "INVALID_ARGUMENT",
                clip(str(exc), 1000),
                "未回显内容",
                "按有效引用、路径或范围重读",
            )
        )
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
