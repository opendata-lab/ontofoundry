"""Separate document instances; discard snapshot instances and invalidate old runs."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "20261021_000002"
down_revision = "20261021_000001"
branch_labels = None
depends_on = None


def _lifecycle():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
        ),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _constraints(prefix):
    return [
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
        ),
        sa.CheckConstraint(
            "state IN ('staged', 'active', 'deleted')", name=f"ck_{prefix}_state"
        ),
        sa.CheckConstraint(
            "state <> 'staged' OR session_id IS NOT NULL", name=f"ck_{prefix}_session"
        ),
        sa.CheckConstraint("revision > 0", name=f"ck_{prefix}_revision"),
    ]


def cutover(bind):
    """Do not migrate content: only retain model definitions and audit reports."""
    from ontofoundry_api.domain.canonical import canonical, jcs, snapshot_sha256

    metadata = sa.MetaData()
    versions = sa.Table("ontology_versions", metadata, autoload_with=bind)
    sessions = sa.Table("modeling_sessions", metadata, autoload_with=bind)
    imports = sa.Table("ontology_imports", metadata, autoload_with=bind)
    items = sa.Table("proposal_items", metadata, autoload_with=bind)
    identities = sa.Table("ontology_element_identities", metadata, autoload_with=bind)
    bind.execute(
        identities.delete().where(
            identities.c.kind.in_(["material_object", "material_link"])
        )
    )

    def strip(value):
        value = dict(value)
        value.pop("material_objects", None)
        value.pop("material_links", None)
        return value

    hashes = {}
    for row in bind.execute(sa.select(versions)).mappings().all():
        snapshot = strip(row["snapshot_json"])
        hashes[row["id"]] = snapshot_sha256(snapshot)
        sha = hashlib.sha256(
            jcs(
                {
                    "snapshot": json.loads(canonical(snapshot)),
                    "validation": row["validation_json"],
                }
            ).encode()
        ).hexdigest()
        bind.execute(
            versions.update()
            .where(versions.c.id == row["id"])
            .values(snapshot_json=snapshot, sha256=sha)
        )
    for row in bind.execute(sa.select(sessions)).mappings().all():
        draft = strip(row["draft_json"])
        manifest = dict(row["run_manifest_json"] or {})
        manifest.pop("pinned_draft", None)
        manifest.pop("instance_baseline", None)
        manifest["invalidated"] = "INSTANCE_STORE_CUTOVER"
        values = {
            "draft_json": draft,
            "draft_sha256": snapshot_sha256(draft),
            "base_version_sha256": hashes.get(
                row["base_version_id"],
                snapshot_sha256(
                    {"schema_version": "core-1", "workspace_id": row["workspace_id"]}
                ),
            ),
            "run_manifest_json": manifest,
            "dataagent_run_token": None,
            "result_state": "failed_permanent",
            "result_claimed_at": None,
            "revision": row["revision"] + 1,
            "task_status": "cancelled",
            "task_detail": "实例库已切换，请重新运行",
        }
        bind.execute(sessions.update().where(sessions.c.id == row["id"]).values(**values))
    # Pending reports refer to the discarded baseline and must never be accepted.
    bind.execute(
        items.update().where(items.c.status == "pending").values(status="superseded")
    )
    for row in (
        bind.execute(sa.select(imports).where(imports.c.session_id.is_(None)))
        .mappings()
        .all()
    ):
        bind.execute(
            imports.update()
            .where(imports.c.id == row["id"])
            .values(
                converted_json={},
                preview_json={"invalidated": "INSTANCE_STORE_CUTOVER"},
                confirmation_sha256=None,
            )
        )


def upgrade():
    op.add_column(
        "workspaces",
        sa.Column(
            "instance_change_sequence", sa.Integer, nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "modeling_sessions", sa.Column("abandoned_by", sa.String(36), nullable=True)
    )
    for name in ("expected_instance_revision", "accepted_instance_revision"):
        op.add_column("proposal_items", sa.Column(name, sa.Integer, nullable=True))
    op.create_table(
        "document_instances",
        *_lifecycle(),
        sa.Column("type_id", sa.String(36), nullable=False),
        sa.Column("values", sa.JSON, nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_document_instance_scope"),
        *_constraints("document_instance"),
    )
    op.create_table(
        "instance_links",
        *_lifecycle(),
        sa.Column("link_type_id", sa.String(36), nullable=False),
        sa.Column("source_instance_id", sa.String(36), nullable=False),
        sa.Column("target_instance_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_instance_link_scope"),
        *_constraints("instance_link"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_instance_id"],
            ["document_instances.workspace_id", "document_instances.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "target_instance_id"],
            ["document_instances.workspace_id", "document_instances.id"],
        ),
    )
    op.create_table(
        "instance_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
        ),
        sa.Column("owner_kind", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column(
            "material_id", sa.String(36), sa.ForeignKey("materials.id"), nullable=True
        ),
        sa.Column("material_sha256", sa.String(64), nullable=True),
        sa.Column("line_start", sa.Integer, nullable=True),
        sa.Column("line_end", sa.Integer, nullable=True),
        sa.Column("heading", sa.String(240), nullable=True),
        sa.Column("quote", sa.Text, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "owner_kind IN ('instance', 'link')", name="ck_instance_evidence_owner"
        ),
        sa.CheckConstraint(
            "kind IN ('material', 'manual')", name="ck_instance_evidence_kind"
        ),
    )
    op.create_table(
        "instance_history",
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
        ),
        sa.Column("owner_kind", sa.String(8), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("operation", sa.String(24), nullable=False),
        sa.Column("before", sa.JSON, nullable=True),
        sa.Column("after", sa.JSON, nullable=True),
        sa.Column("proposal_item_id", sa.String(36), nullable=True),
        sa.Column("actor", sa.String(36), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("owner_kind", "owner_id", "revision"),
        sa.CheckConstraint(
            "owner_kind IN ('instance', 'link')", name="ck_instance_history_owner"
        ),
    )
    for table, columns in {
        "document_instances": ["workspace_id", "session_id", "type_id"],
        "instance_links": [
            "workspace_id",
            "session_id",
            "link_type_id",
            "source_instance_id",
            "target_instance_id",
        ],
        "instance_evidence": ["workspace_id", "owner_kind", "owner_id", "material_id"],
        "instance_history": ["workspace_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    cutover(op.get_bind())


def downgrade():
    # Discarded snapshot instances and invalidated runs require a backup restore.
    for table in (
        "instance_history",
        "instance_evidence",
        "instance_links",
        "document_instances",
    ):
        op.drop_table(table)
    for name in ("expected_instance_revision", "accepted_instance_revision"):
        op.drop_column("proposal_items", name)
    op.drop_column("modeling_sessions", "abandoned_by")
    op.drop_column("modeling_sessions", "abandoned_at")
    op.drop_column("workspaces", "instance_change_sequence")
