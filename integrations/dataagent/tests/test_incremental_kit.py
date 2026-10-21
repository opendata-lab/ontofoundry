from pathlib import Path
BASE = Path(__file__).resolve().parents[1]

"""Offline incremental authoring through public examples and exact element reads."""

import hashlib
import importlib
import json
import sqlite3
import subprocess
import sys
from copy import deepcopy

import pytest
from ontofoundry_api.contracts.proposals import apply_items
from ontofoundry_api.domain.canonical import element_sha256, snapshot_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import reference_index
from test_extract_kit import KIT, MATERIAL_ID, RETAIL, atoms, load_parts, parse, prove
from test_stepwise_workflow import lookup, write_json
from test_workflow import SKILL, budget, checker, pinned, prepare, server_parse

element_reader = importlib.import_module("show_element")
ElementIndex = element_reader.ElementIndex
bounded = element_reader.bounded

V1 = RETAIL / "v1-context.json"


def context():
    return json.loads(V1.read_bytes())


def cli(tmp_path, ctx, *selectors, extra=()):
    path = write_json(tmp_path / "context.json", ctx)
    pack = write_json(tmp_path / "pack.json", {"context_file": str(path)})
    result = subprocess.run(
        [sys.executable, str(SKILL / "scripts/show_element.py"), "--work-pack", str(pack), *selectors, *extra],
        cwd=tmp_path, capture_output=True, check=False,
    )
    assert len(result.stdout) <= 8192
    assert result.stderr == b""
    return result.returncode, json.loads(result.stdout)


def logical_graph(graph, refs):
    ids = {identity: ref for ref, identity in refs.items()}

    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items() if not (k == "id" and value.get("kind") == "material")}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        return ids.get(value, value) if isinstance(value, str) else value

    return {c: sorted((normalize(e) for e in graph[c]), key=lambda e: e["id"]) for c in checker.COLLECTIONS.values()}


def test_fixed_v1_is_the_accepted_conservative_model():
    initial = json.loads((RETAIL / "context.json").read_bytes())
    material = (RETAIL / "material.md").read_bytes()
    accepted = parse(prepare.assemble(initial, load_parts(RETAIL / "conservative")), initial, material, MATERIAL_ID)
    ctx = context()
    assert len(accepted.items) == 63
    assert apply_items(initial["draft"], accepted.items) == ctx["draft"]
    assert json.loads((RETAIL / "v1-refs.json").read_bytes()) == {i.client_ref: i.target_id for i in accepted.items}
    assert ctx["run"]["base_version_id"]
    assert ctx["run"]["source_draft_sha256"] == ctx["run"]["base_version_sha256"] == snapshot_sha256(ctx["draft"])
    assert ctx["element_hashes"] == {e["id"]: element_sha256(e, collection=c) for c in checker.COLLECTIONS.values() for e in ctx["draft"][c]}


