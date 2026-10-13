"""Concept names use Ossie descriptions; relationships retain their own names."""
from copy import deepcopy
from uuid import uuid4

import pytest

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.extensions import reverse_export_edits
from ontofoundry_api.ossie.importer import import_ossie


def document():
    return {
        "version": "0.2.0.dev0",
        "name": "library",
        "ontology": [
            {
                "concept": "Borrower",
                "type": "EntityType",
                "description": "借阅人",
                "relationships": [
                    {"name": "code", "description": "借阅证号", "roles": [{"concept": "Code"}], "verbalizes": ["{Borrower}的证号是{Code}"]},
                    {"name": "borrows", "description": "借阅图书", "roles": [{"concept": "Book"}], "verbalizes": ["{Borrower}借阅{Book}"]},
                ],
            },
            {"concept": "Book", "type": "EntityType", "description": "图书"},
            {"concept": "Code", "type": "ValueType", "description": "证号", "extends": ["String"]},
        ],
    }


def parse(source, workspace_id=None, base=None):
    payload, report = import_ossie(source, workspace_id=workspace_id or uuid4(), base=base, mode="merge" if base else "replace")
    assert not report["skipped"]
    return OntologyDraft.model_validate(payload), report


def export(draft):
    result = compile_ossie(draft, ontology_name="ignored", ontology_description="ignored")
    assert validate_ossie(result)["publishable"]
    return result


def test_concept_description_populates_name_and_description_without_renaming_relationships():
    source = document()
    before = deepcopy(source)
    draft, _ = parse(source)
    for group, expected in ((draft.object_types, ["借阅人", "图书"]), (draft.value_types, ["证号"])):
        assert [item.name for item in group] == expected
        assert [item.description for item in group] == expected
    assert draft.object_types[0].concept == draft.object_types[0].technical_name == "Borrower"
    assert draft.properties[0].technical_name == "code"
    assert draft.link_types[0].technical_name == "borrows"
    assert draft.properties[0].name == "code" and draft.properties[0].description == "借阅证号"
    assert draft.link_types[0].name == "borrows" and draft.link_types[0].description == "借阅图书"
    assert source == before
    assert reverse_export_edits(export(draft)) == source


def test_export_uses_edited_name_without_changing_technical_references():
    draft, _ = parse(document())
    draft.object_types[0].name = "读者"
    draft.object_types[0].description = "用于管理借阅资格的详细说明"
    draft.value_types[0].name = "证件编号"
    draft.properties[0].name = "读者编号"
    draft.link_types[0].name = "借出图书"
    result = export(draft)
    borrower, book, code = result["ontology"]
    assert borrower["concept"] == "Borrower"
    assert borrower["description"] == "读者"
    assert borrower["relationships"][0]["name"] == "code"
    assert borrower["relationships"][0]["description"] == "借阅证号"
    assert borrower["relationships"][0]["roles"] == [{"concept": "Code"}]
    assert borrower["relationships"][1]["description"] == "借阅图书"
    assert borrower["relationships"][1]["roles"] == [{"concept": "Book"}]
    assert code["description"] == "证件编号"
    assert book["concept"] == "Book"
    second, _ = parse(result, draft.workspace_id)
    assert second.object_types[0].name == second.object_types[0].description == "读者"
    assert second.properties[0].name == "读者编号" and second.properties[0].description == "借阅证号"
    assert second.link_types[0].name == "借出图书" and second.link_types[0].description == "借阅图书"
    assert export(second) == result
    _, report = parse(result, draft.workspace_id, second.model_dump(mode="json"))
    assert all(count == 0 for count in report["counts"].values())


@pytest.mark.parametrize("description", [None, "", "  "])
def test_missing_or_empty_description_falls_back_without_adding_source_text(description):
    source = {"version": "0.2.0.dev0", "name": "library", "ontology": [{"concept": "Book", "type": "EntityType"}]}
    source["ontology"][0]["relationships"] = [
        {"name": "code", "roles": [{"concept": "String"}], "verbalizes": ["{Book}的编号是{String}"]},
        {"name": "related_book", "roles": [{"concept": "Book", "name": "related"}], "verbalizes": ["{Book}关联{Book:related}"]},
    ]
    if description is not None:
        source["ontology"][0]["description"] = description
        for relationship in source["ontology"][0]["relationships"]:
            relationship["description"] = description
    draft, _ = parse(source)
    assert draft.object_types[0].name == draft.object_types[0].technical_name == "Book"
    assert draft.properties[0].name == draft.properties[0].technical_name == "code"
    assert draft.link_types[0].name == draft.link_types[0].technical_name == "related_book"
    assert reverse_export_edits(export(draft)) == source
    draft.object_types[0].name = "图书"
    assert export(draft)["ontology"][0]["description"] == "图书"


def test_source_description_takes_precedence_over_old_display_name_extension():
    source = document()
    source["ai_context"] = {"ontofoundry": {"version": "3", "display_names": {"Borrower": "旧名称"}}}
    draft, _ = parse(source)
    assert draft.object_types[0].name == "借阅人"
    assert reverse_export_edits(export(draft)) == source


@pytest.mark.parametrize("client_fixture", ["client", "pg_client"])
def test_import_publish_export_and_repeat_import_persist_names(request, client_fixture):
    client = request.getfixturevalue(client_fixture)
    workspace = client.post("/api/v1/workspaces", json={"name": "图书模型", "slug": "library"}).json()
    root = "/api/v1/workspaces/" + workspace["id"]
    imported = client.post(root + "/imports/ossie", json={"document": document(), "mode": "replace"})
    assert imported.status_code == 201, imported.text
    session = imported.json()
    assert session["draft"]["object_types"][0]["name"] == "借阅人"
    assert session["draft"]["properties"][0]["name"] == "code"
    assert session["draft"]["link_types"][0]["name"] == "borrows"
    preview = client.post(root + f"/sessions/{session['id']}/preview",
                          json={"expected_session_revision": session["revision"]}).json()
    published = client.post(root + f"/sessions/{session['id']}/publish", json={
        "expected_session_revision": session["revision"],
        "expected_current_version_id": preview["current_version_id"],
        "expected_merged_snapshot_sha256": preview["merged_snapshot_sha256"],
    })
    assert published.status_code == 200, published.text
    version_id = published.json()["version"]["version_id"]
    snapshot = client.get(root + "/published-snapshot").json()
    assert snapshot["object_types"][0]["name"] == snapshot["object_types"][0]["description"] == "借阅人"
    exported = client.get(f"/api/v1/ontology/workspaces/{workspace['id']}/versions/{version_id}/export").json()
    assert exported["ontology"][0]["concept"] == "Borrower"
    assert exported["ontology"][0]["description"] == "借阅人"
    repeat = client.post(root + "/imports/ossie", json={"document": exported, "mode": "merge"})
    assert repeat.status_code == 201, repeat.text
    assert all(count == 0 for count in repeat.json()["import_report"]["counts"].values())
