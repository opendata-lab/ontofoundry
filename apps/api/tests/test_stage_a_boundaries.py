"""Regression boundaries for additive upgrades, source facts and revoked access."""

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text
from test_stage_a import ROOT, SERVICE, publish
from test_stage_a import document_session as document_session_fixture
from test_stage_a import mapped_session as mapped_session_fixture

from ontofoundry_api.api import assets, connections
from ontofoundry_api.db_models import WorkspaceMemberRecord
from ontofoundry_api.domain.instance_validation import value_issues
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID, build_demo_draft
from ontofoundry_api.services.source_rows import validate_source_rows

document_session = document_session_fixture
mapped_session = mapped_session_fixture


@pytest.mark.parametrize(
    ("row", "code"),
    [
        ({"__key": None}, "INVALID_SOURCE_KEY"),
        ({"__key": " "}, "INVALID_SOURCE_KEY"),
        ({"__key": float("inf")}, "INVALID_SOURCE_KEY"),
        ({"__key": "S1", "value": float("inf")}, "UNSUPPORTED_SOURCE_VALUE"),
        ({"__key": "S1", "value": Decimal("NaN")}, "UNSUPPORTED_SOURCE_VALUE"),
    ],
)
def test_unusable_source_facts_have_actionable_errors(row, code):
    with pytest.raises(HTTPException) as error:
        validate_source_rows([row])
    assert error.value.status_code == 422
    assert error.value.detail["code"] == code


def test_duplicate_identity_is_not_silently_collapsed():
    with pytest.raises(HTTPException) as error:
        validate_source_rows([{"__key": "S1"}, {"__key": "S1"}])
    assert error.value.detail["code"] == "DUPLICATE_SOURCE_KEY"


def test_instance_authorization_expires_with_issuer_membership(client, document_session):
    publish(client, document_session[0])
    token = client.post(
        ROOT + "/service-tokens",
        json={"name": "撤销成员验证", "scopes": ["instances:read"]},
    ).json()
    headers = {"Authorization": "Bearer " + token["token"]}
    assert client.get(SERVICE + "/objects", headers=headers).status_code == 200
    with client.app.state.session_factory() as db:
        db.execute(
            delete(WorkspaceMemberRecord).where(
                WorkspaceMemberRecord.workspace_id == str(DEMO_WORKSPACE_ID)
            )
        )
        db.commit()
    response = client.get(SERVICE + "/objects", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "INSTANCES_FORBIDDEN"


def test_inherited_required_properties_are_checked():
    model = build_demo_draft().model_dump(mode="json")
    parent, child = model["object_types"][:2]
    child["extends"] = [parent["id"]]
    draft = OntologyDraft.model_validate(model)
    errors = value_issues(draft, draft.object_types[1].id, {}, "$.objects[0].values")
    inherited = [
        attr for attr in parent["attributes"] if attr["required"] or attr["identifier"]
    ]
    assert inherited
    for attr in inherited:
        assert any(
            e["path"].endswith("." + attr["technical_name"])
            and e["code"] == "INSTANCE_REQUIRED"
            for e in errors
        )


def test_repeated_refresh_does_not_clear_unresolved_field_drift(
    client, mapped_session, monkeypatch
):
    publish(client, mapped_session[0])
    monkeypatch.setattr(assets, "connect_readonly", connections.connect_readonly)
    cid = client.get(ROOT + "/connections").json()["items"][0]["id"]
    path = ROOT + f"/connections/{cid}/assets/refresh"
    assert client.post(path).json()["changes"] == []
    with connections.connect_readonly(None, None) as conn:
        conn.execute(text("ALTER TABLE materials RENAME COLUMN name TO renamed"))
        conn.commit()
    changed = client.post(path).json()
    repeated = client.post(path).json()
    assert changed["changes"] and repeated["changes"] == changed["changes"]
    assert (
        next(t for t in repeated["items"] if t["name"] == "materials")["mappings"][0][
            "status"
        ]
        == "invalid"
    )
    with connections.connect_readonly(None, None) as conn:
        conn.execute(text("ALTER TABLE materials RENAME COLUMN renamed TO name"))
        conn.commit()
    restored = client.post(path).json()
    assert restored["changes"] == []
    assert (
        next(t for t in restored["items"] if t["name"] == "materials")["mappings"][0][
            "status"
        ]
        == "valid"
    )
