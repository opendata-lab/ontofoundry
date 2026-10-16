"""Four-tool protocol, search, inherited definitions and signed pagination."""

import json

from test_modeling import ONTOLOGY, create_session, mcp_request, publish, save


def call(client, name, args):
    response = mcp_request(client, "tools/call", {"name": name, "arguments": args})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result


def test_exact_four_tools_and_reject_old_arguments(client):
    result = mcp_request(client, "tools/list").json()["result"]
    assert {t["name"] for t in result["tools"]} == {
        "search_ontology",
        "get_ontology",
        "search_objects",
        "get_object",
    }
    for t in result["tools"]:
        assert "version_id" not in t["inputSchema"]["properties"]
        args = {"version_id": "caller-chosen"}
        if t["name"] == "search_ontology":
            args["query"] = ""
        if t["name"] == "get_object":
            args["id"] = "00000000-0000-4000-8000-000000000001"
        assert call(client, t["name"], args)["isError"]
    assert call(client, "get_ontology", {"ids": []})["isError"]
    assert call(client, "search_objects", {"source": "database"})["isError"]
    assert (
        mcp_request(client, "tools/call", {"name": "query_metric", "arguments": {}}).json()[
            "error"
        ]["code"]
        == -32602
    )


def test_cursor_bound_to_filters_and_new_head(client):
    first = call(client, "get_ontology", {"limit": 1})["structuredContent"]
    assert first["next_cursor"]
    next_page = call(client, "get_ontology", {"limit": 1, "cursor": first["next_cursor"]})[
        "structuredContent"
    ]
    assert next_page["elements"] != first["elements"]
    assert call(
        client,
        "get_ontology",
        {"limit": 1, "kinds": ["object_type"], "cursor": first["next_cursor"]},
    )["isError"]
    s = create_session(client)
    s["draft"]["object_types"][0]["description"] = "新发布"
    assert publish(client, save(client, s, s["draft"]).json()).status_code == 200
    assert (
        call(client, "get_ontology", {"limit": 1, "cursor": first["next_cursor"]})[
            "structuredContent"
        ]["code"]
        == "cursor_invalid"
    )


def test_synonym_and_definition_projection(client):
    s = create_session(client)
    o = s["draft"]["object_types"][0]
    o["synonyms"] = ["购货方"]
    assert publish(client, save(client, s, s["draft"]).json()).status_code == 200
    hits = call(client, "search_ontology", {"query": "购货方"})["structuredContent"]
    assert hits["items"][0]["matched_synonyms"] == ["购货方"]
    detail = call(
        client,
        "get_ontology",
        {"ids": [o["id"]], "include": ["semantic", "physical", "rules", "adjacency"]},
    )["structuredContent"]
    assert detail["elements"][0]["definition"]["synonyms"] == ["购货方"]
    assert "properties" in detail["elements"][0]


def test_protocol_headers_negotiation_and_payload_budget(client):
    assert client.get(ONTOLOGY + "/mcp").status_code == 405
    init = mcp_request(
        client,
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    assert init.json()["result"]["protocolVersion"] == "2025-11-25"
    oversized = client.post(
        ONTOLOGY + "/mcp",
        content=b"x" * 262145,
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert oversized.status_code == 413
    response = call(client, "get_ontology", {"limit": 100})
    assert len(json.dumps(response, ensure_ascii=False).encode()) <= 262144


def test_large_fact_value_is_segmented_and_reassembled(client):
    from uuid import uuid4

    s = create_session(client)
    fact = s["draft"]["material_objects"][0]
    # An untitled long value is large enough to exceed the wire budget by itself.
    s["draft"]["object_types"][0]["title_property_id"] = None
    extra = {
        "id": str(uuid4()),
        "owner_type_id": fact["type_id"],
        "name": "详情",
        "technical_name": "detail",
        "value_kind": "string",
    }
    s["draft"]["properties"].append(extra)
    text = "虚构业务说明" * 20000
    fact["values"]["detail"] = text
    assert publish(client, save(client, s, s["draft"]).json()).status_code == 200
    args = {"id": fact["id"], "include": ["properties"]}
    first = call(client, "get_object", args)["structuredContent"]
    assert len(json.dumps(first, ensure_ascii=False).encode()) < 120000
    segment = next(f for f in first["field_segments"] if f["field"] == "/values/detail")
    result = segment["text"]
    while segment["next_cursor"]:
        page = call(client, "get_object", {**args, "cursor": segment["next_cursor"]})[
            "structuredContent"
        ]
        segment = page["field_segments"][0]
        assert segment["start"] == len(result)
        result += segment["text"]
    assert result == text
