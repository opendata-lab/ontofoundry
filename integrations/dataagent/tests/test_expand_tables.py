"""Table summary and the entities.json expander (design 2026-11-15 MS-01, MS-03, MS-05), offline."""

import importlib
import json
import sys
from pathlib import Path

import pytest
from test_workflow import SCHEMA_PATH

expand_tables = importlib.import_module("expand_tables")
init_workflow = importlib.import_module("init_workflow")
table_summary = importlib.import_module("table_summary")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RETAIL = FIXTURES / "extract-retail"
MATERIAL_ID = "0b2f2b9b-938b-4452-8a7a-45587024538d"
RETAIL_SPEC = {
    "scenario": "全量",
    "items": [
        {"name": "member", "display_name": "会员", "table": "t1", "basis": [{"material_id": MATERIAL_ID, "line": 6}],
         "properties": {"home_store_id": {"required": True}}},
        {"name": "order_item", "display_name": "订单明细", "table": "order_items"},
        {"name": "order", "display_name": "订单", "table": "t3"},
        {"name": "product", "display_name": "商品 SKU", "table": "t4", "title_property": "product_name"},
        {"name": "store", "display_name": "门店", "tables": ["t5"]},
        {"name": "refund", "display_name": "退款", "tables": []},
    ],
    "value_types": [
        {"name": "member_level", "display_name": "会员等级", "columns": ["t1.member_level"]},
        {"name": "order_status", "display_name": "订单状态", "columns": ["t3.status"]},
    ],
}


def tables(path):
    return {t["key"]: t for t in table_summary.load_tables(path)}


def fixture(name):
    return json.loads((RETAIL / "conservative" / name).read_text())


def shape(items, kind):
    """What the platform keeps, without client_ref spelling, evidence or display text."""
    found = {}
    for item in items:
        a = item["after"]
        if item["target_kind"] != kind:
            continue
        if kind == "property":
            found[(a["owner_type_id"]["client_ref"], a["name"])] = (
                a["value_kind"], a.get("identifier", False), a.get("required", False), a.get("unique", False),
                "value_type_id" in a)
        elif kind == "mapping":
            found[a["type_id"]["client_ref"]] = (a["sources"][0]["key_columns"], sorted(
                (k, v["column"]) for k, v in a["fields"].items()))
        elif kind == "value_type":
            found[a["name"]] = a["value_kind"]
        elif kind == "rule":
            found[a["name"]] = a["expression"]
    return found


def test_expansion_matches_the_hand_written_retail_fixture():
    types, datasets, notes = expand_tables.expand(RETAIL_SPEC, tables(RETAIL / "tables.json"), {})
    expected_types = fixture("01-types.json")
    # refund has no synced table: its properties come from the material and are written by hand (01b).
    hand = {k: v for k, v in shape(expected_types, "property").items() if k[0] != "refund"}
    assert shape(types, "property") == hand
    for kind in ("value_type", "rule"):
        assert shape(types, kind) == shape(expected_types, kind), kind
    assert shape(datasets, "mapping") == {
        k: v for k, v in shape(fixture("03-datasets.json"), "mapping").items() if k != "refund"}
    assert all("columns" not in d["after"] for d in datasets if d["target_kind"] == "dataset")
    assert any("refund 没有对应的表" in n for n in notes)
    product = next(i for i in types if i["client_ref"] == "product")
    assert product["after"]["title_property_id"] == {"client_ref": "product_product_name"}


def test_comment_tail_becomes_the_description_not_the_display_name():
    types, _, _ = expand_tables.expand(RETAIL_SPEC, tables(RETAIL / "tables.json"), {})
    member_id = next(i["after"] for i in types if i["client_ref"] == "order_member_id")
    assert (member_id["display_name"], member_id["description"]) == ("下单会员", "散客为空")
    level = next(i["after"] for i in types if i["client_ref"] == "member_member_level")
    assert "description" not in level  # the listed values live on the value type


def test_material_basis_is_quoted_from_the_material_line():
    texts = {MATERIAL_ID: (RETAIL / "material.md").read_text().splitlines()}
    types, _, _ = expand_tables.expand(RETAIL_SPEC, tables(RETAIL / "tables.json"), texts)
    evidence = next(i for i in types if i["client_ref"] == "member")["after"]["evidence"][0]
    assert evidence["locator"] == {"line_start": 6, "line_end": 6} and evidence["quote"] == texts[MATERIAL_ID][5].strip()
    store = next(i for i in types if i["client_ref"] == "store")["after"]["evidence"][0]
    assert store["kind"] == "table" and store["ref"] == "t5"


@pytest.mark.parametrize("change, message", [
    (lambda s: s["value_types"].append({"name": "Member", "columns": ["t1.city"], "values": ["a", "b"]}), "共用标识"),
    (lambda s: s["items"][0].update(exclude_columns=["member_id"]), "主键"),
    (lambda s: s["items"][0].update(exclude_columns=["nope"]), "没有的列"),
    (lambda s: s["items"][0].update(table="t9"), "不在本轮表结构"),
    (lambda s: s["value_types"].append({"name": "city_kind", "columns": ["t1.city"]}), "没有可识别的取值"),
])
def test_spec_mistakes_are_reported_before_anything_is_written(change, message):
    spec = json.loads(json.dumps(RETAIL_SPEC))
    change(spec)
    with pytest.raises(expand_tables.SpecError, match=message):
        expand_tables.expand(spec, tables(RETAIL / "tables.json"), {})


