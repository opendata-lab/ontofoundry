"""Local API/SQLite contracts; no source database or LLM integration is claimed."""

from copy import deepcopy

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
    # Only the disposable fixture database is changed; exercise response projection,
    # including totals larger than the preview, independently of publishing fixtures.
    with client.app.state.session_factory() as db:
        version = current_version(db, str(DEMO_WORKSPACE_ID))
        snapshot = deepcopy(version.snapshot_json)
        type_id = snapshot["object_types"][0]["id"]
        relation_id = snapshot["link_types"][0]["id"]
        evidence = [{"material_id": "private-material", "quote": "private-quote"}]
        snapshot["objects"] = [
            {
                "id": f"o{i}",
                "name": f"private-object-{i}",
                "type_id": type_id,
                "values": {"secret": "private-value"},
                "evidence": evidence,
            }
            for i in range(30)
        ]
        snapshot["links"] = [
            {
                "id": f"l{i}",
                "type_id": relation_id,
                "source_id": "o0",
                "target_id": f"o{i % 30}",
                "evidence": evidence,
            }
            for i in range(90)
        ]
        snapshot["mappings"] = [
            {
                "id": f"m{i}",
                "type_id": type_id,
                "table_name": f"private-table-{i}",
                "connection_id": "private-connection",
                "fields": {"name": "private-column"},
            }
            for i in range(30)
        ]
        snapshot["link_types"][0]["data_join"] = {
            "source_column": "private-column",
            "target_column": "private-column",
        }
        version.snapshot_json = snapshot
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
