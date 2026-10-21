"""Proposal batches and decisions (design §8, frontend contract §5.1–5.2)."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, or_, select, update
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
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.core import MaterialObject, Strict
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind, OntologyDraft
from ontofoundry_api.domain.snapshot import draft_sha256
from ontofoundry_api.services.element_diff import element_label, field_changes, owner_label
from ontofoundry_api.services.errors import ConflictError, ServiceError
from ontofoundry_api.services.identities import check_identities, element_kinds
from ontofoundry_api.services.proposals import batch_items as _batch_items
from ontofoundry_api.services.proposals import (
    dependency_group,
    dependency_map,
    dependent_group,
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
    counts = dict.fromkeys(
        ("pending", "accepted", "rejected", "stale", "conflict", "superseded"), 0
    )
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
        "producer": batch.producer_json,
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
    before, after = item.before_json, item.after_json
    element = after or before or {}
    status, reason = statuses[item.id]
    group = set(dependency_group(item.id, dependencies))
    if item.atomic_group_id:
        peers = db.scalars(
            select(ProposalItemRecord.id).where(
                ProposalItemRecord.workspace_id == workspace_id,
                ProposalItemRecord.session_id == item.session_id,
                ProposalItemRecord.atomic_group_id == item.atomic_group_id,
            )
        ).all()
        for peer in peers:
            group.update(dependency_group(peer, dependencies))
    from ontofoundry_api.services.dataset_proposals import proposal_diagnostics
    return {
        "source_diagnostics": proposal_diagnostics(db, workspace_id, item),
        "id": item.id,
        "batch_id": item.batch_id,
        "ordinal": item.ordinal,
        "client_ref": item.client_ref,
        "operation": item.operation,
        "target_kind": item.target_kind,
        "target_id": item.target_id,
        "display_name": element_label(item.target_kind, element, elements),
        "owner_label": owner_label(item.target_kind, element, elements),
        "before": before,
        "after": after,
        # Agents may omit field_changes (display data); derive them then.
        "field_changes": item.field_changes_json
        or (field_changes(before, after) if before and after else []),
        "evidence": _evidence_view(
            db,
            workspace_id,
            [*(item.evidence_json or []), *((item.after_json or {}).get("evidence") or [])],
        ),
        "reason": item.reason or "",
        "atomic_group_id": item.atomic_group_id,
        "duplicate_candidates": duplicate_candidates(db, item),
        "depends_on": dependencies.get(item.id, []),
        "dependency_group": sorted(group),
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
        if (
            anchor is None
            or anchor.session_id != session_id
            or anchor.workspace_id != workspace_id
        ):
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
        items, dependency_map(db, ids, workspace_id, session_id), session.draft_json
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
    if (
        batch is None
        or batch.workspace_id != workspace_id
        or batch.session_id != session_id
    ):
        raise _fail(404, "BATCH_NOT_FOUND", "提案批次不存在")
    draft = session_draft(session)
    items = _batch_items(db, [batch.id], workspace_id, session_id)
    dependencies = dependency_map(db, [batch.id], workspace_id, session_id)
    statuses = effective_statuses(items, dependencies, session.draft_json)
    elements = _session_elements(draft)
    for item in items:
        element = item.after_json or item.before_json
        if element:
            elements[str(element["id"])] = (item.target_kind, element)
    return {
        **_batch_summary(batch, items, statuses),
        "items": [
            _item_view(db, workspace_id, i, statuses, dependencies, elements) for i in items
        ],
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
    payload["decisions"] = sorted(
        payload["decisions"], key=lambda d: (d["proposal_id"], d["decision"])
    )
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _apply(draft, item):
    collection = COLLECTIONS[ElementKind(item.target_kind)]
    if item.operation == "create":
        draft[collection].append(deepcopy(item.after_json))
    elif item.operation == "update":
        draft[collection] = [
            deepcopy(item.after_json) if e["id"] == item.target_id else e
            for e in draft[collection]
        ]
    else:
        draft[collection] = [e for e in draft[collection] if e["id"] != item.target_id]


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


def _decision_response(record: ProposalDecisionRequestRecord) -> dict:
    # Side-effect history lives in the decision record, never in the API DTO.
    return {key: value for key, value in record.response_json.items() if key != "_undo"}


def _undo_context(db, item):
    return {}


def _check_undo(draft, item, compatibility, undo_context):
    found = _session_elements(draft).get(item.target_id)
    collection = COLLECTIONS[ElementKind(item.target_kind)]
    unchanged = (
        found is None
        if item.operation == "delete"
        else bool(
            found
            and found[0] == item.target_kind
            and element_sha256(found[1], collection=collection)
            == element_sha256(item.after_json, collection=collection)
        )
    )
    if not unchanged:
        raise _fail(409, "PROPOSAL_UNDO_CONFLICT", "该元素在接受后又被修改，不能直接撤销")


def _inverse(item: ProposalItemRecord, context: dict) -> SimpleNamespace:
    after = deepcopy(item.before_json)
    if after is not None and item.target_kind == "link_type" and "data_join" in context:
        after["data_join"] = context["data_join"]
    return SimpleNamespace(
        operation={"create": "delete", "update": "update", "delete": "create"}[
            item.operation
        ],
        target_kind=item.target_kind,
        target_id=item.target_id,
        after_json=after,
    )


@router.post("/proposal-decisions")
def decide(
    workspace_id: str,
    session_id: str,
    body: DecisionRequest,
    request: Request,
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
        return _decision_response(previous)
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
    explicit = {d.proposal_id: d.decision for d in body.decisions}
    expanded = dict(explicit)
    groups = {i.atomic_group_id for i in items.values() if i.atomic_group_id}
    for group in groups:
        members = [i for i in batch_items if i.atomic_group_id == group]
        choices = {explicit[i.id] for i in members if i.id in explicit}
        if len(choices) != 1:
            raise _fail(409, "PROPOSAL_CONFLICT", "同一原子组不能收到相反决定")
        for member in members:
            expanded[member.id] = next(iter(choices))
            items[member.id] = member
    if len(expanded) > 500:
        raise _fail(422, "DEPENDENCY_INCOMPLETE", "展开后的原子组超过决定数量上限")
    body = body.model_copy(
        update={
            "decisions": [Decision(proposal_id=i, decision=d) for i, d in expanded.items()]
        }
    )
    draft = deepcopy(session_draft(session))
    statuses = effective_statuses(batch_items, dependencies, draft)
    by_id = {item.id: item for item in batch_items}

    accepts = [d.proposal_id for d in body.decisions if d.decision == "accept"]
    undoes = [
        d.proposal_id
        for d in body.decisions
        if d.decision == "reject" and items[d.proposal_id].status == "accepted"
    ]
    problems = []
    for decision in body.decisions:
        status, reason = statuses[decision.proposal_id]
        if decision.decision == "accept" and status != "pending":
            code = {"stale": "PROPOSAL_STALE", "conflict": "PROPOSAL_CONFLICT"}.get(
                status, "PROPOSAL_NOT_DECIDABLE"
            )
            problems.append(
                (409, code, decision.proposal_id, reason or f"提案当前为 {status}")
            )
        elif decision.decision == "reject" and status not in (
            "pending",
            "stale",
            "conflict",
            "accepted",
        ):
            problems.append(
                (
                    409,
                    "PROPOSAL_NOT_DECIDABLE",
                    decision.proposal_id,
                    f"提案当前为 {status}",
                )
            )
        elif (
            decision.decision == "restore"
            and items[decision.proposal_id].status != "rejected"
        ):
            problems.append(
                (
                    409,
                    "PROPOSAL_NOT_RESTORABLE",
                    decision.proposal_id,
                    "只有已拒绝的提案可以恢复",
                )
            )
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
            if by_id[dep].status == "accepted" and dep not in undoes:
                continue
            if dep not in accepts:
                raise _fail(
                    422,
                    "DEPENDENCY_INCOMPLETE",
                    "接受提案时必须一并接受其依赖",
                    items=[{"proposal_id": proposal_id, "reason": f"缺少依赖 {dep}"}],
                )

    for proposal_id in undoes:
        missing_dependents = [
            dep
            for dep in dependent_group(proposal_id, dependencies)
            if by_id[dep].status == "accepted" and dep not in undoes
        ]
        if missing_dependents:
            raise _fail(
                422,
                "DEPENDENCY_INCOMPLETE",
                "撤销已接受提案时必须一并拒绝依赖它的已接受提案",
                items=[
                    {
                        "proposal_id": proposal_id,
                        "reason": "缺少已接受的依赖提案：" + "、".join(missing_dependents),
                    }
                ],
            )

    before_mapping_write = deepcopy(draft)
    accepted_items = _topological([items[i] for i in accepts], dependencies)
    undone_items = list(reversed(_topological([items[i] for i in undoes], dependencies)))
    undo_contexts = {}
    for item in undone_items:
        _check_undo(draft, item, {}, {})
        _apply(draft, _inverse(item, {}))
    for item in accepted_items:
        _apply(draft, item)
    changed_items = [*undone_items, *accepted_items]
    if changed_items:
        try:
            model = OntologyDraft.model_validate(draft)
        except ValidationError as exc:
            message = str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
            raise _fail(
                422,
                "VALIDATION_FAILED",
                f"{'撤销' if undone_items else '接受'}后草稿校验未通过：{message}",
                items=[{"proposal_id": i.id, "reason": message} for i in changed_items],
            ) from exc
        from ontofoundry_api.services.join_validation import validate_join_columns

        checked_draft = model.model_dump(mode="json")
        validate_join_columns(
            db,
            workspace_id,
            before_mapping_write,
            checked_draft,
            request.app.state.settings,
        )
        check_identities(
            db,
            workspace_id,
            {
                item.target_id: item.target_kind
                for item in accepted_items
                if item.operation == "create"
            },
        )
        draft = checked_draft
        check_identities(db, workspace_id, element_kinds(draft))

    now = utc_now()
    new_revision = session.revision + 1 if changed_items else session.revision
    if changed_items:
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session.id,
                ModelingSessionRecord.revision == body.expected_session_revision,
            )
            .values(
                draft_json=draft,
                draft_sha256=draft_sha256(draft),
                revision=new_revision,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            db.rollback()
            raise _fail(409, "SESSION_REVISION_CHANGED", "草稿已更新，请刷新后重新确认")
        db.refresh(session)
    results = []
    for decision in body.decisions:
        item = items[decision.proposal_id]
        if decision.decision == "accept":
            item.status, item.accepted_revision = "accepted", new_revision
        elif decision.decision == "reject":
            item.status = "rejected"
            item.accepted_revision = None
        else:
            item.status = "pending"
        item.decided_by, item.decided_at = user.id, now
    db.flush()
    after_statuses = effective_statuses(
        _batch_items(db, batch_ids, workspace_id, session_id),
        dependencies,
        session.draft_json,
    )
    for decision in body.decisions:
        status, reason = after_statuses[decision.proposal_id]
        results.append(
            {"proposal_id": decision.proposal_id, "status": status, "reason": reason}
        )

    response = jsonable(
        {
            "session": session_response(db, session),
            "results": results,
            "validation": validate_draft(
                session_draft(session), _workspace(db, workspace_id)
            ),
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
        response_json={**response, "_undo": undo_contexts},
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
            return _decision_response(winner)
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

    sessions = db.scalars(
        select(ModelingSessionRecord).where(
            ModelingSessionRecord.workspace_id == workspace_id
        )
    ).all()
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
        "batches": {"total": total_batches, **by_status},
        "batch_failure_rate": round(by_status.get("failed", 0) / total_batches, 4)
        if total_batches
        else 0.0,
        "items": effective,
        "stale_rate": round((effective["stale"] + effective["conflict"]) / open_items, 4)
        if open_items
        else 0.0,
        "decisions": decisions,
    }


def duplicate_candidates(db, item):
    if (
        item.target_kind != "material_object"
        or item.operation != "create"
        or item.after_json is None
    ):
        return []
    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.instance_display import (
        business_identity,
        document_display_text,
    )

    draft = CoreDraft.model_validate(
        get_modeling_session(db, item.workspace_id, item.session_id).draft_json
    )
    fact = item.after_json
    identity = business_identity(draft, UUID(fact["type_id"]), fact["values"])
    if identity is None:
        return []
    return [
        {
            "id": str(e.id),
            "type_id": str(e.type_id),
            "display_text": document_display_text(draft, e),
            "expected_target_hash": element_sha256(
                e.model_dump(mode="json"), collection="material_objects"
            ),
        }
        for e in draft.material_objects
        if str(e.type_id) == fact["type_id"]
        and business_identity(draft, e.type_id, e.values) == identity
    ]


class FactProposalRevision(Strict):
    expected_session_revision: int
    target_id: str
    expected_target_hash: str
    after: MaterialObject
    reason: str | None = None


@router.post("/proposal-items/{proposal_id}/revision")
def revise_fact_proposal(
    workspace_id: str,
    session_id: str,
    proposal_id: str,
    body: FactProposalRevision,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.services.fact_revision import revise_fact

    require_member(db, workspace_id, user.id)
    batch_id = revise_fact(
        db, workspace_id, session_id, proposal_id, body, user, request.app.state.settings
    )
    return read_batch(workspace_id, session_id, batch_id, db, user)


class DatasetProposalRevision(BaseModel):
    dataset: __import__("ontofoundry_api.domain.core", fromlist=["Dataset"]).Dataset
    expected_session_revision: int


@router.put("/proposals/{proposal_id}/dataset")
def revise_dataset_source(workspace_id: str, session_id: str, proposal_id: str, body: DatasetProposalRevision, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_member(db, workspace_id, user.id)
    from ontofoundry_api.services.dataset_proposals import revise_dataset
    return revise_dataset(db, workspace_id, session_id, proposal_id, body.dataset, body.expected_session_revision)
