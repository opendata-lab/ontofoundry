from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
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
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(240), default="新的建模会话")
    base_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    draft_json: Mapped[dict] = mapped_column(JSON)
    candidates_json: Mapped[list] = mapped_column(JSON, default=list)
    messages_json: Mapped[list] = mapped_column(JSON, default=list)
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
