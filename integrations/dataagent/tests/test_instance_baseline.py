"""Pinned instance edits stay separate from definitions and copy revision hashes."""

from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator
from ontofoundry_api.contracts.proposals import ProposalContractError
from ontofoundry_api.domain.canonical import domain_sha256
from ontofoundry_api.domain.instances import instance_hash
from test_stepwise_workflow import check_part
from test_workflow import BASE, SCHEMA, SKILL, checker, pinned, prepare, server_parse
from show_element import ElementIndex


def context():
    return pinned(SKILL / "references/examples/update-material_link.json")


def fragment(ctx, kind, operation):
    entry = next(e for e in ctx["instance_baseline"]["items"] if e["target_kind"] == kind)
    item = {"operation": operation, "target_kind": kind, "target_id": entry["target_id"]}
    if operation == "update":
        item["after"] = {k: deepcopy(v) for k, v in entry["element"].items() if k != "id"}
        if kind == "material_object":
            item["after"]["values"]["staff_name"] = "小岚（更新）"
    return item, entry


@pytest.mark.parametrize("kind", sorted(checker.INSTANCE_KINDS))
@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("state", ["active", "staged"])
def test_instance_edits_copy_baseline_before_and_hash(kind, operation, state):
    ctx = context()
    item, entry = fragment(ctx, kind, operation)
    entry.update(state=state, session_id=ctx["run"]["session_id"] if state == "staged" else None)
    original = deepcopy(ctx)
    batch = prepare.assemble(ctx, [[item]])
    edit = batch["items"][0]
    assert edit["before"] == entry["element"] and edit["before"] is not entry["element"]
    assert edit["expected_target_hash"] == entry["hash"] == instance_hash(entry["element"], entry["revision"])
    assert edit["expected_target_hash"] != domain_sha256(entry["element"])
    assert "id" not in (edit["after"] or {})
    assert set(batch) == set(ctx["run"]) | {"items"}
    assert not checker.check_result(batch, SCHEMA, ctx)
    assert not check_part.check_fragment([item], ctx, SCHEMA)["errors"]
    parsed = server_parse(batch, ctx)
    assert parsed.items[0].expected_instance_revision == entry["revision"]
    assert ctx == original


@pytest.mark.parametrize("kind", sorted(checker.INSTANCE_KINDS))
@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("mutation,code", [
    ("missing", "TARGET_NOT_FOUND"),
    ("before", "BEFORE_MISMATCH"),
    ("hash", "TARGET_HASH_MISMATCH"),
])
def test_instance_errors_agree_in_fragment_result_and_platform(kind, operation, mutation, code):
    ctx = context()
    item, entry = fragment(ctx, kind, operation)
    batch = prepare.assemble(ctx, [[item]])
    edited = batch["items"][0]
    if mutation == "missing":
        ctx["instance_baseline"]["items"].remove(entry)
        # Stale legacy collections and definition hashes cannot supply instances.
        ctx["draft"][kind + "s"] = [entry["element"]]
        ctx["element_hashes"][entry["target_id"]] = entry["hash"]
    elif mutation == "before":
        edited["before"]["evidence"] = []
    else:
        edited["expected_target_hash"] = instance_hash(entry["element"], entry["revision"] + 1)
    with pytest.raises(prepare.PrepareInputError, match=code):
        prepare.assemble(ctx, [[edited]])
    assert any(code in e for e in check_part.check_fragment([edited], ctx, SCHEMA)["errors"])
    assert any(code in e for e in checker.check_result(batch, SCHEMA, ctx))
    with pytest.raises(ProposalContractError) as caught:
        server_parse(batch, ctx)
    assert caught.value.code == code


def test_instances_use_kind_and_id_and_never_definition_hashes():
    ctx = context()
    item, entry = fragment(ctx, "material_object", "update")
    ctx["element_hashes"][entry["target_id"]] = "0" * 64
    entry["hash"] = "f" * 64
    batch = prepare.assemble(ctx, [[item]])
    assert batch["items"][0]["expected_target_hash"] == "f" * 64
    assert not checker.check_result(batch, SCHEMA, ctx)
    item["target_kind"] = "material_link"
    with pytest.raises(prepare.PrepareInputError, match="TARGET_NOT_FOUND"):
        prepare.assemble(ctx, [[item]])


@pytest.mark.parametrize("state", ["deleted", "other_session"])
def test_invisible_instances_are_not_targets_or_query_results(state):
    ctx = context()
    item, entry = fragment(ctx, "material_link", "delete")
    entry.update(state="deleted" if state == "deleted" else "staged", session_id="99999999-9999-4999-8999-999999999999")
    with pytest.raises(prepare.PrepareInputError, match="TARGET_NOT_FOUND"):
        prepare.assemble(ctx, [[item]])
    result, status = ElementIndex(ctx).query([f'material_link:{entry["target_id"]}'])
    assert status == 1 and result["errors"][0]["code"] == "TARGET_NOT_FOUND"


def test_exact_instance_reads_use_baseline_and_include_instance_references():
    ctx = context()
    entries = ctx["instance_baseline"]["items"]
    result, status = ElementIndex(ctx).query([f'{e["target_kind"]}:{e["target_id"]}' for e in entries])
    assert status == 0
    for actual, entry in zip(result["elements"], entries, strict=True):
        assert actual["definition"] == entry["element"]
        assert actual["hash"] == entry["hash"]
    link = next(e for e in entries if e["target_kind"] == "material_link")
    for endpoint in (link["element"]["source_id"], link["element"]["target_id"]):
        assert any(r["id"] == link["target_id"] for e in result["elements"] if e["definition"]["id"] == endpoint for r in e["referenced_by"])


def test_baselines_and_fixture_hashes_follow_authoritative_instance_schema():
    source = BASE.parents[1] / "apps/api/src/ontofoundry_api/contracts/ontofoundry.instances.v1.schema.json"
    schema = json.loads(source.read_bytes())
    validator = Draft202012Validator({"$ref": "#/$defs/InstanceBaseline", "$defs": schema["$defs"]})
    for path in (BASE / "tests/fixtures").rglob("*.json"):
        ctx = json.loads(path.read_bytes())
        if not isinstance(ctx, dict) or "draft" not in ctx:
            continue
        assert not {"material_objects", "material_links"} & ctx["draft"].keys(), path
        validator.validate(ctx["instance_baseline"])
        for entry in ctx["instance_baseline"]["items"]:
            assert entry["target_id"] not in ctx["element_hashes"]
            assert entry["hash"] == instance_hash(entry["element"], entry["revision"])


@pytest.mark.parametrize("baseline_value,wrong_value", [(0, False), (1, True)])
def test_before_does_not_conflate_boolean_and_number(baseline_value, wrong_value):
    ctx = context()
    item, entry = fragment(ctx, "material_object", "update")
    entry["element"]["values"]["staff_name"] = baseline_value
    entry["hash"] = instance_hash(entry["element"], entry["revision"])
    batch = prepare.assemble(ctx, [[item]])
    batch["items"][0]["before"]["values"]["staff_name"] = wrong_value
    with pytest.raises(prepare.PrepareInputError, match="BEFORE_MISMATCH"):
        prepare.assemble(ctx, [batch["items"]])
    assert any("BEFORE_MISMATCH" in e for e in checker.check_result(batch, SCHEMA, ctx))
    with pytest.raises(ProposalContractError) as caught:
        server_parse(batch, ctx)
    assert caught.value.code == "BEFORE_MISMATCH"
