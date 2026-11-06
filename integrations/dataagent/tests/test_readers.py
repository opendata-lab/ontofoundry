"""Bounded readable views preserve physical locations and paging coverage."""

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from test_read_input_tables import SCRIPT, table


def read(path, *args):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *args], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert len(out.stdout.encode()) <= 8000
    return out.stdout


def next_args(output, marker="下一页："):
    commands = [
        line.split(marker, 1)[1] for line in output.splitlines() if marker in line
    ]
    return shlex.split(commands[0])[2:] if commands else None


def test_search_paging_filters_columns_and_size(tmp_path):
    path = tmp_path / "tables.json"
    tables = []
    for i in range(1, 96):
        entry = table(f"t{i}", "c1", "云帆资料库", "amount")
        entry.update(
            table=f"public.fiction_{i}", table_name=f"fiction_{i}", comment="虚构供应商"
        )
        entry["columns"][0]["comment"] = "税号"
        tables.append(entry)
    path.write_text(json.dumps({"tables": tables}, ensure_ascii=False))
    args, seen = (
        [
            str(path),
            "--search-tables",
            "税号",
            "--connection",
            "云帆资料库",
            "--schema",
            "public",
            "--kind",
            "table",
        ],
        [],
    )
    while args:
        output = read(Path(args[0]), *args[1:])
        assert len(output.encode()) <= 4000
        refs = re.findall(r"\[ref: (t\d+)\]", output)
        assert len(refs) <= 30
        assert "匹配列 amount(税号)" in output
        seen += refs
        args = next_args(output)
    assert seen == [f"t{i}" for i in range(1, 96)]
    assert "无匹配" in read(path, "--search-tables", "缺失关键词")


def test_wide_table_prioritizes_pk_fk_and_comments(tmp_path):
    entry = table("t1", "c1", "云帆资料库", "unused")
    entry["columns"] = [
        {
            "name": f"c{i}",
            "type": "TEXT",
            "nullable": False,
            "comment": "有注释" if i == 90 else "",
        }
        for i in range(100)
    ]
    entry["primary_key"] = ["c99"]
    entry["foreign_keys"] = [
        {
            "constrained_columns": ["c98"],
            "referred_table": "fiction_parent",
            "referred_columns": ["id"],
        }
    ]
    path = tmp_path / "tables.json"
    path.write_text(json.dumps({"tables": [entry]}))
    output = read(path, "--describe-tables", "t1")
    refs = re.findall(r"\[ref: t1\.(c\d+)\]", output)
    assert refs[:3] == ["c99", "c98", "c90"] and len(refs) <= 60
    seen = refs
    args = next_args(output, "续读：")
    while args:
        output = read(Path(args[0]), *args[1:])
        seen += re.findall(r"\[ref: t1\.(c\d+)\]", output)
        args = next_args(output, "续读：")
    assert len(seen) == len(set(seen)) == 100
    queried = read(path, "--describe-tables", "t1", "--col-query", "有注释")
    assert "[ref: t1.c90]" in queried and "[ref: t1.c89]" not in queried


def test_text_paging_covers_every_source_line_and_truncates_long_lines(tmp_path):
    path = tmp_path / "material.md"
    path.write_text(
        "\n".join(["很长" * 10000, *[f"编号{i} " + "内容" * 200 for i in range(2, 50)]])
    )
    args, seen = [str(path)], []
    while args:
        output = read(Path(args[0]), *args[1:])
        seen += [int(n) for n in re.findall(r"^(\d+)→", output, re.M)]
        if seen == [1]:
            assert "超长内容已截断" in output
        args = next_args(output)
    assert seen == list(range(1, 50))


