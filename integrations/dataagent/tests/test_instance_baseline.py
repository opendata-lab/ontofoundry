"""Instance edits name a target; the platform supplies the pinned before and hash (SC-08)."""

import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from ontofoundry_api.contracts.proposals import ProposalContractError
from ontofoundry_api.domain.instances import instance_hash
from runpaths import without_material_hashes
from show_element import ElementIndex
from test_stepwise_workflow import check_part
from test_workflow import BASE, SCHEMA, SKILL, checker, pinned, prepare, server_parse


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
def test_platform_supplies_the_baseline_before_and_revision_hash(kind, operation, state):
    ctx = context()
    item, entry = fragment(ctx, kind, operation)
    entry.update(state=state, session_id=ctx["run"]["session_id"] if state == "staged" else None)
    original = deepcopy(ctx)
    batch = prepare.assemble(ctx, [[item]])
    edit = batch["items"][0]
    assert set(batch) == {"items"} and "before" not in edit and "expected_target_hash" not in edit
    assert "id" not in (edit["after"] or {})
    assert not checker.check_result(batch, SCHEMA)
    assert not check_part.check_fragment([item], ctx, SCHEMA)["errors"]
    parsed = server_parse(batch, ctx).items[0]
    assert parsed.before == entry["element"]
    assert parsed.expected_target_hash == entry["hash"] == instance_hash(entry["element"], entry["revision"])
    assert parsed.expected_instance_revision == entry["revision"]
    assert ctx == original


@pytest.mark.parametrize("kind", sorted(checker.INSTANCE_KINDS))
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_a_missing_instance_target_is_reported_by_the_platform(kind, operation):
    ctx = context()
    item, entry = fragment(ctx, kind, operation)
    ctx["instance_baseline"]["items"].remove(entry)
    # Stale legacy collections cannot supply instances.
    ctx["draft"][kind + "s"] = [entry["element"]]
    batch = prepare.assemble(ctx, [[item]])
    with pytest.raises(ProposalContractError) as caught:
        server_parse(batch, ctx)
    assert caught.value.code == "TARGET_NOT_FOUND"


@pytest.mark.parametrize("state", ["deleted", "other_session"])
def test_invisible_instances_are_not_targets_or_query_results(state):
    ctx = context()
    item, entry = fragment(ctx, "material_link", "delete")
    entry.update(state="deleted" if state == "deleted" else "staged", session_id="99999999-9999-4999-8999-999999999999")
    result, status = ElementIndex(ctx).query([f'material_link:{entry["target_id"]}'])
    assert status == 1 and result["errors"][0]["code"] == "TARGET_NOT_FOUND"


def test_exact_instance_reads_use_baseline_and_include_instance_references():
    ctx = context()
    entries = ctx["instance_baseline"]["items"]
    result, status = ElementIndex(ctx).query([f'{e["target_kind"]}:{e["target_id"]}' for e in entries])
    assert status == 0
    for actual, entry in zip(result["elements"], entries, strict=True):
        assert actual["definition"] == without_material_hashes(entry["element"])
        assert "hash" not in actual  # nothing for the agent to copy (SC-08)
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
            assert entry["hash"] == instance_hash(entry["element"], entry["revision"])
