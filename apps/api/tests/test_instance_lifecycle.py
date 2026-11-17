"""AI-11: instances follow the definitions' lifecycle; accepted changes wait for publish."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_instance_store import accept_all, baseline, instance_update
from test_modeling import ROOT, create_session, publish
from test_t4_proposal_decisions import decide, seed_batch

from ontofoundry_api.db_models import InstanceDraftRecord


def public(client, target_id):
    return next(i for i in client.get(ROOT + "/instances").json()["items"] if i["target_id"] == target_id)


def test_abandoning_a_session_discards_its_pending_changes(client):
    session, other = create_session(client), create_session(client)
    entry = baseline(client, session)["items"][0]
    session, _ = accept_all(client, session, [instance_update(entry, values={"label": "放弃前修改"})])
    blocked = seed_batch(client, other, [instance_update(entry, values={"label": "另一会话修改"})])
    refused = decide(client, other, [(blocked["items"][0]["id"], "accept")])
    assert refused.json()["error"]["code"] == "INSTANCE_PENDING_ELSEWHERE"

    abandoned = client.post(ROOT + f"/sessions/{session['id']}/abandon",
                            json={"expected_session_revision": session["revision"]})
    assert abandoned.status_code == 200, abandoned.text
    with client.app.state.session_factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(InstanceDraftRecord)) == 0
    assert public(client, entry["target_id"])["element"] == entry["element"]
    history = client.get(ROOT + f"/instances/material_object/{entry['target_id']}/history",
                         params={"session_id": session["id"]}).json()["items"]
    assert "abandon_session" not in {h["operation"] for h in history}
    # The instance is free again for the other session.
    accepted = decide(client, other, [(blocked["items"][0]["id"], "accept")])
    assert accepted.status_code == 200, accepted.text


def test_publishing_applies_pending_changes_in_one_step(client):
    session = create_session(client)
    entry = baseline(client, session)["items"][0]
    session, _ = accept_all(client, session, [instance_update(entry, values={"label": "发布后可见"})])
    assert public(client, entry["target_id"])["element"]["values"]["label"] != "发布后可见"
    published = publish(client, session)
    assert published.status_code == 200, published.text
    shown = public(client, entry["target_id"])
    assert shown["element"]["values"]["label"] == "发布后可见" and shown["state"] == "active"
    history = client.get(ROOT + f"/instances/material_object/{entry['target_id']}/history").json()["items"]
    assert history[-1]["operation"] == "activate"
    assert len({h["revision"] for h in history}) == len(history)
    with client.app.state.session_factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(InstanceDraftRecord)) == 0


def migration():
    path = Path(__file__).parents[1] / "src/ontofoundry_api/alembic/versions/20261117_000002_instance_drafts.py"
    spec = importlib.util.spec_from_file_location("instance_drafts_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_and_removes_the_draft_table(monkeypatch):
    module = migration()
    with sa.create_engine("sqlite://").begin() as conn:
        conn.execute(sa.text("CREATE TABLE workspaces (id VARCHAR(36) PRIMARY KEY)"))
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        module.upgrade()
        conn.execute(sa.text(
            "INSERT INTO instance_drafts (id, workspace_id, session_id, kind, target_id, revision, updated_at) "
            "VALUES ('d1', 'w', 's', 'material_object', 't', 2, '2026-11-17')"))
        with pytest.raises(sa.exc.IntegrityError):  # one pending change per instance
            conn.execute(sa.text(
                "INSERT INTO instance_drafts (id, workspace_id, session_id, kind, target_id, revision, updated_at) "
                "VALUES ('d2', 'w', 's2', 'material_object', 't', 2, '2026-11-17')"))
        module.downgrade()
        assert "instance_drafts" not in sa.inspect(conn).get_table_names()
