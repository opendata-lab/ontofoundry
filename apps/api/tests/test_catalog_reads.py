"""Catalog and focused reads preserve legacy resources and authorization boundaries."""

from uuid import uuid4

import jsonschema
from test_modeling import ONTOLOGY, ROOT

from ontofoundry_api.contracts.read_models import read_models_schema


def assert_contract(value, model):
    schema = read_models_schema()
    jsonschema.validate(
        value,
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/" + model,
        },
    )


def test_catalog_is_small_paged_and_bound_to_version_filters_and_permission(
    client, monkeypatch
):
    version = client.get(ONTOLOGY + "/version").json()["version_id"]
    first = client.get(
        ONTOLOGY + "/catalog",
        params={"version_id": version, "kind": "object_type", "limit": 1},
    )
    assert first.status_code == 200, first.text
    data = first.json()
    assert_contract(data, "CatalogPageRead")
    assert len(data["items"]) == 1
    assert "definition" not in data["items"][0]
    assert "model" not in data and "material_objects" not in data
    assert data["next_cursor"]
    second = client.get(
        ONTOLOGY + "/catalog",
        params={
            "version_id": version,
            "kind": "object_type",
            "limit": 1,
            "cursor": data["next_cursor"],
        },
    ).json()
    assert second["items"][0]["id"] != data["items"][0]["id"]
    bad = client.get(
        ONTOLOGY + "/catalog",
        params={"kind": "link_type", "limit": 1, "cursor": data["next_cursor"]},
    )
    assert bad.status_code == 422
    from ontofoundry_api.services import catalog_reads

    monkeypatch.setattr(catalog_reads, "authorization_fingerprint", lambda *args: "changed")
    assert (
        client.get(
            ONTOLOGY + "/catalog",
            params={
                "version_id": version,
                "kind": "object_type",
                "limit": 1,
                "cursor": data["next_cursor"],
            },
        ).status_code
        == 422
    )

    assert (
        client.get(ONTOLOGY + "/catalog", params={"version_id": str(uuid4())}).status_code
        == 404
    )


def test_single_id_and_name_do_not_project_the_whole_space(client, monkeypatch):
    from ontofoundry_api.services import ontology_query as query

    legacy = client.get(ONTOLOGY + "/types").json()
    expected = next(item for item in legacy["items"] if item["kind"] == "object_type")
    original = query.resource_items
    selected = []

    def focus(*args, **kwargs):
        assert kwargs.get("selected") is not None
        selected.append(kwargs["selected"])
        return original(*args, **kwargs)

    monkeypatch.setattr(query, "resource_items", focus)
    for identity in (expected["definition"]["id"], expected["definition"]["name"]):
        actual = client.get(ONTOLOGY + "/types/" + identity)
        assert actual.status_code == 200, actual.text
        assert actual.json()["item"] == expected
    assert all(len(ids) == 1 for ids in selected)


def test_element_projection_is_incomplete_and_documents_are_separate_and_scoped(client):
    snapshot = client.get(ROOT + "/published-snapshot").json()
    target = snapshot["object_types"][0]
    version = client.get(ONTOLOGY + "/version").json()["version_id"]
    path = ONTOLOGY + "/types/" + target["id"]
    response = client.get(
        path + "/presentation", params={"kind": "object_type", "version_id": version}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert_contract(data, "ElementProjectionRead")
    assert data["complete"] is False
    assert "material_objects" not in data["model"]
    assert target in data["model"]["object_types"]
    documents = client.get(
        path + "/document-context", params={"kind": "object_type", "version_id": version}
    )
    assert documents.status_code == 200, documents.text
    assert_contract(documents.json(), "DocumentContextRead")
    assert documents.json()["version_id"] == version
    # A different kind cannot be used to address the same UUID.
    assert (
        client.get(
            path + "/presentation", params={"kind": "dataset", "version_id": version}
        ).status_code
        == 404
    )


def test_mcp_instances_do_not_build_type_resources(client, monkeypatch):
    from ontofoundry_api.services import mcp_ontology

    def forbidden(*args, **kwargs):
        raise AssertionError("instance tool built resource projections")

    monkeypatch.setattr(mcp_ontology, "resource_items", forbidden)
    from test_core1_mcp import call

    assert not call(client, "search_objects", {})["isError"]


def test_inheritance_closure_keeps_effective_fields_links_rules_and_bindings(client):
    from pr23_fixtures import example_session

    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.graph import DraftIndex

    session = example_session(client, "06-inheritance", published=True)
    full = CoreDraft.model_validate(session["draft"])
    full_index = DraftIndex(full)
    for name in ("person", "device", "vehicle", "asset"):
        target = next(obj for obj in full.object_types if obj.name == name)
        response = client.get(
            ONTOLOGY + "/types/" + str(target.id) + "/presentation",
            params={"kind": "object_type"},
        )
        assert response.status_code == 200, response.text
        projection = response.json()["model"]
        partial = DraftIndex(CoreDraft.model_validate(projection))
        assert [p.id for p in partial.effective_properties(target.id)] == [
            p.id for p in full_index.effective_properties(target.id)
        ]
        assert [link.id for link in partial.effective_links(target.id)] == [
            link.id for link in full_index.effective_links(target.id)
        ]
        assert [rule.id for rule in partial.effective_rules(target.id)] == [
            rule.id for rule in full_index.effective_rules(target.id)
        ]
