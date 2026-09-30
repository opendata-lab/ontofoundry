from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class WorkspaceRecord(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    versions: Mapped[list[OntologyVersionRecord]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="OntologyVersionRecord.version_number",
    )


class WorkspaceMemberRecord(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class OntologyVersionRecord(Base):
    __tablename__ = "ontology_versions"
    __table_args__ = (UniqueConstraint("workspace_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="published", nullable=False)
    message: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    ossie_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    published_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    workspace: Mapped[WorkspaceRecord] = relationship(back_populates="versions")


class ModelingSessionRecord(Base):
    __tablename__ = "modeling_sessions"
    # Target of composite foreign keys, so proposal rows can only ever point at
    # a session of their own workspace.
    __table_args__ = (UniqueConstraint("workspace_id", "id", name="uq_modeling_sessions_ws_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(240), default="新的建模会话")
    base_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    draft_json: Mapped[dict] = mapped_column(JSON)
    # normalized_snapshot_sha256 of the base version, pinned at creation, and
    # the domain hash of draft_json, kept in step with every draft write.
    base_version_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidates_json: Mapped[list] = mapped_column(JSON, default=list)
    material_ids: Mapped[list] = mapped_column(JSON, default=list)
    task_status: Mapped[str] = mapped_column(String(24), default="idle")
    task_detail: Mapped[str] = mapped_column(Text, default="")
    dataagent_topic_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataagent_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataagent_task_mode: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=""
    )
    dataagent_run_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_material_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )
    last_result_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=""
    )
    result_warnings: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )
    result_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MaterialRecord(Base):
    __tablename__ = "materials"
    __table_args__ = (UniqueConstraint("workspace_id", "sha256"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(240))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # Referenced material is archived, never deleted: evidence must stay
    # recoverable for every proposal, draft and published version.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class MaterialChunkRecord(Base):
    __tablename__ = "material_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class ConnectionRecord(Base):
    __tablename__ = "data_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))
    config_json: Mapped[dict] = mapped_column(JSON)
    secret_encrypted: Mapped[str] = mapped_column(Text)


class ServiceTokenRecord(Base):
    __tablename__ = "service_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ServiceTokenScopeRecord(Base):
    __tablename__ = "service_token_scopes"
    token_id: Mapped[str] = mapped_column(ForeignKey("service_tokens.id"), primary_key=True)
    scope: Mapped[str] = mapped_column(String(40), primary_key=True)


class MetadataSnapshotRecord(Base):
    __tablename__ = "metadata_snapshots"
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("data_connections.id"), primary_key=True
    )
    schema_name: Mapped[str] = mapped_column(String(240), primary_key=True, default="")
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    changes_json: Mapped[list] = mapped_column(JSON, default=list)
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class OntologyElementIdentityRecord(Base):
    """Which kind an element id was minted as. Never reused across kinds.

    Content lives in drafts and version snapshots; this only pins identity.
    `retired_at` marks ids absent from the current head; they stay registered.
    """

    __tablename__ = "ontology_element_identities"
    __table_args__ = (
        PrimaryKeyConstraint("workspace_id", "element_id"),
        UniqueConstraint("workspace_id", "element_id", "kind", name="uq_element_identity_kind"),
    )
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    element_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProposalBatchRecord(Base):
    __tablename__ = "proposal_batches"
    __table_args__ = (
        UniqueConstraint("workspace_id", "session_id", "run_token", name="uq_batch_run"),
        UniqueConstraint("workspace_id", "session_id", "result_sha256", name="uq_batch_result"),
        UniqueConstraint("workspace_id", "session_id", "id", name="uq_batch_scope"),
        ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
            name="fk_batch_session",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    dataagent_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_token: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(64))
    base_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    base_version_sha256: Mapped[str] = mapped_column(String(64))
    source_session_revision: Mapped[int] = mapped_column(Integer)
    source_draft_sha256: Mapped[str] = mapped_column(String(64))
    material_manifest_json: Mapped[list] = mapped_column(JSON, default=list)
    producer_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_sha256: Mapped[str] = mapped_column(String(64))
    # validating | available | failed — never "stale": staleness is per item.
    status: Mapped[str] = mapped_column(String(16))
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProposalItemRecord(Base):
    __tablename__ = "proposal_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", name="uq_item_ordinal"),
        UniqueConstraint("batch_id", "fingerprint", name="uq_item_fingerprint"),
        UniqueConstraint("workspace_id", "session_id", "batch_id", "id", name="uq_item_scope"),
        ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id"],
            ["proposal_batches.workspace_id", "proposal_batches.session_id", "proposal_batches.id"],
            name="fk_item_batch",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    client_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(8))
    target_kind: Mapped[str] = mapped_column(String(24))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    expected_target_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_changes_json: Mapped[list] = mapped_column(JSON, default=list)
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, default="")
    # Stored decision state only: pending | accepted | rejected | superseded.
    # stale / conflict are derived on read and never written (design §7.3).
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProposalItemDependencyRecord(Base):
    __tablename__ = "proposal_item_dependencies"
    __table_args__ = (
        PrimaryKeyConstraint("item_id", "depends_on_item_id"),
        ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id", "item_id"],
            [
                "proposal_items.workspace_id",
                "proposal_items.session_id",
                "proposal_items.batch_id",
                "proposal_items.id",
            ],
            name="fk_dependency_item",
        ),
        # Both ends in the same batch, enforced by the database.
        ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id", "depends_on_item_id"],
            [
                "proposal_items.workspace_id",
                "proposal_items.session_id",
                "proposal_items.batch_id",
                "proposal_items.id",
            ],
            name="fk_dependency_target",
        ),
        CheckConstraint("item_id <> depends_on_item_id", name="ck_dependency_not_self"),
    )
    workspace_id: Mapped[str] = mapped_column(String(36))
    session_id: Mapped[str] = mapped_column(String(36))
    batch_id: Mapped[str] = mapped_column(String(36))
    item_id: Mapped[str] = mapped_column(String(36))
    depends_on_item_id: Mapped[str] = mapped_column(String(36))


class ProposalDecisionRequestRecord(Base):
    """One successful decision request; replays return `response_json`."""

    __tablename__ = "proposal_decision_requests"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "session_id", "idempotency_key", name="uq_decision_idempotency"
        ),
        UniqueConstraint("workspace_id", "session_id", "id", name="uq_decision_scope"),
        ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
            name="fk_decision_session",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    expected_session_revision: Mapped[int] = mapped_column(Integer)
    result_session_revision: Mapped[int] = mapped_column(Integer)
    response_json: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProposalDecisionItemRecord(Base):
    __tablename__ = "proposal_decision_items"
    __table_args__ = (
        PrimaryKeyConstraint("request_id", "item_id"),
        ForeignKeyConstraint(
            ["workspace_id", "session_id", "request_id"],
            [
                "proposal_decision_requests.workspace_id",
                "proposal_decision_requests.session_id",
                "proposal_decision_requests.id",
            ],
            name="fk_decision_item_request",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "session_id", "batch_id", "item_id"],
            [
                "proposal_items.workspace_id",
                "proposal_items.session_id",
                "proposal_items.batch_id",
                "proposal_items.id",
            ],
            name="fk_decision_item_target",
        ),
    )
    workspace_id: Mapped[str] = mapped_column(String(36))
    session_id: Mapped[str] = mapped_column(String(36))
    request_id: Mapped[str] = mapped_column(String(36))
    batch_id: Mapped[str] = mapped_column(String(36))
    item_id: Mapped[str] = mapped_column(String(36))
    decision: Mapped[str] = mapped_column(String(8))