def test_new_incremental_route_proves_seven_items_final_graph_and_sqlite(tmp_path, monkeypatch):
    ctx = context()
    definitions = {}
    for selectors in budget.INCREMENTAL_QUERIES:
        status, payload = cli(tmp_path, ctx, *selectors)
        assert status == 0
        definitions.update({e["selector"]: e["definition"] for e in payload["elements"]})
    example = lookup("--part", "update")
    assert example.returncode == 0 and len(example.stdout) <= 8192
    shapes = json.loads(example.stdout)
    # Business literals come only from the offline fixture, never the public kit.
    items = json.loads((RETAIL / "v1-increment.json").read_bytes())
    for item, shape in zip(items, shapes, strict=True):
        assert item["operation"] == shape["operation"]
        assert atoms(item) <= atoms(shape)
    assert len(items) == 7
    assert all("before" not in i and "expected_target_hash" not in i for i in items)
    assert [i["operation"] for i in items].count("update") == 1

    # Author the existing target from show_element, preserving unrelated fields.
    dataset = definitions["dataset:refunds"]
    supplied = items[0]["after"]
    after = {k: deepcopy(v) for k, v in dataset.items() if k != "id"}
    after.update(columns=supplied["columns"], description=supplied["description"])
    items[0] = {"operation": "update", "target_kind": "dataset", "target_id": dataset["id"], "after": after}
    mapping = items[1]["after"]
    mapping["type_id"] = definitions["object_type:refund"]["id"]
    mapping["sources"][0]["dataset_id"] = dataset["id"]
    assert set(mapping["fields"]) == {d["name"] for s, d in definitions.items() if s.startswith("property:")}

    # Every existing UUID used by the template is present in the exact reads.
    known = {d["id"] for d in definitions.values()}
    old_ids = set(ctx["element_hashes"])

    def references(value):
        if isinstance(value, dict):
            return set().union(*(references(v) for v in value.values()))
        if isinstance(value, list):
            return set().union(*(references(v) for v in value))
        return {value} if isinstance(value, str) and value in old_ids else set()

    assert references(items) <= known
    parsed = prove([items, [], [], [], []], ctx, (RETAIL / "material.md").read_bytes(), MATERIAL_ID, tmp_path / "proof", monkeypatch)
    final = apply_items(ctx["draft"], parsed.items)
    update = parsed.items[0]
    assert update.before == dataset
    batch = json.loads((tmp_path / "proof/output/result.json").read_bytes())
    assert batch["items"][0]["expected_target_hash"] == ctx["element_hashes"][dataset["id"]]
    assert len(next(d for d in final["datasets"] if d["id"] == dataset["id"])["columns"]) == 5
    assert not any(i.target_kind in {"property", "object_type", "link_type"} for i in parsed.items)

    # Supplemented candidates are used only as the independent expected graph.
    initial = json.loads((RETAIL / "context.json").read_bytes())
    expected = parse(prepare.assemble(initial, load_parts(RETAIL / "supplemented")), initial, (RETAIL / "material.md").read_bytes(), MATERIAL_ID)
    assert len(expected.items) == 69
    refs = json.loads((RETAIL / "v1-refs.json").read_bytes())
    refs.update({i.client_ref: i.target_id for i in parsed.items if i.client_ref})
    assert logical_graph(final, refs) == logical_graph(apply_items(initial["draft"], expected.items), {i.client_ref: i.target_id for i in expected.items})

    metrics = {m["id"]: m for m in final["metrics"]}
    ratio = next(m for m in metrics.values() if m["name"] == "refund_rate")
    numerator, denominator = metrics[ratio["numerator_id"]], metrics[ratio["denominator_id"]]
    assert numerator["dataset_id"] == denominator["dataset_id"]
    assert numerator["kind"] == denominator["kind"] == "simple"
    assert numerator["aggregation"] == denominator["aggregation"] == "sum"
    assert numerator["filters"] == denominator["filters"] == []
    query = next(d["query_sql"] for d in final["datasets"] if d["id"] == numerator["dataset_id"])
    with sqlite3.connect(":memory:") as connection:
        connection.executescript((RETAIL / "events-seed.sql").read_text())
        refund, sales = connection.execute(f'SELECT SUM("{numerator["measure"]["column"]}"), SUM("{denominator["measure"]["column"]}") FROM ({query})').fetchone()
    assert round(refund, 2) == 71.70
    assert round(sales, 2) == 668.90
    assert f"{refund / sales * 100:.2f}%" == "10.72%"


@pytest.mark.parametrize("parts", [("update",), ("edit",), ("update", "edit")])
def test_incremental_examples_pass_all_three_validators(parts, tmp_path, monkeypatch):
    payloads = []
    for part in parts:
        result = lookup("--part", part)
        assert result.returncode == 0 and len(result.stdout) <= 8192
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)
        assert all("before" not in i and "expected_target_hash" not in i for i in payload)
        payloads.append(payload)
    payloads += [[] for _ in range(5 - len(payloads))]
    library = BASE / "tests/fixtures/extract-library"
    ctx = json.loads((library / "v1-context.json").read_bytes())
    parsed = prove(payloads, ctx, (KIT / "material.md").read_bytes(), "11111111-1111-4111-8111-111111111111", tmp_path, monkeypatch)
    if "edit" in parts:
        assert any(i.operation == "delete" for i in parsed.items)
        assert any(i.target_kind == "rule" and i.operation == "create" and isinstance(i.after["owner_id"], str) for i in parsed.items)
        for kind in ("property", "metric"):
            item = next(i for i in parsed.items if i.target_kind == kind and i.operation == "update")
            assert {k: v for k, v in item.before.items() if k not in {"id", "display_name", "description"}} == {k: v for k, v in item.after.items() if k not in {"id", "display_name", "description"}}


