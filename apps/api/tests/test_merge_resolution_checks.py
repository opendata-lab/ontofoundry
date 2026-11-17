"""Values typed while resolving a merge go through the accept checks (§4.3)."""

from copy import deepcopy
from uuid import uuid4

import pytest
from core1_fixtures import example_draft_json

from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.sessions import _check_custom_resolutions


def test_a_custom_value_that_leaves_a_bound_object_incomplete_is_refused():
    draft = example_draft_json("01-basic-sales")
    merged = deepcopy(draft)
    customer = next(o for o in merged["object_types"] if o["name"] == "customer")
    prop = {"id": str(uuid4()), "owner_type_id": customer["id"], "name": "vip_level", "value_kind": "string"}
    merged["properties"].append(prop)
    with pytest.raises(ServiceError) as error:
        _check_custom_resolutions(draft, merged, {("property", prop["id"])})
    assert error.value.code == "ACCEPT_CHECK_FAILED"


def test_only_the_custom_elements_become_items():
    draft = example_draft_json("01-basic-sales")
    merged = deepcopy(draft)
    merged["object_types"][0]["description"] = "人工合并描述"
    merged["object_types"][1]["description"] = "来自最新版本"
    items = _check_custom_resolutions(draft, merged, {("object_type", merged["object_types"][0]["id"])})
    assert [(i.target_kind, i.target_id, i.operation) for i in items] == [
        ("object_type", merged["object_types"][0]["id"], "update"),
    ]
