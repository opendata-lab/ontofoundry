"""A source server's databases retain distinct identities throughout metadata sync."""

from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects.mysql.pymysql import MySQLDialect_pymysql

from ontofoundry_api.api import assets, connections
from ontofoundry_api.contracts.metadata_sync import SyncRequest
from ontofoundry_api.db_models import (
    ConnectionRecord,
    MetadataSnapshotRecord,
    MetadataSyncBatchRecord,
    MetadataSyncJobRecord,
)
from ontofoundry_api.services import (
    dataset_validation,
    metadata_sync,
    readonly,
    table_preview,
)
from ontofoundry_api.services.dataset_sources import registered_table_catalog
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metadata_catalog import list_tables, read_doris_table
from ontofoundry_api.services.workspaces import DEV_USER_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
SCHEMAS = ("fiction_alpha", "fiction_beta")
INVENTORY = {
    "fiction_alpha": {"fiction_shared", "fiction_alpha_only", "fiction_view"},
    "fiction_beta": {"fiction_shared", "fiction_beta_only", "fiction_view"},
}


@pytest.fixture(params=["mysql", "doris"])
def server(request, client, tmp_path, monkeypatch):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'default.db'}")

    @sa.event.listens_for(engine, "connect")
    def attach(dbapi, _):
        for schema in (*SCHEMAS, "information_schema"):
            dbapi.execute(f'ATTACH DATABASE ? AS "{schema}"', (str(tmp_path / f"{schema}.db"),))

    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE fiction_default_only (wrong_default TEXT)")
        for schema, definition in zip(SCHEMAS, (
            "id INTEGER PRIMARY KEY, alpha_value TEXT",
            "code INTEGER PRIMARY KEY, beta_value INTEGER NOT NULL",
        ), strict=True):
            conn.exec_driver_sql(f"CREATE TABLE {schema}.fiction_shared ({definition})")
            conn.exec_driver_sql(f"CREATE TABLE {schema}.{schema}_only (id INTEGER PRIMARY KEY)")
            conn.exec_driver_sql(f"CREATE VIEW {schema}.fiction_view AS SELECT * FROM fiction_shared")
        conn.exec_driver_sql("CREATE TABLE information_schema.tables (TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, TABLE_COMMENT)")
        conn.exec_driver_sql("CREATE TABLE information_schema.columns (TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, DATA_TYPE, IS_NULLABLE, COLUMN_COMMENT, COLUMN_KEY, ORDINAL_POSITION)")
        for schema in SCHEMAS:
            inspector = sa.inspect(conn)
            for name in INVENTORY[schema]:
                conn.execute(sa.text("INSERT INTO information_schema.tables VALUES (:schema, :name, :kind, :comment)"), {
                    "schema": schema, "name": name, "kind": "VIEW" if name == "fiction_view" else "BASE TABLE", "comment": f"虚构来源 {schema}",
                })
                for ordinal, column in enumerate(inspector.get_columns(name, schema=schema)):
                    conn.execute(sa.text("INSERT INTO information_schema.columns VALUES (:schema, :name, :column, :type, :type, :nullable, '', :key, :ordinal)"), {
                        "schema": schema, "name": name, "column": column["name"], "type": str(column["type"]),
                        "nullable": "YES" if column["nullable"] else "NO", "key": "PRI" if column.get("primary_key") else "", "ordinal": ordinal,
                    })

    opened = []

    @contextmanager
    def connect(item, settings, *, timeout_ms=None):
        opened.append(item.id)
        with engine.connect() as conn:
            conn.info["source_kind"] = item.kind
            yield conn

    for module in (metadata_sync, assets, connections, table_preview, dataset_validation):
        monkeypatch.setattr(module, "connect_readonly", connect)
    identity = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(ConnectionRecord(
            id=identity, workspace_id=str(DEMO_WORKSPACE_ID), name="虚构多库服务", kind=request.param,
            # Legacy values must never supply a library for a server-wide connection.
            config_json={"database": "main", "schema_name": "main"}, secret_encrypted="",
        ))
        db.commit()
    yield SimpleNamespace(id=identity, kind=request.param, engine=engine, opened=opened)
    engine.dispose()


