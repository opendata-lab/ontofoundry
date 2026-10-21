"""Proposal batches and decisions (design §8, frontend contract §5.1–5.2)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import (
    get_modeling_session,
    require_member,
    session_draft,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import (
    MaterialRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalDecisionItemRecord,
    ProposalItemRecord,
)
from ontofoundry_api.domain.core import MaterialObject, Strict
from ontofoundry_api.domain.models import (
    PROPOSAL_COLLECTIONS,
)
from ontofoundry_api.services import instance_store
from ontofoundry_api.services.element_diff import element_label, field_changes, owner_label
from ontofoundry_api.services.errors import ServiceError
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


def _item_view(db, workspace_id, item, statuses, dependencies, elements, alignment=None) -> dict[str, Any]:
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
        # Review hints derived on read, never stored (AR-04).
        "similar_definitions": alignment.similar_definitions(item) if alignment else [],
        "physical_differences": alignment.physical_differences(item, elements) if alignment else [],
        "depends_on": dependencies.get(item.id, []),
        "dependency_group": sorted(group),
        "status": status,
        "stored_status": item.status,
        "status_reason": reason,
        "accepted_revision": item.accepted_revision,
        "expected_instance_revision": item.expected_instance_revision,
        "accepted_instance_revision": item.accepted_instance_revision,
        "decided_at": item.decided_at,
    }


def _session_elements(draft: dict) -> dict[str, tuple[str, dict]]:
    return {
        str(element["id"]): (kind.value, element)
        for kind, collection in PROPOSAL_COLLECTIONS.items()
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
        items,
        dependency_map(db, ids, workspace_id, session_id),
        session.draft_json,
        instance_store.baseline(db, workspace_id, session_id),
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
    statuses = effective_statuses(
        items,
        dependencies,
        session.draft_json,
        instance_store.baseline(db, workspace_id, session_id),
    )
    elements = _session_elements(
        instance_store.session_snapshot(db, workspace_id, session_id, draft)
    )
    for item in items:
        element = item.after_json or item.before_json
        if element:
            elements[str(element["id"])] = (item.target_kind, element)
    from ontofoundry_api.services.proposal_alignment import AlignmentContext

    alignment = AlignmentContext(db, workspace_id, draft)
    return {
        **_batch_summary(batch, items, statuses),
        "items": [
            _item_view(db, workspace_id, i, statuses, dependencies, elements, alignment)
            for i in items
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


@router.post("/proposal-decisions")
def decide(
    workspace_id: str,
    session_id: str,
    body: DecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.services.proposal_decisions import decide as decide_proposals

    require_member(db, workspace_id, user.id)
    get_modeling_session(db, workspace_id, session_id)
    return decide_proposals(
        db, workspace_id, session_id, body, user.id, request.app.state.settings
    )


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
        for status, _ in effective_statuses(
            items,
            deps,
            session_draft(session),
            instance_store.baseline(db, workspace_id, session.id),
        ).values():
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
    candidates = instance_store.baseline(db, item.workspace_id, item.session_id)["items"]
    return [
        {
            "id": str(e.id),
            "type_id": str(e.type_id),
            "display_text": document_display_text(draft, e),
            "expected_target_hash": entry["hash"],
            "revision": entry["revision"],
        }
        for entry in candidates
        if entry["target_kind"] == "material_object"
        for e in [MaterialObject.model_validate(entry["element"])]
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


class ProposalContentRevision(BaseModel):
    model_config = {"extra": "forbid"}
    # Top-level fields to replace; the rest of the proposed content stays as stored.
    fields: dict = Field(min_length=1)
    expected_session_revision: int


@router.patch("/proposals/{proposal_id}/after")
def revise_proposal_content(
    workspace_id: str,
    session_id: str,
    proposal_id: str,
    body: ProposalContentRevision,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    from ontofoundry_api.services.proposal_revision import revise_proposal

    return revise_proposal(
        db,
        workspace_id,
        session_id,
        proposal_id,
        body.fields,
        body.expected_session_revision,
    )


class DatasetProposalRevision(BaseModel):
    dataset: __import__("ontofoundry_api.domain.core", fromlist=["Dataset"]).Dataset
    expected_session_revision: int


@router.put("/proposals/{proposal_id}/dataset")
def revise_dataset_source(
    workspace_id: str,
    session_id: str,
    proposal_id: str,
    body: DatasetProposalRevision,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    from ontofoundry_api.services.dataset_proposals import revise_dataset

    return revise_dataset(
        db,
        workspace_id,
        session_id,
        proposal_id,
        body.dataset,
        body.expected_session_revision,
    )
