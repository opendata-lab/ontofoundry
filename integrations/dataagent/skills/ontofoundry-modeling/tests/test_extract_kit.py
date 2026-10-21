"""Fixed extraction examples and conservative/incremental proofs, without services."""

import hashlib
import json
import shlex
import subprocess
import sys
from copy import deepcopy

import pytest
from ontofoundry_api.contracts.proposals import RunContext, apply_items, parse_result
from ontofoundry_api.domain.canonical import element_sha256, snapshot_sha256
from test_stepwise_workflow import check_part, init_workflow, invoke, lookup, write_json
from test_workflow import SCHEMA, SCHEMA_PATH, SKILL, checker, pinned, prepare

KIT = SKILL / "references/extract-kit"
RETAIL = SKILL / "tests/fixtures/extract-retail"
PART_NAMES = ["01-types", "02-links", "03-datasets", "04-metrics-rules", "05-facts"]
MATERIAL_ID = "0b2f2b9b-938b-4452-8a7a-45587024538d"


def load_parts(directory, kit=False):
    return [json.loads((directory / f"{n[:2] if kit else n}.json").read_bytes()) for n in PART_NAMES]


def parse(batch, ctx, material, material_id):
    return parse_result(
        json.dumps(batch).encode(),
        RunContext(**{k: v for k, v in ctx["run"].items() if k != "schema_version"}, draft=ctx["draft"]),
        lambda mid: (hashlib.sha256(material).hexdigest(), material.decode().splitlines())
        if mid == material_id else None,
    )


def prove(parts, ctx, material, material_id, tmp_path, monkeypatch):
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    context = write_json(tmp_path / "context.json", ctx)
    directory = tmp_path / "parts"
    directory.mkdir()
    for name, part in zip(PART_NAMES, parts, strict=True):
        fragment = write_json(directory / f"{name}.json", part)
        assert invoke(monkeypatch, check_part, "--context", context, "--schema", SCHEMA_PATH, fragment) == 0
        report = json.loads((tmp_path / f"modeling/checks/{name}.json").read_bytes())
        assert report["errors"] == []
    output = tmp_path / "output/result.json"
    assert invoke(monkeypatch, prepare, "--context", context, "--schema", SCHEMA_PATH, "--output", output, directory) == 0
    batch = json.loads(output.read_bytes())
    assert checker.check_result(batch, SCHEMA, ctx) == []
    parsed = parse(batch, ctx, material, material_id)
    assert len(parsed.items) == sum(map(len, parts))
    return parsed


def atoms(item):
    """Normalize variable names but retain field paths, types and union values."""
    result = set()
    discriminants = {"kind", "source_kind", "binding_mode", "aggregation", "operator", "owner_kind", "rule_kind"}

    def visit(value, path):
        result.add((path, type(value).__name__))
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = "*" if path == "after/fields" else key
                visit(child, f"{path}/{normalized}")
                if key in discriminants and isinstance(child, str):
                    result.add((f"{path}/{normalized}", child))
        elif isinstance(value, list):
            for child in value:
                visit(child, path + "/*")
    visit(item["after"], "after")
    return {(item["target_kind"], *atom) for atom in result}


def test_fixed_kit_is_bounded_bare_arrays_and_passes_all_validators(tmp_path, monkeypatch):
    parts = []
    for name in PART_NAMES:
        result = lookup("--part", name[:2])
        assert result.returncode == 0, result.stdout.decode()
        assert len(result.stdout) <= 8192
        items = json.loads(result.stdout)
        assert isinstance(items, list)
        assert all(i["operation"] == "create" for i in items)
        assert all(i["after"].get("display_name") for i in items if "name" in i["after"])
        parts.append(items)
    for option in ("--guide", "--values"):
        result = lookup(option)
        assert result.returncode == 0 and len(result.stdout) <= 8192
    ctx = pinned(SKILL / "references/examples/create-object_type.json")
    prove(parts, ctx, (KIT / "material.md").read_bytes(), "11111111-1111-4111-8111-111111111111", tmp_path, monkeypatch)