def finished(client, server, schema, scope="all", tables=None):
    base = ROOT + f"/connections/{server.id}/assets/sync-jobs"
    response = client.post(base, params={"schema_name": schema}, json={"scope": scope, "tables": tables or []})
    assert response.status_code == 202, response.text
    assert response.json()["schema_name"] == schema
    job = client.get(base + "/" + response.json()["id"]).json()
    assert job["state"] == "succeeded", job
    assert job["failed"] == 0
    return job


def snapshot(client, server, schema):
    with client.app.state.session_factory() as db:
        record = db.get(MetadataSnapshotRecord, (server.id, schema))
        return {t["name"]: t for t in record.snapshot_json["tables"]} if record else {}


def test_list_selected_full_sync_and_snapshot_reads_keep_each_database(client, server):
    base = ROOT + f"/connections/{server.id}"
    schemas = client.get(base + "/schemas").json()["items"]
    assert set(SCHEMAS) <= set(schemas) and "information_schema" not in schemas
    for schema in SCHEMAS:
        listed = client.get(base + "/tables", params={"schema_name": schema})
        assert listed.status_code == 200, listed.text
        assert {t["name"] for t in listed.json()["items"]} == INVENTORY[schema]
        assert all(t["schema"] == schema for t in listed.json()["items"])
        detail = client.get(base + "/tables", params={"schema_name": schema, "table": "fiction_shared"}).json()
        assert {c["name"] for c in detail["items"][0]["columns"]} == (
            {"id", "alpha_value"} if schema == SCHEMAS[0] else {"code", "beta_value"}
        )
        finished(client, server, schema, "selected", ["fiction_shared"])
        assert set(snapshot(client, server, schema)) == {"fiction_shared"}
    for schema in SCHEMAS:
        job = finished(client, server, schema)
        assert job["total"] == 3 and job["available"] == 3
        saved = snapshot(client, server, schema)
        assert set(saved) == INVENTORY[schema]
        assert all(t["schema"] == schema and not t["missing"] for t in saved.values())
        assert saved["fiction_shared"]["primary_key"] == (["id"] if schema == SCHEMAS[0] else ["code"])
        assert saved["fiction_view"]["kind"] == "view"
        read = client.get(base + "/assets", params={"schema_name": schema}).json()
        assert read["metadata_snapshot_id"] == f"{server.id}:{schema}"
        assert {t["name"] for t in read["items"]} == INVENTORY[schema]
        assert all(t["schema"] == schema for t in read["items"])
        history = client.get(base + "/assets/sync-jobs", params={"schema_name": schema}).json()["items"]
        assert len(history) == 2 and all(j["schema_name"] == schema for j in history)
    catalog = client.get(ROOT + "/registered-tables").json()["items"]
    actual = {(t["schema_name"], t["table_name"]) for t in catalog if t["connection_id"] == server.id}
    assert actual == {(s, t) for s in SCHEMAS for t in INVENTORY[s]}
    # Selecting another database's exclusive table does not register or alter it here.
    finished(client, server, SCHEMAS[0], "selected", ["fiction_beta_only"])
    assert set(snapshot(client, server, SCHEMAS[0])) == INVENTORY[SCHEMAS[0]]
    assert not snapshot(client, server, SCHEMAS[1])["fiction_beta_only"]["missing"]


def test_full_sync_removal_and_unregister_are_scoped_to_one_database(client, server):
    for schema in SCHEMAS:
        finished(client, server, schema)
    beta_before = snapshot(client, server, SCHEMAS[1])
    with server.engine.begin() as conn:
        conn.exec_driver_sql("DROP VIEW fiction_alpha.fiction_view")
        conn.exec_driver_sql("DROP TABLE fiction_alpha.fiction_shared")
        conn.execute(sa.text("DELETE FROM information_schema.tables WHERE TABLE_SCHEMA = :schema AND TABLE_NAME IN ('fiction_shared', 'fiction_view')"), {"schema": SCHEMAS[0]})
    finished(client, server, SCHEMAS[0])
    assert snapshot(client, server, SCHEMAS[0])["fiction_shared"]["missing"]
    assert snapshot(client, server, SCHEMAS[1]) == beta_before
    deleted = client.delete(ROOT + f"/connections/{server.id}/assets/tables", params={"schema_name": SCHEMAS[0], "table_name": "fiction_shared"})
    assert deleted.status_code == 200, deleted.text
    assert "fiction_shared" not in snapshot(client, server, SCHEMAS[0])
    assert snapshot(client, server, SCHEMAS[1]) == beta_before


