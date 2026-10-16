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


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL"),
    reason="Disposable PostgreSQL not supplied; fresh base→head and old head→head remain unverified",
)
@pytest.mark.parametrize("starting", ["base", "20261009_000001"])
def test_postgres_fresh_and_old_head_upgrade(starting, tmp_path):
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
        if starting != "base":
            upgrade(starting)
        upgrade("head")
        engine = sa.create_engine(disposable)
        with engine.connect() as c:
            assert (
                c.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                == "20261016_000001"
            )
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()
