"""Proposal batches and decisions (design §8, frontend contract §5.1–5.2)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.contracts.proposal_reviews import ProposalBatchSummary
from ontofoundry_api.contracts.proposal_submit import ProposalSubmitResponse
from ontofoundry_api.contracts.read_models import ElementSaveImpact
from ontofoundry_api.contracts.session_writes import (
    ChangeEventPageRead,
    ElementSave,
    ElementSavePreview,
    SessionRead,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import (
    MaterialRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemRecord,
)
from ontofoundry_api.domain.core import MaterialObject, Strict
from ontofoundry_api.domain.models import PROPOSAL_COLLECTIONS
from ontofoundry_api.services import change_log, changes, instance_store
from ontofoundry_api.services.access import can_edit_workspace, require_edit, require_read
from ontofoundry_api.services.element_diff import element_label, field_changes, owner_label
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposal_submit import submit_result
from ontofoundry_api.services.proposals import (
    batch_items as _batch_items,
)
from ontofoundry_api.services.proposals import (
    dependency_group,
    dependency_map,
    effective_statuses,
)
from ontofoundry_api.services.run_credentials import verify
from ontofoundry_api.services.session_gate import batch_read_only
from ontofoundry_api.services.sessions import get_modeling_session, session_draft

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/sessions/{session_id}", tags=["proposals"]
)


def _fail(status: int, code: str, message: str, **details: Any) -> ServiceError:
    return ServiceError(message, code=code, status_code=status, details=details)


# --- reading ------------------------------------------------------------------


def _counts(items, statuses) -> dict[str, int]:
    counts = dict.fromkeys(
        ("pending", "accepted", "rejected"), 0
    )
    for item in items:
        status = statuses[item.id][0]
        if status in counts:  # superseded items are history, not counted for review
            counts[status] += 1
    return counts


def _batch_summary(batch: ProposalBatchRecord, items, statuses, session) -> dict[str, Any]:
    return ProposalBatchSummary(**{
        "id": batch.id,
        "status": batch.status,
        "created_at": batch.created_at,
        "source_session_revision": batch.source_session_revision,
        "base_version_id": batch.base_version_id,
        "counts": _counts(items, statuses),
        "error": batch.error_json,
        "producer": batch.producer_json,
        "read_only": batch_read_only(session, batch),
    }).model_dump(mode="json")


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


def _atomic_peers(db, workspace_id, session_id, items) -> dict[str, list[str]]:
    """Members of each atomic group in the session, read in one query."""
    groups = {i.atomic_group_id for i in items if i.atomic_group_id}
    peers: dict[str, list[str]] = {}
    if groups:
        for identity, group in db.execute(
            select(ProposalItemRecord.id, ProposalItemRecord.atomic_group_id).where(
                ProposalItemRecord.workspace_id == workspace_id,
                ProposalItemRecord.session_id == session_id,
                ProposalItemRecord.atomic_group_id.in_(groups),
            )
        ):
            peers.setdefault(group, []).append(identity)
    return peers


def _item_view(item, statuses, dependencies, elements, context) -> dict[str, Any]:
    db, workspace_id = context.db, context.workspace_id
    before, after = item.before_json, item.after_json
    element = after or before or {}
    status, reason = statuses[item.id]
    group = set(dependency_group(item.id, dependencies))
    for peer in context.peers.get(item.atomic_group_id, []) if item.atomic_group_id else []:
        group.update(dependency_group(peer, dependencies))
    from ontofoundry_api.services.dataset_proposals import proposal_diagnostics

    return {
        "source_diagnostics": proposal_diagnostics(db, workspace_id, item, context.diagnostics),
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
        "duplicate_candidates": context.duplicates(item),
        # What must change before this proposal can be accepted (AC-05).
        "acceptance_issues": context.acceptance(item),
        # Review hints derived on read, never stored (AR-04).
        "similar_definitions": context.alignment.similar_definitions(item),
        "physical_differences": context.alignment.physical_differences(item, elements),
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
    require_read(db, str(workspace_id), user)
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
    statuses = effective_statuses(items)
    by_batch: dict[str, list] = {}
    for item in items:
        by_batch.setdefault(item.batch_id, []).append(item)
    return {
        "items": [_batch_summary(b, by_batch.get(b.id, []), statuses, session) for b in page],
        "next_cursor": page[-1].id if len(batches) > limit else None,
    }


@router.get("/proposal-batches/{batch_id}")
def read_batch(
    workspace_id: str,
    session_id: str,
    batch_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
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
    statuses = effective_statuses(items)
    snapshot = instance_store.session_snapshot(db, workspace_id, session_id, draft)
    elements = _session_elements(snapshot)
    for item in items:
        element = item.after_json or item.before_json
        if element:
            elements[str(element["id"])] = (item.target_kind, element)
    from ontofoundry_api.services.acceptance_issues import AcceptanceIssues
    from ontofoundry_api.services.dataset_proposals import DiagnosticsContext
    from ontofoundry_api.services.instance_duplicates import DuplicateCandidates
    from ontofoundry_api.services.proposal_alignment import AlignmentContext

    # Everything an item view derives from the whole session, built once per read.
    context = SimpleNamespace(
        db=db,
        workspace_id=workspace_id,
        alignment=AlignmentContext(db, workspace_id, draft),
        diagnostics=DiagnosticsContext(db, workspace_id, session),
        duplicates=DuplicateCandidates(db, workspace_id, session),
        peers=_atomic_peers(db, workspace_id, session_id, items),
    )
    context.acceptance = AcceptanceIssues(db, session, items, dependencies, request.app.state.settings)
    return {
        **_batch_summary(batch, items, statuses, session),
        "items": [_item_view(i, statuses, dependencies, elements, context) for i in items],
    }


# --- deciding -----------------------------------------------------------------


class Decision(BaseModel):
    proposal_id: str
    decision: Literal["accept", "reject", "restore", "back_to_pending"]


class DecisionRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)
    expected_session_revision: int
    decisions: list[Decision] = Field(min_length=1, max_length=500)
    # "Accept all": accept what passes; refused proposals stay pending with their reason.
    partial: bool = False


@router.post("/proposal-decisions")
def decide(
    workspace_id: str,
    session_id: str,
    body: DecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    from ontofoundry_api.services.proposal_decisions import decide as decide_proposals

    get_modeling_session(db, workspace_id, session_id)
    return decide_proposals(
        db, workspace_id, session_id, body, user.id, request.app.state.settings
    )


class FactProposalRevision(Strict):
    expected_session_revision: int
    target_id: str
    expected_target_hash: str
    after: MaterialObject
    reason: str | None = None


@router.post("/proposals/{proposal_id}/fact-revision")
def revise_fact_proposal(
    workspace_id: str,
    session_id: str,
    proposal_id: str,
    body: FactProposalRevision,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    from ontofoundry_api.services.fact_revision import revise_fact

    batch_id = revise_fact(
        db, workspace_id, session_id, proposal_id, body, user, request.app.state.settings
    )
    return read_batch(workspace_id, session_id, batch_id, request, db, user)


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
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    from ontofoundry_api.services.proposal_revision import revise_proposal

    return revise_proposal(
        db,
        workspace_id,
        session_id,
        proposal_id,
        body.fields,
        body.expected_session_revision,
        request.app.state.settings,
        actor_id=user.id,
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
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    from ontofoundry_api.services.dataset_proposals import revise_dataset

    return revise_dataset(
        db,
        workspace_id,
        session_id,
        proposal_id,
        body.dataset,
        body.expected_session_revision,
        request.app.state.settings,
        actor_id=user.id,
    )


@router.post("/element-saves/preview", response_model=ElementSaveImpact)
def preview_element(
    workspace_id: str,
    session_id: str,
    body: ElementSavePreview,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    return changes.preview_element_save(db, workspace_id, session_id, body, request.app.state.settings, user.id)


@router.post("/element-saves", response_model=SessionRead)
def save_element(
    workspace_id: str,
    session_id: str,
    body: ElementSave,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    return changes.save_element(db, workspace_id, session_id, body, request.app.state.settings, user.id)


MAX_RESULT_BYTES = 8 * 1024 * 1024


def _invalid():
    return ServiceError(
        "错误 [RUN_CREDENTIAL_INVALID]：需要本轮运行凭据。未提交。同参重试无效，请重新发起建模。",
        code="RUN_CREDENTIAL_INVALID",
        status_code=401,
    )


@router.post("/proposals", response_model=ProposalSubmitResponse)
async def submit_proposals(
    workspace_id: str,
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    # Not mcp_principal: that one ends with the run, but a submitter whose
    # response was lost must still be able to fetch its receipt.
    token = request.headers.get("authorization", "").partition(" ")[2]
    grant = verify(request.app.state.settings.session_secret, token)
    if grant is None or grant.session_id != session_id or grant.workspace_id != workspace_id:
        raise _invalid()
    session = db.get(ModelingSessionRecord, grant.session_id)
    if (
        session is None
        or session.workspace_id != workspace_id
        or not can_edit_workspace(db, workspace_id, grant.user_id)
    ):
        raise _invalid()
    raw = await request.body()
    if len(raw) > MAX_RESULT_BYTES:
        raise ServiceError("建模结果超过 8 MB", code="RESULT_TOO_LARGE", status_code=413)
    return submit_result(
        db,
        request.app.state.settings,
        workspace_id,
        session_id,
        grant.run_token,
        raw,
        actor_id=grant.user_id,
    )


@router.get("/change-events", response_model=ChangeEventPageRead)
def list_change_events(
    workspace_id: str,
    session_id: str,
    target_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    get_modeling_session(db, workspace_id, session_id)
    return change_log.list_events(
        db,
        workspace_id,
        session_id,
        target_id=target_id,
        limit=limit,
        cursor=cursor,
    )
