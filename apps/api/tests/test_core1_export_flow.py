"""Export reports and downloads use the same authorized, immutable artifact."""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select

from ontofoundry_api.api.auth import Principal, ontology_principal
from ontofoundry_api.db_models import OntologyVersionRecord, WorkspaceRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.workspaces import DEV_USER_ID

ROOT = f"/api/v1/modeling/workspaces/{DEMO_WORKSPACE_ID}/exports"


def version(client):
    with client.app.state.session_factory() as db:
        return db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID)).current_version_id


def test_report_download_and_repeated_get_share_bytes_without_model_writes(client):
    vid = version(client)
    before = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/published-snapshot").json()
    response = client.get(ROOT + f"/ontofoundry-core-1?version_id={vid}")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["download_url"] and result["report"]["direction"] == "export"
    download = client.get(result["download_url"])
    assert download.status_code == 200
    assert (
        hashlib.sha256(download.content).hexdigest()
        == result["content_sha256"]
        == result["report"]["content_sha256"]
    )
    assert json.loads(download.content)["draft"] == before
    assert result["filename"] in download.headers["content-disposition"]
    assert download.headers["x-content-sha256"] == result["content_sha256"]
    assert client.get(ROOT + f"/ontofoundry-core-1?version_id={vid}").json() == result
    assert (
        client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/published-snapshot").json()
        == before
    )
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(OntologyVersionRecord)) == 1


def test_no_artifact_for_empty_ossie_and_native_is_explicitly_available(client):
    from ontofoundry_api.domain.models import OntologyDraft, WorkspaceCreate
    from ontofoundry_api.services.workspaces import create_workspace, publish_draft

    with client.app.state.session_factory() as db:
        # Keep service invocation keyword-only, as production does.
        workspace = create_workspace(
            db,
            payload=WorkspaceCreate(name="虚构空导出", slug="fiction-empty"),
            user_id=DEV_USER_ID,
        )
        published = publish_draft(
            db,
            workspace_id=workspace.id,
            draft=OntologyDraft(workspace_id=workspace.id),
            user_id=DEV_USER_ID,
            message="虚构空模型",
        )
        wid = workspace.id
        vid = published.id
    root = f"/api/v1/modeling/workspaces/{wid}/exports"
    response = client.get(root + f"/ossie-0.2?version_id={vid}")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["download_url"] is None and result["content_sha256"] is None
    assert any(i["outcome"] == "error" for i in result["report"]["issues"])
    native = client.get(root + f"/ontofoundry-core-1?version_id={vid}")
    assert native.status_code == 200 and native.json()["download_url"]


def test_download_rechecks_instance_mapping_and_workspace_permissions(client):
    vid = version(client)
    result = client.get(ROOT + f"/ontofoundry-core-1?version_id={vid}").json()

    def principal(scopes):
        return Principal(
            id=DEV_USER_ID,
            subject="fictional-token-owner",
            display_name="虚构签发人",
            email=None,
            service_token_id="fictional-token",
            scopes=frozenset(scopes),
        )

    try:
        for scopes in [[], ["instances:read"], ["mappings:read"]]:
            client.app.dependency_overrides[ontology_principal] = lambda scopes=scopes: (
                principal(scopes)
            )
            assert client.get(result["download_url"]).status_code == 403
            assert (
                client.get(ROOT + f"/ontofoundry-core-1?version_id={vid}").status_code
                == 403
            )
        client.app.dependency_overrides[ontology_principal] = lambda: principal(
            ["instances:read", "mappings:read"]
        )
        assert client.get(result["download_url"]).status_code == 200
        client.app.dependency_overrides[ontology_principal] = lambda: Principal(
            id=str(uuid4()),
            subject="fictional-outsider",
            display_name="虚构访客",
            email=None,
        )
        assert client.get(result["download_url"]).status_code == 403
    finally:
        client.app.dependency_overrides.clear()


def test_wrong_version_workspace_adapter_and_tampering_do_not_deliver(client):
    vid = version(client)
    assert client.get(ROOT + "/ontofoundry-core-1").status_code == 422
    assert client.get(ROOT + f"/unknown?version_id={vid}").status_code == 404
    assert client.get(ROOT + f"/ontofoundry-core-1?version_id={uuid4()}").status_code == 404
    result = client.get(ROOT + f"/ontofoundry-core-1?version_id={vid}").json()
    path = (
        client.app.state.settings.data_dir
        / str(DEMO_WORKSPACE_ID)
        / "exports"
        / vid
        / "ontofoundry-core-1"
        / (result["content_sha256"] + ".json")
    )
    path.write_bytes(b"{}")
    broken = client.get(result["download_url"])
    assert (
        broken.status_code == 409
        and broken.json()["error"]["code"] == "EXPORT_ARTIFACT_CHANGED"
    )
    regenerated = client.get(ROOT + f"/ontofoundry-core-1?version_id={vid}")
    assert regenerated.status_code == 200
    assert client.get(regenerated.json()["download_url"]).status_code == 200


def test_export_scopes_follow_server_connections_and_ambiguous_sources_split(client):
    from core1_fixtures import example_draft

    from ontofoundry_api.db_models import ConnectionRecord
    from ontofoundry_api.services.workspaces import publish_draft

    model = example_draft("01-basic-sales")
    model.workspace_id = DEMO_WORKSPACE_ID
    with client.app.state.session_factory() as db:
        published = publish_draft(
            db,
            workspace_id=str(DEMO_WORKSPACE_ID),
            draft=model,
            user_id=DEV_USER_ID,
            message="虚构来源验收",
        )
        vid = published.id
        first = ConnectionRecord(
            id=str(uuid4()),
            workspace_id=str(DEMO_WORKSPACE_ID),
            name="虚构来源一",
            kind="mysql",
            config_json={
                "database": "dw",
                "host": "fiction.invalid",
                "port": 3306,
                "username": "fiction",
            },
            secret_encrypted="",
        )
        db.add(first)
        db.commit()
    endpoint = ROOT + f"/ossie-0.2?version_id={vid}"
    preview = client.get(endpoint).json()
    assert preview["download_url"], preview
    one = client.get(preview["download_url"]).json()
    assert len(one["ontology_mappings"]) == 1
    assert any(
        r["from"] != r["to"]
        for r in one["ontology_mappings"][0]["semantic_model"]["relationships"]
    )
    with client.app.state.session_factory() as db:
        db.add(
            ConnectionRecord(
                id=str(uuid4()),
                workspace_id=str(DEMO_WORKSPACE_ID),
                name="虚构来源二",
                kind="mysql",
                config_json=first.config_json,
                secret_encrypted="",
            )
        )
        db.commit()
    preview = client.get(endpoint).json()
    split = client.get(preview["download_url"]).json()
    assert len(split["ontology_mappings"]) == len(model.datasets)
    assert all(
        r["from"] == r["to"]
        for scope in split["ontology_mappings"]
        for r in scope["semantic_model"]["relationships"]
    )
