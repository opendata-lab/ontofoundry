"""Run the actual migration chain on disposable PostgreSQL, without create_all."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from core1_fixtures import EXAMPLES_DIR
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from test_core1_cutover import postgres_cutover_database as _postgres_cutover_database
from test_core1_import_flow import accept, batch, confirm, preview, publish

from ontofoundry_api.config import Settings
from ontofoundry_api.db_models import ImportRecord, OntologyVersionRecord, WorkspaceRecord
from ontofoundry_api.main import create_app

postgres_cutover_database = _postgres_cutover_database


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL"),
    reason="Disposable PostgreSQL not supplied",
)
@pytest.mark.parametrize("starting", ["base", "20261016_000001"])
def test_postgres_import_upgrade_preserves_core_and_runs_http_lifecycle(
    postgres_cutover_database,
    tmp_path,
    starting,
):
    engine, upgrade = postgres_cutover_database
    if starting != "base":
        upgrade(starting)
    upgrade("head")
    assert {c["name"] for c in inspect(engine).get_columns("ontology_imports")} == set(
        ImportRecord.__table__.columns.keys()
    )
    settings = Settings(
        environment="test",
        database_url=engine.url.render_as_string(hide_password=False),
        data_dir=tmp_path / "files",
        auto_create_schema=False,
        seed_demo=False,
        auth_mode="dev",
        session_secret="fictional-import-secret-more-than-32-characters",
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/v1/workspaces",
            json={
                "name": "虚构迁移" + uuid4().hex[:8],
                "slug": "fiction-migration-" + uuid4().hex[:8],
            },
        ).json()["id"]
        p = preview(
            client, wid, (EXAMPLES_DIR / "07-instances-and-evidence.json").read_bytes()
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: confirm(client, wid, p), range(2)))
        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
        assert responses[0].json() == responses[1].json()
        result = responses[0].json()
        assert batch(client, wid, result)["items"]
        published = publish(client, wid, accept(client, wid, result))
        with client.app.state.session_factory() as db:
            before = db.get(WorkspaceRecord, wid).current_version_id
            snapshot = db.get(OntologyVersionRecord, before).snapshot_json
        upgrade("head")
        with client.app.state.session_factory() as db:
            assert db.get(WorkspaceRecord, wid).current_version_id == before
            assert db.get(OntologyVersionRecord, before).snapshot_json == snapshot
            assert db.scalar(select(ImportRecord.id)) == p["import_id"]
        assert published
