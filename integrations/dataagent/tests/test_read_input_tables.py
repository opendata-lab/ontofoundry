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
    assert result.returncode == 1 and "--search-tables" in result.stdout


def test_key_read_names_the_binding_of_same_named_tables(tmp_path):
    result = read(tmp_path, "t2")
    assert result.returncode == 0
    assert "connection_id=c2 schema_name=public table_name=sales" in result.stdout
    assert "amount_b" in result.stdout and "amount_a" not in result.stdout


def test_batch_tables_keeps_requested_order_and_full_columns(tmp_path):
    result = read(tmp_path, "t2,t1")
    assert result.returncode == 0
    assert result.stdout.index("[ref: t2]") < result.stdout.index("[ref: t1]")
    assert "amount_a · DECIMAL" in result.stdout and "amount_b · DECIMAL" in result.stdout
    assert len(result.stdout.encode()) <= 8192


def test_bounded_descriptions_keep_exact_continuation_commands(tmp_path):
    tables = [table("t1", "c1", "云帆资料库", "amount_a"), table("t2", "c2", "雾岭资料库", "amount_b")]
    for entry in tables:
        entry["columns"] = [{"name": f"column_{i}", "type": "TEXT", "nullable": True, "comment": "虚构列说明" * 8} for i in range(60)]
    path = tmp_path / "tables.json"
    original = json.dumps({"tables": tables}, ensure_ascii=False)
    path.write_text(original)
    combined = subprocess.run([sys.executable, str(SCRIPT), str(path), "--describe-tables", "t1,t2"], capture_output=True, text=True)
    assert combined.returncode == 0 and len(combined.stdout.encode()) <= 8000
    assert "续读：" in combined.stdout and "--describe-tables" in combined.stdout
    assert path.read_text() == original


def test_reader_and_platform_receipt_lines_are_identical(tmp_path):
    from ontofoundry_api.domain.table_reading import table_lines

    one = table("t1", "c1", "雾岭订单库", "amount_a")
    one["comment"] = "订单"
    one["columns"].append({"name": "status", "type": "ENUM", "nullable": False, "comment": "状态(open/closed)"})
    path = tmp_path / "tables.json"
    path.write_text(json.dumps({"tables": [one]}, ensure_ascii=False))
    out = subprocess.run([sys.executable, str(SCRIPT), str(path), "--describe-tables", "t1"], capture_output=True, text=True, check=True).stdout
    assert out.splitlines() == table_lines(one)
