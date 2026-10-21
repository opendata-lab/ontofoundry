"""Background metadata sync: batches, progress, partial failure and retry (DS-12)."""

from contextlib import contextmanager
from uuid import uuid4

import sqlalchemy as sa

from ontofoundry_api.contracts.metadata_sync import SyncRequest
from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.services import metadata_sync
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.workspaces import DEV_USER_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"


def source_database(tmp_path, tables):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    with engine.begin() as conn:
        for i in range(tables):
            conn.exec_driver_sql(f'CREATE TABLE fiction_{i:02d} (id INTEGER PRIMARY KEY, label TEXT)')
        conn.exec_driver_sql("CREATE VIEW fiction_view AS SELECT id FROM fiction_00")
    return engine


def install(client, monkeypatch, engine):
    opened = []

    @contextmanager
    def connect(item, settings, *, timeout_ms=None):
        opened.append(item.id)
        with engine.connect() as conn:
            yield conn

    monkeypatch.setattr(metadata_sync, "connect_readonly", connect)
    identity = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(
            ConnectionRecord(
                id=identity,
                workspace_id=str(DEMO_WORKSPACE_ID),
                name="虚构同步源" + identity[:4],
                kind="mysql",
                config_json={"database": ""},
                secret_encrypted="",
            )
        )
        db.commit()
    return identity, opened


def sync(client, connection_id, body):
    response = client.post(ROOT + f"/connections/{connection_id}/assets/sync-jobs", json=body)
    assert response.status_code == 202, response.text
    # TestClient runs background tasks before returning; read the finished job.
    job = client.get(ROOT + f"/connections/{connection_id}/assets/sync-jobs/{response.json()['id']}")
    assert job.status_code == 200, job.text
    return job.json()


def registered(client, connection_id):
    with client.app.state.session_factory() as db:
        record = db.get(MetadataSnapshotRecord, (connection_id, ""))
        return {t["name"]: t for t in record.snapshot_json["tables"]} if record else {}


def test_full_sync_has_no_cap_and_runs_in_batches_with_one_connection_each(client, tmp_path, monkeypatch):
    engine = source_database(tmp_path, 44)
    connection_id, opened = install(client, monkeypatch, engine)
    job = sync(client, connection_id, {"scope": "all"})
    assert job["state"] == "succeeded"
    assert job["total"] == 45 and job["available"] == 45 and job["failed"] == 0
    assert [len(b["tables"]) for b in job["batches"]] == [20, 20, 5]
    # Inventory plus one source connection per batch, not one per table.
    assert len(opened) == 1 + 3
    tables = registered(client, connection_id)
    assert len(tables) == 45 and tables["fiction_view"]["kind"] == "view"
    assert tables["fiction_03"]["primary_key"] == ["id"]


def test_failed_tables_keep_successes_and_retry_only_reruns_failures(client, tmp_path, monkeypatch):
    engine = source_database(tmp_path, 3)
    connection_id, _ = install(client, monkeypatch, engine)
    real = metadata_sync.read_table
    broken = {"fiction_01"}

    def flaky(conn, schema, name, kind=None):
        if name in broken:
            raise RuntimeError("fictional permission error")
        return real(conn, schema, name, kind)

    monkeypatch.setattr(metadata_sync, "read_table", flaky)
    job = sync(client, connection_id, {"scope": "selected", "tables": ["fiction_00", "fiction_01", "fiction_02"]})
    assert job["state"] == "partial_failed" and job["available"] == 2 and job["failed"] == 1
    assert set(registered(client, connection_id)) == {"fiction_00", "fiction_02"}
    broken.clear()
    retried = client.post(ROOT + f"/connections/{connection_id}/assets/sync-jobs/{job['id']}/retry")
    assert retried.status_code == 202, retried.text
    job = client.get(ROOT + f"/connections/{connection_id}/assets/sync-jobs/{job['id']}").json()
    assert job["state"] == "succeeded" and job["available"] == 3
    assert job["batches"][0]["attempt"] == 2 and job["batches"][0]["history"]
    assert set(registered(client, connection_id)) == {"fiction_00", "fiction_01", "fiction_02"}


