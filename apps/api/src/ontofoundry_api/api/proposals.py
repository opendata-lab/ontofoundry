"""Proposal batches and decisions (design §8, frontend contract §5.1–5.2)."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import (
    get_modeling_session,
    require_member,
    session_draft,
    session_response,
    validate_draft,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import (
    MaterialRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalDecisionItemRecord,
    ProposalDecisionRequestRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind, OntologyDraft
from ontofoundry_api.domain.snapshot import draft_sha256
from ontofoundry_api.services.element_diff import element_label, field_changes, owner_label
from ontofoundry_api.services.errors import ConflictError, ServiceError
from ontofoundry_api.services.identities import check_identities
from ontofoundry_api.services.proposals import batch_items as _batch_items
from ontofoundry_api.services.proposals import (
    dependency_group,
    dependency_map,
    effective_statuses,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/sessions/{session_id}", tags=["proposals"]
)
metrics_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["proposals"])


def _fail(status: int, code: str, message: str, **details: Any) -> ServiceError:
    return ServiceError(message, code=code, status_code=status, details=details)


# --- reading ------------------------------------------------------------------


def _counts(items, statuses) -> dict[str, int]:
    counts = dict.fromkeys(("pending", "accepted", "rejected", "stale", "conflict", "superseded"), 0)
    for item in items:
        counts[statuses[item.id][0]] += 1
    return counts


def _batch_summary(batch: ProposalBatchRecord, items, statuses) -> dict[str, Any]:
    return {
        "id": batch.id,
        "status": batch.status,
        "created_at": batch.created_at,
        "source_session_revision": batch.source_session_revision,
        "base_version_id": batch.base_version_id,
        "counts": _counts(items, statuses),
        "error": batch.error_json,
    }


def _evidence_view(db: Session, workspace_id: str, entries: list[dict]) -> list[dict]:
    views = []
    for entry in entries or []:
        if entry.get("kind") == "material":
            material = db.get(MaterialRecord, str(entry["material_id"]))
            same_space = material is not None and material.workspace_id == workspace_id
            views.append(
                {
                    **entry,
                    "material_name": material.name if same_space else "(材料不存在)",
                    "material_archived": bool(same_space and material.archived_at),
                }
            )
        else:
            views.append(entry)
    return views


def _item_view(db, workspace_id, item, statuses, dependencies, elements) -> dict[str, Any]:
    element = item.after_json or item.before_json or {}
    status, reason = statuses[item.id]
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "ordinal": item.ordinal,
        "client_ref": item.client_ref,
        "operation": item.operation,
        "target_kind": item.target_kind,
        "target_id": item.target_id,
        "display_name": element_label(item.target_kind, element, elements),
        "owner_label": owner_label(item.target_kind, element, elements),
        "before": item.before_json,
        "after": item.after_json,
        # Agents may omit field_changes (display data); derive them then.
        "field_changes": item.field_changes_json
        or (
            field_changes(item.before_json, item.after_json)
            if item.before_json and item.after_json
            else []
        ),
        "evidence": _evidence_view(
            db,
            workspace_id,
            [*(item.evidence_json or []), *((item.after_json or {}).get("evidence") or [])],
        ),
        "reason": item.reason or "",
        "depends_on": dependencies.get(item.id, []),
        "dependency_group": dependency_group(item.id, dependencies),
        "status": status,
        "stored_status": item.status,
        "status_reason": reason,
        "accepted_revision": item.accepted_revision,
        "decided_at": item.decided_at,
    }


def _session_elements(draft: dict) -> dict[str, tuple[str, dict]]:
    return {
        str(element["id"]): (kind.value, element)
        for kind, collection in COLLECTIONS.items()
        for element in draft.get(collection) or []
    }


@router.get("/proposal-batches")
def list_batches(
    workspace_id: str,
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    session = get_modeling_session(db, workspace_id, session_id)
    query = (
        select(ProposalBatchRecord)
        .where(
            ProposalBatchRecord.workspace_id == workspace_id,
            ProposalBatchRecord.session_id == session_id,
        )
        .order_by(ProposalBatchRecord.created_at.desc(), ProposalBatchRecord.id.desc())
    )
    if cursor:
        anchor = db.get(ProposalBatchRecord, cursor)
        if anchor is None or anchor.session_id != session_id or anchor.workspace_id != workspace_id:
            raise _fail(422, "INVALID_CURSOR", "游标无效")
        # Keyset paging in (created_at, id) descending order.
        query = query.where(
            or_(
                ProposalBatchRecord.created_at < anchor.created_at,
                and_(
                    ProposalBatchRecord.created_at == anchor.created_at,
                    ProposalBatchRecord.id < anchor.id,
                ),
            )
        )
    batches = list(db.scalars(query.limit(limit + 1)).all())
    page = batches[:limit]
    ids = [b.id for b in page]
    items = _batch_items(db, ids, workspace_id, session_id)
    statuses = effective_statuses(
        items, dependency_map(db, ids, workspace_id, session_id), session_draft(session)
    )
    by_batch: dict[str, list] = {}
    for item in items:
        by_batch.setdefault(item.batch_id, []).append(item)
    return {
        "items": [_batch_summary(b, by_batch.get(b.id, []), statuses) for b in page],
        "next_cursor": page[-1].id if len(batches) > limit else None,
    }


@router.get("/proposal-batches/{batch_id}")
def read_batch(
    workspace_id: str,
    session_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    session = get_modeling_session(db, workspace_id, session_id)
    batch = db.get(ProposalBatchRecord, batch_id)
    if batch is None or batch.workspace_id != workspace_id or batch.session_id != session_id:
        raise _fail(404, "BATCH_NOT_FOUND", "提案批次不存在")
    draft = session_draft(session)
    items = _batch_items(db, [batch.id], workspace_id, session_id)
    dependencies = dependency_map(db, [batch.id], workspace_id, session_id)
    statuses = effective_statuses(items, dependencies, draft)
    elements = _session_elements(draft)
    for item in items:
        for element in (item.after_json, item.before_json):
            if element:
                elements.setdefault(str(element["id"]), (item.target_kind, element))
    return {
        **_batch_summary(batch, items, statuses),
        "items": [_item_view(db, workspace_id, i, statuses, dependencies, elements) for i in items],
    }


# --- deciding -----------------------------------------------------------------


class Decision(BaseModel):
    proposal_id: str
    decision: Literal["accept", "reject", "restore"]


class DecisionRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)
    expected_session_revision: int
    decisions: list[Decision] = Field(min_length=1, max_length=500)


def _request_sha256(body: DecisionRequest) -> str:
    payload = body.model_dump()
    payload["decisions"] = sorted(payload["decisions"], key=lambda d: (d["proposal_id"], d["decision"]))
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _apply(draft: dict, item: ProposalItemRecord) -> None:
    collection = COLLECTIONS[ElementKind(item.target_kind)]
    elements = draft.setdefault(collection, [])
    if item.operation == "create":
        elements.append(deepcopy(item.after_json))
    elif item.operation == "update":
        draft[collection] = [
            deepcopy(item.after_json) if str(e["id"]) == item.target_id else e for e in elements
        ]
    else:
        draft[collection] = [e for e in elements if str(e["id"]) != item.target_id]


def _topological(items: list[ProposalItemRecord], dependencies: dict[str, list[str]]):
    chosen = {item.id: item for item in items}
    ordered, seen = [], set()

    def visit(item_id: str) -> None:
        if item_id in seen or item_id not in chosen:
            return
        seen.add(item_id)
        for dep in dependencies.get(item_id, []):
            visit(dep)
        ordered.append(chosen[item_id])

    for item in sorted(items, key=lambda i: i.ordinal):
        visit(item.id)
    return ordered


@router.post("/proposal-decisions")
def decide(
    workspace_id: str,
    session_id: str,
    body: DecisionRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    get_modeling_session(db, workspace_id, session_id)
    # 1. Lock the session row.
    session = db.scalar(
        select(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == session_id,
            ModelingSessionRecord.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    # 2. Idempotency before anything else, so a replay after success returns
    #    the first response even though the revision has moved on.
    request_hash = _request_sha256(body)
    previous = db.scalar(
        select(ProposalDecisionRequestRecord).where(
            ProposalDecisionRequestRecord.workspace_id == workspace_id,
            ProposalDecisionRequestRecord.session_id == session_id,
            ProposalDecisionRequestRecord.idempotency_key == body.idempotency_key,
        )
    )
    if previous is not None:
        if previous.request_sha256 != request_hash:
            raise _fail(409, "IDEMPOTENCY_MISMATCH", "同一幂等键已用于不同的请求")
        return previous.response_json
    # 2a. Revision.
    if session.revision != body.expected_session_revision:
        raise _fail(409, "SESSION_REVISION_CHANGED", "草稿已更新，请刷新后重新确认")

    # 2b. Items, all of this session, with their effective status now.
    ids = [d.proposal_id for d in body.decisions]
    if len(set(ids)) != len(ids):
        raise _fail(422, "DECISION_DUPLICATE", "同一提案在请求中出现多次")
    items = {
        item.id: item
        for item in db.scalars(
            select(ProposalItemRecord).where(
                ProposalItemRecord.id.in_(ids),
                ProposalItemRecord.workspace_id == workspace_id,
                ProposalItemRecord.session_id == session_id,
            )
        )
    }
    missing = [i for i in ids if i not in items]
    if missing:
        raise _fail(
            422,
            "PROPOSAL_NOT_FOUND",
            "请求包含不属于本会话的提案",
            items=[{"proposal_id": i, "reason": "不存在或不属于本会话"} for i in missing],
        )
    batch_ids = sorted({item.batch_id for item in items.values()})
    batch_items = _batch_items(db, batch_ids, workspace_id, session_id)
    dependencies = dependency_map(db, batch_ids, workspace_id, session_id)
    draft = deepcopy(session_draft(session))
    statuses = effective_statuses(batch_items, dependencies, draft)
    by_id = {item.id: item for item in batch_items}

    accepts = [d.proposal_id for d in body.decisions if d.decision == "accept"]
    problems = []
    for decision in body.decisions:
        status, reason = statuses[decision.proposal_id]
        if decision.decision == "accept" and status != "pending":
            code = {"stale": "PROPOSAL_STALE", "conflict": "PROPOSAL_CONFLICT"}.get(
                status, "PROPOSAL_NOT_DECIDABLE"
            )
            problems.append((409, code, decision.proposal_id, reason or f"提案当前为 {status}"))
        elif decision.decision == "reject" and status not in ("pending", "stale", "conflict"):
            problems.append((409, "PROPOSAL_NOT_DECIDABLE", decision.proposal_id, f"提案当前为 {status}"))
        elif decision.decision == "restore" and items[decision.proposal_id].status != "rejected":
            problems.append((409, "PROPOSAL_NOT_RESTORABLE", decision.proposal_id, "只有已拒绝的提案可以恢复"))
    if problems:
        status_code, code = problems[0][0], problems[0][1]
        raise _fail(
            status_code,
            code,
            problems[0][3],
            items=[{"proposal_id": p[2], "reason": p[3]} for p in problems],
        )

    # Dependency groups are accepted together (or were accepted before).
    for proposal_id in accepts:
        for dep in dependency_group(proposal_id, dependencies):
            if dep == proposal_id:
                continue
            if by_id[dep].status == "accepted":
                continue
            if dep not in accepts:
                raise _fail(
                    422,
                    "DEPENDENCY_INCOMPLETE",
                    "接受提案时必须一并接受其依赖",
                    items=[{"proposal_id": proposal_id, "reason": f"缺少依赖 {dep}"}],
                )

    # Apply accepted items in dependency order and validate the whole draft.
    accepted_items = _topological([items[i] for i in accepts], dependencies)
    for item in accepted_items:
        _apply(draft, item)
    if accepted_items:
        try:
            model = OntologyDraft.model_validate(draft)
        except ValidationError as exc:
            message = str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
            raise _fail(
                422,
                "VALIDATION_FAILED",
                f"接受后草稿校验未通过：{message}",
                items=[{"proposal_id": i.id, "reason": message} for i in accepted_items],
            ) from exc
        check_identities(
            db,
            workspace_id,
            {
                item.target_id: item.target_kind
                for item in accepted_items
                if item.operation == "create"
            },
        )
        draft = model.model_dump(mode="json")

    now = utc_now()
    new_revision = session.revision + 1 if accepted_items else session.revision
    if accepted_items:
        session.draft_json = draft
        session.draft_sha256 = draft_sha256(draft, workspace_id)
        session.revision = new_revision
        session.updated_at = now
    results = []
    for decision in body.decisions:
        item = items[decision.proposal_id]
        if decision.decision == "accept":
            item.status, item.accepted_revision = "accepted", new_revision
        elif decision.decision == "reject":
            item.status = "rejected"
        else:
            item.status = "pending"
        item.decided_by, item.decided_at = user.id, now
    db.flush()
    after_statuses = effective_statuses(
        _batch_items(db, batch_ids, workspace_id, session_id), dependencies, session_draft(session)
    )
    for decision in body.decisions:
        status, reason = after_statuses[decision.proposal_id]
        results.append({"proposal_id": decision.proposal_id, "status": status, "reason": reason})

    response = jsonable(
        {
            "session": session_response(db, session),
            "results": results,
            "validation": validate_draft(session_draft(session), _workspace(db, workspace_id)),
        }
    )
    record = ProposalDecisionRequestRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        session_id=session_id,
        idempotency_key=body.idempotency_key,
        request_sha256=request_hash,
        expected_session_revision=body.expected_session_revision,
        result_session_revision=new_revision,
        response_json=response,
        actor_id=user.id,
        created_at=now,
    )
    db.add(record)
    db.flush()
    for decision in body.decisions:
        db.add(
            ProposalDecisionItemRecord(
                workspace_id=workspace_id,
                session_id=session_id,
                request_id=record.id,
                batch_id=items[decision.proposal_id].batch_id,
                item_id=decision.proposal_id,
                decision=decision.decision,
            )
        )
    try:
        db.commit()
    except Exception as exc:  # a concurrent replay with the same key won the race
        db.rollback()
        winner = db.scalar(
            select(ProposalDecisionRequestRecord).where(
                ProposalDecisionRequestRecord.workspace_id == workspace_id,
                ProposalDecisionRequestRecord.session_id == session_id,
                ProposalDecisionRequestRecord.idempotency_key == body.idempotency_key,
            )
        )
        if winner is not None and winner.request_sha256 == request_hash:
            return winner.response_json
        raise ConflictError("决策提交冲突，请刷新后重试") from exc
    return response


def jsonable(value: Any) -> Any:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(value)


def _workspace(db: Session, workspace_id: str):
    from ontofoundry_api.services.workspaces import get_workspace

    return get_workspace(db, workspace_id)


@metrics_router.get("/proposal-metrics")
def proposal_metrics(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """What T8 watches before legacy code can go: legacy runs still active,
    batch outcomes, how often proposals go stale, and what users decide."""
    require_member(db, workspace_id, user.id)
    from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES

    sessions = db.scalars(
        select(ModelingSessionRecord).where(ModelingSessionRecord.workspace_id == workspace_id)
    ).all()
    legacy_active = sum(
        1
        for s in sessions
        if s.task_status in ACTIVE_RUN_STATUSES
        and (s.run_manifest_json or {}).get("result_contract") != "proposals"
    )
    batches = db.scalars(
        select(ProposalBatchRecord).where(ProposalBatchRecord.workspace_id == workspace_id)
    ).all()
    by_status: dict[str, int] = {}
    for batch in batches:
        by_status[batch.status] = by_status.get(batch.status, 0) + 1
    effective: dict[str, int] = dict.fromkeys(
        ("pending", "accepted", "rejected", "stale", "conflict", "superseded"), 0
    )
    for session in sessions:
        ids = [b.id for b in batches if b.session_id == session.id]
        items = _batch_items(db, ids, workspace_id, session.id)
        deps = dependency_map(db, ids, workspace_id, session.id)
        for status, _ in effective_statuses(items, deps, session_draft(session)).values():
            effective[status] += 1
    decisions: dict[str, int] = {"accept": 0, "reject": 0, "restore": 0}
    for row in db.scalars(
        select(ProposalDecisionItemRecord).where(
            ProposalDecisionItemRecord.workspace_id == workspace_id
        )
    ):
        decisions[row.decision] = decisions.get(row.decision, 0) + 1
    total_batches = len(batches)
    open_items = effective["pending"] + effective["stale"] + effective["conflict"]
    return {
        "legacy_active_runs": legacy_active,
        "batches": {"total": total_batches, **by_status},
        "batch_failure_rate": round(by_status.get("failed", 0) / total_batches, 4) if total_batches else 0.0,
        "items": effective,
        "stale_rate": round((effective["stale"] + effective["conflict"]) / open_items, 4) if open_items else 0.0,
        "decisions": decisions,
    }
