"""Whole-batch core proposal parsing, evidence, stable IDs and pinned context."""

import json
from uuid import uuid4

import pytest

from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    RunContext,
    parse_result,
    result_schema,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services.demo import build_demo_draft


def context(draft=None):
    draft = draft or build_demo_draft().model_dump(mode="json")
    return RunContext(
        draft["workspace_id"],
        str(uuid4()),
        "round",
        None,
        snapshot_sha256(draft),
        1,
        snapshot_sha256(draft),
        draft,
    )


def result(ctx, items):
    return {
        "schema_version": "ontofoundry.proposals/v1",
        **{
            k: getattr(ctx, k)
            for k in (
                "workspace_id",
                "session_id",
                "run_token",
                "base_version_id",
                "base_version_sha256",
                "source_session_revision",
                "source_draft_sha256",
            )
        },
        "items": items,
    }


def create(ref, kind, after):
    return {
        "operation": "create",
        "target_kind": kind,
        "client_ref": ref,
        "before": None,
        "after": after,
    }


def parse(payload, ctx, lookup=lambda _: None):
    return parse_result(json.dumps(payload).encode(), ctx, lookup)


def test_schema_has_exact_ten_targets():
    assert set(result_schema()["$defs"]["item"]["properties"]["target_kind"]["enum"]) == {
        "object_type",
        "property",
        "link_type",
        "rule",
        "metric",
        "dataset",
        "mapping",
        "material_object",
        "material_link",
        "value_type",
    }


def test_nested_column_and_ratio_client_refs():
    ctx = context(empty_snapshot(uuid4()))
    items = [
        create(
            "ds",
            "dataset",
            {
                "name": "daily",
                "table_name": "fictional_daily",
                "columns": [{"name": "n", "physical_type": "integer"}],
            },
        ),
        create(
            "n",
            "metric",
            {
                "kind": "simple",
                "display_name": "数量",
                "name": "quantity",
                "dataset_id": {"client_ref": "ds"},
                "aggregation": "sum",
                "measure": {"dataset_id": {"client_ref": "ds"}, "column": "n"},
            },
        ),
        create(
            "r",
            "metric",
            {
                "kind": "ratio",
                "display_name": "占比",
                "name": "share",
                "numerator_id": {"client_ref": "n"},
                "denominator_id": {"client_ref": "n"},
            },
        ),
    ]
    payload = result(ctx, items)
    parsed = parse(payload, ctx)
    assert parsed == parse(payload, ctx)
    assert parsed.items[1].after["dataset_id"] == parsed.items[0].target_id
    assert parsed.items[2].after["numerator_id"] == parsed.items[1].target_id


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown", "old_kind", "context", "invalid_graph"]
)
def test_whole_result_rejected(mutation):
    ctx = context()
    payload = result(
        ctx, [create("new", "object_type", {"display_name": "新增", "name": "fresh"})]
    )
    if mutation == "duplicate":
        payload["items"] *= 2
    if mutation == "unknown":
        payload["items"][0]["after"]["extends"] = {"client_ref": "missing"}
    if mutation == "old_kind":
        payload["items"][0]["target_kind"] = "action"
    if mutation == "context":
        payload["run_token"] = "other"
    if mutation == "invalid_graph":
        payload["items"][0]["after"]["name"] = "customer"
    with pytest.raises(ProposalContractError):
        parse(payload, ctx)


def test_material_quote_checked_and_manual_cannot_be_authored():
    ctx = context()
    eid = str(uuid4())
    evidence = {
        "kind": "material",
        "id": eid,
        "material_id": "fictional-material",
        "material_sha256": "a" * 64,
        "locator": {"line_start": 1, "line_end": 1},
        "quote": "客户",
    }
    item = create(
        "new",
        "object_type",
        {"display_name": "新增", "name": "fresh", "evidence": [evidence]},
    )
    assert parse(result(ctx, [item]), ctx, lambda _: ("a" * 64, ["客户订单"])).items
    evidence["quote"] = "不存在"
    with pytest.raises(ProposalContractError):
        parse(result(ctx, [item]), ctx, lambda _: ("a" * 64, ["客户订单"]))




