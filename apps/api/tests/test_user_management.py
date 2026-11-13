"""Fixed user-directory contract, login identity and membership invariants."""

from uuid import uuid4

import pytest
import test_auth as auth_tests
from sqlalchemy import func, select
from test_auth import complete_oauth, start_oauth

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.contracts.export_schema import export
from ontofoundry_api.db_models import UserRecord, WorkspaceMemberRecord
from ontofoundry_api.services.auth import login_local
from ontofoundry_api.services.auth_config import AuthConfig
from ontofoundry_api.services.workspaces import DEV_USER_ID

login_client = auth_tests.login_client
oauth_http = auth_tests.oauth_http


def new_user(client, username="fiction-user"):
    response = client.post("/api/v1/admin/users", json={"username": username, "display_name": "虚构用户"})
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_directory_and_precreated_membership_contract(client):
    user = new_user(client)
    assert set(user) == {"id", "username", "display_name", "email", "local_account", "platform_admin", "last_login_at", "workspaces"}
    assert user["last_login_at"] is None and user["workspaces"] == []
    assert client.post("/api/v1/admin/users", json={"username": "FICTION-USER", "display_name": "重名"}).json()["error"] == {"code": "USERNAME_EXISTS", "message": "用户名已存在"}
    space = client.post("/api/v1/workspaces", json={"name": "云帆财务", "slug": "fiction-finance"}).json()
    wid = space["id"]
    assert space["is_public"] is False
    assert {"id": wid, "name": "云帆财务", "is_public": False} in client.get("/api/v1/admin/workspaces").json()["items"]
    path = f"/api/v1/admin/users/{user['id']}/workspaces/{wid}"
    assert client.put(path, json={"role": "viewer"}).json() == {"workspace_id": wid, "role": "viewer"}
    assert client.put(path, json={"role": "member"}).status_code == 200
    assert client.get("/api/v1/admin/users?q=FICTION").json()["items"][0]["workspaces"] == [{"id": wid, "name": "云帆财务", "role": "member"}]
    assert client.delete(path).status_code == 204
    assert client.delete(path).status_code == 204
    assert client.get("/api/v1/admin/users?q=nomatch").json() == {"items": []}


def test_members_search_and_last_admin_are_shared_by_both_interfaces(client):
    user = new_user(client)
    wid = client.post("/api/v1/workspaces", json={"name": "星河零售", "slug": "fiction-retail"}).json()["id"]
    root = f"/api/v1/workspaces/{wid}"
    search = client.get(root + "/users/search?q=FICTION").json()["items"]
    assert search == [{"id": user["id"], "username": user["username"], "display_name": user["display_name"], "last_login_at": None}]
    member = client.post(root + "/members", json={"user_id": user["id"], "role": "viewer"})
    assert member.status_code == 201
    assert set(member.json()) == {"id", "user_id", "username", "display_name", "role", "last_login_at"}
    assert client.get(root + "/users/search?q=fiction").json()["items"] == []
    assert client.post(root + "/members", json={"user_id": user["id"], "role": "viewer"}).json()["error"]["code"] == "ALREADY_MEMBER"
    missing = client.post(root + "/members", json={"user_id": str(uuid4()), "role": "member"})
    assert missing.status_code == 404 and missing.json()["error"] == {"code": "USER_NOT_FOUND", "message": "用户不存在，请联系平台管理员在用户管理中创建"}
    admin = next(m for m in client.get(root + "/members").json()["items"] if m["user_id"] == DEV_USER_ID)
    for method, path, body in [
        ("delete", root + f"/members/{admin['id']}", None),
        ("patch", root + f"/members/{admin['id']}", {"role": "viewer"}),
        ("delete", f"/api/v1/admin/users/{DEV_USER_ID}/workspaces/{wid}", None),
        ("put", f"/api/v1/admin/users/{DEV_USER_ID}/workspaces/{wid}", {"role": "member"}),
    ]:
        response = client.request(method, path, json=body)
        assert response.status_code == 409 and response.json()["error"] == {"code": "LAST_ADMIN", "message": "该空间至少需要一名管理员"}
    assert client.patch(root + f"/members/{member.json()['id']}", json={"role": "admin"}).status_code == 200
    assert client.delete(root + f"/members/{admin['id']}").status_code == 200
    # Dev still manages the space, but has no synthetic membership to count.
    remaining = client.get(root + "/members").json()["items"]
    assert len(remaining) == 1
    assert client.delete(root + f"/members/{remaining[0]['id']}").status_code == 409
    assert all(s["id"] != wid for s in client.get("/api/v1/me/workspaces").json()["items"])
    summary = client.get(root).json()
    assert summary["role"] == "admin" and summary["visibility"] == "member"


