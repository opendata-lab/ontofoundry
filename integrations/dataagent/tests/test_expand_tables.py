"""Table summary and the entities.json expander (design 2026-11-15 MS-01, MS-03, MS-05), offline."""

import importlib
import json
import sys
from pathlib import Path

import pytest

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
    types, datasets, notes, _ = expand_tables.expand(RETAIL_SPEC, tables(RETAIL / "tables.json"))
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
    types, _, _, _ = expand_tables.expand(RETAIL_SPEC, tables(RETAIL / "tables.json"))
    member_id = next(i["after"] for i in types if i["client_ref"] == "order_member_id")
    assert (member_id["display_name"], member_id["description"]) == ("下单会员", "散客为空")
    level = next(i["after"] for i in types if i["client_ref"] == "member_member_level")
    assert "description" not in level  # the listed values live on the value type


def test_material_basis_cites_lines_and_leaves_the_quote_to_the_platform():
    types, _, _, _ = expand_tables.expand(RETAIL_SPEC, tables(RETAIL / "tables.json"))
    evidence = next(i for i in types if i["client_ref"] == "member")["after"]["evidence"][0]
    assert evidence["locator"] == {"line_start": 6, "line_end": 6} and "quote" not in evidence
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
        expand_tables.expand(spec, tables(RETAIL / "tables.json"))


def test_booleans_exclusions_and_renames_follow_the_spec_only():
    qinghe = tables(FIXTURES / "qinghe-tables.json")
    spec = {"items": [{"name": "product", "display_name": "商品", "table": "t10", "boolean_columns": ["is_fresh"],
                       "exclude_columns": ["barcode"], "properties": {"spec": {"name": "pack_spec", "display_name": "包装规格"}}},
                      {"name": "brand", "display_name": "品牌", "table": "t8"}]}
    types, datasets, notes, _ = expand_tables.expand(spec, qinghe)
    props = {i["after"]["name"]: i["after"] for i in types if i["target_kind"] == "property"
             and i["after"]["owner_type_id"]["client_ref"] == "product"}
    assert props["is_fresh"]["value_kind"] == "boolean" and "barcode" not in props
    assert props["pack_spec"]["display_name"] == "包装规格"
    brand_flag = next(i["after"] for i in types if i["client_ref"] == "brand_is_private_label")
    assert brand_flag["value_kind"] == "integer"  # a candidate only; not listed as boolean
    mapping = next(d["after"] for d in datasets if d["client_ref"] == "map_product")
    assert mapping["fields"]["pack_spec"]["column"] == "spec"
    assert any("t33 ods_sync_log" in n for n in notes)


def test_expander_writes_parts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modeling").mkdir()
    (tmp_path / "modeling/entities.json").write_text(json.dumps(RETAIL_SPEC, ensure_ascii=False))
    (tmp_path / "plan.md").write_text("")
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"tables_file": str(RETAIL / "tables.json")}))
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




# Review findings (Gemini Argon, 2026-11-15) — each pinned by one case.

def qinghe_expand(items, value_types=()):
    return expand_tables.expand({"items": items, "value_types": list(value_types)}, tables(FIXTURES / "qinghe-tables.json"))


def prop(types, ref):
    return next(i["after"] for i in types if i["client_ref"] == ref)


def test_open_lists_keep_their_text_and_covered_tails_are_dropped():
    types, _, _, _ = qinghe_expand(
        [{"name": "price_change", "display_name": "调价", "table": "t31"},
         {"name": "product", "display_name": "商品", "table": "t10", "boolean_columns": ["is_fresh"]}],
        [{"name": "storage_mode", "columns": ["t10.storage_type"]}])
    assert prop(types, "price_change_reason")["description"] == "促销/成本变动/临期"  # not a value type
    assert "description" not in prop(types, "product_is_fresh")  # "1 是 0 否" says nothing for a boolean
    assert "description" not in prop(types, "product_storage_type")  # values live on the value type


def test_generated_ref_clashes_are_reported_not_merged():
    with pytest.raises(expand_tables.SpecError, match="重名"):
        qinghe_expand([{"name": "member", "display_name": "会员", "table": "t6", "properties": {"level_code": {"name": "level"}}},
                       {"name": "member_level", "display_name": "会员等级", "table": "t5"}])


def test_value_type_decides_kind_and_keys_cannot_be_overridden():
    types, _, _, _ = qinghe_expand(
        [{"name": "store", "display_name": "门店", "table": "t2",
          "properties": {"status": {"value_kind": "integer"}, "store_id": {"unique": False}}}],
        [{"name": "store_status", "columns": ["t2.status"]}])
    assert prop(types, "store_status")["value_kind"] == "string"
    assert prop(types, "store_store_id")["unique"] is True


@pytest.mark.parametrize("value_type, message", [
    ({"name": "any_status", "columns": ["t2.status", "t2.nope"]}, "不存在"),
    ({"name": "mixed", "columns": ["t2.status", "t2.area_sqm"], "values": ["a", "b"]}, "基础类型不同"),
    ({"name": "level_no", "columns": ["t7.level"], "values": ["一级", "二级"]}, "不全是数字"),
])
def test_every_bound_column_is_checked(value_type, message):
    with pytest.raises(expand_tables.SpecError, match=message):
        qinghe_expand([{"name": "store", "display_name": "门店", "table": "t2"}], [value_type])