def test_exact_queries_return_full_definitions_hashes_and_only_small_reference_labels(tmp_path):
    ctx = context()
    status, data = cli(tmp_path, ctx, "refund", "property:refund.refund_amount", "refund.refund_for_order")
    assert status == 0
    existing = {e["id"]: e for c in checker.COLLECTIONS.values() for e in ctx["draft"][c]}
    for element in data["elements"]:
        definition = element["definition"]
        assert definition == existing[definition["id"]]
        assert element["hash"] == ctx["element_hashes"][definition["id"]]
        assert all(set(r) <= {"id", "name"} for r in element["referenced_by"])
        status, by_id = cli(tmp_path, ctx, definition["id"])
        assert status == 0 and by_id["elements"] == [element]
    refs = data["elements"][1]["referenced_by"]
    assert any(r.get("name") == "refund_limit" for r in refs)


@pytest.mark.parametrize("selector", ["missing_refund", "Refund", "退款", "city", "property:city"])
def test_nonexistent_and_ambiguous_queries_fail_with_exact_candidates(tmp_path, selector):
    status, data = cli(tmp_path, context(), selector)
    assert status == 1
    error = data["errors"][0]
    assert ("有歧义" if "city" in selector else "不存在") in error["错误"]
    candidates = error["候选精确写法"]
    assert candidates
    index = ElementIndex(context())
    assert all(index.find(s)[1] is None for s in candidates)
    if "city" in selector:
        assert candidates == ["property:member.city", "property:store.city"]


def test_pagination_reconstructs_full_unicode_definition_and_pins_hash(tmp_path):
    ctx = context()
    ctx["draft"]["object_types"][0]["description"] = '说明与引号"\\\n' * 3000
    selectors = [ctx["draft"]["object_types"][0]["id"]]
    status, summary = cli(tmp_path, ctx, *selectors)
    assert status == 0
    assert "elements" not in summary
    pages = summary["分页"]
    assert pages["pages"] > 1
    content = ""
    for page in range(1, pages["pages"] + 1):
        status, part = cli(tmp_path, ctx, *selectors, extra=("--page", str(page), "--sha256", pages["sha256"]))
        assert status == 0
        content += part["text"]
    assert hashlib.sha256(content.encode()).hexdigest() == pages["sha256"]
    assert json.loads(content)["elements"][0]["definition"] == ctx["draft"]["object_types"][0]
    ctx["draft"]["object_types"][0]["description"] += "变化"
    status, error = cli(tmp_path, ctx, *selectors, extra=("--page", "1", "--sha256", pages["sha256"]))
    assert status == 1 and "已变化" in error["原因"]
    status, error = cli(tmp_path, ctx, *selectors, extra=("--page", "0"))
    assert status == 1 and "页码" in error["原因"]


def test_bounded_errors_preserve_all_exact_candidates(tmp_path):
    ctx = context()
    for number in range(400):
        e = deepcopy(ctx["draft"]["datasets"][0])
        e.update(id=f"88888888-8888-4888-8888-{number:012d}", name=f"dataset_{number:04d}")
        ctx["draft"]["datasets"].append(e)
    value, status = ElementIndex(ctx).query(["missing"])
    assert status == 1
    summary = json.loads(bounded(value))
    assert summary["分页"]["pages"] > 1
    chunks = [json.loads(bounded(value, n))["text"] for n in range(1, summary["分页"]["pages"] + 1)]
    assert json.loads("".join(chunks)) == value