def test_values_are_exactly_derived_from_current_contract():
    values = json.loads(lookup("--values").stdout)
    definitions = SCHEMA["$defs"]
    expected = {key: definitions[definition]["enum"] for key, definition in {
        "value_kind": "AfterValueKind", "aggregation": "AfterAggregation", "operator": "AfterOperator",
        "multiplicity": "AfterMultiplicity", "binding_mode": "AfterBindingMode",
        "rule_kind": "AfterRuleKind", "rule_owner_kind": "AfterRuleOwnerKind",
    }.items()}
    for key, names in {
        "binding_kind": ["ColumnBinding", "ExpressionBinding"],
        "data_join_kind": ["AfterDirectJoin", "AfterMappingTableJoin"],
        "metric_kind": ["AfterSimpleMetric", "AfterRatioMetric", "AfterExpressionMetric"],
    }.items():
        expected[key] = [definitions[name]["properties"]["kind"]["const"] for name in names]
    expected["source_kind"] = definitions["dataset_after"]["properties"]["source_kind"]["enum"]
    assert values == expected
    assert len(values["value_kind"]) == 7


def test_kit_explicit_shape_inventory_and_fixture_coverage():
    parts = load_parts(KIT, kit=True)
    items = [i for part in parts for i in part]
    by_ref = {i["client_ref"]: i["after"] for i in items}
    shapes = set()
    identifiers = {}
    for item in items:
        after, kind = item["after"], item["target_kind"]
        if kind == "property" and after.get("identifier"):
            identifiers.setdefault(after["owner_type_id"]["client_ref"], []).append(after)
        if kind == "property" and after.get("value_type_id"):
            value_type = by_ref[after["value_type_id"]["client_ref"]]
            assert after["value_kind"] == value_type["value_kind"]
            shapes.add("值类型引用属性")
        if kind == "rule":
            shapes.add("规则/" + after["owner_kind"])
            if after["owner_kind"] == "link_type":
                assert "refund.refund_for_order.pay_amount" in after["expression"]
                shapes.add("跨关系约束")
        if kind == "link_type":
            assert after["data_join"]["kind"] == "direct"
            assert all("{source}" in v and "{target}" in v for v in after["verbalizes"])
            shapes.add("direct与正反读法")
        if kind == "dataset":
            assert after["connection_id"]
            if after["source_kind"] == "query":
                assert "UNION ALL" in after["query_sql"]
                assert "o.order_date AS biz_date" in after["query_sql"]
                assert "r.refund_date AS biz_date" in after["query_sql"]
                shapes.add("UNION各带日期")
            else:
                shapes.add("表列" if after["columns"] else "未同步无列")
        if kind == "mapping":
            shapes.add("复合键映射" if len(after["sources"][0]["key_columns"]) > 1 else "普通映射")
        if kind == "metric":
            shapes.add("指标/" + after["kind"])
            if after["kind"] == "simple":
                shapes.add(after["aggregation"])
                if after.get("filters") and after.get("time_field"):
                    shapes.add("过滤与时间")
                if after["aggregation"] == "count":
                    assert "measure" not in after
            else:
                assert by_ref[after["numerator_id"]["client_ref"]]["dataset_id"] == by_ref[after["denominator_id"]["client_ref"]]["dataset_id"]
        if after.get("evidence"):
            shapes.add("材料证据")
    for group in identifiers.values():
        assert all(p["required"] for p in group)
        if len(group) == 1:
            assert group[0]["unique"]
            shapes.add("单标识")
        else:
            assert all(not p["unique"] for p in group)
            shapes.add("复合标识")
    assert parts[-1] == []
    shapes.add("空事实")
    assert shapes == {
        "单标识", "复合标识", "值类型引用属性", "规则/value_type", "规则/property", "规则/link_type",
        "跨关系约束", "direct与正反读法", "表列", "未同步无列", "UNION各带日期", "普通映射", "复合键映射",
        "指标/simple", "指标/ratio", "sum", "count", "过滤与时间", "材料证据", "空事实",
    }
    covered = set().union(*(atoms(i) for i in items))
    for version in ("conservative", "supplemented"):
        for part in load_parts(RETAIL / version):
            for item in part:
                assert atoms(item) <= covered, (version, item["client_ref"], atoms(item) - covered)