def test_omitted_schema_never_falls_back_to_legacy_config(client, server):
    base = ROOT + f"/connections/{server.id}"
    for path in ("/tables", "/assets", "/assets/sync-jobs", "/assets/rows?table_name=fiction_shared"):
        response = client.get(base + path)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "SCHEMA_REQUIRED"
    response = client.post(base + "/assets/sync-jobs", json={"scope": "all"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "SCHEMA_REQUIRED"
    response = client.post(base + "/assets/refresh", json={"scope": "all"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "SCHEMA_REQUIRED"
    response = client.delete(base + "/assets/tables", params={"table_name": "fiction_shared"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "SCHEMA_REQUIRED"
    assert not server.opened


def test_new_server_connection_through_sync_details_dataset_edit_and_builder_links(client, server):
    from test_modeling import create_session

    created = client.post(ROOT + "/connections", json={
        "name": "虚构新建服务", "kind": server.kind, "host": "fiction.invalid",
        "port": 3306, "username": "reader", "password": "",
    })
    assert created.status_code == 201, created.text
    assert created.json()["database"] == ""
    server.id = created.json()["id"]
    base = ROOT + f"/connections/{server.id}"
    assert client.post(base + "/test").status_code == 200
    assert set(SCHEMAS) <= set(client.get(base + "/schemas").json()["items"])
    # Each schema has a different shape and value for the same table name.
    with server.engine.begin() as source:
        source.exec_driver_sql("INSERT INTO fiction_alpha.fiction_shared VALUES (11, '虚构甲库')")
        source.exec_driver_sql("INSERT INTO fiction_beta.fiction_shared VALUES (22, 42)")
    session = create_session(client)
    dataset_id = str(uuid4())
    for schema, columns, row in (
        (SCHEMAS[0], ["id", "alpha_value"], {"id": 11, "alpha_value": "虚构甲库"}),
        (SCHEMAS[1], ["code", "beta_value"], {"code": 22, "beta_value": 42}),
    ):
        inventory = client.get(base + "/tables", params={"schema_name": schema})
        assert inventory.status_code == 200, inventory.text
        finished(client, server, schema, "selected", ["fiction_shared"])
        details = client.get(base + "/assets", params={"schema_name": schema})
        assert details.status_code == 200, details.text
        assert [c["name"] for c in details.json()["items"][0]["columns"]] == columns
        preview = client.get(base + "/assets/rows", params={"schema_name": schema, "table_name": "fiction_shared"})
        assert preview.status_code == 200, preview.text
        assert preview.json()["items"] == [row]
        dataset = {"id": dataset_id, "name": "fiction_dataset", "display_name": "虚构数据集", "source_kind": "table", "connection_id": server.id, "dialect": server.kind, "schema_name": schema, "table_name": "fiction_shared"}
        checked = client.post(ROOT + "/datasets/validate", json={"dataset": dataset})
        assert checked.status_code == 200 and checked.json()["valid"], checked.text
        assert [c["name"] for c in checked.json()["columns"]] == columns
        data = client.post(ROOT + "/datasets/preview", json={"dataset": dataset})
        assert data.status_code == 200, data.text
        assert data.json()["items"] == [row]
        # Save creation, then edit the same dataset to the other database.
        draft = {**session["draft"], "datasets": [dataset]}
        linked = [{"connection_id": server.id, "schema_name": schema, "table_name": "fiction_shared"}]
        saved = client.put(ROOT + f"/sessions/{session['id']}", json={"revision": session["revision"], "draft": draft, "linked_tables": linked})
        assert saved.status_code == 200, saved.text
        session = saved.json()
        assert session["draft"]["datasets"][0]["schema_name"] == schema
        assert session["linked_tables"] == linked
        catalog = client.get(ROOT + "/registered-tables", params={"session_id": session["id"]})
        assert catalog.status_code == 200, catalog.text
        used = [t for t in catalog.json()["items"] if t["connection_id"] == server.id and t["datasets"]]
        assert [(t["schema_name"], t["table_name"]) for t in used] == [(schema, "fiction_shared")]
    legacy = client.post(base + "/table-material", json={"tables": ["fiction_shared"]})
    assert legacy.status_code == 422
    assert legacy.json()["error"]["code"] == "DATASET_ASSOCIATION_REQUIRED"


def test_postgresql_connection_requires_database_even_when_mysql_does_not(client, server):
    body = {"name": "虚构PG服务", "kind": "postgresql", "host": "fiction.invalid", "port": 5432, "username": "reader", "password": ""}
    for extra in ({}, {"database": ""}, {"database": "  "}):
        response = client.post(ROOT + "/connections", json={**body, **extra})
        assert response.status_code == 422, response.text
    assert not server.opened
    created = client.post(ROOT + "/connections", json={**body, "database": "fiction_database"})
    assert created.status_code == 201, created.text
    assert created.json()["database"] == "fiction_database"


@pytest.mark.parametrize("schema,allowed", [("", None), ("fiction_alpha", ["fiction_beta"])])
def test_background_checks_legacy_job_schema_and_current_permissions(client, server, schema, allowed):
    identity = str(uuid4())
    with client.app.state.session_factory() as db:
        connection = db.get(ConnectionRecord, server.id)
        if allowed:
            connection.config_json = {**connection.config_json, "schemas": allowed}
        db.add(MetadataSyncJobRecord(
            id=identity, workspace_id=str(DEMO_WORKSPACE_ID), connection_id=server.id,
            schema_name=schema, scope="all", state="queued", created_by=DEV_USER_ID,
        ))
        db.commit()
    metadata_sync.run_job(client.app.state.session_factory, identity, client.app.state.settings)
    with client.app.state.session_factory() as db:
        job = db.get(MetadataSyncJobRecord, identity)
        assert job.state == "failed"
        assert job.error == ("请选择库" if not schema else "该库不在连接允许的范围内")
        assert db.get(MetadataSnapshotRecord, (server.id, schema)) is None
    assert not server.opened


def test_mismatched_observation_cannot_be_saved_under_another_database(client, server, monkeypatch):
    monkeypatch.setattr(metadata_sync, "read_table", lambda *args: {
        "name": "fiction_shared", "schema": SCHEMAS[1], "columns": [], "missing": False,
    })
    with client.app.state.session_factory() as db:
        job = metadata_sync.create_job(db, str(DEMO_WORKSPACE_ID), db.get(ConnectionRecord, server.id), SCHEMAS[0], SyncRequest(scope="selected", tables=["fiction_shared"]), DEV_USER_ID)
        identity = job.id
    metadata_sync.run_job(client.app.state.session_factory, identity, client.app.state.settings)
    with client.app.state.session_factory() as db:
        job = db.get(MetadataSyncJobRecord, identity)
        result = metadata_sync.job_response(db, job)
        assert result["state"] == "partial_failed" and result["failed"] == 1
        assert result["batches"][0]["results"][0]["error"] == "读取结果的库与同步任务不一致"
    assert snapshot(client, server, SCHEMAS[0]) == {}
    assert snapshot(client, server, SCHEMAS[1]) == {}


def test_registered_catalog_does_not_attach_unqualified_dataset_to_every_database(client, server):
    for schema in SCHEMAS:
        finished(client, server, schema)
    datasets = [
        {"id": "fiction-explicit", "name": "虚构明确库", "connection_id": server.id, "schema_name": SCHEMAS[0], "table_name": "fiction_shared"},
        {"id": "fiction-unqualified", "name": "虚构缺少库", "connection_id": server.id, "table_name": "fiction_shared"},
    ]
    with client.app.state.session_factory() as db:
        items = registered_table_catalog(db, str(DEMO_WORKSPACE_ID), {"datasets": datasets})
    shared = {i["schema_name"]: i["datasets"] for i in items if i["connection_id"] == server.id and i["table_name"] == "fiction_shared"}
    assert [d["id"] for d in shared[SCHEMAS[0]]] == ["fiction-explicit"]
    assert shared[SCHEMAS[1]] == []


def test_doris_information_schema_prefix_is_matched_exactly(server):
    with server.engine.begin() as conn:
        conn.info["source_kind"] = "doris"
        conn.exec_driver_sql("INSERT INTO information_schema.tables VALUES ('fiction_catalog:fiction_alpha', 'fiction_prefixed_only', 'BASE TABLE', '')")
        assert list_tables(conn, "fiction_catalog:fiction_alpha") == ["fiction_prefixed_only"]
        assert set(list_tables(conn, SCHEMAS[0])) == INVENTORY[SCHEMAS[0]]


def test_migration_clears_old_inventories_and_preserves_models(client, server):
    finished(client, server, SCHEMAS[0])
    path = Path(__file__).parents[1] / "src/ontofoundry_api/alembic/versions/20261022_000001_server_wide_connections.py"
    spec = spec_from_file_location("server_wide_connections", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with client.app.state.engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        before = {table: conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() for table in ("workspaces", "ontology_versions", "data_connections")}
        postgres = conn.execute(sa.text("SELECT config_json FROM data_connections WHERE kind = 'postgresql'")).all()
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        migration.upgrade()
        for table in ("metadata_snapshots", "metadata_sync_jobs", "metadata_sync_batches"):
            assert conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0
        assert {table: conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() for table in before} == before
        assert conn.execute(sa.text("SELECT config_json FROM data_connections WHERE kind = 'postgresql'")).all() == postgres
    with client.app.state.session_factory() as db:
        assert db.get(ConnectionRecord, server.id).config_json["database"] == ""


def test_stale_snapshot_survives_full_sync_as_missing_until_migration(client, server):
    with client.app.state.session_factory() as db:
        for schema in SCHEMAS:
            db.add(MetadataSnapshotRecord(
                connection_id=server.id, schema_name=schema,
                snapshot_json={"tables": [{"name": "fiction_default_only", "schema": schema, "columns": []}]}, changes_json=[],
            ))
        db.commit()
    for schema in SCHEMAS:
        finished(client, server, schema)
        stored = snapshot(client, server, schema)
        assert stored["fiction_default_only"]["missing"]
        assert {name for name, table in stored.items() if not table["missing"]} == INVENTORY[schema]
        response = client.get(ROOT + f"/connections/{server.id}/assets", params={"schema_name": schema}).json()
        assert "fiction_default_only" in {t["name"] for t in response["items"]}
    registered = client.get(ROOT + "/registered-tables").json()["items"]
    assert not any(t["table_name"] == "fiction_default_only" for t in registered)


def test_retry_keeps_stale_inventory_and_cannot_discover_the_correct_tables(client, server):
    identity = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(MetadataSyncJobRecord(
            id=identity, workspace_id=str(DEMO_WORKSPACE_ID), connection_id=server.id,
            schema_name=SCHEMAS[0], scope="all", state="partial_failed", created_by=DEV_USER_ID,
            inventory_json=["fiction_default_only"],
        ))
        db.flush()
        db.add(MetadataSyncBatchRecord(
            id=str(uuid4()), job_id=identity, ordinal=0, state="failed",
            table_names_json=["fiction_default_only"], results_json=[], history_json=[],
        ))
        db.commit()
    base = ROOT + f"/connections/{server.id}/assets/sync-jobs/{identity}"
    assert client.post(base + "/retry").status_code == 202
    retried = client.get(base).json()
    assert retried["state"] == "succeeded" and retried["total"] == 1 and retried["available"] == 0
    assert retried["batches"][0]["tables"] == ["fiction_default_only"]
    assert retried["batches"][0]["results"][0]["state"] == "missing"
    assert snapshot(client, server, SCHEMAS[0]) == {}
    finished(client, server, SCHEMAS[0])
    assert set(snapshot(client, server, SCHEMAS[0])) == INVENTORY[SCHEMAS[0]]


@pytest.mark.parametrize("kind", ["mysql", "doris"])
def test_low_level_readers_reject_empty_schema_before_using_driver_defaults(kind):
    source = SimpleNamespace(info={"source_kind": kind})
    for reader in (lambda: list_tables(source, None), lambda: metadata_sync.read_table(source, None, "fiction_shared")):
        with pytest.raises(ServiceError) as error:
            reader()
        assert error.value.code == "SCHEMA_REQUIRED"


def test_postgresql_keeps_its_configured_or_public_default_schema():
    source = SimpleNamespace(kind="postgresql", config_json={"database": "fiction_database"})
    assert metadata_sync.normalize_schema(source, None) == "public"
    source.config_json["schema_name"] = "fiction_schema"
    assert metadata_sync.normalize_schema(source, "") == "fiction_schema"
    assert metadata_sync.normalize_schema(source, "fiction_other") == "fiction_other"


def test_mysql_dialect_uses_default_only_when_schema_is_none(monkeypatch):
    dialect = MySQLDialect_pymysql()
    dialect.default_schema_name = "fiction_default"
    dialect._connection_charset = "utf8mb4"
    statements = []

    class Result:
        def fetchall(self):
            return [("fiction_shared", "BASE TABLE")]

        def fetchone(self):
            return ("id",)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def execute(statement, **kwargs):
        statements.append(statement)
        return Result()

    source = SimpleNamespace(exec_driver_sql=execute)
    monkeypatch.setattr(dialect, "_ensure_has_table_connection", lambda _: None)
    for schema in (None, *SCHEMAS):
        dialect.get_table_names(source, schema=schema)
        dialect.get_view_names(source, schema=schema)
        dialect.has_table(source, "fiction_shared", schema=schema)
    assert statements == [
        statement
        for schema in ("fiction_default", *SCHEMAS)
        for statement in (f"SHOW FULL TABLES FROM `{schema}`", f"SHOW FULL TABLES FROM `{schema}`", f"DESCRIBE `{schema}`.`fiction_shared`")
    ]


@pytest.mark.parametrize("kind", ["mysql", "doris", "postgresql"])
def test_readonly_url_never_selects_default_database_for_mysql_or_doris(kind, monkeypatch):
    urls = []

    class Engine:
        @contextmanager
        def connect(self):
            yield SimpleNamespace(info={}, execute=lambda _: None, rollback=lambda: None)

        def dispose(self):
            pass

    def engine(url, **kwargs):
        urls.append(url)
        return Engine()

    monkeypatch.setattr(readonly, "create_engine", engine)
    item = SimpleNamespace(kind=kind, config_json={"database": "fiction_legacy"}, secret_encrypted="")
    with readonly.connect_readonly(item, None):
        pass
    assert urls[0].database == ("fiction_legacy" if kind == "postgresql" else None)


def test_doris_type_fallback_qualifies_and_escapes_database_and_table():
    executed = []
    responses = iter([
        SimpleNamespace(first=lambda: ("BASE TABLE", "")),
        SimpleNamespace(all=lambda: [("id", "", "", "NO", "", "PRI")]),
    ])

    def shown(sql):
        executed.append(sql)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [{"Field": "id", "Type": "bigint"}]))

    source = SimpleNamespace(info={"source_kind": "doris"}, execute=lambda *args: next(responses), exec_driver_sql=shown)
    table = read_doris_table(source, "fiction`alpha", "fiction`shared", "t")
    assert executed == ["SHOW FULL COLUMNS FROM `fiction``alpha`.`fiction``shared`"]
    assert table["columns"][0]["type"] == "bigint"


def test_synced_tables_are_listed_per_database_without_a_schema_or_the_source(client, server, monkeypatch):
    base = ROOT + f"/connections/{server.id}"
    for schema in SCHEMAS:
        finished(client, server, schema, "selected", ["fiction_shared", f"{schema}_only"])

    # The data tables page reads what was synced; it must not open the source.
    def no_source(*args, **kwargs):
        raise AssertionError("listing synced tables must not connect to the source")

    monkeypatch.setattr(assets, "connect_readonly", no_source)
    response = client.get(base + "/assets/synced")
    assert response.status_code == 200, response.text
    groups = {g["schema"]: g["assets"] for g in response.json()["items"]}
    assert set(groups) == set(SCHEMAS)
    for schema in SCHEMAS:
        assert {t["name"] for t in groups[schema]["items"]} == {"fiction_shared", f"{schema}_only"}
        assert all(t["schema"] == schema for t in groups[schema]["items"])
