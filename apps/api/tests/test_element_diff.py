"""Review labels derive document titles without changing persisted facts."""

from copy import deepcopy
from uuid import uuid4

import pytest

from ontofoundry_api.services.element_diff import element_changes, element_label


def fact_draft():
    obj, title, identifier, lan, zhou, link = [str(uuid4()) for _ in range(6)]
    return {
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


def test_instances_are_absent_from_version_differences():
    draft = fact_draft()
    blank = deepcopy(draft)
    blank["material_objects"], blank["material_links"] = [], []
    assert element_changes(blank, draft) == []


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
    elements = {e["id"]: (k, e) for k, c in [("object_type", "object_types"), ("property", "properties"), ("material_object", "material_objects")] for e in draft[c]}
    assert element_label("material_object", fact, elements) == expected
