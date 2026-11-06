"""Linked-table reads keep the full table identity (connection, schema, table)."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "shared/scripts/read_input.py"


def table(key, connection_id, connection, column):
    return {
        "key": key, "table": "public.sales", "connection_id": connection_id, "connection": connection, "dialect": "mysql",
        "schema_name": "public", "table_name": "sales", "kind": "table", "comment": "", "primary_key": ["id"],
        "foreign_keys": [], "columns": [{"name": column, "type": "DECIMAL", "nullable": True, "comment": ""}],
    }


def read(tmp_path, wanted):
    path = tmp_path / "tables.json"
    path.write_text(json.dumps({"tables": [table("t1", "c1", "雾岭订单库", "amount_a"), table("t2", "c2", "雾岭退款库", "amount_b")]}, ensure_ascii=False))
    return subprocess.run([sys.executable, str(SCRIPT), str(path), "--tables", wanted], capture_output=True, text=True, check=False)


def test_tables_are_selected_by_key_only(tmp_path):
    result = read(tmp_path, "public.sales")
    assert result.returncode == 1 and "t2=雾岭退款库:public.sales" in result.stdout


def test_key_read_names_the_binding_of_same_named_tables(tmp_path):
    result = read(tmp_path, "t2")
    assert result.returncode == 0
    assert "connection_id=c2 schema_name=public table_name=sales" in result.stdout
    assert "amount_b" in result.stdout and "amount_a" not in result.stdout


def test_batch_tables_keeps_requested_order_and_full_columns(tmp_path):
    result = read(tmp_path, "t2,t1")
    assert result.returncode == 0
    assert result.stdout.index("## t2") < result.stdout.index("## t1")
    assert "amount_a DECIMAL" in result.stdout and "amount_b DECIMAL" in result.stdout
    assert len(result.stdout.encode()) <= 8192


def test_oversize_batch_can_be_read_in_separate_bounded_batches(tmp_path):
    tables = [table("t1", "c1", "云帆资料库", "amount_a"), table("t2", "c2", "雾岭资料库", "amount_b")]
    for entry in tables:
        entry["columns"] = [{"name": f"column_{i}", "type": "TEXT", "nullable": True, "comment": "虚构列说明" * 8} for i in range(30)]
    path = tmp_path / "tables.json"
    original = json.dumps({"tables": tables}, ensure_ascii=False)
    path.write_text(original)
    command = [sys.executable, str(SCRIPT), str(path), "--tables"]
    combined = subprocess.run([*command, "t1,t2"], capture_output=True, text=True, check=False)
    assert combined.returncode == 1 and "OUTPUT_TOO_LARGE" in combined.stdout and "分 2 批" in combined.stdout
    assert "column_0" not in combined.stdout
    for key in ("t1", "t2"):
        part = subprocess.run([*command, key], capture_output=True, text=True, check=False)
        assert part.returncode == 0 and len(part.stdout.encode()) <= 8192
        assert all(f"- column_{i} TEXT" in part.stdout for i in range(30))
    assert path.read_text() == original


def test_printed_receipt_lines_pass_the_platform_evidence_check(tmp_path):
    import re

    from ontofoundry_api.domain.evidence import check_material_evidence

    one = table("t1", "c1", "雾岭订单库", "amount_a")
    one["comment"] = "订单"
    one["columns"].append({"name": "status", "type": "ENUM", "nullable": False, "comment": "状态(open/closed)"})
    # Same serialization as the platform's receipt (TE-02).
    text = json.dumps({"tables": [one]}, indent=2, ensure_ascii=False)
    path = tmp_path / "tables.json"
    path.write_text(text)
    out = subprocess.run([sys.executable, str(SCRIPT), str(path), "--tables", "t1"],
                         capture_output=True, text=True, check=True).stdout
    spans = {"table" if line.startswith("##") else line.split()[1]: tuple(map(int, m.groups()))
             for line in out.splitlines() if (m := re.search(r"收据第 (\d+)–(\d+) 行", line))}
    lines = text.splitlines()
    lookup = lambda _id: ("sha", lines)
    for name, quote in (("table", '"table": "public.sales"'), ("status", "状态(open/closed)"),
                        ("amount_a", '"name": "amount_a"')):
        start, end = spans[name]
        check_material_evidence({"material_id": "m", "material_sha256": "sha",
                                 "locator": {"line_start": start, "line_end": end}, "quote": quote}, lookup, name)
