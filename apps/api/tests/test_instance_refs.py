"""Invalid and expired database references fail before any source access."""

import base64
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from core1_fixtures import example_draft_json
from test_modeling import ONTOLOGY, ROOT, create_session

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.services.errors import NotFoundError, ServiceError
from ontofoundry_api.services.instance_neighborhood import (
    database_neighborhood,
    related_rows,
)
from ontofoundry_api.services.instance_plan import key_values, query_instances
from ontofoundry_api.services.instance_query import (
    ObjectSearch,
    db_ref,
    get_object,
    object_neighborhood,
    parse_ref,
    search_objects,
)

KEY = [{"type": "string", "value": "C001"}]


def encoded_ref(type_id, key=KEY):
    payload = json.dumps([type_id, key]).encode()
    return "db." + base64.urlsafe_b64encode(payload).decode().rstrip("=")


@pytest.mark.parametrize("type_id", [123, True, None, {}, [], "", "not-a-uuid"])
@pytest.mark.parametrize("entry", ["parse", "detail", "neighborhood"])
def test_invalid_ref_type_id_returns_422_without_database(type_id, entry):
    ref = encoded_ref(type_id)
    with pytest.raises(ServiceError) as error:
        if entry == "parse":
            parse_ref(ref)
        elif entry == "detail":
            get_object(None, None, ref, None)
        else:
            object_neighborhood(None, None, ref, 1, None)
    assert error.value.status_code == 422
    assert error.value.code == "INVALID_OBJECT_REF"


def test_valid_ref_normalizes_uuid_and_preserves_key():
    type_id = uuid4()
    assert parse_ref(encoded_ref(str(type_id).upper())) == (
        "database",
        str(type_id),
        KEY,
    )


INVALID_NUMERIC_KEYS = [
    pytest.param([{"type": "decimal", "value": "abc"}], id="malformed-decimal"),
    pytest.param([{"type": "float", "value": 10**400}], id="overflowing-float"),
    *[
        pytest.param([{"type": "decimal", "value": value}], id=f"decimal-{value}")
        for value in ("NaN", "sNaN", "Infinity", "-Infinity")
    ],
]


@pytest.mark.parametrize("key", INVALID_NUMERIC_KEYS)
@pytest.mark.parametrize(
    "entry",
    ["key", "encode", "parse", "detail", "neighborhood", "query", "direct", "related"],
)
def test_invalid_numeric_keys_return_422_before_source_access(monkeypatch, key, entry):
    from ontofoundry_api.services import instance_neighborhood, instance_plan

    def unexpected_source(*args, **kwargs):
        pytest.fail("Invalid numeric keys must fail before binding or source access")

    for module in (instance_plan, instance_neighborhood):
        monkeypatch.setattr(module, "resolve_binding", unexpected_source)
        monkeypatch.setattr(module, "connect_readonly", unexpected_source)
    raw = example_draft_json("07-instances-and-evidence")
    draft = CoreDraft.model_validate(raw)
    type_id = draft.object_types[0].id
    ref = encoded_ref(str(type_id), key)
    with pytest.raises(ServiceError) as error:
        if entry == "key":
            key_values(key)
        elif entry == "encode":
            db_ref(type_id, key)
        elif entry == "parse":
            parse_ref(ref)
        elif entry == "detail":
            get_object(None, None, ref, None)
        elif entry == "neighborhood":
            object_neighborhood(None, None, ref, 1, None)
        elif entry == "query":
            query_instances(None, str(draft.workspace_id), draft, type_id, None, key=key)
        elif entry == "direct":
            database_neighborhood(
                None,
                str(draft.workspace_id),
                draft,
                SimpleNamespace(type_id=type_id, key=key, depth=1, snapshot_date=None),
                None,
            )
        else:
            related_rows(
                None,
                str(draft.workspace_id),
                draft,
                None,
                type_id,
                type_id,
                None,
                key,
                True,
                None,
            )
    assert error.value.status_code == 422
    assert error.value.code == "INVALID_OBJECT_REF"
    assert error.value.message == "实例键类型无效"


