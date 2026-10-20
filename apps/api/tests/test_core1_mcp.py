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


def test_example06_physical_projection_carries_membership_and_local_inherited_links(client):
    from pr23_fixtures import example_session

    from ontofoundry_api.services.physical_projection import EffectiveBindingRead

    session = example_session(client, "06-inheritance", published=True)
    draft = session["draft"]
    objects = {o["technical_name"]: o for o in draft["object_types"]}
    responsible = next(
        relation
        for relation in draft["link_types"]
        if relation["name"] == "responsible_party"
    )
    detail = call(
        client,
        "get_ontology",
        {
            "ids": [objects[n]["id"] for n in ("person", "device", "vehicle", "asset")],
            "include": ["physical", "adjacency"],
            "limit": 100,
        },
    )["structuredContent"]
    elements = {e["technical_name"]: e for e in detail["elements"]}
    person = elements["person"]
    binding = person["effective_bindings"]["items"][0]
    assert binding["type_id"] == objects["person"]["id"]
    assert [m["membership_source_id"] for m in binding["memberships"]] == [
        None,
        "extension",
    ]
    assert binding["memberships"][1]["binding_mode"] == "shared_parent"
    assert binding["fields"]["id_card_no"]["source_id"] == "extension"
    assert binding["fields"]["party_no"]["source_id"] == "main"
    assert {d["table_name"] for d in person["datasets"]["items"]} == {
        "parties",
        "person_extensions",
    }
    for name in ("device", "vehicle"):
        element = elements[name]
        binding = element["effective_bindings"]["items"][0]
        assert binding["type_id"] == objects[name]["id"]
        effective = next(
            relation
            for relation in binding["links"]
            if relation["link_type_id"] == responsible["id"]
        )
        mapping = next(m for m in draft["mappings"] if m["type_id"] == objects[name]["id"])
        assert (
            effective["data_join"] == mapping["inherited_link_bindings"][responsible["id"]]
        )
        link = next(
            relation
            for relation in element["links"]["items"]
            if relation["id"] == responsible["id"]
        )
        assert (
            link["data_join"] == effective["data_join"]
            and link["inherited_from"] == objects["asset"]["id"]
        )
    asset = elements["asset"]
    assert {b["type_id"] for b in asset["effective_bindings"]["items"]} == {
        objects[n]["id"] for n in ("device", "vehicle")
    }
    assert {d["table_name"] for d in asset["datasets"]["items"]} == {"devices", "vehicles"}
    for element in elements.values():
        for binding in element["effective_bindings"]["items"]:
            EffectiveBindingRead.model_validate(binding)
    args = {"ids": [objects["asset"]["id"]], "include": ["physical"], "limit": 1}
    first = call(client, "get_ontology", args)["structuredContent"]["elements"][0][
        "effective_bindings"
    ]
    assert first["total"] == 2 and first["next_cursor"]
    second = call(client, "get_ontology", {**args, "cursor": first["next_cursor"]})[
        "structuredContent"
    ]["elements"][0]["effective_bindings"]
    assert second["items"][0]["type_id"] != first["items"][0]["type_id"]
    assert second["next_cursor"] is None


def test_metric_and_mapping_table_physical_projection_includes_datasets(client):
    from pr23_fixtures import example_session

    session = example_session(client, "13-dataset-metrics", published=True)
    ratio = next(m for m in session["draft"]["metrics"] if m["kind"] == "ratio")
    element = call(client, "get_ontology", {"ids": [ratio["id"]], "include": ["physical"]})[
        "structuredContent"
    ]["elements"][0]
    assert element["datasets"]["total"] == 1
    dataset = element["datasets"]["items"][0]
    assert dataset["id"] == element["dataset_id"] == session["draft"]["datasets"][0]["id"]
    assert dataset["table_name"] == "code_lines_daily"
    assert {c["name"] for c in dataset["columns"]} == {"repo", "stat_date", "commit_count"}
    assert element["components"]["numerator"]["id"] == ratio["numerator_id"]
    assert element["components"]["denominator"]["id"] == ratio["denominator_id"]
    session = example_session(client, "02-many-to-many", published=True)
    link = next(
        relation
        for relation in session["draft"]["link_types"]
        if relation["name"] == "courses"
    )
    element = call(client, "get_ontology", {"ids": [link["id"]], "include": ["physical"]})[
        "structuredContent"
    ]["elements"][0]
    assert link["data_join"]["dataset_id"] in {
        d["id"] for d in element["datasets"]["items"]
    }
    assert {d["table_name"] for d in element["datasets"]["items"]} == {
        "students",
        "courses",
        "enrollments",
    }


def test_physical_projection_keeps_each_source_snapshot_declaration(client):
    from pr23_fixtures import example_session

    session = example_session(client, "12-snapshot-and-trends", published=True)
    component = next(
        o for o in session["draft"]["object_types"] if o["technical_name"] == "component"
    )
    element = call(
        client, "get_ontology", {"ids": [component["id"]], "include": ["physical"]}
    )["structuredContent"]["elements"][0]
    sources = element["effective_bindings"]["items"][0]["sources"]
    datasets = {d["id"]: d for d in element["datasets"]["items"]}
    assert len(sources) == 2
    assert {s["dataset_id"] for s in sources} == set(datasets)
    assert all(
        datasets[s["dataset_id"]]["snapshot_date_column"] == "snapshot_date"
        for s in sources
    )


def test_relationship_status_and_self_adjacency_use_shared_projection(client):
    from core1_fixtures import example_draft

    s = create_session(client)
    draft = example_draft("05-self-and-parallel-links").model_dump(mode="json")
    draft["workspace_id"] = s["workspace_id"]
    draft["mappings"] = []
    link = next(
        link
        for link in draft["link_types"]
        if link["source_type_id"] == link["target_type_id"]
    )
    assert link["data_join"] is not None
    response = publish(client, save(client, s, draft).json())
    assert response.status_code == 200, response.text
    detail = call(
        client,
        "get_ontology",
        {
            "ids": [link["id"], link["source_type_id"]],
            "include": ["semantic", "physical", "adjacency"],
        },
    )["structuredContent"]
    relationship = next(e for e in detail["elements"] if e["kind"] == "link_type")
    assert relationship["binding_status"] == "unbound"
    assert relationship["technical_name"] == relationship["definition"]["name"]
    assert "technical_name" not in relationship["definition"]
    obj = next(e for e in detail["elements"] if e["kind"] == "object_type")
    views = [v for v in obj["links"]["items"] if v["id"] == link["id"]]
    assert [v["direction"] for v in views] == ["forward", "reverse"]
    assert all(v["binding_status"] == "unbound" for v in views)
