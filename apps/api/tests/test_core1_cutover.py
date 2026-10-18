"""Cutover deletes ontology content and preserves business/platform configuration."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_modeling import create_session

from ontofoundry_api.database import Base

PATH = (
    Path(__file__).parents[1]
    / "src/ontofoundry_api/alembic/versions/20261016_000001_core1_cutover.py"
)


def migration():
    spec = importlib.util.spec_from_file_location("cutover", PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_old_head_cutover_sqlite_is_idempotent_preserves_unrelated_rows(client):
    session = create_session(client)
    from test_t4_proposal_decisions import chain, decide, seed_batch

    batch = seed_batch(client, session, chain(session))
    accepted = decide(client, session, [(item["id"], "accept") for item in batch["items"]])
    assert accepted.status_code == 200, accepted.text
    material = client.post(
        f"/api/v1/workspaces/{session['workspace_id']}/materials",
        params={"name": "虚构迁移材料.md"},
        content="保留材料".encode(),
    )
    assert material.status_code == 201
    engine = client.app.state.engine
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql("ALTER TABLE proposal_items DROP COLUMN atomic_group_id")
        conn.exec_driver_sql(
            "ALTER TABLE ontology_versions ADD COLUMN ossie_json JSON NOT NULL DEFAULT '{}'"
        )
        keep = [
            t
            for t in Base.metadata.tables
            if t
            in {
                "users",
                "workspaces",
                "workspace_members",
                "materials",
                "material_chunks",
                "data_connections",
                "service_tokens",
                "service_token_scopes",
                "metadata_snapshots",
            }
        ]
        before = {
            t: conn.execute(sa.text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in keep
        }
        m = migration()
        m.op = Operations(MigrationContext.configure(conn))
        m.upgrade()
        m.discard_ontology(conn)
        for t in [
            "modeling_sessions",
            "ontology_element_identities",
            "ontology_versions",
            "proposal_items",
            "proposal_batches",
            "proposal_decision_requests",
        ]:
            assert conn.execute(sa.text(f'SELECT COUNT(*) FROM "{t}"')).scalar() == 0
        assert {
            t: conn.execute(sa.text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in keep
        } == before
        assert not conn.execute(
            sa.text("SELECT current_version_id FROM workspaces")
        ).scalar()
        assert "ossie_json" not in {
            c["name"] for c in sa.inspect(conn).get_columns("ontology_versions")
        }
        assert "atomic_group_id" in {
            c["name"] for c in sa.inspect(conn).get_columns("proposal_items")
        }


@pytest.fixture
def postgres_cutover_database():
    import subprocess
    import sys

    from sqlalchemy.engine import make_url

    url = os.environ["ONTOFOUNDRY_TEST_POSTGRES_URL"]
    name = "of_core1_" + uuid4().hex[:12]
    admin = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    disposable = make_url(url).set(database=name).render_as_string(hide_password=False)
    api = Path(__file__).parents[1]
    engine = sa.create_engine(disposable)

    def upgrade(rev):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "src/ontofoundry_api/alembic.ini",
                "upgrade",
                rev,
            ],
            cwd=api,
            env={
                **os.environ,
                "ONTOFOUNDRY_DATABASE_URL": disposable,
                "ONTOFOUNDRY_SEED_DEMO": "false",
            },
            check=True,
            capture_output=True,
        )

    try:
        yield engine, upgrade
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL"),
    reason="Disposable PostgreSQL not supplied; fresh base→head and old head→head remain unverified",
)
@pytest.mark.parametrize("starting", ["base", "20261009_000001"])
def test_postgres_fresh_and_old_head_upgrade(starting, postgres_cutover_database):
    engine, upgrade = postgres_cutover_database
    if starting != "base":
        upgrade(starting)
    upgrade("20261016_000001")
    with engine.connect() as c:
        assert (
            c.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            == "20261016_000001"
        )


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL"),
    reason="Disposable PostgreSQL not supplied; populated old head→head remains unverified",
)
def test_postgres_populated_cutover_preserves_platform_rows(postgres_cutover_database):
    engine, upgrade = postgres_cutover_database
    upgrade("20261009_000001")
    keep = {
        "users",
        "workspaces",
        "workspace_members",
        "materials",
        "material_chunks",
        "data_connections",
        "service_tokens",
        "service_token_scopes",
        "metadata_snapshots",
    }
    discard = {
        "ontology_versions",
        "ontology_element_identities",
        "modeling_sessions",
        "proposal_batches",
        "proposal_items",
        "proposal_item_dependencies",
        "proposal_decision_requests",
        "proposal_decision_items",
    }

    def snapshot(conn):
        metadata = sa.MetaData()
        metadata.reflect(bind=conn)
        return {
            name: [
                dict(row)
                for row in conn.execute(
                    sa.select(table).order_by(*table.primary_key.columns)
                ).mappings()
            ]
            for name, table in metadata.tables.items()
        }

    with engine.begin() as conn:
        assert set(sa.inspect(conn).get_table_names()) == keep | discard | {
            "alembic_version"
        }
        old_version_columns = {
            c["name"] for c in sa.inspect(conn).get_columns("ontology_versions")
        }
        old_item_columns = {
            c["name"] for c in sa.inspect(conn).get_columns("proposal_items")
        }
        assert "ossie_json" in old_version_columns
        assert "atomic_group_id" not in old_item_columns
        conn.exec_driver_sql(
            """
            INSERT INTO users (id, subject, display_name, email, created_at)
            VALUES ('cutover-user', 'fictional:cutover', '虚构迁移用户',
                    'cutover@example.invalid', '2026-10-01T08:30:00Z');
            INSERT INTO workspaces
                (id, slug, name, description, created_by, current_version_id,
                 created_at, updated_at)
            VALUES ('cutover-space', 'fictional-cutover', '虚构迁移空间', '保留配置',
                    'cutover-user', NULL,
                    '2026-10-01T08:30:00Z', '2026-10-02T09:00:00Z');
            INSERT INTO workspace_members (workspace_id, user_id, role, created_at)
            VALUES ('cutover-space', 'cutover-user', 'owner', '2026-10-01T08:30:00Z');
            INSERT INTO materials
                (id, workspace_id, name, sha256, byte_size, chunk_count,
                 created_at, archived_at, archived_by)
            VALUES ('cutover-material', 'cutover-space', '虚构采购说明.md',
                    repeat('a', 64), 36, 2, '2026-10-01T08:30:00Z',
                    '2026-10-02T09:00:00Z', 'cutover-user');
            INSERT INTO material_chunks (material_id, ordinal, line_start, line_end, text)
            VALUES ('cutover-material', 0, 1, 1, '采购订单说明'),
                   ('cutover-material', 1, 2, 2, '材料分块应保留');
            INSERT INTO data_connections
                (id, workspace_id, name, kind, config_json, secret_encrypted)
            VALUES ('cutover-connection', 'cutover-space', '虚构采购数据源',
                    'postgresql', '{"database":"fictional_procurement","schema":"public"}',
                    'fictional-encrypted-secret');
            INSERT INTO metadata_snapshots
                (connection_id, schema_name, snapshot_json, changes_json, observed_at, error)
            VALUES ('cutover-connection', 'public',
                    '{"tables":[{"name":"fictional_orders","columns":["order_no"]}]}',
                    '{"added":["fictional_orders"]}', '2026-10-02T09:00:00Z',
                    '虚构历史采集提示');
            INSERT INTO service_tokens
                (id, workspace_id, created_by, name, token_hash, created_at)
            VALUES ('cutover-token', 'cutover-space', 'cutover-user', '虚构只读令牌',
                    repeat('b', 64), '2026-10-01T08:30:00Z');
            INSERT INTO service_token_scopes (token_id, scope)
            VALUES ('cutover-token', 'ontology:read'), ('cutover-token', 'materials:read');
            INSERT INTO ontology_versions
                (id, workspace_id, version_number, status, message, snapshot_json,
                 ossie_json, validation_json, sha256, published_by, created_at)
            VALUES ('cutover-version', 'cutover-space', 1, 'published', '虚构旧版本',
                    '{"schema_version":"3","object_types":[{"id":"cutover-object"}]}',
                    '{"name":"fictional_ontology"}', '{"valid":true}', repeat('c', 64),
                    'cutover-user', '2026-10-01T08:30:00Z');
            UPDATE workspaces SET current_version_id = 'cutover-version'
            WHERE id = 'cutover-space';
            INSERT INTO ontology_element_identities
                (workspace_id, element_id, kind, created_at, created_by)
            VALUES ('cutover-space', 'cutover-object', 'object_type',
                    '2026-10-01T08:30:00Z', 'cutover-user');
            INSERT INTO modeling_sessions
                (id, workspace_id, created_by, title, base_version_id, revision,
                 draft_json, candidates_json, material_ids, task_status, task_detail,
                 updated_at, base_version_sha256, draft_sha256, run_manifest_json,
                 dataagent_topic_id, dataagent_task_id, uploaded_material_ids)
            VALUES ('cutover-session', 'cutover-space', 'cutover-user', '虚构旧建模会话',
                    'cutover-version', 2,
                    '{"schema_version":"3","object_types":[{"id":"cutover-object"}]}',
                    '[{"name":"虚构导入候选"}]', '["cutover-material"]', 'idle', '',
                    '2026-10-02T09:00:00Z', repeat('c', 64), repeat('d', 64),
                    '{"material_ids":["cutover-material"]}', 'fictional-topic',
                    'fictional-task', '["cutover-material"]');
            INSERT INTO proposal_batches
                (id, workspace_id, session_id, dataagent_task_id, run_token,
                 schema_version, base_version_id, base_version_sha256,
                 source_session_revision, source_draft_sha256, material_manifest_json,
                 producer_json, result_sha256, status, created_at)
            VALUES ('cutover-batch', 'cutover-space', 'cutover-session', 'fictional-task',
                    'fictional-run', 'ontofoundry.proposals/v1', 'cutover-version',
                    repeat('c', 64), 1, repeat('d', 64), '[{"id":"cutover-material"}]',
                    '{"name":"fictional-agent"}', repeat('e', 64), 'ready',
                    '2026-10-02T09:00:00Z');
            INSERT INTO proposal_items
                (id, batch_id, workspace_id, session_id, ordinal, client_ref,
                 fingerprint, operation, target_kind, target_id, after_json,
                 evidence_json, status, decided_by, decided_at, accepted_revision)
            VALUES ('cutover-item-object', 'cutover-batch', 'cutover-space',
                    'cutover-session', 0, 'object', repeat('f', 64), 'create',
                    'object_type', 'cutover-object', '{"name":"虚构采购订单"}',
                    '[{"material_id":"cutover-material","line_start":1}]',
                    'accepted', 'cutover-user', '2026-10-02T09:00:00Z', 2),
                   ('cutover-item-property', 'cutover-batch', 'cutover-space',
                    'cutover-session', 1, 'property', repeat('1', 64), 'create',
                    'property', 'cutover-property',
                    '{"owner_type_id":"cutover-object","technical_name":"order_no"}',
                    '[]', 'accepted', 'cutover-user', '2026-10-02T09:00:00Z', 2);
            INSERT INTO proposal_item_dependencies
                (workspace_id, session_id, batch_id, item_id, depends_on_item_id)
            VALUES ('cutover-space', 'cutover-session', 'cutover-batch',
                    'cutover-item-property', 'cutover-item-object');
            INSERT INTO proposal_decision_requests
                (id, workspace_id, session_id, idempotency_key, request_sha256,
                 expected_session_revision, result_session_revision, response_json,
                 actor_id, created_at)
            VALUES ('cutover-request', 'cutover-space', 'cutover-session',
                    'fictional-decision', repeat('2', 64), 1, 2, '{"revision":2}',
                    'cutover-user', '2026-10-02T09:00:00Z');
            INSERT INTO proposal_decision_items
                (workspace_id, session_id, request_id, batch_id, item_id, decision)
            VALUES ('cutover-space', 'cutover-session', 'cutover-request',
                    'cutover-batch', 'cutover-item-object', 'accept'),
                   ('cutover-space', 'cutover-session', 'cutover-request',
                    'cutover-batch', 'cutover-item-property', 'accept');
            """
        )
        before = snapshot(conn)
        assert all(before[name] for name in keep | discard)
        assert before["alembic_version"] == [{"version_num": "20261009_000001"}]
        assert before["workspaces"][0]["current_version_id"] == "cutover-version"

    expected_keep = {name: before[name] for name in keep}
    # Clearing the published pointer is the only allowed change to a retained row.
    expected_keep["workspaces"] = [
        {**row, "current_version_id": None} for row in before["workspaces"]
    ]
    first_result = None
    for _ in range(2):
        upgrade("20261016_000001")
        with engine.connect() as conn:
            after = snapshot(conn)
            assert set(after) == set(before)
            assert {name: len(after[name]) for name in keep} == {
                name: len(before[name]) for name in keep
            }
            assert {name: after[name] for name in keep} == expected_keep
            assert {name: after[name] for name in discard} == {name: [] for name in discard}
            assert after["alembic_version"] == [{"version_num": "20261016_000001"}]
            inspector = sa.inspect(conn)
            assert {
                c["name"] for c in inspector.get_columns("ontology_versions")
            } == old_version_columns - {"ossie_json"}
            item_columns = {c["name"]: c for c in inspector.get_columns("proposal_items")}
            assert set(item_columns) == old_item_columns | {"atomic_group_id"}
            assert item_columns["atomic_group_id"]["nullable"] is True
            assert isinstance(item_columns["atomic_group_id"]["type"], sa.String)
            assert item_columns["atomic_group_id"]["type"].length == 36
            if first_result is None:
                first_result = after
            else:
                assert after == first_result