def test_booleans_exclusions_and_renames_follow_the_spec_only():
    qinghe = tables(FIXTURES / "qinghe-tables.json")
    spec = {"items": [{"name": "product", "display_name": "商品", "table": "t10", "boolean_columns": ["is_fresh"],
                       "exclude_columns": ["barcode"], "properties": {"spec": {"name": "pack_spec", "display_name": "包装规格"}}},
                      {"name": "brand", "display_name": "品牌", "table": "t8"}]}
    types, datasets, notes = expand_tables.expand(spec, qinghe, {})
    props = {i["after"]["name"]: i["after"] for i in types if i["target_kind"] == "property"
             and i["after"]["owner_type_id"]["client_ref"] == "product"}
    assert props["is_fresh"]["value_kind"] == "boolean" and "barcode" not in props
    assert props["pack_spec"]["display_name"] == "包装规格"
    brand_flag = next(i["after"] for i in types if i["client_ref"] == "brand_is_private_label")
    assert brand_flag["value_kind"] == "integer"  # a candidate only; not listed as boolean
    mapping = next(d["after"] for d in datasets if d["client_ref"] == "map_product")
    assert mapping["fields"]["pack_spec"]["column"] == "spec"
    assert any("t33 ods_sync_log" in n for n in notes)


def test_expander_writes_parts_and_runs_the_fragment_check(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modeling").mkdir()
    (tmp_path / "modeling/entities.json").write_text(json.dumps(RETAIL_SPEC, ensure_ascii=False))
    (tmp_path / "plan.md").write_text("")
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"tables_file": str(RETAIL / "tables.json"), "context_file": str(RETAIL / "context.json"),
                                "schema_file": str(SCHEMA_PATH)}))
    monkeypatch.setattr(sys, "argv", ["expand_tables.py", "--work-pack", str(pack)])
    code = expand_tables.main()
    out = capsys.readouterr().out
    assert (tmp_path / "modeling/parts/01-types.json").exists() and (tmp_path / "modeling/parts/03-datasets.json").exists()
    assert "01b-*.json" in out
    assert code == 0, out


def test_init_lists_every_table_with_candidates(tmp_path):
    lines = init_workflow.table_list(str(FIXTURES / "qinghe-tables.json"))
    text = "\n".join(lines)
    assert lines[0].startswith("- 关联表 34 张") and len(lines) == 35
    assert "po_no→t11" in text and "stocktake_no→t18" in text  # composite-key columns still link
    assert "布尔候选 is_fresh" in text and "取值候选 store_type，status" in text
    assert "t33 ods_sync_log" in text and "像技术表" in text
    assert " id→" not in text and "，id→" not in text  # a generic "id" key links nothing
    assert len(text.encode()) < 6000


def test_init_table_list_is_cut_at_whole_lines(tmp_path):
    lines = table_summary.summary_lines(table_summary.load_tables(FIXTURES / "qinghe-tables.json"), limit=800)
    assert lines[-1].startswith("…其余") and "--search-tables" in lines[-1]
    assert len("\n".join(lines[:-1]).encode()) <= 800


coverage = importlib.import_module("material_coverage")
check_part = importlib.import_module("check_part")


def coverage_workspace(tmp_path, monkeypatch, cited_lines, planned=()):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modeling/parts").mkdir(parents=True)
    material = tmp_path / "material.md"
    material.write_text((RETAIL / "material.md").read_text())
    item = {"operation": "create", "target_kind": "metric", "client_ref": "sales", "after": {
        "name": "sales_amount", "evidence": [{"kind": "material", "material_id": MATERIAL_ID,
                                              "locator": {"line_start": a, "line_end": b}, "quote": "x"} for a, b in cited_lines]}}
    (tmp_path / "modeling/parts/04-metrics-rules.json").write_text(json.dumps([item]))
    (tmp_path / "modeling/entities.json").write_text(json.dumps({"items": [], "planned_metrics": list(planned)}))
    return {"materials": [{"id": MATERIAL_ID, "path": str(material)},
                          {"id": "request", "path": str(material), "from_request": True}]}


def test_coverage_lists_uncited_rule_lines_and_unmet_plans(tmp_path, monkeypatch):
    pack = coverage_workspace(tmp_path, monkeypatch, [(22, 26)], planned=[
        {"name": "sales_amount", "display_name": "销售额", "as": "metric"},
        {"name": "order_count", "display_name": "成交订单数", "as": "metric"},
        {"name": "refund_note", "as": "deferred"}])
    text = "\n".join(coverage.coverage_hints(pack))
    assert "L32" in text and "L33" in text  # metric definitions nobody cites
    assert "L22" not in text and "L26" not in text  # cited through a line range
    assert "成交订单数（计划为 metric order_count）" in text and "销售额（" not in text
    assert "refund_note" not in text  # deferred on purpose
    assert text.count(MATERIAL_ID[:8]) == len([l for l in text.splitlines() if " L" in l])  # request copy not scanned


def test_check_part_prints_coverage_only_with_04_and_never_fails_for_it(tmp_path, monkeypatch, capsys):
    pack = coverage_workspace(tmp_path, monkeypatch, [])
    pack.update(context_file=str(RETAIL / "context.json"), schema_file=str(SCHEMA_PATH))
    (tmp_path / "pack.json").write_text(json.dumps(pack))
    (tmp_path / "modeling/parts/02-links.json").write_text("[]")
    monkeypatch.setattr(sys, "argv", ["check_part.py", "--work-pack", "pack.json", "02"])
    check_part.main()
    assert "没有提案引作证据" not in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["check_part.py", "--work-pack", "pack.json", "04"])
    check_part.main()
    out = capsys.readouterr().out
    assert "没有提案引作证据" in out and "L32" in out
