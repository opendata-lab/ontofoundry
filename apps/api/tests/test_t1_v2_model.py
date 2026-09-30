"""T1: schema-v2 draft, the read_snapshot boundary and extension v3."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_modeling import ROOT, create_session, publish, save

from ontofoundry_api.db_models import OntologyVersionRecord, WorkspaceRecord
from ontofoundry_api.domain.legacy_v1 import OntologyDraftV1
from ontofoundry_api.domain.models import OntologyDraft, RuleKind
from ontofoundry_api.domain.snapshot import read_snapshot, read_snapshot_json
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID, build_demo_draft

FIXTURES = Path(__file__).parent / "fixtures"
WORKSPACE = UUID(str(DEMO_WORKSPACE_ID))


def v1_demo() -> dict:
    """The demo model in the stored v1 shape, with rules and one instance."""
    draft = build_demo_draft()
    types = []
    for item in draft.object_types:
        types.append(
            {
                **item.model_dump(mode="json", exclude={"evidence"}),
                "requires": [],
                "derived_by": [],
                "attributes": [
                    {
                        **p.model_dump(mode="json", exclude={"owner_type_id", "evidence"}),
                        "requires": [],
                        "derived_by": [],
                    }
                    for p in draft.properties_of(item.id)
                ],
            }
        )
    types[0]["requires"] = ["supplier.code IS NOT NULL", "supplier.code IS NOT NULL"]
    types[0]["attributes"][0]["derived_by"] = ["UPPER(supplier.code)"]
    links = [
        {**link.model_dump(mode="json", exclude={"evidence"}), "requires": [], "derived_by": []}
        for link in draft.link_types
    ]
    return OntologyDraftV1.model_validate(
        {
            "schema_version": "1",
            "workspace_id": str(WORKSPACE),
            "requires": ["EXISTS (supplier)"],
            "object_types": types,
            "link_types": links,
            "objects": [
                {
                    "id": "10375c4d-64e2-4ddf-a6e6-f3fc36d2a001",
                    "type_id": types[0]["id"],
                    "name": "供应商甲",
                    "values": {
                        a["technical_name"]: "甲"
                        for a in types[0]["attributes"]
                        if a["required"] or a["identifier"]
                    },
                    "evidence": [
                        {"material_id": "m1", "line_start": 3, "line_end": 4, "quote": "甲"}
                    ],
                }
            ],
        }
    ).model_dump(mode="json")


def action_draft() -> OntologyDraft:
    """Demo model plus a rule-guarded action with every effect kind."""
    draft = build_demo_draft()
    supplier = draft.object_types[0]
    prop = draft.properties_of(supplier.id)[0]
    link = next(link for link in draft.link_types if supplier.id in (link.source_type_id, link.target_type_id))
    payload = draft.model_dump(mode="json")
    action_id, rule_id, owned_rule = str(uuid4()), str(uuid4()), str(uuid4())
    payload["rules"] = [
        {
            "id": rule_id,
            "name": "编码必填",
            "technical_name": "code_required",
            "owner_kind": "property",
            "owner_id": str(prop.id),
            "rule_kind": "constraint",
            "expression": f"{supplier.technical_name}.{prop.technical_name} IS NOT NULL",
        },
        {
            "id": owned_rule,
            "name": "仅审批一次",
            "technical_name": "approve_once",
            "owner_kind": "action",
            "owner_id": action_id,
            "rule_kind": "constraint",
            "expression": "approved = FALSE",
        },
    ]
    payload["actions"] = [
        {
            "id": action_id,
            "name": "审批供应商",
            "technical_name": "approve_supplier",
            "description": "把供应商标记为已审批",
            "input_type_id": str(supplier.id),
            "parameters": [
                {"id": str(uuid4()), "name": "意见", "technical_name": "comment", "value_kind": "string"}
            ],
            "precondition_rule_ids": [rule_id, owned_rule],
            "effects": [
                {
                    "id": str(uuid4()),
                    "kind": "set_property",
                    "property_id": str(prop.id),
                    "expression": ":comment",
                },
                {"id": str(uuid4()), "kind": "create_link", "link_type_id": str(link.id)},
            ],
        }
    ]
    return OntologyDraft.model_validate(payload)


# --- v1 → v2 normalization ------------------------------------------------


def test_v1_rules_become_elements_with_stable_ids():
    v1 = v1_demo()
    first, second = read_snapshot(v1), read_snapshot(deepcopy(v1))

    assert [r.id for r in first.rules] == [r.id for r in second.rules]
    supplier = first.object_types[0]
    # The duplicated v1 expression is one rule, not two.
    assert first.expressions_of(supplier.id, RuleKind.CONSTRAINT) == ["supplier.code IS NOT NULL"]
    code = first.properties_of(supplier.id)[0]
    assert first.expressions_of(code.id, RuleKind.DERIVATION) == ["UPPER(supplier.code)"]
    assert first.ontology_requires == ["EXISTS (supplier)"]
    assert {r.owner_kind.value for r in first.rules} == {"object_type", "property"}


def test_v1_instances_and_evidence_are_normalized():
    draft = read_snapshot(v1_demo())
    (instance,) = draft.material_objects
    (evidence,) = instance.evidence
    assert evidence.kind == "material"
    assert evidence.material_id == "m1"
    assert (evidence.locator.line_start, evidence.locator.line_end) == (3, 4)
    assert evidence.material_sha256 is None  # predates the field
    assert read_snapshot(v1_demo()).material_objects[0].evidence[0].id == evidence.id


def test_editing_a_rule_expression_keeps_its_id():
    draft = read_snapshot(v1_demo())
    rule = draft.rules[0]
    payload = draft.model_dump(mode="json")
    payload["rules"][0]["expression"] = "supplier.code <> ''"
    assert OntologyDraft.model_validate(payload).rules[0].id == rule.id


def test_v2_read_is_identity():
    payload = action_draft().model_dump(mode="json")
    assert read_snapshot_json(payload) == payload


# --- invariants -------------------------------------------------------------


def test_rules_must_belong_to_a_concrete_element():
    payload = action_draft().model_dump(mode="json")
    workspace_rule = deepcopy(payload)
    workspace_rule["rules"][0]["owner_kind"] = "workspace"
    with pytest.raises(ValidationError):
        OntologyDraft.model_validate(workspace_rule)

    missing_owner = deepcopy(payload)
    missing_owner["rules"][0]["owner_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="归属元素"):
        OntologyDraft.model_validate(missing_owner)

    wrong_kind = deepcopy(payload)
    wrong_kind["rules"][0]["owner_kind"] = "link_type"
    with pytest.raises(ValidationError, match="归属元素"):
        OntologyDraft.model_validate(wrong_kind)


def test_action_references_are_checked():
    payload = action_draft().model_dump(mode="json")
    bad_rule = deepcopy(payload)
    bad_rule["actions"][0]["precondition_rule_ids"].append(str(uuid4()))
    with pytest.raises(ValidationError, match="前置规则"):
        OntologyDraft.model_validate(bad_rule)

    bad_effect = deepcopy(payload)
    bad_effect["actions"][0]["effects"][0]["property_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="属性"):
        OntologyDraft.model_validate(bad_effect)

    wrong_shape = deepcopy(payload)
    wrong_shape["actions"][0]["effects"][1]["property_id"] = wrong_shape["actions"][0][
        "effects"
    ][0]["property_id"]
    with pytest.raises(ValidationError, match="link_type_id"):
        OntologyDraft.model_validate(wrong_shape)


def test_manual_evidence_needs_author_and_time():
    payload = action_draft().model_dump(mode="json")
    payload["object_types"][0]["evidence"] = [{"kind": "manual", "id": str(uuid4()), "note": "x"}]
    with pytest.raises(ValidationError):
        OntologyDraft.model_validate(payload)


# --- Ossie extension v3 -----------------------------------------------------


def test_rules_and_actions_round_trip_through_extension_v3():
    draft = action_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    assert validate_ossie(document)["publishable"], validate_ossie(document)
    extension = document["ai_context"]["ontofoundry"]
    assert extension["version"] == "3"
    assert extension["actions"][0]["technical_name"] == "approve_supplier"

    payload, report = import_ossie(document, workspace_id=str(WORKSPACE), mode="replace")
    imported = OntologyDraft.model_validate(payload)
    assert report["skipped"] == []

    assert {(r.id, r.technical_name, r.expression) for r in imported.rules} == {
        (r.id, r.technical_name, r.expression) for r in draft.rules
    }
    (action,) = imported.actions
    (original,) = draft.actions
    assert action.id == original.id
    assert action.precondition_rule_ids == original.precondition_rule_ids
    assert [e.kind for e in action.effects] == [e.kind for e in original.effects]
    # Replace import derives type/property/link ids from their names, so
    # effect targets are compared by name; action and rule ids come from the file.
    def targets(model, act):
        props = {p.id: p.technical_name for p in model.properties}
        links = {link.id: link.technical_name for link in model.link_types}
        return [(props.get(e.property_id), links.get(e.link_type_id)) for e in act.effects]

    assert targets(imported, action) == targets(draft, original)
    assert action.parameters == original.parameters


def test_merge_import_keeps_rule_ids_of_unchanged_expressions():
    draft = action_draft()
    document = compile_ossie(draft, ontology_name="mfg", ontology_description="制造")
    del document["ai_context"]["ontofoundry"]["rules"]  # no identities in the file
    payload, _ = import_ossie(
        document, workspace_id=str(WORKSPACE), base=draft.model_dump(mode="json"), mode="merge"
    )
    merged = OntologyDraft.model_validate(payload)
    property_rule = next(r for r in draft.rules if r.owner_kind.value == "property")
    assert property_rule.id in {r.id for r in merged.rules}


def test_frozen_extension_v2_exports_still_import():
    samples = json.loads((FIXTURES / "ossie_extension_v2_export.json").read_text(encoding="utf-8"))
    for name, sample in samples.items():
        assert sample["ossie"]["ai_context"]["ontofoundry"]["version"] == "2"
        payload, report = import_ossie(
            sample["ossie"], workspace_id=sample["workspace_id"], mode="replace"
        )
        model = OntologyDraft.model_validate(payload)
        expected = read_snapshot(sample["draft"])
        assert {t.technical_name for t in model.object_types} == {
            t.technical_name for t in expected.object_types
        }, name
        assert sorted(r.expression for r in model.rules) == sorted(
            r.expression for r in expected.rules
        ), name
        assert report["skipped"] == [], name


def test_frozen_extension_v3_export_still_imports():
    path = FIXTURES / "ossie_extension_v3_export.json"
    sample = json.loads(path.read_text(encoding="utf-8"))
    assert sample["ossie"]["ai_context"]["ontofoundry"]["version"] == "3"
    payload, report = import_ossie(sample["ossie"], workspace_id=sample["workspace_id"], mode="replace")
    model = OntologyDraft.model_validate(payload)
    assert [a.technical_name for a in model.actions] == ["approve_supplier"]
    assert {str(r.id) for r in model.rules} == {r["id"] for r in sample["draft"]["rules"]}
    assert report["skipped"] == []


# --- historical v1 versions through the API ---------------------------------


def install_v1_head(client) -> dict:
    """Rewrite the current version row to a v1 snapshot, as an old database has."""
    v1 = v1_demo()
    with client.app.state.session_factory() as db:
        space = db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
        version = db.get(OntologyVersionRecord, space.current_version_id)
        version.snapshot_json = v1
        db.commit()
    return v1


def test_historical_v1_version_is_readable_comparable_and_exportable(client):
    install_v1_head(client)
    snapshot = client.get(ROOT + "/published-snapshot").json()
    assert snapshot["schema_version"] == "2"
    assert len(snapshot["rules"]) == 2

    versions = client.get(ROOT + "/versions").json()["items"]
    head = versions[0]["version_id"]
    assert versions[0]["normalized_snapshot_sha256"]
    assert versions[0]["version_content_sha256"] == versions[0]["version_sha256"]

    exported = client.get(
        f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}/versions/{head}/export"
    )
    assert exported.status_code == 200


def test_session_from_a_v1_head_is_v2_and_publishes_v2(client):
    install_v1_head(client)
    session = create_session(client)
    assert session["draft"]["schema_version"] == "2"
    session["draft"]["object_types"][0]["description"] = "基于历史 v1 版本修改"
    session = save(client, session, session["draft"]).json()
    published = publish(client, session)
    assert published.status_code == 200, published.text

    with client.app.state.session_factory() as db:
        space = db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
        latest = db.get(OntologyVersionRecord, space.current_version_id)
        assert latest.snapshot_json["schema_version"] == "2"
        assert len(latest.snapshot_json["rules"]) == 2

    items = client.get(ROOT + "/versions").json()["items"]
    comparison = client.get(
        ROOT + "/version-comparison",
        params={"right_id": items[0]["version_id"], "left_id": items[1]["version_id"]},
    )
    assert comparison.status_code == 200
    assert any(c["path"].endswith(".description") for c in comparison.json()["changes"])
