"""Core facts retain UUID identities, scalar values and display fallbacks."""

from uuid import uuid4

import pytest
from test_modeling import ONTOLOGY, create_session, publish

from ontofoundry_api.domain.core import CoreDraft, MaterialObject, ObjectType, Property
from ontofoundry_api.domain.instance_display import business_identity, document_display_text
from ontofoundry_api.domain.instance_validation import valid_value

SERVICE = ONTOLOGY


@pytest.mark.parametrize(
    "kind,value,valid",
    [
        ("integer", 0, True),
        ("boolean", False, True),
        ("integer", True, False),
        ("decimal", "10.5", True),
        ("date", "2026-01-01", True),
        ("date", "wrong", False),
    ],
)
def test_fact_value_semantics(kind, value, valid):
    assert valid_value(kind, value) == valid


def test_display_zero_false_missing_identity_and_uuid():
    o = ObjectType(id=uuid4(), display_name="记录", name="record")
    p = Property(
        id=uuid4(),
        owner_type_id=o.id,
        display_name="编号",
        name="code",
        value_kind="integer",
        identifier=True,
        unique=True,
    )
    d = CoreDraft(workspace_id=uuid4(), object_types=[o], properties=[p])
    f = MaterialObject(id=uuid4(), type_id=o.id, values={"code": 0})
    assert document_display_text(d, f) == "0"
    assert business_identity(d, o.id, f.values) == (("integer", 0),)
    f.values = {}
    assert document_display_text(d, f) == str(f.id)
    assert business_identity(d, o.id, f.values) is None


def test_two_facts_same_business_key_survive_publication_and_pagination(client):
    s = create_session(client)
    typ = s["draft"]["object_types"][0]["id"]
    values = [
        {
            "id": str(uuid4()),
            "type_id": typ,
            "values": {"label": "相同名称"},
            "evidence": [],
        }
        for _ in range(2)
    ]
    from pr23_fixtures import seed_instances
    seed_instances(client, s, {"material_objects": values})
    assert publish(client, s).status_code == 200
    first = client.get(SERVICE + "/objects", params={"limit": 1, "q": "相同名称"}).json()
    second = client.get(
        SERVICE + "/objects", params={"limit": 1, "q": "相同名称", "cursor": first["next_cursor"]}
    ).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert first["items"][0]["display_text"] == second["items"][0]["display_text"]
