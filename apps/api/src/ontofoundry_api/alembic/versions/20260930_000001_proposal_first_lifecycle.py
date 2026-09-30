"""Proposal-first lifecycle: identities, proposals, decisions, pinned hashes.

Adds the element identity registry, proposal batches/items/dependencies,
decision requests/items, session base/draft hashes and run manifests, and
material archiving. Existing rows are backfilled from the stored snapshots
through the same v1→v2 normalization the application reads with; historical
version rows are never rewritten.

The identity backfill stops the migration if one id was ever used as two
different kinds, listing them, instead of renumbering anything.

Revision ID: 20260930_000001
Revises: 20260921_000003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260930_000001"
down_revision = "20260921_000003"
branch_labels = None
depends_on = None


def _json(value):
    import json

    return json.loads(value) if isinstance(value, str) else value


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_modeling_sessions_ws_id", "modeling_sessions", ["workspace_id", "id"]
    )
    op.add_column("modeling_sessions", sa.Column("base_version_sha256", sa.String(64), nullable=True))
    op.add_column("modeling_sessions", sa.Column("draft_sha256", sa.String(64), nullable=True))
    op.add_column("modeling_sessions", sa.Column("run_manifest_json", sa.JSON(), nullable=True))
    op.add_column("materials", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "materials",
        sa.Column("archived_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "ontology_element_identities",
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("element_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("workspace_id", "element_id"),
        sa.UniqueConstraint("workspace_id", "element_id", "kind", name="uq_element_identity_kind"),
    )
    op.create_table(
        "proposal_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("dataagent_task_id", sa.String(64), nullable=True),
        sa.Column("run_token", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("base_version_id", sa.String(36), nullable=True),
        sa.Column("base_version_sha256", sa.String(64), nullable=False),
        sa.Column("source_session_revision", sa.Integer(), nullable=False),
        sa.Column("source_draft_sha256", sa.String(64), nullable=False),
        sa.Column("material_manifest_json", sa.JSON(), nullable=True),
        sa.Column("producer_json", sa.JSON(), nullable=True),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "session_id", "run_token", name="uq_batch_run"),
        sa.UniqueConstraint("workspace_id", "session_id", "result_sha256", name="uq_batch_result"),
        sa.UniqueConstraint("workspace_id", "session_id", "id", name="uq_batch_scope"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
            name="fk_batch_session",
        ),
    )
    op.create_index("ix_proposal_batches_session", "proposal_batches", ["session_id"])
    op.create_table(
        "proposal_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("client_ref", sa.String(80), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(8), nullable=False),
        sa.Column("target_kind", sa.String(24), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("expected_target_hash", sa.String(64), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("field_changes_json", sa.JSON(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_item_ordinal"),
        sa.UniqueConstraint("batch_id", "fingerprint", name="uq_item_fingerprint"),
        sa.UniqueConstraint("workspace_id", "session_id", "batch_id", "id", name="uq_item_scope"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id"],
            ["proposal_batches.workspace_id", "proposal_batches.session_id", "proposal_batches.id"],
            name="fk_item_batch",
        ),
    )
    op.create_index("ix_proposal_items_batch", "proposal_items", ["batch_id"])
    op.create_index("ix_proposal_items_target", "proposal_items", ["target_id"])
    item_cols = ["proposal_items.workspace_id", "proposal_items.session_id", "proposal_items.batch_id", "proposal_items.id"]
    op.create_table(
        "proposal_item_dependencies",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("depends_on_item_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("item_id", "depends_on_item_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id", "item_id"], item_cols, name="fk_dependency_item"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id", "depends_on_item_id"],
            item_cols,
            name="fk_dependency_target",
        ),
        sa.CheckConstraint("item_id <> depends_on_item_id", name="ck_dependency_not_self"),
    )
    op.create_table(
        "proposal_decision_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("expected_session_revision", sa.Integer(), nullable=False),
        sa.Column("result_session_revision", sa.Integer(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "workspace_id", "session_id", "idempotency_key", name="uq_decision_idempotency"
        ),
        sa.UniqueConstraint("workspace_id", "session_id", "id", name="uq_decision_scope"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
            name="fk_decision_session",
        ),
    )
    op.create_table(
        "proposal_decision_items",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.PrimaryKeyConstraint("request_id", "item_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id", "request_id"],
            [
                "proposal_decision_requests.workspace_id",
                "proposal_decision_requests.session_id",
                "proposal_decision_requests.id",
            ],
            name="fk_decision_item_request",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id", "item_id"], item_cols, name="fk_decision_item_target"
        ),
    )

    _backfill()

    with op.batch_alter_table("modeling_sessions") as batch:
        batch.alter_column("base_version_sha256", existing_type=sa.String(64), nullable=False)
        batch.alter_column("draft_sha256", existing_type=sa.String(64), nullable=False)


def _backfill() -> None:
    from datetime import UTC, datetime

    from ontofoundry_api.domain.canonical import snapshot_sha256
    from ontofoundry_api.domain.snapshot import as_v2_dict, empty_snapshot
    from ontofoundry_api.services.identities import element_kinds

    bind = op.get_bind()
    now = datetime.now(UTC)
    workspaces = {
        row.id: row.current_version_id
        for row in bind.execute(sa.text("SELECT id, current_version_id FROM workspaces"))
    }
    versions = bind.execute(
        sa.text(
            "SELECT id, workspace_id, snapshot_json, published_by FROM ontology_versions "
            "ORDER BY workspace_id, version_number"
        )
    ).fetchall()
    sessions = bind.execute(
        sa.text(
            "SELECT id, workspace_id, base_version_id, draft_json, created_by FROM modeling_sessions"
        )
    ).fetchall()

    snapshots = {v.id: as_v2_dict(_json(v.snapshot_json), v.workspace_id) for v in versions}
    seen: dict[tuple[str, str], tuple[str, str | None]] = {}
    clashes: list[str] = []

    def record(workspace_id: str, snapshot: dict, author: str | None) -> None:
        for element_id, kind in element_kinds(snapshot).items():
            key = (workspace_id, element_id)
            if key in seen and seen[key][0] != kind:
                clashes.append(f"{workspace_id}/{element_id}: {seen[key][0]} vs {kind}")
            seen.setdefault(key, (kind, author))

    for version in versions:
        record(version.workspace_id, snapshots[version.id], version.published_by)
    drafts = {}
    for item in sessions:
        drafts[item.id] = as_v2_dict(_json(item.draft_json), item.workspace_id)
        record(item.workspace_id, drafts[item.id], item.created_by)
    if clashes:
        raise RuntimeError(
            "同一元素 id 在历史中被用作不同类型，迁移已中止，请人工处理：\n" + "\n".join(clashes)
        )

    heads = {
        workspace_id: set(element_kinds(snapshots[head])) if head in snapshots else set()
        for workspace_id, head in workspaces.items()
    }
    identities = sa.table(
        "ontology_element_identities",
        sa.column("workspace_id"),
        sa.column("element_id"),
        sa.column("kind"),
        sa.column("created_at"),
        sa.column("created_by"),
        sa.column("retired_at"),
    )
    rows = [
        {
            "workspace_id": workspace_id,
            "element_id": element_id,
            "kind": kind,
            "created_at": now,
            "created_by": author,
            "retired_at": None if element_id in heads.get(workspace_id, set()) else now,
        }
        for (workspace_id, element_id), (kind, author) in seen.items()
    ]
    if rows:
        op.bulk_insert(identities, rows)

    for item in sessions:
        base = (
            snapshots[item.base_version_id]
            if item.base_version_id in snapshots
            else empty_snapshot(item.workspace_id)
        )
        bind.execute(
            sa.text(
                "UPDATE modeling_sessions SET base_version_sha256 = :base, draft_sha256 = :draft "
                "WHERE id = :id"
            ),
            {"base": snapshot_sha256(base), "draft": snapshot_sha256(drafts[item.id]), "id": item.id},
        )


def downgrade() -> None:
    # New tables and columns only; version snapshots and materials are untouched.
    for table in (
        "proposal_decision_items",
        "proposal_decision_requests",
        "proposal_item_dependencies",
        "proposal_items",
        "proposal_batches",
        "ontology_element_identities",
    ):
        op.drop_table(table)
    with op.batch_alter_table("materials") as batch:
        batch.drop_column("archived_by")
        batch.drop_column("archived_at")
    with op.batch_alter_table("modeling_sessions") as batch:
        batch.drop_column("run_manifest_json")
        batch.drop_column("draft_sha256")
        batch.drop_column("base_version_sha256")
        batch.drop_constraint("uq_modeling_sessions_ws_id", type_="unique")
