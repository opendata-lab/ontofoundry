"""Proposal-first lifecycle: identities, proposals, decisions, pinned hashes.

Adds the element identity registry, proposal batches/items/dependencies,
decision requests/items, session base/draft hashes and run manifests, and
material archiving. The obsolete data conversion was retired at the core-1
cutover: its sessions, identities and versions are discarded by that revision.
Historical DDL is preserved; no old runtime converters are imported here.

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
    op.add_column(
        "modeling_sessions", sa.Column("base_version_sha256", sa.String(64), nullable=True)
    )
    op.add_column(
        "modeling_sessions", sa.Column("draft_sha256", sa.String(64), nullable=True)
    )
    op.add_column(
        "modeling_sessions", sa.Column("run_manifest_json", sa.JSON(), nullable=True)
    )
    op.add_column(
        "materials", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "materials",
        sa.Column("archived_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "ontology_element_identities",
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
        ),
        sa.Column("element_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("workspace_id", "element_id"),
        sa.UniqueConstraint(
            "workspace_id", "element_id", "kind", name="uq_element_identity_kind"
        ),
    )
    op.create_table(
        "proposal_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
        ),
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
        sa.UniqueConstraint(
            "workspace_id", "session_id", "result_sha256", name="uq_batch_result"
        ),
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
        sa.UniqueConstraint(
            "workspace_id", "session_id", "batch_id", "id", name="uq_item_scope"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id"],
            [
                "proposal_batches.workspace_id",
                "proposal_batches.session_id",
                "proposal_batches.id",
            ],
            name="fk_item_batch",
        ),
    )
    op.create_index("ix_proposal_items_batch", "proposal_items", ["batch_id"])
    op.create_index("ix_proposal_items_target", "proposal_items", ["target_id"])
    item_cols = [
        "proposal_items.workspace_id",
        "proposal_items.session_id",
        "proposal_items.batch_id",
        "proposal_items.id",
    ]
    op.create_table(
        "proposal_item_dependencies",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("depends_on_item_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("item_id", "depends_on_item_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id", "item_id"],
            item_cols,
            name="fk_dependency_item",
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
            ["workspace_id", "session_id", "batch_id", "item_id"],
            item_cols,
            name="fk_decision_item_target",
        ),
    )

    _backfill()

    with op.batch_alter_table("modeling_sessions") as batch:
        batch.alter_column(
            "base_version_sha256", existing_type=sa.String(64), nullable=False
        )
        batch.alter_column("draft_sha256", existing_type=sa.String(64), nullable=False)


def _backfill() -> None:
    # Core-1 discards these sessions at the cutover revision. A placeholder
    # satisfies historical NOT NULL DDL without interpreting obsolete models.
    op.get_bind().execute(
        sa.text(
            "UPDATE modeling_sessions SET base_version_sha256 = :empty, draft_sha256 = :empty"
        ),
        {"empty": "0" * 64},
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
