from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ontofoundry_api.db_models import (
    OntologyVersionRecord,
    UserRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
)
from ontofoundry_api.domain.models import OntologyDraft, WorkspaceCreate
from ontofoundry_api.ossie.compiler import compile_ossie, sha256_json, validate_ossie

from .errors import ConflictError, NotFoundError, PublishValidationError

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


def ensure_dev_user(session: Session) -> UserRecord:
    user = session.get(UserRecord, DEV_USER_ID)
    if user is None:
        user = UserRecord(
            id=DEV_USER_ID,
            subject="dev:admin",
            display_name="admin",
            email=None,
        )
        session.add(user)
        session.commit()
    return user


def upsert_oauth_user(
    session: Session,
    *,
    subject: str,
    display_name: str,
    email: str | None,
) -> UserRecord:
    user = session.scalar(select(UserRecord).where(UserRecord.subject == subject))
    if user is None:
        user = UserRecord(
            id=str(uuid4()),
            subject=subject,
            display_name=display_name,
            email=email,
        )
        session.add(user)
    else:
        user.display_name = display_name
        user.email = email
    session.commit()
    return user


def create_workspace(
    session: Session,
    *,
    payload: WorkspaceCreate,
    user_id: str,
    workspace_id: UUID | None = None,
) -> WorkspaceRecord:
    normalized_name = payload.name.casefold()
    existing_names = session.scalars(select(WorkspaceRecord.name)).all()
    if any(item.casefold() == normalized_name for item in existing_names):
        raise ConflictError("工作空间名称已存在，请使用其他名称")
    if session.scalar(select(WorkspaceRecord).where(WorkspaceRecord.slug == payload.slug)):
        raise ConflictError("工作空间标识已存在，请使用其他标识")

    workspace = WorkspaceRecord(
        id=str(workspace_id or uuid4()),
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        created_by=user_id,
    )
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceMemberRecord(
            workspace_id=workspace.id,
            user_id=user_id,
            role="admin",
        )
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("工作空间名称或标识已存在") from exc
    return workspace


def get_workspace(session: Session, workspace_id: str) -> WorkspaceRecord:
    workspace = session.get(WorkspaceRecord, workspace_id)
    if workspace is None:
        raise NotFoundError("没有找到该工作空间")
    return workspace


def membership_role(session: Session, workspace_id: str, user_id: str) -> str | None:
    return session.scalar(
        select(WorkspaceMemberRecord.role).where(
            WorkspaceMemberRecord.workspace_id == workspace_id,
            WorkspaceMemberRecord.user_id == user_id,
        )
    )


def workspace_summary(session: Session, workspace: WorkspaceRecord, user_id: str) -> dict:
    version = (
        session.get(OntologyVersionRecord, workspace.current_version_id)
        if workspace.current_version_id
        else None
    )
    draft = version.snapshot_json if version else {}
    return {
        "id": workspace.id,
        "slug": workspace.slug,
        "name": workspace.name,
        "description": workspace.description,
        "role": membership_role(session, workspace.id, user_id),
        "visibility": "member"
        if membership_role(session, workspace.id, user_id)
        else "published_only",
        "current_version": version.version_number if version else None,
        "version_id": version.id if version else None,
        "version_sha256": version.sha256 if version else None,
        "object_type_count": len(draft.get("object_types", [])),
        "link_type_count": len(draft.get("link_types", [])),
        "updated_at": workspace.updated_at,
    }


def list_workspaces(session: Session, user_id: str) -> list[dict]:
    workspaces = session.scalars(
        select(WorkspaceRecord).order_by(WorkspaceRecord.updated_at.desc())
    ).all()
    return [workspace_summary(session, item, user_id) for item in workspaces]


def publish_draft(
    session: Session,
    *,
    workspace_id: str,
    draft: OntologyDraft,
    user_id: str,
    message: str,
    commit: bool = True,
) -> OntologyVersionRecord:
    workspace = get_workspace(session, workspace_id)
    previous_version_id = workspace.current_version_id
    if str(draft.workspace_id) != workspace.id:
        raise PublishValidationError(
            "草稿所属工作空间与发布目标不一致",
            {
                "publishable": False,
                "errors": [
                    {
                        "severity": "error",
                        "code": "WORKSPACE_MISMATCH",
                        "path": "$.workspace_id",
                        "message": "draft.workspace_id must match the route workspace",
                    }
                ],
                "warnings": [],
            },
        )
    if membership_role(session, workspace_id, user_id) is None:
        raise NotFoundError("没有找到可发布的工作空间")

    ossie = compile_ossie(
        draft,
        ontology_name=workspace.slug.replace("-", "_"),
        ontology_description=workspace.description or workspace.name,
    )
    report = validate_ossie(ossie)
    if not report["publishable"]:
        raise PublishValidationError("Ossie 校验未通过，版本未发布", report)

    next_version = (
        session.scalar(
            select(func.max(OntologyVersionRecord.version_number)).where(
                OntologyVersionRecord.workspace_id == workspace_id
            )
        )
        or 0
    ) + 1
    snapshot = draft.model_dump(mode="json")
    sha256 = sha256_json(
        {
            "snapshot": snapshot,
            "ossie": ossie,
            "validation": report,
        }
    )
    version = OntologyVersionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        version_number=next_version,
        message=message,
        snapshot_json=snapshot,
        ossie_json=ossie,
        validation_json=report,
        sha256=sha256,
        published_by=user_id,
    )
    session.add(version)
    session.flush()
    changed = session.execute(
        update(WorkspaceRecord)
        .where(
            WorkspaceRecord.id == workspace.id,
            WorkspaceRecord.current_version_id == previous_version_id,
        )
        .values(current_version_id=version.id, updated_at=datetime.now(UTC))
    )
    if changed.rowcount != 1:
        session.rollback()
        raise ConflictError("发布版本已变化，请重新比较后发布")
    if commit:
        session.commit()
    return version
