"""API setup for result regressions using the shared fictional design examples."""

from core1_fixtures import example_draft_json
from test_modeling import create_session, publish, save


def example_session(client, name, *, published=False):
    session = create_session(client)
    raw = example_draft_json(name)
    raw["workspace_id"] = session["workspace_id"]
    for elements in raw.values():
        if isinstance(elements, list):
            for element in elements:
                if "evidence" in element:
                    element["evidence"] = []
    response = save(client, session, raw)
    assert response.status_code == 200, response.text
    session = response.json()
    if published:
        response = publish(client, session)
        assert response.status_code == 200, response.text
        session = create_session(client)
    return session


def typed_fact_swap(left_kind, left, right_kind, right):
    """A valid example-07 graph whose swapped values compare loosely equal."""
    from copy import deepcopy

    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.validation import validate_core_graph

    before = example_draft_json("07-instances-and-evidence")
    for collection in before.values():
        if isinstance(collection, list):
            for element in collection:
                if "evidence" in element:
                    element["evidence"] = []
    first, second = [
        next(p for p in before["properties"] if p["name"] == name)
        for name in ("name", "is_vip")
    ]
    first["value_kind"], second["value_kind"] = left_kind, right_kind
    for fact in before["material_objects"]:
        if fact["type_id"] == first["owner_type_id"]:
            fact["values"].update(name=left, is_vip=right)
    before = validate_core_graph(CoreDraft.model_validate(before)).model_dump(mode="json")
    candidate = deepcopy(before)
    for prop in candidate["properties"]:
        if prop["id"] == first["id"]:
            prop["name"] = "is_vip"
        elif prop["id"] == second["id"]:
            prop["name"] = "name"
    return before, candidate, first["owner_type_id"]
