"""T7: element-level MCP tools, permission trimming and the pinned run view."""

from uuid import uuid4

from test_modeling import ONTOLOGY, ROOT, create_session, mcp_request, save
from test_t2_pinned_context import start_run
from test_t6_publish_preview import preview, publish

from ontofoundry_api.domain.canonical import snapshot_sha256


def call(client, tool, headers=None, **arguments):
    response = mcp_request(client, "tools/call", {"name": tool, "arguments": arguments}, headers=headers)
    body = response.json()
    assert "result" in body, body
    return body["result"]["structuredContent"]


def with_instance(client):
    """Publish a version that has a material instance with evidence."""
    session = create_session(client)
    supplier = session["draft"]["object_types"][0]
    required = {
        p["technical_name"]: "S1"
        for p in session["draft"]["properties"]
        if p["owner_type_id"] == supplier["id"] and (p["required"] or p["identifier"])
    }
    session["draft"]["material_objects"] = [
        {
            "id": str(uuid4()),
            "type_id": supplier["id"],
            "name": "供应商甲",
            "values": required,
            "evidence": [
                {
                    "kind": "manual",
                    "id": str(uuid4()),
                    "note": "敏感的人工说明",
                    "created_by": "x",
                    "created_at": "2026-09-30T00:00:00Z",
                }
            ],
        }
    ]
    session = save(client, session, session["draft"]).json()
    assert publish(client, session, preview(client, session).json()).status_code == 200


def test_manifest_lists_and_looks_up_elements(client):
    manifest = call(client, "get_ontology_manifest")
    version = client.get(ONTOLOGY + "/version").json()
    assert manifest["version_id"] == version["version_id"]
    assert manifest["normalized_snapshot_sha256"] == version["normalized_snapshot_sha256"]
    assert manifest["counts"]["object_type"] == 5 and manifest["counts"]["property"] == 12

    first = call(client, "list_ontology_elements", kind="property", limit=5)
    assert len(first["items"]) == 5 and first["next_cursor"]
    rest = call(client, "list_ontology_elements", kind="property", limit=50, cursor=first["next_cursor"])
    ids = [i["id"] for i in first["items"] + rest["items"]]
    assert len(ids) == len(set(ids)) == 12 and rest["next_cursor"] is None

    found = call(client, "get_ontology_elements", element_ids=[ids[0], "nope"])
    assert [f["kind"] for f in found["items"]] == ["property"]
    assert found["missing"] == ["nope"]


def test_ontology_only_tokens_see_no_instances_mappings_or_evidence(client):
    with_instance(client)
    member = call(client, "get_ontology_manifest")
    assert member["counts"]["material_object"] == 1
    token = client.post(
        ROOT + "/service-tokens", json={"name": "reader", "scopes": ["ontology:read"]}
    ).json()["token"]
    headers = {"Authorization": "Bearer " + token}
    manifest = call(client, "get_ontology_manifest", headers=headers)
    assert "material_object" not in manifest["counts"] and "mapping" not in manifest["counts"]
    refused = mcp_request(
        client,
        "tools/call",
        {"name": "list_ontology_elements", "arguments": {"kind": "material_object"}},
        headers=headers,
    ).json()
    assert "error" in refused or refused["result"].get("isError")
    types = call(client, "list_ontology_elements", headers=headers, kind="object_type")
    assert all(item["evidence"] == [] for item in types["items"])


def test_a_run_lists_elements_of_its_pinned_version_only(client):
    pinned = create_session(client)
    other = create_session(client)
    other["draft"]["object_types"][0]["description"] = "新版本"
    other = save(client, other, other["draft"]).json()
    assert publish(client, other, preview(client, other).json()).status_code == 200

    credential = start_run(client, pinned)
    headers = {"Authorization": "Bearer " + credential}
    manifest = call(client, "get_ontology_manifest", headers=headers)
    assert manifest["version_id"] == pinned["base_version_id"]
    assert manifest["normalized_snapshot_sha256"] == pinned["base_version_sha256"]
    types = call(client, "list_ontology_elements", headers=headers, kind="object_type")
    assert "新版本" not in {t["description"] for t in types["items"]}
    assert snapshot_sha256(pinned["draft"]) == pinned["base_version_sha256"]