def test_reference_projection_matches_domain_on_v1_and_expressions():
    ctx = context()
    graph = ctx["draft"]
    actual = ElementIndex(ctx).reverse_refs()
    expected = {}
    for owner, refs in reference_index(CoreDraft.model_validate(graph)).items():
        for ref in refs:
            expected.setdefault(str(ref.target_id), set()).add(str(owner))
    assert dict(actual) == expected
    index = ElementIndex(ctx)
    root = next(e for e in graph["object_types"] if e["name"] == "refund")
    prop = index.member("property", root["id"], "refund_amount")
    assert index.expression_refs("'refund.refund_amount' /* refund.refund_amount */") == set()
    assert index.expression_refs('"refund"."refund_amount" >= 0') == {root["id"], prop["id"]}
    owner = next(e for e in graph["object_types"] if e["name"] == "order")
    link = next(e for e in graph["link_types"] if e["name"] == "refund_for_order")
    assert index.expression_refs("EXISTS(order.REVERSE(refund_for_order))") == {owner["id"], link["id"]}


@pytest.mark.parametrize("filename", ["inheritance.json", "link-joins.json", "expression-binding.json", "reified-event.json", "facts.json"])
def test_reference_projection_uses_existing_semantic_paths(filename):
    path = SKILL / "references/examples" / filename
    ctx = pinned(path)
    batch = server_parse(prepare.assemble(ctx, [json.loads(path.read_bytes())]), ctx)
    ctx["draft"] = apply_items(ctx["draft"], batch.items)
    expected = {}
    for owner, refs in reference_index(CoreDraft.model_validate(ctx["draft"])).items():
        for ref in refs:
            expected.setdefault(str(ref.target_id), set()).add(str(owner))
    assert dict(ElementIndex(ctx).reverse_refs()) == expected


def test_incremental_read_budget_counts_public_outputs_and_enforces_limit(monkeypatch):
    report = budget.byte_report()
    route = report["routes"]["增量（退款补齐）"]
    assert route["pass"] and report["all_limits_pass"]
    assert route["bytes"] == sum(c["bytes"] for c in route["components"].values())
    assert route["estimated_rounds"]["normal"] == [6, 8]
    assert route["estimated_rounds"]["two_repairs"] == [10, 12]
    assert route["optional_edit_bytes"] == len(lookup("--part", "edit").stdout)
    assert {"工作包", "带原行号材料", "表结构", "原则", "技能入口", "写法包/incremental.md", "写法包/values.json", "写法包/update.json", "已有元素/0", "已有元素/1"} <= route["components"].keys()
    assert any(k.startswith("工作包索引/") for k in route["components"])
    for n, selectors in enumerate(budget.INCREMENTAL_QUERIES):
        value, status = ElementIndex(context()).query(selectors)
        assert status == 0
        assert route["components"][f"已有元素/{n}"]["bytes"] == len((bounded(value) + "\n").encode())
    monkeypatch.setattr(budget, "INCREMENTAL_ROUTE_LIMIT", 1)
    report = budget.byte_report()
    assert not report["routes"]["增量（退款补齐）"]["pass"]
    assert not report["all_limits_pass"]


def test_skill_incremental_instructions_and_guide_are_bounded():
    skill = (BASE / "skills/ontology-discovery/SKILL.md").read_bytes()
    assert len(skill) <= 4000
    assert "不读 context_file 全文、脚本源码或 Schema" in skill.decode()
    for args in [("--incremental-guide",), ("--part", "edit"), ("--part", "update")]:
        result = lookup(*args)
        assert result.returncode == 0 and len(result.stdout) <= 8192
    assert "display_name 只写名称" in (KIT / "incremental.md").read_text()