def test_search_limit_literal_wildcards_and_manage_permissions(client):
    with client.app.state.session_factory() as db:
        db.add_all([UserRecord(id=str(uuid4()), username=f"fiction-{i:02}", display_name="虚构用户") for i in range(25)])
        db.commit()
    wid = client.get("/api/v1/workspaces").json()["items"][0]["id"]
    root = f"/api/v1/workspaces/{wid}"
    assert len(client.get(root + "/users/search?q=fiction").json()["items"]) == 20
    assert client.get(root + "/users/search?q=%").json()["items"] == []
    client.app.dependency_overrides[current_principal] = lambda: Principal(str(uuid4()), "visitor", "虚构访客", None)
    assert client.get(root + "/users/search").status_code == 403
    assert client.get(root + "/members").status_code == 403


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/v1/admin/users", None), ("POST", "/api/v1/admin/users", {"username": "fiction", "display_name": "虚构"}),
    ("GET", "/api/v1/admin/workspaces", None), ("PUT", "/api/v1/admin/users/u/workspaces/w", {"role": "member"}),
    ("DELETE", "/api/v1/admin/users/u/workspaces/w", None),
])
def test_all_admin_routes_require_platform_admin(client, method, path, body):
    client.app.dependency_overrides[current_principal] = lambda: Principal(str(uuid4()), "visitor", "虚构访客", None)
    response = client.request(method, path, json=body)
    assert response.status_code == 403
    assert response.json()["error"] == {"code": "PLATFORM_ADMIN_REQUIRED", "message": "需要平台管理员权限"}


@pytest.mark.parametrize("explicit_username", [True, False])
def test_precreated_user_keeps_memberships_on_first_sso_login(login_client, oauth_http, explicit_username):
    assert login_client.post("/api/v1/auth/login/local", json={"username": "admin", "password": "admin123"}).status_code == 204
    user = new_user(login_client, "starlane-user")
    wid = login_client.post("/api/v1/workspaces", json={"name": "星河零售", "slug": "fiction-retail"}).json()["id"]
    assert login_client.put(f"/api/v1/admin/users/{user['id']}/workspaces/{wid}", json={"role": "member"}).status_code == 200
    login_client.post("/api/v1/auth/logout")
    profile = oauth_http["profile"]["data"]
    profile["sub"] = "provider-sub" if explicit_username else "STARLANE-USER"
    if explicit_username:
        profile["username"] = "STARLANE-USER"
    assert complete_oauth(login_client, start_oauth(login_client)).status_code == 302
    principal = login_client.get("/api/v1/auth/me").json()
    assert principal["id"] == user["id"] and principal["username"] == "starlane-user"
    assert principal["display_name"] == "星港用户" and "subject" not in principal
    assert login_client.get("/api/v1/me/workspaces").json()["items"] == [{"id": wid, "name": "星河零售", "role": "member", "is_public": False}]
    assert login_client.get("/api/v1/workspaces").json()["items"][0]["id"] == wid
    with login_client.app.state.session_factory() as db:
        assert db.get(UserRecord, user["id"]).last_login_at is not None


def test_same_username_local_and_sso_share_user_and_local_preserves_profile(login_client, oauth_http):
    assert login_client.post("/api/v1/auth/login/local", json={"username": "ADMIN", "password": "admin123"}).status_code == 204
    uid = login_client.get("/api/v1/auth/me").json()["id"]
    wid = login_client.post("/api/v1/workspaces", json={"name": "云帆财务", "slug": "fiction-finance"}).json()["id"]
    login_client.post("/api/v1/auth/logout")
    oauth_http["profile"]["data"].update(username="Admin", display_name="虚构管理员")
    complete_oauth(login_client, start_oauth(login_client))
    me = login_client.get("/api/v1/auth/me").json()
    assert me["id"] == uid and me["local_account"] is True
    assert login_client.get("/api/v1/me/workspaces").json()["items"][0]["id"] == wid
    login_client.post("/api/v1/auth/logout")
    login_client.post("/api/v1/auth/login/local", json={"username": "admin", "password": "admin123"})
    assert login_client.get("/api/v1/auth/me").json()["display_name"] == "虚构管理员"
    with login_client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(UserRecord)) == 1
        assert db.scalar(select(WorkspaceMemberRecord.role).where(WorkspaceMemberRecord.user_id == uid)) == "admin"