def mapping_name_collision_items():
    names = [
        "source_id",
        "target_id",
        "type_id",
        "property_id",
        "dataset_id",
        "source_property_ids",
        "inherited_link_bindings",
        "values",
        "evidence",
        "kind",
    ]
    return [
        create(
            "collision-type",
            "object_type",
            {"display_name": "星港客户", "name": "starport_customer"},
        ),
        *[
            create(
                "prop-" + name,
                "property",
                {
                    "owner_type_id": {"client_ref": "collision-type"},
                    "display_name": "属性" + name,
                    "name": name,
                    "value_kind": "string",
                },
            )
            for name in names
        ],
        create(
            "collision-dataset",
            "dataset",
            {
                "name": "fictional_collision",
                "table_name": "fictional_collision",
                "columns": [{"name": name, "physical_type": "text"} for name in names],
            },
        ),
        create(
            "collision-mapping",
            "mapping",
            {
                "type_id": {"client_ref": "collision-type"},
                "binding_mode": "independent",
                "sources": [
                    {
                        "id": "main",
                        "dataset_id": {"client_ref": "collision-dataset"},
                        "key_columns": ["source_id"],
                    }
                ],
                "fields": {
                    name: {"kind": "column", "source_id": "main", "column": name}
                    for name in names
                },
            },
        ),
    ]


def test_mapping_names_are_not_reference_paths():
    from ontofoundry_api.contracts.proposals import apply_items
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.validation import validate_core_graph

    ctx = context(empty_snapshot(uuid4()))
    items = mapping_name_collision_items()
    parsed = parse(result(ctx, items), ctx)
    assert parsed.items[-1].after["fields"] == items[-1]["after"]["fields"]
    candidate = validate_core_graph(
        CoreDraft.model_validate(apply_items(ctx.draft, parsed.items))
    )
    assert candidate.mappings[0].sources[0].dataset_id == candidate.datasets[0].id


@pytest.mark.parametrize(
    "name,reading",
    [
        ("汇报给", "{source}汇报给{target}"),
        ("reports_to", "员工汇报给主管"),
        ("reports_to", "{source}汇报给{other}{target}"),
        ("reports_to", "{{source}}汇报给{target}"),
        ("reports_to", "{source}汇报给{target}{"),
    ],
)
def test_schema_rejects_invalid_relationship_names_and_readings(name, reading):
    from jsonschema import Draft202012Validator

    ctx = context()
    identity = ctx.draft["object_types"][0]["id"]
    payload = result(
        ctx,
        [
            create(
                "reports",
                "link_type",
                {
                    "name": name,
                    "source_type_id": identity,
                    "target_type_id": identity,
                    "multiplicity": "many_to_one",
                    "verbalizes": [reading],
                },
            )
        ],
    )
    assert list(Draft202012Validator(result_schema()).iter_errors(payload))
    with pytest.raises(ProposalContractError) as error:
        parse(payload, ctx)
    assert error.value.code == "RESULT_SCHEMA_INVALID"


def test_committed_proposal_schema_matches_runtime():
    from pathlib import Path

    import ontofoundry_api.contracts.proposals as contract

    schema = json.loads(
        Path(contract.__file__)
        .with_name("ontofoundry.proposals.v1.schema.json")
        .read_text()
    )
    assert schema == result_schema()


def test_skill_fact_example_is_valid_as_a_complete_graph():
    import hashlib
    from pathlib import Path

    integration = Path(__file__).parents[3] / "integrations/dataagent"
    items = json.loads(
        (integration / "shared/references/examples/create-material_link.json").read_bytes()
    )
    material = (integration / "tests/fixtures/material.md").read_bytes()
    ctx = context(empty_snapshot(uuid4()))
    parsed = parse(
        result(ctx, items),
        ctx,
        lambda _: (hashlib.sha256(material).hexdigest(), material.decode().splitlines()),
    )
    assert parsed.items[-1].after["source_id"] == parsed.items[-3].target_id


def test_import_id_rewrite_preserves_reference_named_mapping_fields():
    from ontofoundry_api.contracts.proposals import apply_items
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.services.import_matching import rewrite_import_ids

    ctx = context(empty_snapshot(uuid4()))
    parsed = parse(result(ctx, mapping_name_collision_items()), ctx)
    draft = CoreDraft.model_validate(apply_items(ctx.draft, parsed.items))
    ids = {item.target_id: str(uuid4()) for item in parsed.items}
    rewritten = rewrite_import_ids(draft, ids)
    assert rewritten.mappings[0].fields == draft.mappings[0].fields
    assert str(rewritten.mappings[0].type_id) == ids[str(draft.mappings[0].type_id)]
    assert (
        str(rewritten.mappings[0].sources[0].dataset_id) == ids[str(draft.datasets[0].id)]
    )