def test_library_base_is_independent_and_incremental_references_are_explicit():
    library = BASE / "tests/fixtures/extract-library"
    initial = json.loads((library / "context.json").read_bytes())
    ctx = json.loads((library / "v1-context.json").read_bytes())
    parts = load_parts(KIT, kit=True)
    added = {"claim_map", "ledger_ds", "charge", "ledger_deposits", "ledger_charges", "claim_share"}
    base = []
    for part in parts:
        subset = [deepcopy(i) for i in part if i["client_ref"] not in added]
        for item in subset:
            if item["client_ref"] == "claim_ds":
                item["after"].update(columns=[], description="赔偿表待同步")
        base.append(subset)
    material = (KIT / "material.md").read_bytes()
    accepted = parse(prepare.assemble(initial, base), initial, material, "11111111-1111-4111-8111-111111111111")
    assert apply_items(initial["draft"], accepted.items) == ctx["draft"]
    refs = json.loads((library / "v1-refs.json").read_bytes())
    assert refs == {i.client_ref: i.target_id for i in accepted.items}
    assert set(ctx["element_hashes"]).isdisjoint(context()["element_hashes"])
    assert ctx["run"]["source_draft_sha256"] == snapshot_sha256(ctx["draft"])
    assert ctx["element_hashes"] == {e["id"]: element_sha256(e, collection=c) for c in checker.COLLECTIONS.values() for e in ctx["draft"][c]}
    items = json.loads(lookup("--part", "update").stdout)
    assert len(items) == 7
    target, mapping, query, metric, first, second, ratio = items
    assert target["target_id"] == refs["claim_ds"]
    existing = next(d for d in ctx["draft"]["datasets"] if d["id"] == target["target_id"])
    assert existing["columns"] == [] and len(target["after"]["columns"]) == 5
    assert {k: v for k, v in existing.items() if k not in {"id", "columns", "description"}} == {k: v for k, v in target["after"].items() if k not in {"columns", "description"}}
    assert mapping["after"]["type_id"] == refs["claim"]
    assert mapping["after"]["sources"][0]["dataset_id"] == refs["claim_ds"]
    assert metric["after"]["dataset_id"] == refs["claim_ds"]
    assert first["after"]["dataset_id"] == second["after"]["dataset_id"] == {"client_ref": query["client_ref"]}
    assert ratio["after"]["numerator_id"] == {"client_ref": second["client_ref"]}
    assert ratio["after"]["denominator_id"] == {"client_ref": first["client_ref"]}
    edits = json.loads(lookup("--part", "edit").stdout)
    parsed = parse(prepare.assemble(ctx, [items, edits]), ctx, material, "11111111-1111-4111-8111-111111111111")
    for item in parsed.items:
        if item.operation == "update" and item.target_kind in {"property", "metric"}:
            assert item.after["display_name"] != item.before["display_name"]
            assert item.after["description"] != item.before["description"]
    assert edits[2]["after"]["owner_id"] == refs["claim_charge"]
    assert edits[3] == {"operation": "delete", "target_kind": "rule", "target_id": refs["copy_count_nonnegative"]}


def test_library_event_query_keeps_both_event_dates_without_repeating_deposits():
    query = next(i["after"]["query_sql"] for i in json.loads(lookup("--part", "update").stdout) if i.get("client_ref") == "ledger_ds")
    with sqlite3.connect(":memory:") as connection:
        connection.executescript("""
            ATTACH DATABASE ':memory:' AS chengye_library;
            CREATE TABLE chengye_library.loans (loan_no TEXT, lent_on TEXT, branch_code TEXT, deposit NUMERIC, status TEXT);
            CREATE TABLE chengye_library.claims (claim_no TEXT, loan_no TEXT, assessed_on TEXT, charge NUMERIC);
            INSERT INTO chengye_library.loans VALUES ('L1','2026-01-01','B1',120,'已借出'),('L2','2026-01-02','B1',30,'已取消');
            INSERT INTO chengye_library.claims VALUES ('C1','L1','2026-02-01',10),('C2','L1','2026-02-03',5);
        """)
        rows = connection.execute("SELECT substr(event_on,1,7), SUM(deposit_total), SUM(charge) FROM (" + query + ") GROUP BY 1").fetchall()
    assert rows == [("2026-01", 120, 0), ("2026-02", 0, 15)]
