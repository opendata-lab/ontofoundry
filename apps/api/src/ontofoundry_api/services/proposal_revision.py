"""Revise the content of a pending create or update proposal before it is decided."""

from copy import deepcopy

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from ontofoundry_api.contracts.proposals import item_fingerprint
from ontofoundry_api.db_models import ModelingSessionRecord, ProposalItemRecord
from ontofoundry_api.domain.models import ELEMENT_MODELS, ElementKind
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposals import (
    batch_items,
    dependency_map,
    effective_statuses,
)


def revise_proposal(db, workspace_id, session_id, proposal_id, after, expected_revision):
    def fail(code, message, status=409):
        raise ServiceError(message, code=code, status_code=status)

    session = db.scalar(
        select(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == session_id,
            ModelingSessionRecord.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if session is None:
        fail("SESSION_NOT_FOUND", "会话不存在", 404)
    if session.revision != expected_revision:
        fail("SESSION_REVISION_CHANGED", "草稿已更新，请刷新后重试")
    item = db.get(ProposalItemRecord, proposal_id)
    if item is None or item.workspace_id != workspace_id or item.session_id != session_id:
        fail("PROPOSAL_NOT_FOUND", "提案不属于当前会话", 404)
    items = batch_items(db, [item.batch_id], workspace_id, session_id)
    dependencies = dependency_map(db, [item.batch_id], workspace_id, session_id)
    status = effective_statuses(items, dependencies, session.draft_json)[item.id][0]
    if status != "pending" or item.operation not in {"create", "update"}:
        fail("PROPOSAL_NOT_DECIDABLE", "只有待审阅的新增或修改提案可以修改")

    revised = deepcopy(after)
    # Identity and evidence belong to the proposal, not to the reviewer's edit.
    revised["id"] = item.target_id
    if "evidence" in (item.after_json or {}):
        revised["evidence"] = deepcopy(item.after_json["evidence"])
    try:
        revised = (
            TypeAdapter(ELEMENT_MODELS[ElementKind(item.target_kind)])
            .validate_python(revised)
            .model_dump(mode="json")
        )
    except ValidationError as exc:
        details = [
            {"path": "/".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors()[:10]
        ]
        raise ServiceError(
            "修改后的内容不符合元素格式", code="VALIDATION_FAILED", status_code=422, details={"errors": details}
        ) from exc

    item.after_json = revised
    item.fingerprint = item_fingerprint(item.operation, item.target_kind, item.target_id, revised)
    # Display differences are derived from before/after on read.
    item.field_changes_json = []
    session.revision += 1
    db.commit()
    return {"proposal_id": item.id, "session_revision": session.revision}