@pytest.mark.parametrize("version,count", [("conservative", 63), ("supplemented", 69)])
def test_retail_candidates_and_no_unknown_refund_columns(version, count, tmp_path, monkeypatch):
    parts = load_parts(RETAIL / version)
    ctx = json.loads((RETAIL / "context.json").read_bytes())
    parsed = prove(parts, ctx, (RETAIL / "material.md").read_bytes(), MATERIAL_ID, tmp_path, monkeypatch)
    assert len(parsed.items) == count
    items = {i["client_ref"]: i["after"] for p in parts for i in p}
    assert items["product"]["display_name"] == "商品 SKU"
    assert items["order_item"]["name"] == "order_item"
    assert not items["order_member_id"].get("required")
    assert items["member_home_store_id"]["required"]
    assert items["order_item_map"]["sources"][0]["key_columns"] == ["order_no", "line_no"]
    missing = {"refund_map", "events_ds", "refund_amount", "events_sales", "events_refunds", "refund_rate"}
    if version == "conservative":
        assert items.keys().isdisjoint(missing)
        assert items["refund_ds"]["columns"] == []
        assert not any(t["table_name"] == "refunds" for t in json.loads((RETAIL / "tables.json").read_bytes())["tables"])
        assert "先在数据管理同步该表，再发起补齐" in (RETAIL / "delivery.md").read_text()
        assert sum(i.target_kind == "metric" for i in parsed.items) == 3
    else:
        assert missing <= items.keys()
        assert len(items["refund_ds"]["columns"]) == 5
        assert sum(i.target_kind == "metric" for i in parsed.items) == 7


def test_sync_refunds_then_incrementally_complete_existing_graph(tmp_path, monkeypatch):
    ctx = json.loads((RETAIL / "context.json").read_bytes())
    material = (RETAIL / "material.md").read_bytes()
    conservative = parse(prepare.assemble(ctx, load_parts(RETAIL / "conservative")), ctx, material, MATERIAL_ID)
    existing = {i.client_ref: i.target_id for i in conservative.items}
    ctx["draft"] = apply_items(ctx["draft"], conservative.items)
    ctx["run"].update(run_token="offline-refunds-increment", source_session_revision=2, source_draft_sha256=snapshot_sha256(ctx["draft"]))
    ctx["element_hashes"] = {e["id"]: element_sha256(e, collection=collection) for collection in checker.COLLECTIONS.values() for e in ctx["draft"][collection]}

    def resolve(value):
        if isinstance(value, dict):
            if set(value) == {"client_ref"} and value["client_ref"] in existing:
                return existing[value["client_ref"]]
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    parts = []
    for part in load_parts(RETAIL / "supplemented"):
        changes = []
        for raw in part:
            ref = raw["client_ref"]
            if ref == "refund_ds":
                changes.append({"operation": "update", "target_kind": "dataset", "target_id": existing[ref], "after": resolve(raw["after"])})
            elif ref not in existing:
                changes.append(resolve(deepcopy(raw)))
        parts.append(changes)
    parsed = prove(parts, ctx, material, MATERIAL_ID, tmp_path, monkeypatch)
    assert len(parsed.items) == 7
    assert sum(i.operation == "update" for i in parsed.items) == 1
    final = apply_items(ctx["draft"], parsed.items)
    assert len(final["object_types"]) == 6
    assert len(final["metrics"]) == 7
    refund = next(d for d in final["datasets"] if d["id"] == existing["refund_ds"])
    assert len(refund["columns"]) == 5
    assert not any(i.target_kind in {"object_type", "property", "link_type"} for i in parsed.items)
    full_ctx = json.loads((RETAIL / "context.json").read_bytes())
    full = parse(prepare.assemble(full_ctx, load_parts(RETAIL / "supplemented")), full_ctx, material, MATERIAL_ID)

    def logical_graph(graph, refs):
        ids = {identity: ref for ref, identity in refs.items()}

        def normalize(value):
            if isinstance(value, dict):
                return {k: normalize(v) for k, v in value.items() if not (k == "id" and value.get("kind") == "material")}
            if isinstance(value, list):
                return [normalize(v) for v in value]
            return ids.get(value, value) if isinstance(value, str) else value
        return {c: sorted((normalize(e) for e in graph[c]), key=lambda e: e["id"]) for c in checker.COLLECTIONS.values()}
    final_refs = {**existing, **{i.client_ref: i.target_id for i in parsed.items if i.client_ref}}
    assert logical_graph(final, final_refs) == logical_graph(apply_items(full_ctx["draft"], full.items), {i.client_ref: i.target_id for i in full.items})


