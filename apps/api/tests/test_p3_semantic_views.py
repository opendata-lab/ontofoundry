"""P3 native projections: only query inputs are interpreted; source is immutable."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from test_instance_queries import ROOT
from test_instance_queries import mapped_session as sql_session
from test_p1_native_roundtrip import FIXTURES

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.runtime_views import apply_mapping_form, legacy_mapping_form
from ontofoundry_api.domain.semantic_views import (
    SemanticViews,
    join_columns,
    join_view,
    mapping_view,
)
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.extensions import reverse_export_edits
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.instance_query import mapping_for

mapped_session = sql_session


def imported(stem="REDACTED"):
    original = json.loads((FIXTURES / (stem + ".ossie.json")).read_text())
    raw, _ = import_ossie(original, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    return original, OntologyDraft.model_validate(raw)


@pytest.mark.parametrize("stem", ["REDACTED", "REDACTED"])
def test_views_never_mutate_native_or_export(stem):
    original, draft = imported(stem)
    before = draft.model_dump(mode="json")
    for concept in draft.object_types:
        mapping_view(draft, concept.id)
    for link in draft.link_types:
        join_view(draft, link.id)
    assert draft.model_dump(mode="json") == before
    assert (
        reverse_export_edits(
            compile_ossie(draft, ontology_name="", ontology_description="")
        )
        == original
    )


def test_b_coverage_and_unused_computed_fields():
    _, draft = imported()
    views = SemanticViews(draft)
    queryable = {c.concept for c in draft.object_types if views.analyze(c.id).mapping}
    assert queryable == {
        "system",
        "REDACTED",
        "environment",
        "zone",
        "REDACTED",
        "host",
        "REDACTED",
        "REDACTED",
        "REDACTED",
        "REDACTED",
    }
    reasons = [views.analyze(c.id).reason for c in draft.object_types]
    assert reasons.count("multiple_roots") == 2
    assert reasons.count("referent_mapping") == 9
    assert (
        sum(
            not views.analyze(c.id).mapping and not views.analyze(c.id).reason
            for c in draft.object_types
        )
        == 8
    )
    REDACTED = next(c for c in draft.object_types if c.concept == "REDACTED")
    # REDACTED is a CASE expression in the same dataset, unrelated to this query.
    assert mapping_view(draft, REDACTED.id).key_column == "REDACTED"
    component = next(c for c in draft.object_types if c.concept == "component")
    with pytest.raises(Exception) as error:
        mapping_for(draft, component.id)
    assert error.value.detail == {
        "code": "COMPLEX_MAPPING_READ_ONLY",
        "message": "复杂映射暂不支持实例查询",
        "reason": "multiple_roots",
    }
    form = legacy_mapping_form(draft.model_dump(mode="json"))
    with pytest.raises(ValueError, match="复杂映射请在语义模型中编辑"):
        apply_mapping_form(
            draft.model_dump(mode="json"),
            [
                *form["mappings"],
                dict(
                    id=str(uuid4()),
                    type_id=str(component.id),
                    connection_alias="new",
                    table_name="t",
                    key_column="id",
                    fields={},
                ),
            ],
        )


def test_composite_join_and_native_edit_roundtrip(client, mapped_session):
    session, supplier, material = mapped_session
    draft = OntologyDraft.model_validate(session["draft"])
    relation = next(r for r in draft.link_types if r.technical_name == "supplies")
    form = legacy_mapping_form(session["draft"])
    joins = {
        **form["joins"],
        str(relation.id): dict(
            source_columns=["code", "name"], target_columns=["supplier_code", "name"]
        ),
    }
    updated = apply_mapping_form(session["draft"], joins=joins)
    join = join_view(OntologyDraft.model_validate(updated), relation.id)
    assert join_columns(join) == (("code", "name"), ("supplier_code", "name"))
    assert updated["mappings"] == []
    assert (
        legacy_mapping_form(updated)["joins"][str(relation.id)]["owner_columns"]
        == joins[str(relation.id)]["source_columns"]
    )
    # Re-editing a property mapping retains unrelated native join, identities and metadata.
    raw_maps = deepcopy(form["mappings"])
    next(m for m in raw_maps if m["type_id"] == supplier["id"])["fields"][
        "supplier_code"
    ] = "name"
    edited = apply_mapping_form(updated, mappings=raw_maps)
    assert edited["dataset_relationships"] == updated["dataset_relationships"]
    exported = compile_ossie(
        OntologyDraft.model_validate(edited), ontology_name="test", ontology_description=""
    )
    assert validate_ossie(exported)["publishable"]
    reloaded, _ = import_ossie(exported, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    assert (
        compile_ossie(
            OntologyDraft.model_validate(reloaded),
            ontology_name="test",
            ontology_description="",
        )
        == exported
    )
    assert join_columns(
        join_view(OntologyDraft.model_validate(reloaded), relation.id)
    ) == join_columns(join)
    for collection in (
        "datasets",
        "dataset_fields",
        "concept_mappings",
        "mapping_nodes",
        "dataset_relationships",
    ):
        assert {n["id"] for n in reloaded[collection]} == {
            n["id"] for n in edited[collection]
        }


def test_composite_sql_join_filters_every_key_in_both_directions(client, mapped_session):
    from sqlalchemy import text

    from ontofoundry_api.api import connections

    session, supplier, material = mapped_session
    with connections.connect_readonly(None, None) as sql:
        sql.execute(text("ALTER TABLE suppliers ADD tenant TEXT DEFAULT 't1'"))
        sql.execute(text("ALTER TABLE materials ADD tenant TEXT DEFAULT 't1'"))
        sql.execute(text("UPDATE materials SET tenant='t2' WHERE code='M2'"))
        sql.commit()
    link = next(
        r for r in session["draft"]["link_types"] if r["technical_name"] == "supplies"
    )
    edited = apply_mapping_form(
        session["draft"],
        joins={
            link["id"]: dict(
                source_columns=["code", "tenant"],
                target_columns=["supplier_code", "tenant"],
            )
        },
    )
    saved = client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": edited},
    )
    assert saved.status_code == 200, saved.text

    def query(type_id, key):
        result = client.post(
            ROOT + "/instance-neighborhood",
            json={"session_id": session["id"], "type_id": type_id, "key": key},
        )
        assert result.status_code == 200, result.text
        assert not any(
            "关系字段" in w or "对象映射字段" in w for w in result.json()["warnings"]
        )
        return {o["key"] for o in result.json()["objects"]}

    assert query(supplier["id"], "S1") == {"S1", "M1"}
    assert query(material["id"], "M1") == {"S1", "M1"}
    assert query(material["id"], "M2") == {"M2"}


def test_native_shared_join_binding_can_be_overridden_and_disabled(client, mapped_session):
    session, _, _ = mapped_session
    raw = deepcopy(session["draft"])
    relation = next(r for r in raw["link_types"] if r["technical_name"] == "supplies")
    raw["dataset_relationships"][0]["name"] = "native_shared_join"
    draft = OntologyDraft.model_validate(raw)
    assert join_view(draft, relation["id"]) is not None
    edited = apply_mapping_form(
        raw, joins={relation["id"]: dict(source_column="name", target_column="name")}
    )
    assert raw["dataset_relationships"][0] in edited["dataset_relationships"]
    assert join_columns(
        join_view(OntologyDraft.model_validate(edited), relation["id"])
    ) == (("name",), ("name",))
    disabled = apply_mapping_form(edited, joins={relation["id"]: None})
    assert join_view(OntologyDraft.model_validate(disabled), relation["id"]) is None
    assert raw["dataset_relationships"][0] in disabled["dataset_relationships"]


def test_element_save_publishes_only_selected_mapping_keeps_other_session_trees(
    client, mapped_session
):
    session, supplier, material = mapped_session
    raw = deepcopy(session["draft"])
    next(t for t in raw["object_types"] if t["id"] == supplier["id"])["description"] = (
        "只保存供应商"
    )
    form = session["legacy_mapping_form"]
    saved = client.post(
        ROOT + "/element-saves",
        json={
            "target_kind": "object_type",
            "target_id": supplier["id"],
            "session_id": session["id"],
            "expected_session_revision": session["revision"],
            "expected_current_version_id": session["base_version_id"],
            "draft": raw,
            "legacy_mappings": form["mappings"],
            "legacy_joins": form["joins"],
        },
    )
    assert saved.status_code == 200, saved.text
    result = saved.json()
    published = legacy_mapping_form(result["draft"])
    assert [m["type_id"] for m in published["mappings"]] == [supplier["id"]]
    kept = result["session"]["draft"]
    assert {m["type_id"] for m in legacy_mapping_form(kept)["mappings"]} == {
        supplier["id"],
        material["id"],
    }
    assert kept["semantic_models"] == session["draft"]["semantic_models"]
    assert kept["dataset_relationships"] == session["draft"]["dataset_relationships"]
    assert kept["mapping_nodes"] == session["draft"]["mapping_nodes"]


def test_v2_migration_adds_unmapped_join_fields_without_changing_source():
    from test_ossie_import import mapped_draft

    from ontofoundry_api.domain.canonical import snapshot_sha256
    from ontofoundry_api.domain.snapshot import read_snapshot

    legacy = mapped_draft().model_dump(mode="json")
    before = deepcopy(legacy)
    digest = snapshot_sha256(legacy)
    migrated = read_snapshot(legacy, target_version="3")
    link = next(r for r in migrated.link_types if r.technical_name == "supplies")
    assert join_columns(join_view(migrated, link.id)) == (("code",), ("supplier_code",))
    views = SemanticViews(migrated)
    for relation in migrated.dataset_relationships:
        datasets = {
            d.name: d
            for d in migrated.datasets
            if d.semantic_model_id == relation.semantic_model_id
        }
        for name, columns in (
            (relation.from_, relation.from_columns),
            (relation.to, relation.to_columns),
        ):
            assert set(columns) <= views.fields[datasets[name].id].keys()
    assert legacy == before and snapshot_sha256(legacy) == digest
    assert read_snapshot(legacy, target_version="3") == migrated
    assert validate_ossie(
        compile_ossie(migrated, ontology_name="test", ontology_description="")
    )["publishable"]


def test_join_form_preserves_conflicting_native_field_and_resolves_alias(
    client, mapped_session
):
    session, _, _ = mapped_session
    raw = deepcopy(session["draft"])
    link = next(r for r in raw["link_types"] if r["technical_name"] == "supplies")
    material = next(d for d in raw["datasets"] if d["name"] == "material")
    field = next(
        f
        for f in raw["dataset_fields"]
        if f["dataset_id"] == material["id"] and f["name"] == "material_name"
    )
    field["name"] = "new_key"
    raw["dataset_relationships"] = []
    # new_key is already a logical field for physical name, and must not be overwritten.
    unchanged = deepcopy(field)
    edited = apply_mapping_form(
        raw, joins={link["id"]: dict(source_column="code", target_column="new_key")}
    )
    assert unchanged in edited["dataset_fields"]
    assert join_columns(join_view(OntologyDraft.model_validate(edited), link["id"])) == (
        ("code",),
        ("new_key",),
    )
    rel = edited["dataset_relationships"][0]
    assert rel["to_columns"] == ["new_key__join"]
    assert (
        apply_mapping_form(
            edited, joins={link["id"]: dict(source_column="code", target_column="new_key")}
        )
        == edited
    )


@pytest.mark.parametrize("failure", ["missing_dataset_field", "missing_physical_column"])
def test_neighborhood_reports_specific_missing_join_field(client, mapped_session, failure):
    session, supplier, _ = mapped_session
    raw = deepcopy(session["draft"])
    material = next(d for d in raw["datasets"] if d["name"] == "material")
    field = next(
        f
        for f in raw["dataset_fields"]
        if f["dataset_id"] == material["id"] and f["name"] == "supplier_code"
    )
    if failure == "missing_dataset_field":
        raw["dataset_fields"].remove(field)
        expected = "material.supplier_code"
    else:
        field["expression"]["dialects"][0]["expression"] = "deleted_supplier_code"
        expected = "materials.deleted_supplier_code"
    saved = client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": raw},
    )
    if failure == "missing_physical_column":
        assert saved.status_code == 422, saved.text
        assert saved.json()["error"]["code"] == "JOIN_COLUMN_NOT_FOUND"
        # Historical/imported snapshots are not rewritten. Query diagnostics
        # still identify their missing physical column.
        from ontofoundry_api.db_models import ModelingSessionRecord
        from ontofoundry_api.domain.canonical import snapshot_sha256
        with client.app.state.session_factory() as db:
            record = db.get(ModelingSessionRecord, session["id"])
            record.draft_json = raw
            record.draft_sha256 = snapshot_sha256(raw)
            db.commit()
    else:
        assert saved.status_code == 200, saved.text
    result = client.post(
        ROOT + "/instance-neighborhood",
        json={"session_id": session["id"], "type_id": supplier["id"], "key": "S1"},
    )
    assert result.status_code == 200, result.text
    assert any(expected in warning for warning in result.json()["warnings"]), result.json()