def test_json_outline_real_lines_escaped_pointers_ranges_and_queries(tmp_path):
    path = tmp_path / "source.json"
    text = json.dumps(
        {
            "items": [{"code": "same", "note": "重复"} for _ in range(40)],
            "a/b": {"~": 7},
        },
        ensure_ascii=False,
        indent=2,
    )
    path.write_text(text)
    output = read(path, "--outline", "--ref", "m1")
    assert "数组 40 项" in output and "code:string" in output
    source_lines = text.splitlines()
    first = source_lines.index("    {") + 1
    assert f"[ref: m1#/items/0 · L{first}–{first + 3}]" in output
    output = read(path, "--pointer", "/items/2-4", "--ref", "m1")
    assert (
        "m1#/items/2" in output
        and "m1#/items/4" in output
        and "m1#/items/5" not in output
    )
    assert "number · 7" not in read(
        path, "--pointer", "/a~1b/~0"
    )  # Raw, numbered source value.
    assert "→7" in read(path, "--pointer", "/a~1b/~0")
    args, seen = [str(path), "--query", "code=same", "--ref", "m1"], []
    while args:
        output = read(Path(args[0]), *args[1:])
        refs = re.findall(r"\[ref: m1#/items/(\d+) ·", output)
        assert len(refs) <= 20
        seen += refs
        args = next_args(output)
    assert seen == [str(i) for i in range(40)]
    assert "m1#/items/39/note" in read(
        path, "--query", "重复", "--ref", "m1", "--page", "2"
    )


def test_json_large_default_outline_and_pointer_pages_are_bounded(tmp_path):
    path = tmp_path / "wide.json"
    path.write_text(
        json.dumps(
            {"items": [{"note": "测试" * 200} for _ in range(300)]},
            ensure_ascii=False,
            indent=2,
        )
    )
    assert "数组 300 项" in read(path)
    output = read(path, "--pointer", "/items")
    assert "下一页：" in output
    assert "--pointer /items" in output


def test_csv_outline_rows_queries_and_multiline_physical_lines(tmp_path):
    path = tmp_path / "material.csv"
    path.write_text('code,note,amount\na,"第一行\n第二行",3\nb,普通,4\nc,,5\n')
    output = read(path, "--ref", "m2")
    assert (
        "数据共 3 行" in output and "列 amount · number · 非空 3 · 不同值 3" in output
    )
    assert "[ref: m2#row:1 · L2–3]" in output and "[ref: m2#row:2 · L4]" in output
    assert "第一行 第二行" in output
    output = read(path, "--rows", "2-3", "--cols", "code,amount", "--ref", "m2")
    assert "note=" not in output and "row:1" not in output and "row:3 · L5" in output
    output = read(path, "--query", "code=b", "--ref", "m2")
    assert "row:2 · L4" in output and "row:1" not in output
    assert "row:1 · L2–3" in read(path, "--query", "第二行", "--ref", "m2")


def test_csv_scan_cap_and_paging(tmp_path):
    path = tmp_path / "large.csv"
    path.write_text("code,note\n" + "\n".join(f"{i},虚构" for i in range(10002)))
    output = read(path)
    assert "扫描上限 10000 行" in output and "≥1001（封顶）" in output
    output = read(path, "--rows", "1-80", "--cols", "code", "--ref", "m1")
    assert "下一页：" in output and "row:20" in output and "row:21" not in output


def test_nested_json_outline_zero_values_and_duplicate_key_source_positions(tmp_path):
    path = tmp_path / "nested.json"
    path.write_text(
        '{\n "same": 0,\n "same": 1,\n "data": {"rows": [{"flag": false, "count": 0}]}\n}'
    )
    output = read(path, "--outline", "--ref", "m1")
    assert "m1#/data/rows" in output and "数组 1 项" in output
    assert "m1#/same · L3–3" in output
    assert "number · 0" in output and "boolean · False" in output
    assert "m1#/data/rows/0 · L4–4" in read(
        path, "--query", "flag=false", "--ref", "m1"
    )


def test_wide_csv_outline_has_bounded_continuation(tmp_path):
    path = tmp_path / "wide.csv"
    columns = [f"column_{i}" for i in range(300)]
    path.write_text(",".join(columns) + "\n" + ",".join("虚构" for _ in columns) + "\n")
    args, seen = [str(path), "--outline", "--ref", "m1"], []
    while args:
        output = read(Path(args[0]), *args[1:])
        seen += re.findall(r"^列 (column_\d+) ·", output, re.M)
        args = next_args(output)
    assert seen == columns