def test_numeric_values_are_not_quoted():
    types, _, _, _ = qinghe_expand([{"name": "category", "display_name": "品类", "table": "t7"}],
                                [{"name": "category_level", "columns": ["t7.level"], "values": [1, 2]}])
    assert prop(types, "vt_category_level_values")["expression"] == "category_level IN (1, 2)"


def test_table_basis_by_name_and_line_ranges():
    spec = {"items": [{"name": "order", "display_name": "订单", "table": "orders",
                       "basis": [{"table": "orders"}, {"material_id": MATERIAL_ID, "line": "2-3"}]}]}
    types, _, _, _ = expand_tables.expand(spec, tables(RETAIL / "tables.json"))
    table_ev, material_ev = prop(types, "order")["evidence"]
    assert table_ev["ref"] == "t3" and material_ev["locator"] == {"line_start": 2, "line_end": 3}
    assert "quote" not in material_ev  # the platform quotes the lines and checks they exist
    spec["items"][0]["basis"] = [{"material_id": MATERIAL_ID, "line": "两行"}]
    with pytest.raises(expand_tables.SpecError, match="12-15"):
        expand_tables.expand(spec, tables(RETAIL / "tables.json"))


def test_same_table_name_in_two_schemas_gets_two_datasets():
    copy = json.loads((RETAIL / "tables.json").read_text())["tables"]
    other = json.loads(json.dumps(copy[2]))
    other.update(key="t9", schema_name="archive")
    pool = {t["key"]: t for t in [*copy, other]}
    _, datasets, _, _ = expand_tables.expand({"items": [
        {"name": "order", "display_name": "订单", "table": "t3"},
        {"name": "old_order", "display_name": "归档订单", "table": "t9"}]}, pool)
    names = [d["after"]["name"] for d in datasets if d["target_kind"] == "dataset"]
    assert len(set(names)) == 2 and "archive_orders" in names


def test_expander_waits_for_plan_approval(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATAAGENT_PLAN_STATE", "pending")
    monkeypatch.setattr(sys, "argv", ["expand_tables.py", "--work-pack", "pack.json"])
    assert expand_tables.main() == 2
    assert "PLAN_NOT_APPROVED" in capsys.readouterr().out and not (tmp_path / "modeling").exists()


RETAIL_LINKS = [
    {"name": "member_home_store", "display_name": "开卡门店", "from": "member", "to": "store", "multiplicity": "many_to_one",
     "on": "home_store_id", "reads": ["{source}在门店开卡{target}", "{target}对应{source}"]},
    {"name": "order_member", "display_name": "下单会员", "from": "order", "to": "member", "multiplicity": "many_to_one", "on": "member_id"},
    {"name": "order_store", "display_name": "成交门店", "from": "order", "to": "store", "multiplicity": "many_to_one", "on": "store_id"},
    {"name": "line_order", "display_name": "属于订单", "from": "order_item", "to": "order", "multiplicity": "many_to_one", "on": "order_no"},
    {"name": "line_product", "display_name": "对应商品", "from": "order_item", "to": "product", "multiplicity": "many_to_one", "on": ["sku"]},
]


def test_compact_links_match_the_hand_written_fixture():
    spec = {**RETAIL_SPEC, "links": RETAIL_LINKS}
    _, _, _, links = expand_tables.expand(spec, tables(RETAIL / "tables.json"))
    expected = {x["after"]["name"]: x["after"] for x in fixture("02-links.json")}
    assert len(links) == 5
    for item in links:
        after, want = item["after"], expected[item["after"]["name"]]
        for key in ("source_type_id", "target_type_id", "multiplicity", "data_join"):
            assert after[key] == want[key], (after["name"], key)
    assert links[0]["after"]["verbalizes"] == expected["member_home_store"]["verbalizes"]
    size = len(json.dumps(RETAIL_LINKS, ensure_ascii=False).encode())
    assert size * 2 < len(json.dumps(links, ensure_ascii=False).encode())  # the point: much less to write


def test_link_through_a_junction_table_gets_its_dataset():
    spec = {"items": [{"name": "promotion", "display_name": "促销活动", "table": "t25"},
                      {"name": "product", "display_name": "商品", "table": "t10"}],
            "links": [{"name": "promoted_product", "display_name": "参与商品", "from": "promotion", "to": "product",
                       "multiplicity": "many_to_many", "via": "t26", "via_from": "promotion_id", "via_to": "sku"}]}
    _, datasets, notes, links = expand_tables.expand(spec, tables(FIXTURES / "qinghe-tables.json"))
    join = links[0]["after"]["data_join"]
    assert join["kind"] == "mapping_table" and join["dataset_id"] == {"client_ref": "ds_promotion_products"}
    assert join["source_key"]["property_ids"] == [{"client_ref": "promotion_promotion_id"}]
    assert join["target_key"]["property_ids"] == [{"client_ref": "product_sku"}]
    assert any(d["client_ref"] == "ds_promotion_products" for d in datasets)
    assert not any("t26 promotion_products" in n for n in notes)  # used, so not listed as left out


@pytest.mark.parametrize("change, message", [
    (lambda link: link.update(multiplicity="one_to_many"), "multiplicity"),
    (lambda link: link.update(on="nope"), "没有属性或列"),
    (lambda link: link.update(to="refund"), "02b-links"),
    (lambda link: link.update(name="order"), "重名"),
    (lambda link: link.pop("on"), "缺 on"),
])
def test_link_spec_mistakes_are_reported(change, message):
    links = json.loads(json.dumps(RETAIL_LINKS))
    change(links[1])
    with pytest.raises(expand_tables.SpecError, match=message):
        expand_tables.expand({**RETAIL_SPEC, "links": links}, tables(RETAIL / "tables.json"))


def test_links_file_is_written_only_when_the_spec_has_links(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modeling/parts").mkdir(parents=True)
    (tmp_path / "modeling/parts/02-links.json").write_text("[]  ")
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"tables_file": str(RETAIL / "tables.json")}))
    monkeypatch.setattr(sys, "argv", ["expand_tables.py", "--work-pack", str(pack)])
    (tmp_path / "modeling/entities.json").write_text(json.dumps(RETAIL_SPEC, ensure_ascii=False))
    expand_tables.main()
    assert (tmp_path / "modeling/parts/02-links.json").read_text() == "[]  "  # hand-written file untouched
    (tmp_path / "modeling/entities.json").write_text(json.dumps({**RETAIL_SPEC, "links": RETAIL_LINKS}, ensure_ascii=False))
    expand_tables.main()
    assert len(json.loads((tmp_path / "modeling/parts/02-links.json").read_text())) == 5
    assert "02-links.json" in capsys.readouterr().out


