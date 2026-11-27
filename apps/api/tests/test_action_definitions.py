"""Platform support for Action definitions: validation, proposals, reads, MCP, and adapters."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_modeling import ROOT, create_session, mcp_request, publish, save
from test_t4_proposal_decisions import create, seed_batch

from ontofoundry_api.adapters.base import ExportContext, ImportContext
from ontofoundry_api.adapters.native.importer import resolve_material_evidence
from ontofoundry_api.adapters.native.package import NativePackageAdapter
from ontofoundry_api.adapters.ossie.importer import OssieAdapter
from ontofoundry_api.contracts.proposals import ProposalContractError, RunContext, parse_result
from ontofoundry_api.domain.core import (
    Action,
    ActionParameter,
    AddLinkEffect,
    CoreDraft,
    CreateObjectEffect,
    LinkType,
    MaterialEvidence,
    ObjectType,
    Property,
    RemoveLinkEffect,
    SetPropertyEffect,
    ValueKind,
    ValueType,
)
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.domain.validation import GraphValidationError, validate_core_graph
from ontofoundry_api.services.element_save import calculate_element_save
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.public_projection import authorized_snapshot


def _mcp(client, name, args):
    response = mcp_request(client, "tools/call", {"name": name, "arguments": args})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result


def _work_order_proposal_fixture(evidence=None):
    """Fixed fictional work-order / team proposal fixture (design §3.1 examples)."""
    ev = [evidence] if evidence else []
    return [
        create(
            "vt_team_code",
            "value_type",
            {
                "name": "team_code",
                "display_name": "班组编码",
                "description": "运维班组唯一编码",
                "value_kind": "string",
            },
        ),
        create(
            "obj_work_order",
            "object_type",
            {
                "name": "work_order",
                "display_name": "工单",
                "description": "现场运维工单",
                "synonyms": ["运维工单"],
                "tags": ["运维"],
            },
        ),
        create(
            "obj_inspection_order",
            "object_type",
            {
                "name": "inspection_order",
                "display_name": "巡检工单",
                "description": "定期巡检工单",
                "extends": {"client_ref": "obj_work_order"},
            },
        ),
        create(
            "obj_team",
            "object_type",
            {
                "name": "maintenance_team",
                "display_name": "受理班组",
                "description": "负责处理工单的运维班组",
            },
        ),
        create(
            "prop_wo_status",
            "property",
            {
                "owner_type_id": {"client_ref": "obj_work_order"},
                "name": "status",
                "display_name": "状态",
                "value_kind": "string",
                "required": True,
            },
        ),
        create(
            "prop_team_pending",
            "property",
            {
                "owner_type_id": {"client_ref": "obj_team"},
                "name": "pending_count",
                "display_name": "待办数",
                "value_kind": "integer",
            },
        ),
        create(
            "link_wo_team",
            "link_type",
            {
                "name": "handled_by",
                "display_name": "受理班组关系",
                "source_type_id": {"client_ref": "obj_work_order"},
                "target_type_id": {"client_ref": "obj_team"},
                "multiplicity": "many_to_one",
                "verbalizes": ["{source}由{target}受理"],
            },
        ),
        # Instance action with cross-object effect (updates maintenance_team.pending_count)
        create(
            "act_dispatch",
            "action",
            {
                "name": "dispatch_work_order",
                "display_name": "派单",
                "description": "只有待派单的工单可以派单，派单时必须指定受理班组。派单后状态变为已派单。",
                "synonyms": ["分派工单"],
                "tags": ["工单流转"],
                "target_type_id": {"client_ref": "obj_work_order"},
                "parameters": [
                    {
                        "name": "team_code",
                        "display_name": "受理班组编码",
                        "description": "接收工单的班组编码",
                        "value_kind": "string",
                        "value_type_id": {"client_ref": "vt_team_code"},
                        "required": True,
                    }
                ],
                "effects": [
                    {
                        "kind": "set_property",
                        "property_id": {"client_ref": "prop_wo_status"},
                        "description": "待派单 → 已派单",
                    },
                    {
                        "kind": "add_link",
                        "link_type_id": {"client_ref": "link_wo_team"},
                        "description": "建立工单与受理班组的关系",
                    },
                    {
                        "kind": "set_property",
                        "property_id": {"client_ref": "prop_team_pending"},
                        "description": "受理班组待办数加 1",
                    },
                ],
                "evidence": ev,
            },
        ),
        # Global create action (target_type_id = None)
        create(
            "act_create_inspection",
            "action",
            {
                "name": "create_inspection_order",
                "display_name": "新建巡检工单",
                "description": "为指定站点创建待派单状态的巡检工单。",
                "synonyms": ["发起巡检"],
                "tags": ["工单流转"],
                "target_type_id": None,
                "parameters": [
                    {
                        "name": "site_code",
                        "display_name": "站点编码",
                        "description": "站点标识",
                        "value_kind": "string",
                        "required": True,
                    }
                ],
                "effects": [
                    {
                        "kind": "create_object",
                        "object_type_id": {"client_ref": "obj_inspection_order"},
                        "description": "新建一张巡检工单",
                    }
                ],
                "evidence": ev,
            },
        ),
    ]


def test_action_model_and_graph_validation_rules():
    ws_id = uuid4()
    obj_id, prop_id, link_id, vt_id = uuid4(), uuid4(), uuid4(), uuid4()
    base = CoreDraft(
        workspace_id=ws_id,
        value_types=[ValueType(id=vt_id, name="team_code", value_kind=ValueKind.STRING)],
        object_types=[ObjectType(id=obj_id, name="work_order", display_name="工单")],
        properties=[
            Property(
                id=prop_id,
                owner_type_id=obj_id,
                name="status",
                value_kind=ValueKind.STRING,
            )
        ],
        link_types=[
            LinkType(
                id=link_id,
                name="handled_by",
                source_type_id=obj_id,
                target_type_id=obj_id,
                multiplicity="many_to_one",
            )
        ],
    )

    # Duplicate parameter names (case-insensitive) rejected.
    with pytest.raises(ValidationError):
        Action(
            id=uuid4(),
            name="dup_param",
            parameters=[
                ActionParameter(name="teamCode", value_kind=ValueKind.STRING),
                ActionParameter(name="teamcode", value_kind=ValueKind.STRING),
            ],
        )

    # Description > 200 chars rejected on parameters and effects.
    with pytest.raises(ValidationError):
        ActionParameter(name="p", value_kind=ValueKind.STRING, description="长" * 201)
    with pytest.raises(ValidationError):
        SetPropertyEffect(kind="set_property", property_id=prop_id, description="长" * 201)

    # Duplicate (kind, ref) rejected; remove_link + add_link on same link_type allowed.
    with pytest.raises(ValidationError):
        Action(
            id=uuid4(),
            name="dup_effect",
            effects=[
                SetPropertyEffect(kind="set_property", property_id=prop_id, description="a"),
                SetPropertyEffect(kind="set_property", property_id=prop_id, description="b"),
            ],
        )
    reassign = Action(
        id=uuid4(),
        name="reassign_team",
        display_name="转派班组",
        target_type_id=obj_id,
        effects=[
            RemoveLinkEffect(kind="remove_link", link_type_id=link_id, description="解除原班组"),
            AddLinkEffect(kind="add_link", link_type_id=link_id, description="绑定新班组"),
        ],
    )
    valid = base.model_copy(deep=True)
    valid.actions = [reassign]
    validate_core_graph(valid)

    # Workspace-unique action names (casefold).
    dup_name = valid.model_copy(deep=True)
    dup_name.actions.append(Action(id=uuid4(), name="Reassign_Team"))
    with pytest.raises(GraphValidationError):
        validate_core_graph(dup_name)

    # Wrong element kind in effect (e.g., object_type UUID passed as property_id) rejected.
    wrong_kind = base.model_copy(deep=True)
    wrong_kind.actions = [
        Action(
            id=uuid4(),
            name="bad_ref",
            effects=[SetPropertyEffect(kind="set_property", property_id=obj_id)],
        )
    ]
    with pytest.raises(GraphValidationError):
        validate_core_graph(wrong_kind)

    # Value type kind mismatch rejected.
    bad_vt = base.model_copy(deep=True)
    bad_vt.actions = [
        Action(
            id=uuid4(),
            name="bad_vt",
            parameters=[
                ActionParameter(
                    name="code",
                    value_kind=ValueKind.INTEGER,
                    value_type_id=vt_id,
                )
            ],
        )
    ]
    with pytest.raises(GraphValidationError):
        validate_core_graph(bad_vt)


def test_proposal_rejects_wrong_kind_client_ref_and_supports_name_swap():
    ws_id = uuid4()
    draft = empty_snapshot(ws_id)
    ctx = RunContext(
        workspace_id=str(ws_id),
        session_id=str(uuid4()),
        run_token="tok-1",
        base_version_id=None,
        base_version_sha256="0" * 64,
        source_session_revision=1,
        source_draft_sha256="0" * 64,
        draft=draft,
    )
    # Same-batch client_ref pointing to a metric used as property_id must fail.
    bad_payload = {
        "items": [
            create(
                "ds1",
                "dataset",
                {"name": "wo_ds", "table_name": "fictional_wo", "columns": [{"name": "n", "physical_type": "integer"}]},
            ),
            create(
                "m1",
                "metric",
                {"kind": "simple", "name": "wo_cnt", "dataset_id": {"client_ref": "ds1"}, "aggregation": "count"},
            ),
            create(
                "a1",
                "action",
                {
                    "name": "bad_action",
                    "effects": [{"kind": "set_property", "property_id": {"client_ref": "m1"}, "description": "错用指标"}],
                },
            ),
        ]
    }
    with pytest.raises(ProposalContractError):
        parse_result(json.dumps(bad_payload).encode(), ctx, lambda _: None)

    # Action name swap is grouped into one atomic group.
    a1_id, a2_id = str(uuid4()), str(uuid4())
    swap_draft = empty_snapshot(ws_id)
    swap_draft["actions"] = [
        Action(id=UUID(a1_id), name="alpha_act", display_name="动作甲").model_dump(mode="json"),
        Action(id=UUID(a2_id), name="beta_act", display_name="动作乙").model_dump(mode="json"),
    ]
    swap_ctx = RunContext(
        workspace_id=str(ws_id),
        session_id=str(uuid4()),
        run_token="tok-swap",
        base_version_id=None,
        base_version_sha256="0" * 64,
        source_session_revision=1,
        source_draft_sha256="0" * 64,
        draft=swap_draft,
    )
    swap_payload = {
        "items": [
            {
                "operation": "update",
                "target_kind": "action",
                "target_id": a1_id,
                "after": {**{k: v for k, v in swap_draft["actions"][0].items() if k != "id"}, "name": "beta_act"},
            },
            {
                "operation": "update",
                "target_kind": "action",
                "target_id": a2_id,
                "after": {**{k: v for k, v in swap_draft["actions"][1].items() if k != "id"}, "name": "alpha_act"},
            },
        ]
    }
    parsed = parse_result(json.dumps(swap_payload).encode(), swap_ctx, lambda _: None)
    assert parsed.items[0].atomic_group_id is not None
    assert parsed.items[0].atomic_group_id == parsed.items[1].atomic_group_id


def test_value_type_base_kind_sync_in_element_save_and_proposal_atomic_group(client):
    # 1. Seed a value_type + referencing action in a session.
    session = create_session(client)
    batch = seed_batch(client, session, _work_order_proposal_fixture())
    accept = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": "accept-all-actions-vt-1",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": i["id"], "decision": "accept"} for i in batch["items"]],
        },
    )
    assert accept.status_code == 200, accept.text
    session = accept.json()["session"]
    vt = next(v for v in session["draft"]["value_types"] if v["name"] == "team_code")
    act = next(a for a in session["draft"]["actions"] if a["name"] == "dispatch_work_order")

    # 2. element_save for value_type allows updating referencing action parameter value_kind,
    #    and rejects unrelated action edits (like changing effects or description).
    edited = deepcopy(session["draft"])
    next(v for v in edited["value_types"] if v["id"] == vt["id"])["value_kind"] = "integer"
    next(a for a in edited["actions"] if a["id"] == act["id"])["parameters"][0]["value_kind"] = "integer"
    calc = calculate_element_save(session["draft"], edited, "value_type", vt["id"])
    assert next(a for a in calc.session_draft["actions"] if a["id"] == act["id"])["parameters"][0]["value_kind"] == "integer"

    bad_edited = deepcopy(edited)
    next(a for a in bad_edited["actions"] if a["id"] == act["id"])["description"] = "偷改描述"
    with pytest.raises(ServiceError) as exc_info:
        calculate_element_save(session["draft"], bad_edited, "value_type", vt["id"])
    assert exc_info.value.code == "ELEMENT_SCOPE_INVALID"

    # 3. Proposal batch updating value_type.value_kind + action parameter groups into one atomic group
    #    and supports both atomic accept and atomic back_to_pending.
    vt_after = {k: v for k, v in vt.items() if k != "id"}
    vt_after["value_kind"] = "integer"
    act_after = deepcopy({k: v for k, v in act.items() if k != "id"})
    act_after["parameters"][0]["value_kind"] = "integer"
    update_batch = seed_batch(
        client,
        session,
        [
            {"operation": "update", "target_kind": "value_type", "target_id": vt["id"], "after": vt_after},
            {"operation": "update", "target_kind": "action", "target_id": act["id"], "after": act_after},
        ],
    )
    vt_item = next(i for i in update_batch["items"] if i["target_kind"] == "value_type")
    act_item = next(i for i in update_batch["items"] if i["target_kind"] == "action")
    assert vt_item["atomic_group_id"] is not None
    assert vt_item["atomic_group_id"] == act_item["atomic_group_id"]

    # Accepting only vt_item pulls in act_item atomically.
    dec = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": "vt-action-atomic-accept",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": vt_item["id"], "decision": "accept"}],
        },
    )
    assert dec.status_code == 200, dec.text
    assert {r["proposal_id"] for r in dec.json()["results"]} == {vt_item["id"], act_item["id"]}
    session = dec.json()["session"]

    # Undoing (back_to_pending) only vt_item pulls back act_item atomically.
    undo = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": "vt-action-atomic-undo",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": vt_item["id"], "decision": "back_to_pending"}],
        },
    )
    assert undo.status_code == 200, undo.text
    assert {r["proposal_id"] for r in undo.json()["results"]} == {vt_item["id"], act_item["id"]}
    restored = undo.json()["session"]["draft"]
    assert next(a for a in restored["actions"] if a["id"] == act["id"])["parameters"][0]["value_kind"] == "string"


def test_review_locks_parameters_effects_and_computes_server_side_action_diff(client):
    session = create_session(client)
    batch = seed_batch(client, session, _work_order_proposal_fixture())
    accept = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": "accept-for-review-diff",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": i["id"], "decision": "accept"} for i in batch["items"]],
        },
    )
    assert accept.status_code == 200, accept.text
    session = accept.json()["session"]
    act = next(a for a in session["draft"]["actions"] if a["name"] == "dispatch_work_order")
    wo = next(o for o in session["draft"]["object_types"] if o["name"] == "work_order")

    # Propose an update that adds a new effect + changes description, while the submitter
    # intentionally omits `effects` from `field_changes`.
    act_after = deepcopy({k: v for k, v in act.items() if k != "id"})
    act_after["description"] = "新派单说明"
    act_after["effects"].append(
        {"kind": "create_object", "object_type_id": wo["id"], "description": "顺带记录工单日志"}
    )
    update_batch = seed_batch(
        client,
        session,
        [
            {
                "operation": "update",
                "target_kind": "action",
                "target_id": act["id"],
                "after": act_after,
                "field_changes": [{"path": "description", "before": act["description"], "after": "新派单说明"}],
            }
        ],
    )
    item = update_batch["items"][0]
    changed_paths = {fc["path"] for fc in item["field_changes"]}
    assert "effects" in changed_paths
    assert "description" in changed_paths

    # Inline revision during review locks `parameters` and `effects`, while allowing `display_name`.
    for locked_field, value in (("parameters", []), ("effects", [])):
        resp = client.patch(
            ROOT + f"/sessions/{session['id']}/proposals/{item['id']}/after",
            json={
                "fields": {locked_field: value},
                "expected_session_revision": session["revision"],
            },
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "FIELD_NOT_EDITABLE"

    ok = client.patch(
        ROOT + f"/sessions/{session['id']}/proposals/{item['id']}/after",
        json={
            "fields": {"display_name": "工单派发"},
            "expected_session_revision": session["revision"],
        },
    )
    assert ok.status_code == 200, ok.text


def test_end_to_end_acceptance_fixture_reads_mcp_ossie_and_native_package(client):
    """Full PR B acceptance: proposal -> accept -> publish -> HTTP/MCP -> Ossie ZIP & Native package roundtrip."""
    # Upload a fictional policy document as evidence for the action.
    policy_text = "# 运维工单流转制度\n只有待派单的工单可以派单，派单时必须指定受理班组。\n巡检工单可由调度员新建。\n"
    upload = client.post(
        ROOT + "/materials",
        params={"name": "work-order-policy.md"},
        content=policy_text.encode("utf-8"),
    )
    assert upload.status_code in (200, 201), upload.text
    material = upload.json()
    evidence = {
        "kind": "material",
        "material_id": material["id"],
        "locator": {"heading": "运维工单流转制度", "line_start": 2, "line_end": 2},
        "quote": "只有待派单的工单可以派单，派单时必须指定受理班组。",
    }

    # 1. Submit fixed proposal fixture, accept all, publish.
    session = create_session(client)
    batch = seed_batch(client, session, _work_order_proposal_fixture(evidence=evidence))
    dec = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": "e2e-accept-work-order-actions",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": i["id"], "decision": "accept"} for i in batch["items"]],
        },
    )
    assert dec.status_code == 200, dec.text
    session = dec.json()["session"]
    pub = publish(client, session)
    assert pub.status_code == 200, pub.text
    version = pub.json()["version"]
    assert version["counts"]["actions"] == 2

    wo = next(o for o in session["draft"]["object_types"] if o["name"] == "work_order")
    insp = next(o for o in session["draft"]["object_types"] if o["name"] == "inspection_order")
    team = next(o for o in session["draft"]["object_types"] if o["name"] == "maintenance_team")
    dispatch = next(a for a in session["draft"]["actions"] if a["name"] == "dispatch_work_order")
    create_insp = next(a for a in session["draft"]["actions"] if a["name"] == "create_inspection_order")

    # 2. HTTP reads: /types, /types/{id}, /catalog, /types/{id}/presentation, authorized_snapshot.
    types_resp = client.get(ROOT + "/types", params={"kind": "action"})
    assert types_resp.status_code == 200
    assert {item["definition"]["name"] for item in types_resp.json()["items"]} == {
        "dispatch_work_order",
        "create_inspection_order",
    }

    insp_detail = client.get(ROOT + f"/types/{insp['id']}").json()["item"]["definition"]
    assert len(insp_detail["actions"]) == 1
    assert insp_detail["actions"][0]["name"] == "dispatch_work_order"
    assert insp_detail["actions"][0]["inherited_from"] == wo["id"]

    catalog_resp = client.get(ROOT + "/catalog", params={"kind": "action"}).json()
    assert catalog_resp["counts"]["actions"] == 2
    assert {item["name"] for item in catalog_resp["items"]} == {
        "dispatch_work_order",
        "create_inspection_order",
    }

    # Element projection on child type includes inherited action + cross-object effect closure (team + pending_count + value_type).
    proj_insp = client.get(
        ROOT + f"/types/{insp['id']}/presentation", params={"kind": "object_type"}
    ).json()["model"]
    assert any(a["id"] == dispatch["id"] for a in proj_insp["actions"])
    assert any(o["id"] == team["id"] for o in proj_insp["object_types"])
    assert any(p["name"] == "pending_count" for p in proj_insp["properties"])
    assert any(v["name"] == "team_code" for v in proj_insp["value_types"])

    # Element projection opening an action directly (including global action).
    proj_global = client.get(
        ROOT + f"/types/{create_insp['id']}/presentation", params={"kind": "action"}
    ).json()["model"]
    assert [a["id"] for a in proj_global["actions"]] == [create_insp["id"]]
    assert any(o["id"] == insp["id"] for o in proj_global["object_types"])

    # authorized_snapshot strips action evidence when instances=False.
    stripped = authorized_snapshot(session["draft"], mappings=True, instances=False)
    assert all(a["evidence"] == [] for a in stripped["actions"])

    # 3. MCP reads: search_ontology two-way expansion + get_ontology list, object summary, single action.
    search_hits = _mcp(client, "search_ontology", {"query": "对工单能做哪些操作"})["structuredContent"]
    dispatch_hit = next((i for i in search_hits["items"] if i["name"] == "dispatch_work_order"), None)
    assert dispatch_hit is not None
    assert dispatch_hit["match"] == {
        "by": "expansion",
        "via": {"id": wo["id"], "relation": "object_action"},
    }

    reverse_hits = _mcp(client, "search_ontology", {"query": "派单"})["structuredContent"]
    wo_hit = next((i for i in reverse_hits["items"] if i["name"] == "work_order"), None)
    assert wo_hit is not None
    assert wo_hit["match"] == {
        "by": "expansion",
        "via": {"id": dispatch["id"], "relation": "action_target_type"},
    }

    # get_ontology without ids lists actions.
    listed = _mcp(client, "get_ontology", {"kinds": ["action"]})["structuredContent"]
    assert {e["name"] for e in listed["elements"]} == {"dispatch_work_order", "create_inspection_order"}

    # get_ontology for object type includes paginated actions (including inherited on inspection_order).
    got_insp = _mcp(client, "get_ontology", {"ids": [insp["id"]]})["structuredContent"]["elements"][0]
    assert got_insp["actions"]["total"] == 1
    assert got_insp["actions"]["items"][0]["name"] == "dispatch_work_order"
    assert got_insp["actions"]["items"][0]["inherited_from"] == wo["id"]

    # get_ontology for single action returns full definition (parameters, effects, evidence).
    got_act = _mcp(client, "get_ontology", {"ids": [dispatch["id"]]})["structuredContent"]["elements"][0]
    assert len(got_act["definition"]["parameters"]) == 1
    assert len(got_act["definition"]["effects"]) == 3
    assert len(got_act["definition"]["evidence"]) == 1

    # 4. Ossie ZIP export & re-import.
    model = CoreDraft.model_validate(session["draft"])
    ossie = OssieAdapter()
    ossie_export = ossie.export_document(
        model,
        ExportContext(workspace_name="运维示例", workspace_slug="ops-demo", workspace_description=""),
    )
    assert ossie_export.document is not None
    action_issues = [i for i in ossie_export.report.issues if i.construct == "actions"]
    assert len(action_issues) == 2
    assert all(i.outcome == "converted" and i.severity == "warning" for i in action_issues)
    with zipfile.ZipFile(io.BytesIO(ossie_export.document)) as zf:
        ext = json.loads(zf.read("ontofoundry-extension.json"))
    assert set(ext["actions"]) == {"dispatch_work_order", "create_inspection_order"}
    assert "dispatch_work_order" not in ext["display_names"]
    assert not any(u["construct"] == "actions" for u in ext["unsupported"])

    reimported_ossie = ossie.import_document(ossie_export.document, ImportContext(workspace_id=uuid4()))
    assert {a.name for a in reimported_ossie.model.actions} == {
        "dispatch_work_order",
        "create_inspection_order",
    }
    re_dispatch = next(a for a in reimported_ossie.model.actions if a.name == "dispatch_work_order")
    assert re_dispatch.display_name == "派单"
    assert re_dispatch.synonyms == ["分派工单"]
    assert re_dispatch.tags == ["工单流转"]
    assert len(re_dispatch.parameters) == 1 and re_dispatch.parameters[0].value_type_id is not None
    assert len(re_dispatch.effects) == 3

    # Corrupt one reference in extension actions: that action is dropped with report, the other still imports.
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(ossie_export.document)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for name in zin.namelist():
            if name == "ontofoundry-extension.json":
                bad_ext = deepcopy(ext)
                bad_ext["actions"]["dispatch_work_order"]["effects"][0]["property"] = "work_order.missing_prop"
                zout.writestr(name, json.dumps(bad_ext, ensure_ascii=False))
            else:
                zout.writestr(name, zin.read(name))
    partial_import = ossie.import_document(buf.getvalue(), ImportContext(workspace_id=uuid4()))
    assert [a.name for a in partial_import.model.actions] == ["create_inspection_order"]
    dropped_actions = [i for i in partial_import.report.issues if i.construct == "Action" and i.outcome == "dropped"]
    assert len(dropped_actions) == 1
    assert dropped_actions[0].completion_status == "available"
    assert dropped_actions[0].original is not None

    # 5. Native complete package export & re-import preserves UUIDs, refs, and evidence.
    pkg = NativePackageAdapter()
    raw_bytes = policy_text.encode("utf-8")
    mat_sha = hashlib.sha256(raw_bytes).hexdigest()
    pkg_export = pkg.export_document(
        model,
        ExportContext(
            workspace_name="运维示例",
            workspace_slug="ops-demo",
            workspace_description="",
            materials=(
                {
                    "material_id": material["id"],
                    "name": "work-order-policy.md",
                    "sha256": mat_sha,
                    "byte_size": len(raw_bytes),
                    "path": f"materials/{mat_sha}.md",
                    "data": raw_bytes,
                },
            ),
        ),
    )
    assert pkg_export.document is not None
    pkg_import = pkg.import_document(pkg_export.document, ImportContext(workspace_id=model.workspace_id))
    assert len(pkg_import.bundled_materials) == 1
    resolved = resolve_material_evidence(
        pkg_import,
        lambda sha: (UUID(material["id"]), policy_text.splitlines()) if sha == mat_sha else None,
    )
    re_native_dispatch = next(a for a in resolved.model.actions if a.name == "dispatch_work_order")
    assert str(re_native_dispatch.id) == dispatch["id"]
    assert str(re_native_dispatch.target_type_id) == wo["id"]
    assert len(re_native_dispatch.evidence) == 1
    assert re_native_dispatch.evidence[0].id == UUID(dispatch["evidence"][0]["id"])


def test_global_only_action_model_refused_by_ossie_and_roundtrips_native_package():
    ws_id = uuid4()
    action_id = uuid4()
    model = CoreDraft(
        workspace_id=ws_id,
        actions=[
            Action(
                id=action_id,
                name="send_oncall_reminder",
                display_name="发送值班提醒",
                description="向当班人员发送定时值班提醒。",
                target_type_id=None,
                parameters=[
                    ActionParameter(name="channel", display_name="通知渠道", value_kind=ValueKind.STRING, required=True)
                ],
                effects=[],
            )
        ],
    )
    validate_core_graph(model)

    # Ossie requires at least one ObjectType.
    ossie_res = OssieAdapter().export_document(
        model, ExportContext(workspace_name="全局示例", workspace_slug="global-only", workspace_description="")
    )
    assert ossie_res.document is None
    assert any(i.outcome == "error" for i in ossie_res.report.issues)

    # Native package round-trips cleanly.
    pkg = NativePackageAdapter()
    pkg_res = pkg.export_document(
        model, ExportContext(workspace_name="全局示例", workspace_slug="global-only", workspace_description="")
    )
    assert pkg_res.document is not None
    reimported = pkg.import_document(pkg_res.document, ImportContext(workspace_id=ws_id))
    assert len(reimported.model.actions) == 1
    assert reimported.model.actions[0].id == action_id
    assert reimported.model.actions[0].name == "send_oncall_reminder"


def test_deleting_referenced_elements_rejected_unless_action_deleted_or_rebound(client):
    session = create_session(client)
    batch = seed_batch(client, session, _work_order_proposal_fixture())
    accept = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": "accept-for-delete-ref-test",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": i["id"], "decision": "accept"} for i in batch["items"]],
        },
    )
    assert accept.status_code == 200, accept.text
    draft = accept.json()["session"]["draft"]
    ctx = RunContext(
        workspace_id=draft["workspace_id"],
        session_id=session["id"],
        run_token="tok-del",
        base_version_id=None,
        base_version_sha256="0" * 64,
        source_session_revision=accept.json()["session"]["revision"],
        source_draft_sha256="0" * 64,
        draft=draft,
    )
    wo = next(o for o in draft["object_types"] if o["name"] == "work_order")
    status_prop = next(p for p in draft["properties"] if p["name"] == "status")
    link = next(l for l in draft["link_types"] if l["name"] == "handled_by")
    vt = next(v for v in draft["value_types"] if v["name"] == "team_code")
    dispatch = next(a for a in draft["actions"] if a["name"] == "dispatch_work_order")

    # Deleting any element referenced by dispatch_work_order without touching the action fails.
    for kind, target_id in (
        ("object_type", wo["id"]),
        ("property", status_prop["id"]),
        ("link_type", link["id"]),
        ("value_type", vt["id"]),
    ):
        with pytest.raises(ProposalContractError):
            parse_result(
                json.dumps({"items": [{"operation": "delete", "target_kind": kind, "target_id": target_id}]}).encode(),
                ctx,
                lambda _: None,
            )

    # Deleting the referencing action in the same proposal allows deleting the value_type.
    ok_delete = parse_result(
        json.dumps(
            {
                "items": [
                    {"operation": "delete", "target_kind": "action", "target_id": dispatch["id"]},
                    {"operation": "delete", "target_kind": "value_type", "target_id": vt["id"]},
                ]
            }
        ).encode(),
        ctx,
        lambda _: None,
    )
    assert len(ok_delete.items) == 2

    # Rebinding the action parameter away from value_type in the same proposal also succeeds.
    rebound_action = deepcopy({k: v for k, v in dispatch.items() if k != "id"})
    rebound_action["parameters"][0]["value_type_id"] = None
    ok_rebind = parse_result(
        json.dumps(
            {
                "items": [
                    {"operation": "update", "target_kind": "action", "target_id": dispatch["id"], "after": rebound_action},
                    {"operation": "delete", "target_kind": "value_type", "target_id": vt["id"]},
                ]
            }
        ).encode(),
        ctx,
        lambda _: None,
    )
    assert len(ok_rebind.items) == 2


def test_public_mcp_get_ontology_strips_action_evidence(client):
    policy_text = "# 派单规范\n内部制度文本不应暴露给公开访客。\n"
    upload = client.post(
        ROOT + "/materials",
        params={"name": "internal-policy.md"},
        content=policy_text.encode("utf-8"),
    )
    assert upload.status_code in (200, 201), upload.text
    evidence = {
        "kind": "material",
        "material_id": upload.json()["id"],
        "locator": {"heading": "派单规范", "line_start": 2, "line_end": 2},
        "quote": "内部制度文本不应暴露给公开访客。",
    }
    session = create_session(client)
    batch = seed_batch(client, session, _work_order_proposal_fixture(evidence=evidence))
    dec = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": "accept-public-mcp-evidence",
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": i["id"], "decision": "accept"} for i in batch["items"]],
        },
    )
    assert dec.status_code == 200, dec.text
    pub = publish(client, dec.json()["session"])
    assert pub.status_code == 200, pub.text
    dispatch = next(a for a in dec.json()["session"]["draft"]["actions"] if a["name"] == "dispatch_work_order")

    # Call MCP with a token that has ontology:read only (no instances:read permission).
    from ontofoundry_api.api.auth import Principal, mcp_principal

    make_public = client.patch(ROOT, json={"is_public": True})
    assert make_public.status_code == 200, make_public.text
    previous = client.app.dependency_overrides.get(mcp_principal)
    guest = Principal(
        id=str(uuid4()),
        username="guest",
        display_name="访客",
        email=None,
        is_platform_admin=False,
        service_token_id=str(uuid4()),
        scopes=frozenset({"ontology:read"}),
    )
    client.app.dependency_overrides[mcp_principal] = lambda: guest
    try:
        got = _mcp(client, "get_ontology", {"ids": [dispatch["id"]]})["structuredContent"]["elements"][0]
        assert got["kind"] == "action"
        assert not got["definition"].get("evidence")
    finally:
        if previous is None:
            client.app.dependency_overrides.pop(mcp_principal, None)
        else:
            client.app.dependency_overrides[mcp_principal] = previous
