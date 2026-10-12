"""Native edits are scoped, transactional, and preserve the real Ossie envelopes."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_modeling import ROOT, create_session, save
from test_p2_mcp_synonyms import publish

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.semantic_authoring import (
    SemanticChange,
    apply_changes,
    identifier_edits,
)
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.extensions import reverse_export_edits


@pytest.fixture(params=["client", "pg_client"])
def editing_client(request):
    return request.getfixturevalue(request.param)


def current(client):
    return client.get(ROOT + "/semantic-models").json()


def write(client, changes, session=None, version=None):
    return client.post(
        ROOT + "/semantic-saves",
        json={
            "expected_current_version_id": version or current(client)["current_version_id"],
            "session_id": session["id"] if session else None,
            "expected_session_revision": session["revision"] if session else None,
            "changes": changes,
        },
    )


def exported(client):
    draft = client.get(ROOT + "/published-snapshot").json()
    result = compile_ossie(
        OntologyDraft.model_validate(draft),
        ontology_name="ignored",
        ontology_description="ignored",
    )
    assert validate_ossie(result)["publishable"], validate_ossie(result)
    return reverse_export_edits(result), draft


def change(kind, target, values=None, **kwargs):
    return dict(kind=kind, id=target["id"], values=values or {}, **kwargs)


@pytest.mark.parametrize("stem", ["account-model-v2", "architecture-governance"])
def test_catalog_and_no_edit_export_are_lossless(editing_client, stem):
    source, _, _ = publish(editing_client, stem)
    catalog = current(editing_client)
    assert exported(editing_client)[0] == source
    assert "native_presence" not in str(catalog) and "origin" not in catalog
    if stem == "architecture-governance":
        model = catalog["items"][0]
        assert len(model["concept_mappings"]) == 21
        assert model["relationships"][0]["from"] == "component_deployment_snapshot"
        assert "from_" not in model["relationships"][0]
        assert sum(len(d["fields"]) for d in model["datasets"]) == 371
        metric = next(m for m in model["metrics"] if m["name"] == "core_service_count")
        assert metric["query"]["requires_snapshot_filter"]
        assert metric["display_name"] == metric["name"]  # no alias/description guess


def test_field_rename_updates_only_identifier_references(editing_client):
    client = editing_client
    source, draft, _ = publish(client, "architecture-governance")
    ds = next(d for d in draft["datasets"] if d["name"] == "component_snapshot")
    field = next(
        f
        for f in draft["dataset_fields"]
        if f["dataset_id"] == ds["id"] and f["name"] == "component_name"
    )
    result = write(client, [change("dataset_field", field, {"name": "service_key"})])
    assert result.status_code == 200, result.text
    output, latest = exported(client)
    model = output["ontology_mappings"][0]["semantic_model"]
    metric = next(m for m in model["metrics"] if m["name"] == "core_service_count")
    assert (
        "component_snapshot.service_key"
        in metric["expression"]["dialects"][0]["expression"]
    )
    rel = next(r for r in model["relationships"] if r["name"] == "deployment_to_component")
    assert rel["to_columns"] == ["env_name", "service_key"]
    assert latest["dataset_fields"][0]["id"] == draft["dataset_fields"][0]["id"]
    assert output["ontology"] == source["ontology"]
    original = next(
        d
        for d in source["ontology_mappings"][0]["semantic_model"]["datasets"]
        if d["name"] == "component_snapshot"
    )
    updated = next(d for d in model["datasets"] if d["name"] == "component_snapshot")
    assert updated["fields"][0] == {**original["fields"][0], "name": "service_key"}
    assert updated["fields"][1:] == original["fields"][1:]


def test_dataset_rename_updates_connections_and_mapping_trees(editing_client):
    client = editing_client
    _, draft, _ = publish(client, "architecture-governance")
    ds = draft["datasets"][0]
    result = write(client, [change("dataset", ds, {"name": "component_current"})])
    assert result.status_code == 200, result.text
    _, latest = exported(client)
    assert all(
        r["to"] != ds["name"] and r["from"] != ds["name"]
        for r in latest["dataset_relationships"]
    )
    assert any(
        "component_current." in n.get("expression", "") for n in latest["mapping_nodes"]
    )


def test_create_edit_delete_field_and_unreferenced_dataset(editing_client):
    client = editing_client
    _, draft, _ = publish(client, "architecture-governance")
    ds_id, field_id = str(uuid4()), str(uuid4())
    create = [
        {
            "kind": "dataset",
            "operation": "create",
            "id": ds_id,
            "parent_id": draft["semantic_models"][0]["id"],
            "values": {"name": "extra_data", "source": "public.extra"},
        },
        {
            "kind": "dataset_field",
            "operation": "create",
            "id": field_id,
            "parent_id": ds_id,
            "values": {
                "name": "key",
                "datatype": "Integer",
                "expression": {
                    "dialects": [{"dialect": "ANSI_SQL", "expression": "physical_id"}]
                },
            },
        },
    ]
    assert write(client, create).status_code == 200
    assert (
        write(
            client,
            [
                {
                    "kind": "dataset_field",
                    "id": field_id,
                    "values": {"description": "标识说明"},
                }
            ],
        ).status_code
        == 200
    )
    assert (
        write(client, [{"kind": "dataset", "id": ds_id, "operation": "delete"}]).status_code
        == 200
    )
    _, latest = exported(client)
    assert not any(d["id"] == ds_id for d in latest["datasets"])
    assert not any(f["id"] == field_id for f in latest["dataset_fields"])


def test_reference_protection_and_atomic_errors(editing_client):
    client = editing_client
    _, draft, version = publish(client, "architecture-governance")
    target = draft["datasets"][0]
    result = write(client, [change("dataset", target, operation="delete")])
    assert (
        result.status_code == 422
        and result.json()["error"]["code"] == "SEMANTIC_ELEMENT_REFERENCED"
    )
    assert result.json()["error"]["references"]
    rel = draft["dataset_relationships"][0]
    result = write(
        client,
        [change("dataset_relationship", rel, {"from_columns": ["missing", "missing_2"]})],
    )
    assert result.status_code == 422 and "missing" in result.json()["error"]["message"]
    assert current(client)["current_version_id"] == version
    result = write(client, [change("dataset", target, {"origin": "platform"})])
    assert result.status_code == 422


def test_mapping_tree_edit_preserves_untouched_roots_and_arrays(editing_client):
    client = editing_client
    source, draft, _ = publish(client, "architecture-governance")
    cm = current(client)["items"][0]["concept_mappings"][0]
    nodes = [{k: v for k, v in n.items() if k != "concept_mapping_id"} for n in cm["nodes"]]
    result = write(client, [change("concept_mapping", cm, nodes=nodes)])
    assert result.status_code == 200, result.text
    assert exported(client)[0] == source
    nodes.append(
        {
            "id": str(uuid4()),
            "parent_id": None,
            "slot": "object_mappings",
            "kind": "object",
            "expression": "component_snapshot.component_name_cn",
        }
    )
    result = write(client, [change("concept_mapping", cm, nodes=nodes)])
    assert result.status_code == 200, result.text
    output, latest = exported(client)
    assert (
        len(output["ontology_mappings"][0]["concept_mappings"][0]["object_mappings"]) == 2
    )
    assert (
        output["ontology_mappings"][0]["concept_mappings"][0]["link_mappings"]
        == source["ontology_mappings"][0]["concept_mappings"][0]["link_mappings"]
    )
    assert set(n["id"] for n in draft["mapping_nodes"]) <= {
        n["id"] for n in latest["mapping_nodes"]
    }


def test_session_cas_preserves_other_pending_semantic_and_concept_changes(editing_client):
    client = editing_client
    _, _, _ = publish(client, "architecture-governance")
    session = create_session(client)
    draft = deepcopy(session["draft"])
    draft["object_types"][0]["description"] = "未保存的本体修改"
    draft["datasets"][1]["description"] = "未保存的其他数据集"
    session = save(client, session, draft).json()
    selected = session["draft"]["datasets"][0]
    result = write(
        client,
        [change("dataset", selected, {"description": "当前数据集修改"})],
        session=session,
    )
    assert result.status_code == 200, result.text
    updated = result.json()["session"]
    assert updated["revision"] == session["revision"] + 1
    assert updated["draft"]["datasets"][1]["description"] == "未保存的其他数据集"
    published = client.get(ROOT + "/published-snapshot").json()
    assert published["datasets"][1]["description"] != "未保存的其他数据集"
    assert published["object_types"][0]["description"] != "未保存的本体修改"
    assert (
        write(
            client, [change("dataset", selected, {"description": "过期"})], session=session
        ).status_code
        == 409
    )


def test_compile_only_draft_preview_never_executes(editing_client, monkeypatch):
    client = editing_client
    _, _, _ = publish(client, "architecture-governance")
    session = create_session(client)
    metric = next(
        m for m in session["draft"]["metrics"] if m["name"] == "core_service_count"
    )

    def forbidden(*args, **kwargs):
        pytest.fail("SQL preview must not open a data connection")

    monkeypatch.setattr("ontofoundry_api.api.connections.connect_readonly", forbidden)
    body = {
        "session_id": session["id"],
        "expected_session_revision": session["revision"],
        "expected_current_version_id": current(client)["current_version_id"],
        "group_by": ["env_name"],
        "as_of": "2026-10-08",
        "dialect": "MYSQL",
        "changes": [
            change(
                "metric",
                metric,
                {
                    "expression": {
                        "dialects": [
                            {
                                "dialect": "ANSI_SQL",
                                "expression": "COUNT(component_snapshot.component_name)",
                            }
                        ]
                    }
                },
            )
        ],
    }
    result = client.post(ROOT + f"/metrics/{metric['id']}/sql-preview", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["executed"] is False and "`public`" in result.json()["sql"]
    assert "CASE" not in result.json()["sql"] and result.json()["parameters"]
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == session["revision"]
    )
    body.pop("as_of")
    assert (
        client.post(ROOT + f"/metrics/{metric['id']}/sql-preview", json=body).json()[
            "error"
        ]["code"]
        == "METRIC_SNAPSHOT_REQUIRED"
    )


def test_token_rename_retains_literals_comments_and_whitespace():
    value = "CONCAT('old.field', old.field) /* old.field */ + old.field_suffix"
    edited, found = identifier_edits(
        value, dataset="old", field="field", replacement="renamed"
    )
    assert (
        found
        and edited == "CONCAT('old.field', old.renamed) /* old.field */ + old.field_suffix"
    )

    rewritten, found = identifier_edits(
        "COUNT(old.field) + COUNT", metric="COUNT", replacement="total"
    )
    assert found and rewritten == "COUNT(old.field) + total"


def test_cyclic_mapping_edit_is_rejected(client):
    _, draft, _ = publish(client, "architecture-governance")
    cm = draft["concept_mappings"][0]
    nid = str(uuid4())
    with pytest.raises(ValueError):
        apply_changes(
            draft,
            [
                SemanticChange(
                    kind="concept_mapping",
                    id=cm["id"],
                    nodes=[
                        {"id": nid, "parent_id": nid, "slot": "children", "kind": "link"}
                    ],
                )
            ],
        )


def test_metric_and_composite_relationship_crud(editing_client):
    client = editing_client
    _, draft, _ = publish(client, "architecture-governance")
    mid = draft["semantic_models"][0]["id"]
    metric_id, rel_id = str(uuid4()), str(uuid4())
    create = [
        dict(
            kind="metric",
            operation="create",
            id=metric_id,
            parent_id=mid,
            values={
                "name": "custom_count",
                "expression": {
                    "dialects": [
                        {
                            "dialect": "ANSI_SQL",
                            "expression": "COUNT(component_snapshot.component_name)",
                        }
                    ]
                },
                "ai_context": {"synonyms": ["自定义组件数"]},
            },
            display_name="组件总数",
        ),
        dict(
            kind="dataset_relationship",
            operation="create",
            id=rel_id,
            parent_id=mid,
            values={
                "name": "custom_composite",
                "from": "component_snapshot",
                "to": "component_snapshot",
                "from_columns": ["env_name", "component_name"],
                "to_columns": ["env_name", "component_name"],
            },
        ),
    ]
    result = write(client, create)
    assert result.status_code == 200, result.text
    model = current(client)["items"][0]
    metric = next(m for m in model["metrics"] if m["id"] == metric_id)
    assert metric["display_name"] == "组件总数" and metric["ai_context"]["synonyms"] == [
        "自定义组件数"
    ]
    from ontofoundry_api.ossie.importer import import_ossie

    _, latest = exported(client)
    raw = compile_ossie(
        OntologyDraft.model_validate(latest),
        ontology_name="ignored",
        ontology_description="ignored",
    )
    recovered, _ = import_ossie(raw, workspace_id=latest["workspace_id"], mode="replace")
    assert recovered["extension_v4"]["display_names"][metric_id] == "组件总数"
    assert (
        write(
            client, [dict(kind="metric", id=metric_id, values={"datatype": "Integer"})]
        ).status_code
        == 200
    )
    assert (
        write(
            client, [dict(kind="metric", id=metric_id, unset_fields=["datatype"])]
        ).status_code
        == 200
    )
    assert (
        write(
            client,
            [
                dict(kind="metric", operation="delete", id=metric_id),
                dict(kind="dataset_relationship", operation="delete", id=rel_id),
            ],
        ).status_code
        == 200
    )
    _, latest = exported(client)
    assert metric_id not in latest["extension_v4"]["display_names"]
    assert not any(r["id"] == rel_id for r in latest["dataset_relationships"])


def test_create_model_and_dataset_atomically(editing_client):
    client = editing_client
    model_id, ds_id = str(uuid4()), str(uuid4())
    result = write(
        client,
        [
            dict(
                kind="semantic_model",
                operation="create",
                id=model_id,
                values={
                    "name": "new_model",
                    "custom_extensions": [
                        {
                            "vendor_name": "ONTOFOUNDRY",
                            "data": '{"connection_alias":"test_query"}',
                        }
                    ],
                },
            ),
            dict(
                kind="dataset",
                operation="create",
                id=ds_id,
                parent_id=model_id,
                values={"name": "data", "source": "public.data"},
            ),
        ],
    )
    assert result.status_code == 200, result.text
    assert current(client)["items"][0]["connection_alias"] == "test_query"
    assert (
        write(
            client, [dict(kind="semantic_model", operation="delete", id=model_id)]
        ).json()["error"]["code"]
        == "SEMANTIC_ELEMENT_REFERENCED"
    )
    assert (
        write(
            client,
            [
                dict(kind="dataset", operation="delete", id=ds_id),
                dict(kind="semantic_model", operation="delete", id=model_id),
            ],
        ).status_code
        == 200
    )
    exported(client)


def test_nary_roles_order_names_and_verbalization_save(editing_client):
    from test_element_save import submit

    client = editing_client
    source, draft, _ = publish(client, "account-model-v2")
    link = next(relation for relation in draft["link_types"] if len(relation["roles"]) >= 2)
    original = deepcopy(link)
    link["roles"].reverse()
    for index, role in enumerate(link["roles"]):
        role["position"] = index
    result = submit(client, draft, kind="link_type", target_id=link["id"])
    assert result.status_code == 200, result.text
    _, latest = exported(client)
    saved = next(
        relation for relation in latest["link_types"] if relation["id"] == link["id"]
    )
    assert [r["id"] for r in saved["roles"]] == [r["id"] for r in link["roles"]]
    assert saved["verbalizes"] == original["verbalizes"]
    assert all(r["name"] is None for r in saved["roles"])
    concept = next(
        c
        for c in latest["object_types"] + latest["value_types"]
        if c["id"] == saved["roles"][0]["concept"]["ref"]
    )
    saved["roles"][0]["name"] = "participant"
    saved["roles"][0]["native_presence"] = [*saved["roles"][0]["native_presence"], "name"]
    saved["verbalizes"] = [
        v.replace(
            "{" + concept["concept"] + "}", "{" + concept["concept"] + ":participant}"
        )
        for v in saved["verbalizes"]
    ]
    assert submit(client, latest, kind="link_type", target_id=link["id"]).status_code == 200
    output, latest = exported(client)
    assert output["ontology"][0]["concept"] == source["ontology"][0]["concept"]
    bad = next(
        relation for relation in latest["link_types"] if relation["id"] == link["id"]
    )
    bad["verbalizes"] = ["{unknown_concept} 无效占位符"]
    bad["native_presence"] = list(dict.fromkeys([*bad["native_presence"], "verbalizes"]))
    version = current(client)["current_version_id"]
    assert submit(client, latest, kind="link_type", target_id=link["id"]).status_code == 422
    assert current(client)["current_version_id"] == version


def test_element_native_mapping_edit_is_scoped(editing_client):
    client = editing_client
    source, draft, _ = publish(client, "architecture-governance")
    cm = current(client)["items"][0]["concept_mappings"][0]
    nodes = [{k: v for k, v in n.items() if k != "concept_mapping_id"} for n in cm["nodes"]]
    nodes.append(
        dict(
            id=str(uuid4()),
            parent_id=None,
            slot="object_mappings",
            kind="object",
            expression="component_snapshot.component_name_cn",
        )
    )
    session = create_session(client)
    response = client.post(
        ROOT + "/element-saves",
        json={
            "target_kind": cm["concept_id"]["kind"],
            "target_id": cm["concept_id"]["ref"],
            "draft": session["draft"],
            "semantic_changes": [change("concept_mapping", cm, nodes=nodes)],
            "expected_current_version_id": current(client)["current_version_id"],
            "session_id": session["id"],
            "expected_session_revision": session["revision"],
        },
    )
    assert response.status_code == 200, response.text
    output, latest = exported(client)
    assert (
        len(output["ontology_mappings"][0]["concept_mappings"][0]["object_mappings"]) == 2
    )
    assert output["ontology"] == source["ontology"]
    other = next(
        c
        for c in latest["concept_mappings"]
        if c["concept_id"]["ref"] != cm["concept_id"]["ref"]
    )
    response = client.post(
        ROOT + "/element-saves",
        json={
            "target_kind": cm["concept_id"]["kind"],
            "target_id": cm["concept_id"]["ref"],
            "draft": latest,
            "semantic_changes": [change("concept_mapping", other, operation="delete")],
            "expected_current_version_id": current(client)["current_version_id"],
        },
    )
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "ELEMENT_SCOPE_INVALID"
    )


def test_preview_uses_same_scope_as_save_and_is_pure(editing_client):
    client = editing_client
    _, _, version = publish(client, "architecture-governance")
    session = create_session(client)
    pending = deepcopy(session["draft"])
    pending["object_types"][0]["description"] = "另一个元素的未处理修改"
    session = save(client, session, pending).json()
    selected = session["draft"]["dataset_fields"][0]
    body = {
        "expected_current_version_id": version,
        "session_id": session["id"],
        "expected_session_revision": session["revision"],
        "changes": [change("dataset_field", selected, {"name": "preview_name"})],
    }
    result = client.post(ROOT + "/semantic-change-preview", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["references"] and result.json()["validation"]["publishable"]
    assert current(client)["current_version_id"] == version
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == session["revision"]
    )
    body["changes"] = [
        dict(kind="dataset", id=session["draft"]["datasets"][0]["id"], operation="delete")
    ]
    result = client.post(ROOT + "/semantic-change-preview", json=body)
    assert result.status_code == 422 and result.json()["error"]["references"]


def test_element_save_supports_unary_and_optional_role_names(editing_client):
    from test_element_save import submit

    client = editing_client
    _, draft, _ = publish(client, "account-model-v2")
    template = deepcopy(
        next(relation for relation in draft["link_types"] if len(relation["roles"]) >= 2)
    )
    owner = next(
        c
        for c in draft["object_types"] + draft["value_types"]
        if c["id"] == template["owner_ref"]["ref"]
    )
    template.update(
        id=str(uuid4()),
        name="active",
        technical_name="active",
        identifier=False,
        roles=[],
        position=None,
        requires=[],
        derived_by=[],
        verbalizes=["{" + owner["concept"] + "} 被标记为活跃"],
        native_presence=["verbalizes"],
        origin="platform",
    )
    draft["link_types"].append(template)
    result = submit(client, draft, kind="link_type", target_id=template["id"])
    assert result.status_code == 200, result.text
    _, latest = exported(client)
    saved = next(r for r in latest["link_types"] if r["id"] == template["id"])
    assert saved["roles"] == []


def test_configured_preview_reason_and_quoted_dataset_references(
    editing_client, monkeypatch
):
    from ontofoundry_api.db_models import ConnectionRecord

    client = editing_client
    _, draft, _ = publish(client, "architecture-governance")
    model = current(client)["items"][0]
    with client.app.state.session_factory() as db:
        db.add(
            ConnectionRecord(
                id=str(uuid4()),
                workspace_id=draft["workspace_id"],
                name=model["connection_alias"],
                kind="postgresql",
                config_json={},
                secret_encrypted="never-used-by-preview",
            )
        )
        db.commit()

    def forbidden(*args, **kwargs):
        pytest.fail("compile-only preview must never open the configured connection")

    monkeypatch.setattr("ontofoundry_api.api.connections.connect_readonly", forbidden)
    metric = next(m for m in draft["metrics"] if m["name"] == "core_service_count")
    result = write(
        client,
        [
            change(
                "metric",
                metric,
                {
                    "expression": {
                        "dialects": [
                            {
                                "dialect": "ANSI_SQL",
                                "expression": 'COUNT("component_snapshot"."component_name")',
                            }
                        ]
                    }
                },
            )
        ],
    )
    assert result.status_code == 200, result.text
    model = current(client)["items"][0]
    item = next(m for m in model["metrics"] if m["id"] == metric["id"])
    dataset = next(d for d in model["datasets"] if d["name"] == "component_snapshot")
    assert metric["id"] in dataset["metrics"] and item["concepts"]
    result = client.post(
        ROOT + f"/metrics/{metric['id']}/sql-preview",
        json={
            "expected_current_version_id": current(client)["current_version_id"],
            "as_of": "2026-10-08",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["executable"] is True and result.json()["reason"] is None
    assert result.json()["executed"] is False and '"public"' in result.json()["sql"]


def test_value_concept_owned_property_is_editable(editing_client):
    from test_element_save import submit

    client = editing_client

    def add_value(snapshot):
        snapshot["value_types"].append(
            dict(
                id=str(uuid4()),
                name="UnitValue",
                technical_name="UnitValue",
                concept="UnitValue",
                extends=[{"kind": "builtin", "ref": "String"}],
                origin="platform",
                native_presence=["extends"],
            )
        )

    _, draft, _ = publish(client, "account-model-v2", mutate=add_value)
    value = draft["value_types"][0]
    prop = dict(
        id=str(uuid4()),
        name="unit",
        technical_name="unit",
        owner_ref={"kind": "value_type", "ref": value["id"]},
        roles=[dict(id=str(uuid4()), concept={"kind": "builtin", "ref": "String"})],
        origin="platform",
        native_presence=[],
        value_kind="string",
        required=False,
        identifier=False,
    )
    draft["properties"].append(prop)
    result = submit(client, draft, kind="value_type", target_id=value["id"])
    assert result.status_code == 200, result.text
    _, latest = exported(client)
    saved = next(p for p in latest["properties"] if p["id"] == prop["id"])
    assert saved["owner_ref"] == {"kind": "value_type", "ref": value["id"]}
