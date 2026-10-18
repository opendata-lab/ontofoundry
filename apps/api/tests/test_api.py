"""Core REST read resources and retired endpoint boundaries."""

from test_modeling import ONTOLOGY, ROOT


def test_health_and_current_user(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/api/v1/auth/me").json()["display_name"] == "admin"


def test_resources_and_graph_share_version(client):
    version = client.get(ONTOLOGY + "/version").json()
    resources = client.get(ONTOLOGY + "/types").json()
    graph = client.get(ONTOLOGY + "/type-graph/neighborhood").json()
    assert (
        version["version_sha256"] == resources["version_sha256"] == graph["version_sha256"]
    )
    assert {r["kind"] for r in resources["items"]} == {
        "object_type",
        "link_type",
        "metric",
        "dataset",
    }
    assert {n["kind"] for n in graph["nodes"]} == {"object_type"}
    assert {e["kind"] for e in graph["edges"]} == {"link_type"}
    resource = resources["items"][0]
    assert (
        client.get(ONTOLOGY + "/types/" + resource["definition"]["id"]).json()["item"]
        == resource
    )
    assert (
        client.get(ONTOLOGY + f"/versions/{version['version_id']}/export").status_code
        == 404
    )
    assert client.post(ROOT + "/publish", json={}).status_code == 404
    assert client.get(ROOT + "/semantic-models").status_code == 404
    assert client.post(ROOT + "/imports/ossie", json={}).status_code == 404


def test_workspace_names_unique(client):
    response = client.post(
        "/api/v1/workspaces", json={"name": "星港销售", "slug": "another-space"}
    )
    assert response.status_code == 409