def test_finite_numeric_keys_keep_decimal_precision_and_ref_identity():
    key = [
        {"type": "integer", "value": str(10**400)},
        {"type": "decimal", "value": "12345678901234567890.0123456789"},
        {"type": "float", "value": 1.5},
        {"type": "float", "value": 10**300},
    ]
    assert key_values(key) == [
        10**400,
        Decimal("12345678901234567890.0123456789"),
        1.5,
        10**300,
    ]
    type_id = str(uuid4())
    assert parse_ref(db_ref(type_id, key)) == ("database", type_id, key)


@pytest.mark.parametrize("key", INVALID_NUMERIC_KEYS)
@pytest.mark.parametrize("suffix", ["", "/neighborhood"])
def test_object_routes_return_invalid_numeric_key_error(client, key, suffix):
    response = client.get(ONTOLOGY + f"/objects/{encoded_ref(str(uuid4()), key)}" + suffix)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_OBJECT_REF"


@pytest.mark.parametrize("key", INVALID_NUMERIC_KEYS)
def test_direct_neighborhood_route_returns_invalid_numeric_key_error(client, key):
    session = create_session(client)
    response = client.post(
        ROOT + "/instance-neighborhood",
        json={
            "session_id": session["id"],
            "type_id": session["draft"]["object_types"][0]["id"],
            "key": key,
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_OBJECT_REF"


@pytest.mark.parametrize("entry", ["query", "detail", "neighborhood", "direct", "search"])
def test_deleted_type_returns_404_without_database(monkeypatch, entry):
    from ontofoundry_api.services import instance_plan

    def unexpected_binding(*args, **kwargs):
        pytest.fail("Missing types must be rejected before resolving a binding or source")

    monkeypatch.setattr(instance_plan, "resolve_binding", unexpected_binding)
    raw = example_draft_json("07-instances-and-evidence")
    draft = CoreDraft.model_validate(raw)
    deleted_type = uuid4()
    assert deleted_type not in {o.id for o in draft.object_types}
    version = SimpleNamespace(workspace_id=raw["workspace_id"], snapshot_json=raw)
    ref = db_ref(deleted_type, KEY)
    with pytest.raises(NotFoundError) as error:
        if entry == "query":
            query_instances(None, version.workspace_id, draft, deleted_type, None)
        elif entry == "detail":
            get_object(None, version, ref, None)
        elif entry == "neighborhood":
            object_neighborhood(None, version, ref, 1, None)
        elif entry == "direct":
            database_neighborhood(
                None,
                version.workspace_id,
                draft,
                SimpleNamespace(type_id=deleted_type, key=KEY, depth=1, snapshot_date=None),
                None,
            )
        else:
            search_objects(
                None, version, ObjectSearch(type_id=deleted_type, source="database"), None
            )
    assert error.value.status_code == 404
    assert error.value.code == "NOT_FOUND"


@pytest.mark.parametrize("type_id", ["not-a-uuid", "", None, 123])
def test_query_rejects_invalid_type_id_without_database(type_id):
    draft = CoreDraft.model_validate(example_draft_json("07-instances-and-evidence"))
    with pytest.raises(ServiceError) as error:
        query_instances(None, str(draft.workspace_id), draft, type_id, None)
    assert error.value.status_code == 422
    assert error.value.code == "INVALID_OBJECT_REF"


@pytest.mark.parametrize("suffix", ["", "/neighborhood"])
@pytest.mark.parametrize("invalid", [True, False])
def test_object_routes_return_ref_errors_without_source_access(client, suffix, invalid):
    ref = encoded_ref(123) if invalid else db_ref(uuid4(), KEY)
    response = client.get(ONTOLOGY + f"/objects/{ref}" + suffix)
    assert response.status_code == (422 if invalid else 404), response.text
    assert response.json()["error"]["code"] == (
        "INVALID_OBJECT_REF" if invalid else "NOT_FOUND"
    )


@pytest.mark.parametrize("type_id", ["not-a-uuid", str(uuid4())])
def test_direct_neighborhood_route_returns_type_error(client, type_id):
    response = client.post(
        ROOT + "/instance-neighborhood", json={"type_id": type_id, "key": KEY}
    )
    invalid = type_id == "not-a-uuid"
    assert response.status_code == (422 if invalid else 404), response.text
    assert response.json()["error"]["code"] == (
        "INVALID_OBJECT_REF" if invalid else "NOT_FOUND"
    )