@pytest.mark.parametrize("username", [None, "", " ", 7, "a" * 121, "a\nb"])
def test_invalid_hook_username_is_rejected(login_client, oauth_http, username):
    oauth_http["profile"]["data"]["username"] = username
    response = complete_oauth(login_client, start_oauth(login_client))
    assert response.headers["location"] == "/login?error=oauth_user_info_failed"
    assert login_client.get("/api/v1/auth/me").status_code == 401


def test_schemas_match():
    export(check=True)


def test_local_account_flag_and_case_insensitive_config(client):
    with client.app.state.session_factory() as db:
        user = login_local(db, AuthConfig(local_users={"Fiction": "secret"}), username="fiction", password="secret")
        assert user.username == "Fiction" and user.last_login_at


def test_fallback_sub_keeps_existing_supported_length(login_client, oauth_http):
    oauth_http["profile"]["data"]["sub"] = "s" * 150
    complete_oauth(login_client, start_oauth(login_client))
    assert login_client.get("/api/v1/auth/me").json()["username"] == "s" * 150


def test_configured_platform_admin_without_membership_sees_and_manages_private_spaces(login_client, oauth_http):
    # First create a private space as an ordinary SSO user.
    complete_oauth(login_client, start_oauth(login_client))
    wid = login_client.post("/api/v1/workspaces", json={"name": "云帆财务", "slug": "fiction-finance"}).json()["id"]
    login_client.post("/api/v1/auth/logout")
    login_client.post("/api/v1/auth/login/local", json={"username": "ADMIN", "password": "admin123"})
    me = login_client.get("/api/v1/auth/me").json()
    assert me["is_platform_admin"] and me["local_account"]
    root = f"/api/v1/workspaces/{wid}"
    assert any(s["id"] == wid for s in login_client.get("/api/v1/workspaces").json()["items"])
    assert any(s["id"] == wid for s in login_client.get("/api/v1/ontology/workspaces").json()["items"])
    assert login_client.get("/api/v1/me/workspaces").json()["items"] == []
    assert login_client.get(root).json()["role"] == "admin"
    assert all(m["user_id"] != me["id"] for m in login_client.get(root + "/members").json()["items"])
    assert login_client.patch(root, json={"is_public": True}).status_code == 200
    created = login_client.post(root + "/sessions", json={"title": "虚构管理员编辑"})
    assert created.status_code == 201
    session = created.json()
    session_root = root + f"/sessions/{session['id']}"
    preview = login_client.post(session_root + "/preview", json={"expected_session_revision": session["revision"]})
    assert preview.status_code == 200, preview.text
    report = preview.json()
    published = login_client.post(session_root + "/publish", json={
        "expected_session_revision": session["revision"],
        "expected_current_version_id": report["current_version_id"],
        "expected_merged_snapshot_sha256": report["merged_snapshot_sha256"],
        "expected_instance_change_sequence": report["instance_change_sequence"],
    })
    assert published.status_code == 200, published.text


def test_actual_session_directory_visibility_and_revocation(login_client, oauth_http):
    login_client.post("/api/v1/auth/login/local", json={"username": "admin", "password": "admin123"})
    wid = login_client.post("/api/v1/workspaces", json={"name": "星河零售", "slug": "fiction-retail"}).json()["id"]
    root = f"/api/v1/workspaces/{wid}"
    login_client.patch(root, json={"is_public": True})
    login_client.post("/api/v1/auth/logout")
    complete_oauth(login_client, start_oauth(login_client))
    for directory in ("/api/v1/workspaces", "/api/v1/ontology/workspaces"):
        item = next(s for s in login_client.get(directory).json()["items"] if s["id"] == wid)
        assert item["role"] is None and item["visibility"] == "public" and item["is_public"]
    assert login_client.get(root + "/sessions").status_code == 200
    assert login_client.post(root + "/sessions", json={"title": "禁止编辑"}).status_code == 403
    from ontofoundry_api.db_models import WorkspaceRecord

    with login_client.app.state.session_factory() as db:
        db.get(WorkspaceRecord, wid).is_public = False
        db.commit()
    for directory in ("/api/v1/workspaces", "/api/v1/ontology/workspaces"):
        assert login_client.get(directory).json()["items"] == []
    response = login_client.get(root)
    assert response.status_code == 404 and response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
