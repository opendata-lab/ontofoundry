"""Local API/SQLite contracts; no source database or LLM integration is claimed."""


from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.ontology_query import current_version

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"


def test_overview_uses_one_published_snapshot_and_ignores_session_drafts(client):
    before = client.get(ROOT + "/overview")
    assert before.status_code == 200
    overview = before.json()
    assert overview["graph"]["version_id"] == overview["version"]["version_id"]
    assert overview["graph"]["version_sha256"] == overview["version"]["version_sha256"]
    assert overview["version"]["counts"]["object_types"] == 5
    assert overview["details"]["objects"] == []
    session = client.post(ROOT + "/sessions", json={"title": "未发布修改"}).json()
    session["draft"]["object_types"][0]["name"] = "只在草稿里的名称"
    saved = client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": session["draft"]},
    )
    assert saved.status_code == 200
    assert client.get(ROOT + "/overview").json() == overview


def add_private_test_snapshot(client):
    """A valid native snapshot with bounded private previews, in fixture DB only."""
    from uuid import UUID, uuid4, uuid5

    from ontofoundry_api.domain.models import OntologyDraft
    from ontofoundry_api.domain.snapshot import as_v3_dict
    from ontofoundry_api.ossie.native import compile_native, parse_native

    with client.app.state.session_factory() as db:
        version = current_version(db, str(DEMO_WORKSPACE_ID))
        original = OntologyDraft.model_validate(as_v3_dict(version.snapshot_json))
        document = compile_native(original, 'overview', '')
        document['ontology_mappings'] = [dict(name=f'private-connection-{i}', semantic_model={
            'name': f'model_{i}', 'datasets': [{'name': 'supplier_rows', 'source': f'private-table-{i}',
                                             'primary_key': ['key'], 'fields': []}],
        }, concept_mappings=[{'concept': 'supplier', 'object_mappings': [{'expression': 'supplier_rows.key'}]}]) for i in range(30)]
        snapshot = parse_native(document, str(DEMO_WORKSPACE_ID)).model_dump(mode='json')
        source = next(t for t in snapshot['object_types'] if t['concept'] == 'supplier')
        target = next(t for t in snapshot['object_types'] if t['concept'] == 'material')
        relation = next(r for r in snapshot['link_types'] if r['technical_name'] == 'supplies')
        evidence = [{'kind': 'material', 'id': str(uuid4()), 'material_id': 'private-material',
                     'material_sha256': 'a' * 64, 'locator': {'line_start': 1, 'line_end': 1}, 'quote': 'private-quote'}]
        objects = [dict(id=str(uuid4()), name=f'private-object-{i}', type_id=source['id'] if i == 0 else target['id'],
                        values={'supplier_name' if i == 0 else 'material_name': 'private-value'}, evidence=evidence) for i in range(30)]
        snapshot['material_objects'] = objects
        owner_role = str(uuid5(UUID(relation['id']), 'role:owner'))
        snapshot['material_links'] = [dict(id=str(uuid4()), type_id=relation['id'], source_id=objects[0]['id'],
                                         target_id=objects[i % 29 + 1]['id'], evidence=evidence,
                                         role_values=[{'role_id': owner_role, 'object_id': objects[0]['id']},
                                                      {'role_id': relation['roles'][0]['id'], 'object_id': objects[i % 29 + 1]['id']}]) for i in range(90)]
        version.snapshot_json = OntologyDraft.model_validate(snapshot).model_dump(mode='json')
        db.commit()


def test_member_overview_bounds_previews_and_omits_raw_evidence_and_configuration(client):
    add_private_test_snapshot(client)
    response = client.get(ROOT + "/overview")
    assert response.status_code == 200
    details = response.json()["details"]
    assert details["object_count"] == 30
    assert details["link_count"] == 90
    assert details["evidence_material_count"] == 1
    assert details["mapping_count"] == 30
    assert len(details["objects"]) == len(details["mappings"]) == 24
    assert all(m["state"] == "readonly" and m["reason"] == "multiple_concept_mappings" for m in details["mappings"])
    assert len(details["links"]) == 48
    ids = {o["id"] for o in details["objects"]}
    assert all(
        link["source_id"] in ids and link["target_id"] in ids for link in details["links"]
    )
    for private in (
        "private-quote",
        "private-value",
        "private-column",
        "private-connection",
        "private-material",
    ):
        assert private not in response.text


def test_nonmember_overview_exposes_only_tbox_not_private_counts_or_names(client):
    add_private_test_snapshot(client)
    client.app.dependency_overrides[current_principal] = lambda: Principal(
        "not-a-member", "test:visitor", "visitor", None
    )
    try:
        response = client.get(ROOT + "/overview")
        assert response.status_code == 200
        assert response.json()["details"] is None
        assert response.json()["version"]["counts"]["object_types"] == 5
        assert "private-" not in response.text
    finally:
        client.app.dependency_overrides.clear()


def test_unpublished_workspace_has_no_overview(client):
    workspace = client.post(
        "/api/v1/workspaces", json={"name": "未发布", "slug": "unpublished"}
    ).json()
    assert client.get(f"/api/v1/workspaces/{workspace['id']}/overview").status_code == 404
