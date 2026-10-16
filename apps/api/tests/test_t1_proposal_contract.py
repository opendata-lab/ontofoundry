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


def test_schema_has_exact_nine_targets():
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
                "name": "数量",
                "technical_name": "quantity",
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
                "name": "占比",
                "technical_name": "share",
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
        ctx, [create("new", "object_type", {"name": "新增", "technical_name": "fresh"})]
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
        payload["items"][0]["after"]["technical_name"] = "customer"
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
        {"name": "新增", "technical_name": "fresh", "evidence": [evidence]},
    )
    assert parse(result(ctx, [item]), ctx, lambda _: ("a" * 64, ["客户订单"])).items
    evidence["quote"] = "不存在"
    with pytest.raises(ProposalContractError):
        parse(result(ctx, [item]), ctx, lambda _: ("a" * 64, ["客户订单"]))
