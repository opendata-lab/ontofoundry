"""T1 gate: the `ontofoundry.proposals/v1` contract, its schema and test vectors."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from test_t1_v2_model import action_draft

from ontofoundry_api.contracts.proposals import (
    SCHEMA_VERSION,
    ProposalContractError,
    RunContext,
    batch_id_for,
    create_target_id,
    item_fingerprint,
    parse_result,
    result_schema,
)
from ontofoundry_api.domain.canonical import element_sha256, snapshot_sha256
from ontofoundry_api.domain.models import OntologyDraft

SCHEMA_FILE = (
    Path(__file__).parents[1]
    / "src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json"
)
MATERIAL_ID = "11111111-1111-4111-8111-111111111111"
MATERIAL_SHA = "a" * 64
MATERIAL_LINES = ["# 供应商管理", "供应商甲是物料乙的主要供应商。", "供应商须有统一编码。"]
SESSION_ID = "22222222-2222-4222-8222-222222222222"


def pinned_draft() -> dict:
    """Demo + action + rules + an instance, a link instance and a mapping."""
    payload = action_draft().model_dump(mode="json")
    supplier = payload["object_types"][0]
    link = next(
        item for item in payload["link_types"] if item["source_type_id"] == supplier["id"]
    )
    target_type = link["target_type_id"]

    def instance(type_id: str, name: str) -> dict:
        required = {
            p["technical_name"]: name
            for p in payload["properties"]
            if p["owner_type_id"] == type_id and (p["required"] or p["identifier"])
        }
        return {"id": str(uuid4()), "type_id": type_id, "name": name, "values": required, "evidence": []}

    first, second = instance(supplier["id"], "甲"), instance(target_type, "乙")
    payload["material_objects"] = [first, second]
    payload["material_links"] = [
        {
            "id": str(uuid4()),
            "type_id": link["id"],
            "source_id": first["id"],
            "target_id": second["id"],
            "evidence": [],
        }
    ]
    payload["mappings"] = [
        {
            "id": str(uuid4()),
            "type_id": supplier["id"],
            "connection_alias": "erp",
            "table_name": "suppliers",
            "key_column": "code",
            "fields": {},
        }
    ]
    return OntologyDraft.model_validate(payload).model_dump(mode="json")


def context(draft: dict, **overrides) -> RunContext:
    values = {
        "workspace_id": draft["workspace_id"],
        "session_id": SESSION_ID,
        "run_token": "run-1",
        "base_version_id": None,
        "base_version_sha256": snapshot_sha256(draft),
        "source_session_revision": 4,
        "source_draft_sha256": snapshot_sha256(draft),
        "draft": draft,
    }
    values.update(overrides)
    return RunContext(**values)


def result(ctx: RunContext, items: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_token": ctx.run_token,
        "workspace_id": ctx.workspace_id,
        "session_id": ctx.session_id,
        "base_version_id": ctx.base_version_id,
        "base_version_sha256": ctx.base_version_sha256,
        "source_session_revision": ctx.source_session_revision,
        "source_draft_sha256": ctx.source_draft_sha256,
        "items": items,
    }


def lookup(material_id: str):
    return (MATERIAL_SHA, MATERIAL_LINES) if material_id == MATERIAL_ID else None


EVIDENCE = {
    "kind": "material",
    "material_id": MATERIAL_ID,
    "material_sha256": MATERIAL_SHA,
    "locator": {"heading": "供应商管理", "line_start": 2, "line_end": 2},
    "quote": "供应商甲是物料乙的主要供应商",
}


def create(ref, kind, after, **extra):
    return {
        "client_ref": ref,
        "operation": "create",
        "target_kind": kind,
        "target_id": None,
        "expected_target_hash": None,
        "before": None,
        "after": after,
        **extra,
    }


def update(kind, element, **changes):
    after = {k: v for k, v in deepcopy(element).items() if k != "id"}
    after.update(changes)
    return {
        "operation": "update",
        "target_kind": kind,
        "target_id": element["id"],
        "expected_target_hash": element_sha256(element),
        "before": element,
        "after": after,
    }


def delete(kind, element):
    return {
        "operation": "delete",
        "target_kind": kind,
        "target_id": element["id"],
        "expected_target_hash": element_sha256(element),
        "before": element,
        "after": None,
    }


def create_items(draft: dict) -> list[dict]:
    supplier = draft["object_types"][0]
    other = draft["object_types"][1]
    link = draft["material_links"][0]
    return [
        create("new-type", "object_type", {"name": "采购订单", "technical_name": "purchase_order"}),
        create(
            "new-prop",
            "property",
            {
                "owner_type_id": {"client_ref": "new-type"},
                "name": "订单号",
                "technical_name": "order_no",
                "identifier": True,
                "evidence": [EVIDENCE],
            },
        ),
        create(
            "new-link",
            "link_type",
            {
                "name": "供应方",
                "technical_name": "supplied_by",
                "source_type_id": {"client_ref": "new-type"},
                "target_type_id": supplier["id"],
            },
        ),
        create(
            "new-rule",
            "rule",
            {
                "name": "订单号必填",
                "technical_name": "order_no_required",
                "owner_kind": "property",
                "owner_id": {"client_ref": "new-prop"},
                "rule_kind": "constraint",
                "expression": "purchase_order.order_no IS NOT NULL",
            },
        ),
        create(
            "new-action",
            "action",
            {
                "name": "关闭订单",
                "technical_name": "close_order",
                "input_type_id": {"client_ref": "new-type"},
                "parameters": [{"name": "原因", "technical_name": "why"}],
                "precondition_rule_ids": [{"client_ref": "new-rule"}],
                "effects": [
                    {"kind": "set_property", "property_id": {"client_ref": "new-prop"}, "expression": ":why"}
                ],
            },
        ),
        create(
            "new-object",
            "material_object",
            {"type_id": supplier["id"], "name": "供应商丙", "evidence": [EVIDENCE]},
        ),
        create(
            "new-instance-link",
            "material_link",
            {
                "type_id": link["type_id"],
                "source_id": {"client_ref": "new-object"},
                "target_id": link["target_id"],
            },
        ),
        create(
            "new-mapping",
            "mapping",
            {
                "type_id": other["id"],
                "connection_alias": "erp",
                "table_name": "materials",
                "key_column": "code",
            },
        ),
    ]


def update_and_delete_items(draft: dict) -> list[dict]:
    rule, action = draft["rules"][0], draft["actions"][0]
    return [
        update("object_type", draft["object_types"][2], description="更新后的定义"),
        update("property", draft["properties"][0], description="编码说明"),
        update("link_type", draft["link_types"][0], description="关系说明"),
        update("rule", rule, expression=rule["expression"] + " AND 1 = 1"),
        update("action", action, description="更新后的 Action"),
        update("material_object", draft["material_objects"][0], name="甲（更名）"),
        update("mapping", draft["mappings"][0], table_name="supplier_v2"),
        delete("material_link", draft["material_links"][0]),
    ]


# --- schema -------------------------------------------------------------------


def test_checked_in_schema_matches_the_models():
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == result_schema(), (
        "run: uv run python -m ontofoundry_api.contracts.export_schema"
    )


# --- positives ------------------------------------------------------------------


def test_create_for_every_kind_resolves_references_and_assigns_ids():
    draft = pinned_draft()
    ctx = context(draft)
    batch = parse_result(result(ctx, create_items(draft)), ctx, material_lookup=lookup)

    assert batch.id == batch_id_for(SESSION_ID, "run-1")
    by_ref = {item.client_ref: item for item in batch.items}
    new_type = create_target_id(batch.id, "new-type")
    assert by_ref["new-type"].target_id == new_type
    assert by_ref["new-prop"].after["owner_type_id"] == new_type
    assert by_ref["new-link"].after["source_type_id"] == new_type
    assert by_ref["new-rule"].after["owner_id"] == by_ref["new-prop"].target_id
    action = by_ref["new-action"].after
    assert action["effects"][0]["property_id"] == by_ref["new-prop"].target_id
    assert action["parameters"][0]["id"] and action["effects"][0]["id"]
    # References become dependencies: the property needs its type, and so on.
    assert by_ref["new-prop"].depends_on == [by_ref["new-type"].id]
    assert set(by_ref["new-action"].depends_on) == {
        by_ref["new-type"].id,
        by_ref["new-prop"].id,
        by_ref["new-rule"].id,
    }
    assert by_ref["new-object"].after["evidence"][0]["id"]
    assert {item.target_kind for item in batch.items} == {
        "object_type", "property", "link_type", "rule", "action",
        "material_object", "material_link", "mapping",
    }


def test_update_and_delete_for_every_kind():
    draft = pinned_draft()
    ctx = context(draft)
    batch = parse_result(result(ctx, update_and_delete_items(draft)), ctx, material_lookup=lookup)
    operations = {(item.operation, item.target_kind) for item in batch.items}
    assert ("delete", "material_link") in operations
    assert len([op for op, _ in operations if op == "update"]) == 7
    for item in batch.items:
        if item.after:
            assert item.after["id"] == item.target_id


def test_deletes_of_every_kind_parse():
    draft = pinned_draft()
    ctx = context(draft)
    items = [
        delete(kind, draft[collection][-1])
        for kind, collection in (
            ("object_type", "object_types"), ("property", "properties"),
            ("link_type", "link_types"), ("rule", "rules"), ("action", "actions"),
            ("material_object", "material_objects"), ("material_link", "material_links"),
            ("mapping", "mappings"),
        )
    ]
    assert len(parse_result(result(ctx, items), ctx).items) == 8


def test_parsing_is_deterministic():
    draft = pinned_draft()
    ctx = context(draft)
    payload = result(ctx, create_items(draft))
    first = parse_result(json.dumps(payload).encode(), ctx, material_lookup=lookup)
    again = parse_result(json.dumps(payload).encode(), ctx, material_lookup=lookup)
    assert [(i.id, i.target_id, i.fingerprint) for i in first.items] == [
        (i.id, i.target_id, i.fingerprint) for i in again.items
    ]
    assert first.result_sha256 == again.result_sha256


def test_manual_evidence_may_only_be_echoed_unchanged():
    draft = pinned_draft()
    manual = {
        "kind": "manual",
        "id": str(uuid4()),
        "note": "业务专家确认",
        "created_by": "user-1",
        "created_at": datetime(2026, 9, 29, tzinfo=UTC).isoformat(),
    }
    draft["object_types"][2]["evidence"] = [manual]
    ctx = context(draft)
    echoed = update("object_type", draft["object_types"][2], description="保留人工证据")
    assert parse_result(result(ctx, [echoed]), ctx).items[0].after["evidence"][0]["id"] == manual["id"]

    altered = deepcopy(echoed)
    altered["after"]["evidence"][0]["note"] = "被智能体改写"
    with pytest.raises(ProposalContractError) as err:
        parse_result(result(ctx, [altered]), ctx)
    assert err.value.code == "MANUAL_EVIDENCE_FORBIDDEN"

    dropped = deepcopy(echoed)
    dropped["after"]["evidence"] = []
    with pytest.raises(ProposalContractError, match="人工证据"):
        parse_result(result(ctx, [dropped]), ctx)

    authored = create(
        "t", "object_type", {"name": "新对象", "technical_name": "fresh", "evidence": [manual]}
    )
    with pytest.raises(ProposalContractError, match="人工证据"):
        parse_result(result(ctx, [authored]), ctx)


# --- negatives ------------------------------------------------------------------


def rejected(draft, items, code, ctx=None, **kwargs):
    ctx = ctx or context(draft)
    with pytest.raises(ProposalContractError) as err:
        parse_result(result(ctx, items), ctx, **kwargs)
    assert err.value.code == code, str(err.value)


def test_context_must_match_the_pinned_run():
    draft = pinned_draft()
    ctx = context(draft)
    payload = result(ctx, [])
    payload["source_session_revision"] = 5
    with pytest.raises(ProposalContractError) as err:
        parse_result(payload, ctx)
    assert err.value.code == "RESULT_CONTEXT_MISMATCH"


def test_schema_violations_are_rejected():
    draft = pinned_draft()
    item = create("a", "object_type", {"name": "对象", "technical_name": "a", "surprise": 1})
    rejected(draft, [item], "RESULT_SCHEMA_INVALID")
    bad_kind = create("a", "workspace_rule", {"name": "x"})
    rejected(draft, [bad_kind], "RESULT_SCHEMA_INVALID")
    manual_on_item = create("a", "object_type", {"name": "对象", "technical_name": "a"})
    manual_on_item["evidence"] = [{"kind": "manual", "note": "x", "created_by": "u", "created_at": "2026-01-01T00:00:00Z"}]
    rejected(draft, [manual_on_item], "RESULT_SCHEMA_INVALID")


def test_operation_shapes_are_enforced():
    draft = pinned_draft()
    with_id = create("a", "object_type", {"name": "对象", "technical_name": "a"})
    with_id["target_id"] = str(uuid4())
    rejected(draft, [with_id], "OPERATION_SHAPE")
    no_ref = create("a", "object_type", {"name": "对象", "technical_name": "a"})
    del no_ref["client_ref"]
    rejected(draft, [no_ref], "CREATE_WITHOUT_CLIENT_REF")
    ghost = delete("object_type", {**draft["object_types"][0], "id": str(uuid4())})
    rejected(draft, [ghost], "TARGET_NOT_FOUND")
    wrong_kind = update("property", draft["object_types"][0])
    rejected(draft, [wrong_kind], "RESULT_SCHEMA_INVALID")


def test_stale_before_or_hash_is_rejected():
    draft = pinned_draft()
    stale_before = update("object_type", draft["object_types"][0], description="x")
    stale_before["before"] = {**stale_before["before"], "description": "旧的"}
    rejected(draft, [stale_before], "BEFORE_MISMATCH")
    stale_hash = update("object_type", draft["object_types"][0], description="x")
    stale_hash["expected_target_hash"] = "0" * 64
    rejected(draft, [stale_hash], "TARGET_HASH_MISMATCH")


def test_references_and_dependencies_are_checked():
    draft = pinned_draft()
    unknown = create(
        "p", "property", {"owner_type_id": {"client_ref": "nope"}, "name": "x", "technical_name": "x"}
    )
    rejected(draft, [unknown], "CLIENT_REF_UNKNOWN")
    dangling = create("p", "property", {"owner_type_id": str(uuid4()), "name": "x", "technical_name": "x"})
    rejected(draft, [dangling], "REFERENCE_UNKNOWN")
    a = create("a", "object_type", {"name": "甲类", "technical_name": "a"}, depends_on=["b"])
    b = create("b", "object_type", {"name": "乙类", "technical_name": "b"}, depends_on=["a"])
    rejected(draft, [a, b], "DEPENDENCY_CYCLE")
    rejected(draft, [create("a", "object_type", {"name": "x", "technical_name": "a"}, depends_on=["z"])], "DEPENDENCY_UNKNOWN")


def test_duplicates_are_rejected():
    draft = pinned_draft()
    one = create("a", "object_type", {"name": "对象", "technical_name": "a"})
    two = create("a", "object_type", {"name": "对象二", "technical_name": "b"})
    rejected(draft, [one, two], "CLIENT_REF_DUPLICATE")
    first = update("object_type", draft["object_types"][0], description="一")
    second = update("object_type", draft["object_types"][0], description="二")
    rejected(draft, [first, second], "TARGET_DUPLICATE")


def test_elements_are_validated_per_kind():
    draft = pinned_draft()
    bad_action = create(
        "act",
        "action",
        {
            "name": "动作",
            "technical_name": "act",
            "input_type_id": draft["object_types"][0]["id"],
            "effects": [
                {"kind": "set_property", "property_id": draft["properties"][0]["id"], "expression": ":undeclared"}
            ],
        },
    )
    rejected(draft, [bad_action], "ELEMENT_INVALID")
    bad_name = create("a", "object_type", {"name": "对象", "technical_name": "9bad"})
    rejected(draft, [bad_name], "ELEMENT_INVALID")


def test_evidence_must_match_saved_material():
    draft = pinned_draft()
    wrong_quote = create(
        "o", "material_object",
        {"type_id": draft["object_types"][0]["id"], "name": "丙", "evidence": [{**EVIDENCE, "quote": "编造的原文"}]},
    )
    rejected(draft, [wrong_quote], "EVIDENCE_INVALID", material_lookup=lookup)
    wrong_sha = deepcopy(wrong_quote)
    wrong_sha["after"]["evidence"] = [{**EVIDENCE, "material_sha256": "b" * 64}]
    rejected(draft, [wrong_sha], "EVIDENCE_INVALID", material_lookup=lookup)
    foreign = deepcopy(wrong_quote)
    foreign["after"]["evidence"] = [{**EVIDENCE, "material_id": str(uuid4())}]
    rejected(draft, [foreign], "EVIDENCE_INVALID", material_lookup=lookup)
    out_of_range = deepcopy(wrong_quote)
    out_of_range["after"]["evidence"] = [{**EVIDENCE, "locator": {"line_start": 9, "line_end": 9}}]
    rejected(draft, [out_of_range], "EVIDENCE_INVALID", material_lookup=lookup)


# --- fixed test vectors -------------------------------------------------------


def test_fingerprint_and_domain_hash_vectors_never_change():
    # These literals are the contract: changing canonicalization breaks them.
    after = {
        "id": "33333333-3333-4333-8333-333333333333",
        "name": "供应商",
        "technical_name": "supplier",
        "description": "",
        "tags": ["采购", "主数据", "采购"],
        "extends": [],
        "evidence": [],
    }
    assert item_fingerprint(
        "create", "object_type", "33333333-3333-4333-8333-333333333333", after
    ) == "269e2007a5551abe0b4327b4e24d2f8c8341af69f38e4da157cb89b266f9b0ba"
    assert item_fingerprint("delete", "rule", "33333333-3333-4333-8333-333333333333", None) == (
        "9ad70a6a65ea52494e647e9131c993b1b2bfeac6374a25042aaa4e2df96010b5"
    )
    snapshot = OntologyDraft(workspace_id="44444444-4444-4444-8444-444444444444").model_dump(mode="json")
    assert snapshot_sha256(snapshot) == "84ff0cdfd63bf311fb8a75b043702c54ec156e1da0f94f57643dfe7337c0eb73"
    # Order of set-like fields and of id-keyed collections does not matter.
    reordered = {**after, "tags": ["主数据", "采购"]}
    assert element_sha256(after) == element_sha256(reordered)
