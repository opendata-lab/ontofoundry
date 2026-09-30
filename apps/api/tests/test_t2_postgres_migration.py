"""T2: the proposal-first migration on real PostgreSQL (opt-in).

Builds a database at the previous head, fills it the way a v1-era deployment
looks (v1 snapshots and drafts), upgrades, checks the backfill and that the
composite keys reject cross-scope rows, then downgrades and upgrades again.
Needs ONTOFOUNDRY_TEST_POSTGRES_URL (see test_t0_postgres_publish).
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from test_t1_v2_model import v1_demo

from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.snapshot import as_v2_dict

ADMIN_URL = os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="Disposable PostgreSQL not supplied")
API = Path(__file__).parents[1]
PREVIOUS = "20260921_000003"


def alembic(url: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/ontofoundry_api/alembic.ini", *args],
        cwd=API,
        env={**os.environ, "ONTOFOUNDRY_DATABASE_URL": url},
        check=True,
        capture_output=True,
    )


@pytest.fixture
def database():
    name = "of_t2_" + uuid4().hex[:12]
    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    engine = sa.create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def seed_v1_deployment(engine) -> dict:
    v1 = v1_demo()
    workspace_id = v1["workspace_id"]
    user_id, version_id, session_id = str(uuid4()), str(uuid4()), str(uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO users (id, subject, display_name, created_at) VALUES (:id, :s, 'u', now())"),
            {"id": user_id, "s": "sub-" + user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO workspaces (id, slug, name, description, created_by, created_at, updated_at) "
                "VALUES (:id, 'demo', 'Demo', '', :u, now(), now())"
            ),
            {"id": workspace_id, "u": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO ontology_versions (id, workspace_id, version_number, status, message, "
                "snapshot_json, ossie_json, validation_json, sha256, published_by, created_at) "
                "VALUES (:id, :w, 1, 'published', '', :snap, '{}', '{}', :sha, :u, now())"
            ),
            {"id": version_id, "w": workspace_id, "snap": json.dumps(v1), "sha": "a" * 64, "u": user_id},
        )
        conn.execute(
            sa.text("UPDATE workspaces SET current_version_id = :v WHERE id = :w"),
            {"v": version_id, "w": workspace_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO modeling_sessions (id, workspace_id, created_by, title, base_version_id, "
                "revision, draft_json, candidates_json, material_ids, task_status, task_detail, updated_at) "
                "VALUES (:id, :w, :u, 's', :v, 3, :draft, '[]', '[]', 'idle', '', now())"
            ),
            {"id": session_id, "w": workspace_id, "u": user_id, "v": version_id, "draft": json.dumps(v1)},
        )
    return {"v1": v1, "workspace_id": workspace_id, "session_id": session_id, "user_id": user_id}


def test_upgrade_backfills_and_constraints_hold_then_round_trips(database):
    url, engine = database
    alembic(url, "upgrade", PREVIOUS)
    seeded = seed_v1_deployment(engine)
    alembic(url, "upgrade", "head")

    expected = as_v2_dict(seeded["v1"])
    with engine.connect() as conn:
        base, draft = conn.execute(
            sa.text("SELECT base_version_sha256, draft_sha256 FROM modeling_sessions WHERE id = :id"),
            {"id": seeded["session_id"]},
        ).one()
        assert base == draft == snapshot_sha256(expected)
        identities = dict(
            conn.execute(sa.text("SELECT element_id, kind FROM ontology_element_identities")).all()
        )
        # Every element of the v1 head, including normalized legacy rules.
        assert identities == {
            element["id"]: kind
            for kind, collection in (
                ("object_type", "object_types"), ("property", "properties"),
                ("link_type", "link_types"), ("rule", "rules"),
                ("material_object", "material_objects"),
            )
            for element in expected[collection]
        }
        nullable = conn.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'modeling_sessions' AND column_name = 'draft_sha256'"
            )
        ).scalar()
        assert nullable == "NO"

    # Composite keys: a batch for another workspace's session must fail.
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO proposal_batches (id, workspace_id, session_id, run_token, schema_version, "
                "base_version_sha256, source_session_revision, source_draft_sha256, result_sha256, status) "
                "VALUES (:id, :w, :s, 'r', 'v1', :h, 0, :h, :h, 'available')"
            ),
            {"id": str(uuid4()), "w": str(uuid4()), "s": seeded["session_id"], "h": "0" * 64},
        )

    alembic(url, "downgrade", PREVIOUS)
    with engine.connect() as conn:
        tables = set(sa.inspect(conn).get_table_names())
        assert "proposal_batches" not in tables
        # The historical snapshot is exactly as it was.
        stored = conn.execute(sa.text("SELECT snapshot_json FROM ontology_versions")).scalar()
        assert stored == seeded["v1"]
    alembic(url, "upgrade", "head")


def test_an_id_used_as_two_kinds_stops_the_migration(database):
    url, engine = database
    alembic(url, "upgrade", PREVIOUS)
    seeded = seed_v1_deployment(engine)
    clash = dict(seeded["v1"])
    clash["link_types"] = [dict(clash["link_types"][0], id=clash["object_types"][0]["id"])] + clash[
        "link_types"
    ][1:]
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO ontology_versions (id, workspace_id, version_number, status, message, "
                "snapshot_json, ossie_json, validation_json, sha256, published_by, created_at) "
                "VALUES (:id, :w, 2, 'published', '', :snap, '{}', '{}', :sha, :u, now())"
            ),
            {
                "id": str(uuid4()),
                "w": seeded["workspace_id"],
                "snap": json.dumps(clash),
                "sha": "b" * 64,
                "u": seeded["user_id"],
            },
        )
    with pytest.raises(subprocess.CalledProcessError) as err:
        alembic(url, "upgrade", "head")
    assert "不同类型" in err.value.stderr.decode()
