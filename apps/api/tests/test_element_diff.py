"""Review labels derive document titles without changing persisted facts."""

from copy import deepcopy
from uuid import uuid4

import pytest

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.services.element_diff import element_changes


def fact_draft():
    obj, title, identifier, lan, zhou, link = [str(uuid4()) for _ in range(6)]
    return CoreDraft.model_validate(
        {
            "workspace_id": str(uuid4()),
            "object_types": [
                {
                    "id": obj,
                    "display_name": "星港员工",
                    "name": "starport_staff",
                    "title_property_id": title,
                }
            ],
            "properties": [
                {
                    "id": title,
                    "owner_type_id": obj,
                    "display_name": "姓名",
                    "name": "staff_name",
                    "value_kind": "string",
                },
                {
                    "id": identifier,
                    "owner_type_id": obj,
                    "display_name": "编号",
                    "name": "staff_no",
                    "value_kind": "string",
                    "identifier": True,
                    "required": True,
                    "unique": True,
                },
            ],
            "material_objects": [
                {
                    "id": lan,
                    "type_id": obj,
                    "values": {"staff_name": "小岚", "staff_no": "E01"},
                },
                {
                    "id": zhou,
                    "type_id": obj,
                    "values": {"staff_name": "小舟", "staff_no": "E02"},
                },
            ],
            "material_links": [
                {"id": link, "type_id": str(uuid4()), "source_id": lan, "target_id": zhou}
            ],
        }
    ).model_dump(mode="json")


@pytest.mark.parametrize("operation", ["created", "updated", "deleted"])
def test_document_fact_and_link_labels_in_publish_differences(operation):
    draft = fact_draft()
    blank = deepcopy(draft)
    blank["material_objects"], blank["material_links"] = [], []
    if operation == "created":
        before, after = blank, draft
    elif operation == "deleted":
        before, after = draft, blank
    else:
        before, after = deepcopy(draft), draft
        before["material_objects"][0]["values"]["staff_name"] = "原姓名"
        before["material_links"][0]["source_id"] = before["material_objects"][1]["id"]
    original = deepcopy((before, after))
    changes = element_changes(before, after)
    labels = {c["element_id"]: c["label"] for c in changes}
    assert labels[draft["material_objects"][0]["id"]] == "小岚"
    assert labels[draft["material_links"][0]["id"]] == "小岚 → 小舟"
    assert (before, after) == original


@pytest.mark.parametrize("fallback", ["identity", "quote", "uuid"])
def test_document_diff_title_fallbacks(fallback):
    draft = fact_draft()
    fact = draft["material_objects"][0]
    fact["values"].pop("staff_name")
    expected = "E01"
    if fallback != "identity":
        fact["values"].clear()
        expected = fact["id"]
    if fallback == "quote":
        fact["evidence"] = [
            {
                "kind": "material",
                "id": str(uuid4()),
                "material_id": "fictional-note",
                "material_sha256": "a" * 64,
                "locator": {"line_start": 1, "line_end": 1},
                "quote": "星港会议中的员工",
            }
        ]
        expected = "星港会议中的员工"
    before = deepcopy(draft)
    before["material_objects"] = []
    changes = element_changes(before, draft)
    assert next(c["label"] for c in changes if c["element_id"] == fact["id"]) == expected


def test_deleted_fact_keeps_title_when_the_title_property_is_deleted_too():
    before = fact_draft()
    after = deepcopy(before)
    fact = after["material_objects"].pop(0)
    after["object_types"][0]["title_property_id"] = None
    after["properties"] = [p for p in after["properties"] if p["name"] != "staff_name"]
    changes = element_changes(before, after)
    assert next(c["label"] for c in changes if c["element_id"] == fact["id"]) == "小岚"