def snapshot_tables():
    """Two daily full-state tables keyed by (stat_date, code), as warehouse _df tables are."""
    def table(key, name, columns, comment):
        return {"key": key, "kind": "table", "comment": comment, "connection_id": "57c308bc-c544-464b-9d0e-ed56131f1b35",
                "dialect": "mysql", "schema_name": "xinghe_dw", "table": f"xinghe_dw.{name}", "table_name": name,
                "foreign_keys": [], "primary_key": ["stat_date", columns[0][0]],
                "columns": [{"name": "stat_date", "type": "VARCHAR(8)", "value_kind": "string", "comment": "快照日期"},
                            *({"name": c, "type": "VARCHAR(32)", "value_kind": "string", "comment": t} for c, t in columns)]}
    return {"t1": table("t1", "dim_store_df", [("store_code", "门店编码"), ("store_name", "门店名称")], "门店每日快照"),
            "t2": table("t2", "dim_shelf_df", [("shelf_code", "货架编码"), ("store_code", "所属门店")], "货架每日快照")}


SNAPSHOT_SPEC = {"items": [
    {"name": "store", "display_name": "门店", "table": "t1", "snapshot_date_column": "stat_date"},
    {"name": "shelf", "display_name": "货架", "table": "t2", "snapshot_date_column": "stat_date"}],
    "links": [{"name": "shelf_store", "from": "shelf", "to": "store", "multiplicity": "many_to_one", "on": "store_code"}]}


def test_snapshot_date_goes_to_the_dataset_and_the_rest_of_the_key_identifies():
    types, datasets, _, links = expand_tables.expand(json.loads(json.dumps(SNAPSHOT_SPEC)), snapshot_tables())
    store_props = shape(types, "property")
    assert ("store", "stat_date") not in store_props
    assert store_props[("store", "store_code")][1:4] == (True, True, True)  # identifier, required, unique
    dataset = next(d["after"] for d in datasets if d["client_ref"] == "ds_dim_store_df")
    assert dataset["snapshot_date_column"] == "stat_date"
    assert shape(datasets, "mapping")["store"][0] == ["store_code"]
    assert links[0]["after"]["data_join"]["target_property_ids"] == [{"client_ref": "store_store_code"}]


def test_without_a_snapshot_column_the_date_stays_in_the_key():
    spec = json.loads(json.dumps(SNAPSHOT_SPEC))
    for item in spec["items"]:
        item.pop("snapshot_date_column")
    with pytest.raises(expand_tables.SpecError, match="目标端标识有 2 个"):
        expand_tables.expand(spec, snapshot_tables())
    spec["items"][0]["exclude_columns"] = ["stat_date"]
    with pytest.raises(expand_tables.SpecError, match="snapshot_date_column"):
        expand_tables.expand(spec, snapshot_tables())


@pytest.mark.parametrize("change, message", [
    (lambda s: s["items"][0].update(snapshot_date_column="nope"), "没有的列"),
    (lambda s: s["items"].append({"name": "store_copy", "display_name": "门店副本", "table": "t1"}), "不一致"),
])
def test_snapshot_spec_mistakes_are_reported(change, message):
    spec = json.loads(json.dumps(SNAPSHOT_SPEC))
    change(spec)
    with pytest.raises(expand_tables.SpecError, match=message):
        expand_tables.expand(spec, snapshot_tables())
