"""Connection deletion guards and atomic, source-independent metadata cleanup."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import select, text

from ontofoundry_api.contracts.connections import ConnectionInUseResponse
from ontofoundry_api.db_models import (
    ConnectionRecord,
    MetadataSnapshotRecord,
    MetadataSyncBatchRecord,
    MetadataSyncJobRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    ProposalBatchRecord,
    ProposalItemRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
)
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.workspaces import DEV_USER_ID

WID = str(DEMO_WORKSPACE_ID)
ROOT = f"/api/v1/workspaces/{WID}"


@pytest.fixture
def connection(client):
    identity = str(uuid4())
    with client.app.state.session_factory() as db:
        # Enforce foreign keys so the cleanup test detects incorrect delete order.
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.add(ConnectionRecord(
            id=identity, workspace_id=WID, name="虚构青禾只读连接", kind="mysql",
            config_json={"host": "fiction.invalid", "database": ""}, secret_encrypted="",
        ))
        db.commit()
    return identity


def dataset(connection, display_name="虚构订单"):
    return {"id": str(uuid4()), "name": "fiction_orders", "display_name": display_name,
            "connection_id": connection, "source_kind": "table", "schema_name": "fiction_sales",
            "table_name": "fiction_orders"}


def add_session(db, *, workspace_id=WID, datasets=None, tables=None):
    session = ModelingSessionRecord(
        id=str(uuid4()), workspace_id=workspace_id, created_by=DEV_USER_ID, title="虚构青禾建模",
        draft_json={"schema_version": "core-1", "datasets": datasets or []},
        base_version_sha256="", draft_sha256="", linked_tables=tables or [],
    )
    db.add(session)
    db.flush()
    return session


def add_proposal(db, session, value, *, status="pending", operation="create"):
    batch = ProposalBatchRecord(
        id=str(uuid4()), workspace_id=session.workspace_id, session_id=session.id,
        run_token=str(uuid4()), schema_version="proposals-1", base_version_sha256="",
        source_session_revision=0, source_draft_sha256="", result_sha256=str(uuid4()), status="available",
    )
    db.add(batch)
    db.flush()
    db.add(ProposalItemRecord(
        id=str(uuid4()), batch_id=batch.id, workspace_id=session.workspace_id,
        session_id=session.id, ordinal=0, fingerprint=str(uuid4()), operation=operation,
        target_kind="dataset", target_id=value["id"], status=status,
        before_json=value if operation == "delete" else None,
        after_json=None if operation == "delete" else value,
    ))


def add_metadata(db, connection, state="succeeded", schema="fiction_sales"):
    job_id, batch_id = str(uuid4()), str(uuid4())
    db.add(MetadataSnapshotRecord(connection_id=connection, schema_name=schema, snapshot_json={
        "tables": [{"name": "fiction_orders", "columns": [{"name": "id"}]}],
    }))
    db.add(MetadataSyncJobRecord(
        id=job_id, workspace_id=WID, connection_id=connection, schema_name=schema,
        scope="all", state=state, created_by=DEV_USER_ID,
    ))
    db.flush()
    db.add(MetadataSyncBatchRecord(id=batch_id, job_id=job_id, ordinal=0,
                                  table_names_json=["fiction_orders"], state=state))
    db.flush()
    return job_id, batch_id


def assert_in_use(client, connection, expected):
    response = client.delete(ROOT + f"/connections/{connection}")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONNECTION_IN_USE"
    assert body["error"]["message"] == "该连接仍被引用，请先改用其他连接或删除这些数据集"
    assert body["error"]["references"] == expected
    ConnectionInUseResponse.model_validate(body)
    schema = Path(__file__).parents[1] / "src/ontofoundry_api/contracts/ontofoundry.connections.v1.schema.json"
    artifact = json.loads(schema.read_text())
    assert artifact == ConnectionInUseResponse.model_json_schema()
    Draft202012Validator(artifact).validate(body)
    with client.app.state.session_factory() as db:
        assert db.get(ConnectionRecord, connection) is not None


def test_delete_unused_connection_cleans_every_schema_and_preserves_other_connections(client, connection, monkeypatch):
    def no_source(*args, **kwargs):
        pytest.fail("Deleting local metadata must never open a business source")

    monkeypatch.setattr("ontofoundry_api.services.readonly.connect_readonly", no_source)
    with client.app.state.session_factory() as db:
        own = [add_metadata(db, connection, schema=schema) for schema in ["fiction_sales", "fiction_archive"]]
        other = ConnectionRecord(id=str(uuid4()), workspace_id=WID, name="虚构白鹭连接", kind="mysql",
                                 config_json={}, secret_encrypted="")
        db.add(other)
        db.flush()
        kept_job, kept_batch = add_metadata(db, other.id)
        db.commit()
    response = client.delete(ROOT + f"/connections/{connection}")
    assert response.status_code == 204, response.text
    assert response.content == b""
    with client.app.state.session_factory() as db:
        assert db.get(ConnectionRecord, connection) is None
        assert list(db.scalars(select(MetadataSnapshotRecord).where(MetadataSnapshotRecord.connection_id == connection))) == []
        for job_id, batch_id in own:
            assert db.get(MetadataSyncJobRecord, job_id) is None
            assert db.get(MetadataSyncBatchRecord, batch_id) is None
        assert db.get(ConnectionRecord, other.id) is not None
        assert db.get(MetadataSnapshotRecord, (other.id, "fiction_sales")) is not None
        assert db.get(MetadataSyncJobRecord, kept_job) is not None
        assert db.get(MetadataSyncBatchRecord, kept_batch) is not None
    assert client.delete(ROOT + f"/connections/{connection}").status_code == 404


def test_current_published_dataset_blocks_deletion(client, connection):
    with client.app.state.session_factory() as db:
        workspace = db.get(WorkspaceRecord, WID)
        version = db.get(OntologyVersionRecord, workspace.current_version_id)
        version.snapshot_json = {**version.snapshot_json, "datasets": [dataset(connection)]}
        db.commit()
    assert_in_use(client, connection, [{"type": "dataset", "name": "虚构订单", "location": "已发布版本"}])


def test_published_dataset_in_session_drafts_is_reported_once(client, connection):
    published = dataset(connection)
    with client.app.state.session_factory() as db:
        workspace = db.get(WorkspaceRecord, WID)
        version = db.get(OntologyVersionRecord, workspace.current_version_id)
        version.snapshot_json = {**version.snapshot_json, "datasets": [published]}
        # Drafts carry the whole model, including what is already published.
        add_session(db, datasets=[published])
        db.commit()
    assert_in_use(client, connection, [{"type": "dataset", "name": "虚构订单", "location": "已发布版本"}])


def test_draft_dataset_blocks_deletion_with_name_fallback(client, connection):
    with client.app.state.session_factory() as db:
        add_session(db, datasets=[dataset(connection, display_name=None)])
        db.commit()
    assert_in_use(client, connection, [{"type": "dataset", "name": "fiction_orders", "location": "虚构青禾建模"}])


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_pending_dataset_proposal_blocks_deletion(client, connection, operation):
    with client.app.state.session_factory() as db:
        session = add_session(db)
        add_proposal(db, session, dataset(connection), operation=operation)
        db.commit()
    assert_in_use(client, connection, [{"type": "dataset_proposal", "name": "虚构订单", "location": "虚构青禾建模"}])


def test_linked_table_blocks_deletion(client, connection):
    with client.app.state.session_factory() as db:
        add_session(db, tables=[{"connection_id": connection, "schema_name": "fiction_sales", "table_name": "fiction_orders"}])
        db.commit()
    assert_in_use(client, connection, [{"type": "linked_table", "name": "fiction_sales.fiction_orders", "location": "虚构青禾建模"}])


def test_all_reference_categories_are_returned_together_and_metadata_is_untouched(client, connection):
    with client.app.state.session_factory() as db:
        workspace = db.get(WorkspaceRecord, WID)
        version = db.get(OntologyVersionRecord, workspace.current_version_id)
        version.snapshot_json = {**version.snapshot_json, "datasets": [dataset(connection)]}
        session = add_session(db, datasets=[dataset(connection)], tables=[{
            "connection_id": connection, "schema_name": "fiction_sales", "table_name": "fiction_orders",
        }])
        add_proposal(db, session, dataset(connection))
        job_id, batch_id = add_metadata(db, connection)
        db.commit()
    assert_in_use(client, connection, [
        {"type": "dataset", "name": "虚构订单", "location": "已发布版本"},
        {"type": "dataset", "name": "虚构订单", "location": "虚构青禾建模"},
        {"type": "linked_table", "name": "fiction_sales.fiction_orders", "location": "虚构青禾建模"},
        {"type": "dataset_proposal", "name": "虚构订单", "location": "虚构青禾建模"},
    ])
    with client.app.state.session_factory() as db:
        assert db.get(MetadataSnapshotRecord, (connection, "fiction_sales")) is not None
        assert db.get(MetadataSyncJobRecord, job_id) is not None
        assert db.get(MetadataSyncBatchRecord, batch_id) is not None


@pytest.mark.parametrize("state", ["queued", "running"])
def test_active_sync_in_any_schema_blocks_deletion(client, connection, state):
    with client.app.state.session_factory() as db:
        job_id, batch_id = add_metadata(db, connection, state=state, schema="fiction_archive")
        db.commit()
    response = client.delete(ROOT + f"/connections/{connection}")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "SYNC_RUNNING"
    with client.app.state.session_factory() as db:
        assert db.get(ConnectionRecord, connection) is not None
        assert db.get(MetadataSyncJobRecord, job_id).state == state
        assert db.get(MetadataSyncBatchRecord, batch_id) is not None
        assert db.get(MetadataSnapshotRecord, (connection, "fiction_archive")) is not None


@pytest.mark.parametrize("role", ["member", "reader"])
def test_non_admin_cannot_delete(client, connection, role):
    with client.app.state.session_factory() as db:
        member = db.scalar(select(WorkspaceMemberRecord).where(
            WorkspaceMemberRecord.workspace_id == WID, WorkspaceMemberRecord.user_id == DEV_USER_ID,
        ))
        member.role = role
        db.commit()
    assert client.delete(ROOT + f"/connections/{connection}").status_code == 403
    with client.app.state.session_factory() as db:
        assert db.get(ConnectionRecord, connection) is not None


def test_historical_versions_and_decided_proposals_do_not_block_deletion(client, connection):
    with client.app.state.session_factory() as db:
        db.add(OntologyVersionRecord(
            id=str(uuid4()), workspace_id=WID, version_number=999, snapshot_json={"datasets": [dataset(connection)]},
            validation_json={}, sha256="fiction", published_by=DEV_USER_ID,
        ))
        session = add_session(db)
        for status in ["accepted", "rejected"]:
            add_proposal(db, session, dataset(connection), status=status)
        db.commit()
    assert client.delete(ROOT + f"/connections/{connection}").status_code == 204


def test_connection_from_another_workspace_is_not_deleted(client, connection):
    with client.app.state.session_factory() as db:
        other = WorkspaceRecord(id=str(uuid4()), slug="fiction_other", name="虚构白鹭空间", created_by=DEV_USER_ID)
        db.add(other)
        db.flush()
        db.add(WorkspaceMemberRecord(workspace_id=other.id, user_id=DEV_USER_ID, role="admin"))
        db.commit()
    response = client.delete(f"/api/v1/workspaces/{other.id}/connections/{connection}")
    assert response.status_code == 404
    with client.app.state.session_factory() as db:
        assert db.get(ConnectionRecord, connection) is not None


def test_abandoned_session_does_not_block_deletion(client, connection):
    from ontofoundry_api.db_models import utc_now

    with client.app.state.session_factory() as db:
        session = add_session(db, datasets=[dataset(connection)],
                              tables=[{"connection_id": connection, "schema_name": "fiction_sales", "table_name": "fiction_orders"}])
        session.abandoned_at = utc_now()
        db.commit()
    assert client.delete(ROOT + f"/connections/{connection}").status_code == 204
