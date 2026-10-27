"""Remove obsolete proposal states and failed batches.

Revision ID: 20261026_000001
Revises: 20261025_000001
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "20261026_000001"
down_revision = "20261025_000001"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    metadata = sa.MetaData()
    tables = {name: sa.Table(name, metadata, autoload_with=db) for name in (
        "proposal_batches", "proposal_items", "proposal_item_dependencies",
        "proposal_decision_items", "proposal_decision_requests",
    )}
    batches, items = tables["proposal_batches"], tables["proposal_items"]
    deps, decisions, requests = (tables[name] for name in (
        "proposal_item_dependencies", "proposal_decision_items", "proposal_decision_requests"))
    failed = sa.select(batches.c.id).where(batches.c.status == "failed")
    removed = sa.select(items.c.id).where(sa.or_(items.c.status == "unacceptable", items.c.batch_id.in_(failed)))
    request_ids = list(db.scalars(sa.select(decisions.c.request_id).where(decisions.c.item_id.in_(removed))))
    if request_ids:
        db.execute(sa.delete(decisions).where(decisions.c.request_id.in_(request_ids)))
        db.execute(sa.delete(requests).where(requests.c.id.in_(request_ids)))
    db.execute(sa.delete(deps).where(sa.or_(deps.c.item_id.in_(removed), deps.c.depends_on_item_id.in_(removed))))
    db.execute(sa.delete(items).where(items.c.id.in_(removed)))
    imports = sa.Table("ontology_imports", metadata, autoload_with=db)
    db.execute(sa.update(imports).where(imports.c.batch_id.in_(failed)).values(batch_id=None))
    db.execute(sa.delete(batches).where(batches.c.status == "failed"))
    db.execute(sa.update(items).where(items.c.status == "superseded").values(status="rejected"))
    # Older batches are read-only now (session_gate.batch_read_only), so a
    # pending proposal left in one could never be decided and would block the
    # session for good. Reject exactly those.
    sessions = sa.Table("modeling_sessions", metadata, autoload_with=db)
    started = {}
    for session_id, manifest in db.execute(sa.select(sessions.c.id, sessions.c.run_manifest_json)):
        if isinstance(manifest, str):
            manifest = json.loads(manifest or "null")
        started[session_id] = (manifest or {}).get("source_session_revision", -1)
    stale = [
        batch_id
        for batch_id, session_id, revision in db.execute(
            sa.select(batches.c.id, batches.c.session_id, batches.c.source_session_revision)
        )
        if started.get(session_id, -1) > revision
    ]
    if stale:
        db.execute(
            sa.update(items)
            .where(items.c.status == "pending", items.c.batch_id.in_(stale))
            .values(status="rejected")
        )


def downgrade():
    pass