@pytest.mark.parametrize("kind,after,pointer,expected", [
    ("metric", {"kind": "simple"}, "/after/filters/0/operator", "--part 04"),
    ("metric", {"kind": "simple", "aggregation": "count"}, "/after/measure", "--part 04"),
    ("metric", {"kind": "ratio"}, "/after/numerator_id", "--variant ratio"),
    ("metric", {"kind": "expression"}, "/after/expression", "--variant expression"),
    ("dataset", {"source_kind": "query"}, "/after/columns", "--part 03"),
    ("dataset", {}, "/after/query_sql", "--part 03"),
    ("link_type", {}, "/after/data_join/source_property_ids", "--part 02"),
    ("link_type", {"data_join": {"kind": "mapping_table"}}, "/after/data_join", "--variant mapping_table"),
    ("mapping", {"fields": {"amount": {"kind": "expression"}}}, "/after/fields/amount/expression", "--variant expression"),
])
def test_error_routes_are_structural_and_executable(kind, after, pointer, expected):
    # Business strings resembling variants must not influence routing.
    after.update(name="filter_ratio_query", description="COUNT data_join expression")
    command = checker.example_command(kind, "create", after, pointer)
    assert expected in command
    result = subprocess.run([sys.executable, *shlex.split(command)[1:]], capture_output=True, check=False)
    assert result.returncode == 0 and len(result.stdout) <= 8192
    for operation in ("update", "delete"):
        command = checker.example_command(kind, operation, after, pointer)
        assert f"--operation {operation}" in command and "--part" not in command


def test_init_creates_both_requested_parent_directories_idempotently(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pack = write_json(tmp_path / "pack.json", {"result_file": "output/results/run.json", "needs_input_file": "output/questions/run.json"})
    for _ in range(2):
        assert invoke(monkeypatch, init_workflow, "--work-pack", pack) == 0
        assert (tmp_path / "output/results").is_dir()
        assert (tmp_path / "output/questions").is_dir()
    assert not (tmp_path / "output/results/run.json").exists()


def test_every_fixed_payload_is_registered_and_invalid_combinations_fail():
    assert {p.name for p in KIT.iterdir()} == {"01.json", "02.json", "03.json", "04.json", "05.json", "values.json", "guide.md", "material.md"}
    for args in (("--part", "06"), ("--part", "01", "metric"), ("--values", "--operation", "update"), ("--part", "01", "--with-deps")):
        result = lookup(*args)
        assert result.returncode != 0
        assert len(result.stdout + result.stderr) <= 8192


def test_event_query_preserves_months_and_does_not_duplicate_sales():
    import sqlite3

    items = {i["client_ref"]: i["after"] for p in load_parts(RETAIL / "supplemented") for i in p}
    query = items["events_ds"]["query_sql"]
    with sqlite3.connect(":memory:") as connection:
        connection.executescript((RETAIL / "events-seed.sql").read_text())
        cursor = connection.execute(query)
        assert [c[0] for c in cursor.description] == [c["name"] for c in items["events_ds"]["columns"]]
        sales, refunds = connection.execute("SELECT SUM(sales_amount), SUM(refund_amount) FROM (" + query + ")").fetchone()
        assert round(sales, 2) == 668.90
        assert round(refunds, 2) == 71.70
        assert round(refunds / sales * 100, 4) == 10.7191
        months = connection.execute("SELECT substr(biz_date,1,7), SUM(sales_amount) FROM (" + query + ") GROUP BY 1").fetchall()
        assert [(month, round(amount, 2)) for month, amount in months] == [("2026-01", 257.20), ("2026-02", 174.60), ("2026-03", 237.10)]


def test_abstract_route_budget_cannot_hide_extraction_overflow(monkeypatch):
    from test_workflow import budget

    monkeypatch.setattr(budget, "EXTRACT_ROUTE_LIMIT", 1)
    report = budget.byte_report()
    assert not report["routes"]["第二步（抽取）"]["pass"]
    assert not report["all_limits_pass"]
