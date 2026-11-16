"""Append-only change log across proposal, draft and version layers (AI-07, AI-12)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ontofoundry_api.contracts.session_writes import (
    ActorKind,
    ChangeAction,
    ChangeEventPageRead,
    ChangeEventRead,
    ChangeSubject,
)
from ontofoundry_api.db_models import ChangeEventRecord, UserRecord, utc_now
from ontofoundry_api.services.errors import ServiceError

PROPOSAL_ACTIONS = frozenset(
    {"created", "revised", "superseded", "accepted", "rejected", "restored", "back_to_pending"}
)
DRAFT_ACTIONS = frozenset({"added", "updated", "removed"})
VERSION_ACTIONS = frozenset({"published"})


def proposal_snapshot(
    *,
    status: str,
    operation: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Canonical proposal-layer snapshot captured in change_events."""
    return {
        "status": status,
        "operation": operation,
        "before": deepcopy(before),
        "after": deepcopy(after),
    }


def _next_seq(db: Session, session_id: str) -> int:
    pending_max = max(
        (
            obj.seq
            for obj in db.new
            if isinstance(obj, ChangeEventRecord) and obj.session_id == session_id
        ),
        default=0,
    )
    stored_max = (
        db.scalar(
            select(func.max(ChangeEventRecord.seq)).where(
                ChangeEventRecord.session_id == session_id
            )
        )
        or 0
    )
    return max(pending_max, stored_max) + 1


def append_event(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    actor_id: str,
    actor_kind: ActorKind,
    subject: ChangeSubject,
    action: ChangeAction,
    run_token: str | None = None,
    target_kind: str | None = None,
    target_id: str | None = None,
    proposal_id: str | None = None,
    batch_id: str | None = None,
    version_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    cause_id: str | None = None,
    at: datetime | None = None,
) -> ChangeEventRecord:
    """Append one immutable change event in the caller's active transaction."""
    if subject == "proposal" and action not in PROPOSAL_ACTIONS:
        raise ValueError(f"Invalid proposal change action: {action}")
    if subject == "draft" and action not in DRAFT_ACTIONS:
        raise ValueError(f"Invalid draft change action: {action}")
    if subject == "version" and action not in VERSION_ACTIONS:
        raise ValueError(f"Invalid version change action: {action}")
    if subject == "version":
        if target_kind is not None or target_id is not None or not version_id:
            raise ValueError("Version change events require version_id and empty target")
    elif not target_kind or not target_id:
        raise ValueError(f"{subject} change events require target_kind and target_id")

    record = ChangeEventRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        session_id=session_id,
        at=at or utc_now(),
        seq=_next_seq(db, session_id),
        actor_id=actor_id,
        actor_kind=actor_kind,
        run_token=run_token if actor_kind == "agent" else None,
        subject=subject,
        action=action,
        target_kind=target_kind,
        target_id=target_id,
        proposal_id=proposal_id,
        batch_id=batch_id,
        version_id=version_id,
        before=deepcopy(before) if before is not None else None,
        after=deepcopy(after) if after is not None else None,
        cause_id=cause_id,
    )
    db.add(record)
    return record


def record_proposal_event(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    actor_id: str,
    actor_kind: ActorKind,
    action: ChangeAction,
    target_kind: str,
    target_id: str,
    proposal_id: str,
    batch_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    run_token: str | None = None,
    cause_id: str | None = None,
    at: datetime | None = None,
) -> ChangeEventRecord:
    return append_event(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        actor_id=actor_id,
        actor_kind=actor_kind,
        run_token=run_token,
        subject="proposal",
        action=action,
        target_kind=target_kind,
        target_id=target_id,
        proposal_id=proposal_id,
        batch_id=batch_id,
        before=before,
        after=after,
        cause_id=cause_id,
        at=at,
    )


def record_draft_event(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    actor_id: str,
    actor_kind: ActorKind,
    action: ChangeAction,
    target_kind: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    proposal_id: str | None = None,
    batch_id: str | None = None,
    cause_id: str | None = None,
    at: datetime | None = None,
) -> ChangeEventRecord:
    return append_event(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        actor_id=actor_id,
        actor_kind=actor_kind,
        subject="draft",
        action=action,
        target_kind=target_kind,
        target_id=target_id,
        proposal_id=proposal_id,
        batch_id=batch_id,
        before=before,
        after=after,
        cause_id=cause_id,
        at=at,
    )


def record_version_event(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    actor_id: str,
    actor_kind: ActorKind,
    version_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> ChangeEventRecord:
    return append_event(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        actor_id=actor_id,
        actor_kind=actor_kind,
        subject="version",
        action="published",
        version_id=version_id,
        before=before,
        after=after,
        at=at,
    )


def list_events(
    db: Session,
    workspace_id: str,
    session_id: str,
    *,
    target_id: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return session change events newest-first with deterministic keyset paging."""
    target_filter = target_id or None
    query = select(ChangeEventRecord).where(
        ChangeEventRecord.workspace_id == workspace_id,
        ChangeEventRecord.session_id == session_id,
    )
    if target_filter:
        query = query.where(ChangeEventRecord.target_id == target_filter)
    if cursor:
        anchor = db.get(ChangeEventRecord, cursor)
        if (
            anchor is None
            or anchor.workspace_id != workspace_id
            or anchor.session_id != session_id
            or (target_filter and anchor.target_id != target_filter)
        ):
            raise ServiceError("游标无效", code="INVALID_CURSOR", status_code=422)
        query = query.where(
            or_(
                ChangeEventRecord.at < anchor.at,
                and_(
                    ChangeEventRecord.at == anchor.at,
                    ChangeEventRecord.seq < anchor.seq,
                ),
                and_(
                    ChangeEventRecord.at == anchor.at,
                    ChangeEventRecord.seq == anchor.seq,
                    ChangeEventRecord.id < anchor.id,
                ),
            )
        )
    rows = list(
        db.scalars(
            query.order_by(
                ChangeEventRecord.at.desc(),
                ChangeEventRecord.seq.desc(),
                ChangeEventRecord.id.desc(),
            ).limit(limit + 1)
        ).all()
    )
    page = rows[:limit]
    actor_ids = sorted({row.actor_id for row in page})
    names: dict[str, str] = {}
    if actor_ids:
        for user in db.scalars(select(UserRecord).where(UserRecord.id.in_(actor_ids))):
            names[user.id] = user.display_name or user.username

    items = [
        ChangeEventRead(
            id=row.id,
            workspace_id=row.workspace_id,
            session_id=row.session_id,
            at=row.at,
            actor_id=row.actor_id,
            actor_display_name=names.get(row.actor_id),
            actor_kind=row.actor_kind,
            run_token=row.run_token,
            subject=row.subject,
            action=row.action,
            target_kind=row.target_kind,
            target_id=row.target_id,
            proposal_id=row.proposal_id,
            batch_id=row.batch_id,
            version_id=row.version_id,
            before=row.before,
            after=row.after,
            cause_id=row.cause_id,
        )
        for row in page
    ]
    return ChangeEventPageRead(
        items=items,
        next_cursor=page[-1].id if len(rows) > limit else None,
    ).model_dump(mode="json")
