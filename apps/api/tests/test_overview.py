"""Overview uses the published snapshot and applies permission projections."""

from test_modeling import ROOT, create_session, save


def test_overview_ignores_unpublished_changes(client):
    before = client.get(ROOT + "/overview").json()
    assert before["version"]["counts"]["metrics"] == 1
    assert before["details"]["object_count"] == 1
    session = create_session(client)
    session["draft"]["object_types"][0]["display_name"] = "草稿客户"
    assert save(client, session, session["draft"]).status_code == 200
    assert client.get(ROOT + "/overview").json() == before


def test_unpublished_overview_and_empty_session(client):
    wid = client.post(
        "/api/v1/workspaces", json={"name": "月湾测试", "slug": "moonbay"}
    ).json()["id"]
    assert client.get(f"/api/v1/workspaces/{wid}/overview").json() == {
        "version": None,
        "graph": None,
        "details": None,
    }
    session = client.post(f"/api/v1/workspaces/{wid}/sessions", json={}).json()
    assert session["draft"]["schema_version"] == "core-1"
    assert all(
        session["draft"][c] == []
        for c in (
            "object_types",
            "properties",
            "link_types",
            "rules",
            "metrics",
            "datasets",
            "mappings",
                )
    )
