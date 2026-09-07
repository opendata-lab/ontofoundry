from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID


def test_health_and_current_user(client):
    assert client.get("/healthz").json()["status"] == "ok"
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["display_name"] == "admin"


def test_workspace_directory_exposes_published_summary(client):
    response = client.get("/api/v1/workspaces")

    assert response.status_code == 200
    workspace = response.json()["items"][0]
    assert workspace["id"] == str(DEMO_WORKSPACE_ID)
    assert workspace["role"] == "admin"
    assert workspace["current_version"] == 1
    assert workspace["object_type_count"] == 5
    assert workspace["link_type_count"] == 4


def test_published_ontology_query_and_export_share_version(client):
    workspace_id = str(DEMO_WORKSPACE_ID)
    version = client.get(f"/api/v1/ontology/workspaces/{workspace_id}/version").json()
    objects = client.get(
        f"/api/v1/ontology/workspaces/{workspace_id}/types",
        params={"kind": "object_type"},
    ).json()
    graph = client.get(
        f"/api/v1/ontology/workspaces/{workspace_id}/type-graph/neighborhood"
    ).json()
    export = client.get(
        f"/api/v1/ontology/workspaces/{workspace_id}/versions/"
        f"{version['version_id']}/export"
    )

    assert version["validation"]["publishable"] is True
    assert version["version_sha256"] == objects["version_sha256"]
    assert version["version_sha256"] == graph["version_sha256"]
    assert len(objects["items"]) == 5
    assert any(item["technical_name"] == "material" for item in objects["items"])
    assert {node["kind"] for node in graph["nodes"]} == {
        "object_type",
        "value_type",
    }
    assert {edge["kind"] for edge in graph["edges"]} == {
        "attribute",
        "link_type",
    }
    assert export.status_code == 200
    assert export.json()["version"] == "0.2.0.dev0"


def test_type_neighborhood_limits_result(client):
    workspace_id = str(DEMO_WORKSPACE_ID)
    objects = client.get(
        f"/api/v1/ontology/workspaces/{workspace_id}/types",
        params={"kind": "object_type", "q": "物料"},
    ).json()["items"]
    material_id = objects[0]["id"]

    response = client.get(
        f"/api/v1/ontology/workspaces/{workspace_id}/type-graph/neighborhood",
        params={"focus_id": material_id, "depth": 1},
    )

    assert response.status_code == 200
    result = response.json()
    assert material_id in {node["id"] for node in result["nodes"]}
    assert len(result["nodes"]) < 16


def test_workspace_names_are_unique_case_insensitively(client):
    response = client.post(
        "/api/v1/workspaces",
        json={
            "name": "制造供应链",
            "slug": "another-space",
            "description": "",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
