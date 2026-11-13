"""Feedback validation, attribution and manager-only paginated history."""

from uuid import uuid4

import pytest
from gateway_helpers import VERSIONS, WID, call, principal_admin, space, token, user
from sqlalchemy import select
from test_modeling import create_session, publish, save

from ontofoundry_api.db_models import (
    OntologyFeedbackRecord,
    OntologyVersionRecord,
    WorkspaceRecord,
)

URL = f"/api/v1/workspaces/{WID}/feedback"


def feedback_args(**extra):
    return {"workspace_id": WID, "kind": "correction", "user_text": " 净销售额应该再扣运费。\n", "agent_text": "用户认为当前净销售额定义应扣除运费", **extra}


def element_id(client):
    with client.app.state.session_factory() as db:
        version = db.get(OntologyVersionRecord, db.get(WorkspaceRecord, WID).current_version_id)
        return version.snapshot_json["object_types"][0]["id"]


def test_feedback_records_exact_text_user_token_and_server_version(client):
    principal = user(client, role="viewer")
    item = token(client)
    identity = element_id(client)
    result = call(client, item["token"], "submit_feedback", feedback_args(element_ids=[identity]))
    assert not result["isError"]
    body = result["structuredContent"]
    assert set(body) == {"feedback_id", "workspace_id", "version_id", "created_at"}
    assert result["_meta"][VERSIONS][0]["version_id"] == body["version_id"]
    with client.app.state.session_factory() as db:
        row = db.get(OntologyFeedbackRecord, body["feedback_id"])
        assert row.user_id == principal.id and row.token_id == item["id"]
        assert row.user_text == feedback_args()["user_text"]
        assert row.agent_text == feedback_args()["agent_text"]
        assert row.element_ids == [identity] and row.version_id == body["version_id"]
    assert client.get(URL).status_code == 403
    principal_admin(client, principal)
    page = client.get(URL).json()
    assert set(page) == {"items", "next_cursor"}
    row = page["items"][0]
    assert set(row) == {"id", "created_at", "user", "kind", "user_text", "agent_text", "elements", "version_number"}
    assert row["user"] == {"id": principal.id, "display_name": principal.display_name}
    assert row["elements"][0]["id"] == identity and row["elements"][0]["name"]
    assert row["version_number"] == 1


@pytest.mark.parametrize("role,public", [("viewer", False), ("member", False), (None, True)])
def test_readers_can_submit_but_cannot_list(client, role, public):
    user(client, role=role, public=public)
    credential = token(client)["token"]
    assert not call(client, credential, "submit_feedback", feedback_args())["isError"]
    denied = client.get(URL)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "WORKSPACE_MANAGE_REQUIRED"


def test_unavailable_and_cross_space_elements(client):
    user(client)
    credential = token(client)["token"]
    assert call(client, credential, "submit_feedback", feedback_args())["structuredContent"]["code"] == "workspace_unavailable"
    private = space(client, "虚构私有空间")
    assert call(client, credential, "submit_feedback", feedback_args(workspace_id=private))["structuredContent"]["code"] == "workspace_unavailable"
    client.app.dependency_overrides.clear()
    credential = token(client)["token"]
    other = space(client, "虚构采购空间")
    cross = call(client, credential, "submit_feedback", feedback_args(workspace_id=other, element_ids=[element_id(client)]))
    assert cross["structuredContent"]["code"] == "invalid_arguments"
    assert cross["_meta"][VERSIONS] == [{"workspace_id": other, "version_id": None, "version_number": None}]
    unknown = call(client, credential, "submit_feedback", feedback_args(element_ids=[str(uuid4())]))
    assert unknown["structuredContent"]["code"] == "invalid_arguments"


@pytest.mark.parametrize("extra", [
    {"user_text": ""}, {"agent_text": " \n"}, {"user_text": "字" * 4001},
    {"agent_text": "字" * 4001}, {"element_ids": [str(uuid4()) for _ in range(21)]},
    {"kind": "other"}, {"version_id": str(uuid4())},
])
def test_invalid_feedback_does_not_persist(client, extra):
    credential = token(client)["token"]
    result = call(client, credential, "submit_feedback", feedback_args(**extra))
    assert result["isError"] and result["structuredContent"]["code"] == "invalid_arguments"
    with client.app.state.session_factory() as db:
        assert db.scalar(select(OntologyFeedbackRecord)) is None


def test_feedback_limits_and_unpublished_version(client):
    credential = token(client)["token"]
    other = space(client, "虚构未发布空间")
    result = call(client, credential, "submit_feedback", feedback_args(workspace_id=other, user_text="字" * 4000, agent_text="字" * 4000))
    assert not result["isError"] and result["structuredContent"]["version_id"] is None


def test_manager_can_list_with_stable_cursor_and_current_names(client):
    credential = token(client)["token"]
    identity = element_id(client)
    created = [call(client, credential, "submit_feedback", feedback_args(element_ids=[identity]))["structuredContent"] for _ in range(3)]
    first = client.get(URL, params={"limit": 1}).json()
    assert first["items"][0]["id"] == created[-1]["feedback_id"]
    assert first["next_cursor"]
    call(client, credential, "submit_feedback", feedback_args())
    second = client.get(URL, params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert second["items"][0]["id"] == created[-2]["feedback_id"]
    assert client.get(URL, params={"cursor": "invalid"}).status_code == 422
    assert client.get(URL, params={"limit": 101}).status_code == 422
    assert client.get(URL, headers={"Authorization": "Bearer " + credential}).status_code == 401
    session = create_session(client)
    original = next(e for e in session["draft"]["object_types"] if e["id"] == identity)
    original["display_name"] = "星港新版名称"
    assert publish(client, save(client, session, session["draft"]).json()).status_code == 200
    listed = client.get(URL).json()["items"]
    old = next(i for i in listed if i["elements"])
    assert old["elements"][0]["display_name"] == "星港新版名称"
    assert old["version_number"] == 1
    # A historical element absent from the current published version resolves to its ID.
    removed = str(uuid4())
    with client.app.state.session_factory() as db:
        db.get(OntologyFeedbackRecord, old["id"]).element_ids = [removed]
        db.commit()
    assert next(i for i in client.get(URL).json()["items"] if i["id"] == old["id"])["elements"] == [{"id": removed}]


def test_workspace_admin_and_other_workspace_admin(client):
    admin = user(client, role="admin")
    assert client.get(URL).status_code == 200
    other = space(client, "虚构其他空间", member_id=admin.id, role="viewer")
    assert client.get(f"/api/v1/workspaces/{other}/feedback").status_code == 403