def test_interrupted_jobs_are_marked_retryable_on_restart(client, tmp_path, monkeypatch):
    engine = source_database(tmp_path, 1)
    connection_id, _ = install(client, monkeypatch, engine)
    with client.app.state.session_factory() as db:
        connection = db.get(ConnectionRecord, connection_id)
        job = metadata_sync.create_job(
            db, str(DEMO_WORKSPACE_ID), connection, "", SyncRequest(scope="all"), DEV_USER_ID
        )
        job.state = "running"
        db.commit()
        metadata_sync.interrupt_jobs(db)
        db.refresh(job)
        assert job.state == "interrupted" and "可重试" in job.error


def test_retrying_an_older_full_job_does_not_remove_tables_registered_later(client, tmp_path, monkeypatch):
    engine = source_database(tmp_path, 2)
    connection_id, _ = install(client, monkeypatch, engine)
    real = metadata_sync.read_table
    broken = {"fiction_01"}

    def flaky(conn, schema, name, kind=None):
        if name in broken:
            raise RuntimeError("fictional timeout")
        return real(conn, schema, name, kind)

    monkeypatch.setattr(metadata_sync, "read_table", flaky)
    older = sync(client, connection_id, {"scope": "all"})
    assert older["state"] == "partial_failed"
    broken.clear()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE fiction_new (id INTEGER PRIMARY KEY)")
    newer = sync(client, connection_id, {"scope": "all"})
    assert newer["state"] == "succeeded" and "fiction_new" in registered(client, connection_id)
    retried = client.post(ROOT + f"/connections/{connection_id}/assets/sync-jobs/{older['id']}/retry")
    assert retried.status_code == 202, retried.text
    tables = registered(client, connection_id)
    assert not tables["fiction_new"].get("missing")


def test_assets_keep_a_recorded_missing_table_missing(client, tmp_path, monkeypatch):
    engine = source_database(tmp_path, 2)
    connection_id, _ = install(client, monkeypatch, engine)
    sync(client, connection_id, {"scope": "all"})
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE fiction_01")
    sync(client, connection_id, {"scope": "all"})
    items = {t["name"]: t for t in client.get(ROOT + f"/connections/{connection_id}/assets").json()["items"]}
    assert items["fiction_01"]["missing"] is True
    assert items["fiction_00"]["missing"] is False


def test_assets_expose_per_table_observation_and_keep_unselected_times(client, tmp_path, monkeypatch):
    engine = source_database(tmp_path, 2)
    connection_id, _ = install(client, monkeypatch, engine)
    sync(client, connection_id, {"scope": "all"})
    before = registered(client, connection_id)
    sync(client, connection_id, {"scope": "selected", "tables": ["fiction_00"]})
    response = client.get(ROOT + f"/connections/{connection_id}/assets").json()
    items = {t["name"]: t for t in response["items"]}
    assert items["fiction_00"]["observed_at"] > before["fiction_00"]["observed_at"]
    assert items["fiction_01"]["observed_at"] == before["fiction_01"]["observed_at"]
    assert response["observed_at"] and len(items) == 3


def test_visible_schemas_respects_postgresql_allowlist_and_mysql_database(monkeypatch):
    from types import SimpleNamespace

    from ontofoundry_api.services import metadata_catalog

    monkeypatch.setattr(metadata_catalog, "inspect", lambda _: SimpleNamespace(
        get_schema_names=lambda: ["fiction_sales", "fiction_crm", "information_schema"]
    ))
    source = object()
    postgres = SimpleNamespace(kind="postgresql", config_json={"schemas": ["fiction_sales", "fiction_hidden"]})
    assert metadata_catalog.visible_schemas(postgres, source) == ["fiction_sales"]
    postgres.config_json = {}
    assert metadata_catalog.visible_schemas(postgres, source) == ["fiction_crm", "fiction_sales", "information_schema"]
    mysql = SimpleNamespace(kind="mysql", config_json={"database": "fiction_crm"})
    assert metadata_catalog.visible_schemas(mysql, source) == ["fiction_crm"]
