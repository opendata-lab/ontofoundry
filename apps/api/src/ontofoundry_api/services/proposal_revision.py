"""Revise the content of a pending create or update proposal before it is decided."""

from copy import deepcopy

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, select, update

from ontofoundry_api.contracts.proposals import item_fingerprint
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
)
from ontofoundry_api.domain.models import ELEMENT_MODELS, ElementKind
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposals import (
    batch_items,
    dependency_map,
    effective_statuses,
)

# Identity, provenance and inheritance stay as proposed.
LOCKED_FIELDS = {"id", "evidence", "extends", "type_id"}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def revise_proposal(db, workspace_id, session_id, proposal_id, fields, expected_revision):
    """Merge reviewed field values into the proposal's current content."""

    def fail(code, message, status=409, details=None):
        raise ServiceError(message, code=code, status_code=status, details=details)

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
    if status != "pending" or item.operation not in {"create", "update"} or item.after_json is None:
        fail("PROPOSAL_NOT_DECIDABLE", "只有待审阅的新增或修改提案可以修改")
    locked = sorted(k for k in fields if k in LOCKED_FIELDS or k.endswith("_id"))
    if locked:
        fail("FIELD_NOT_EDITABLE", "标识、证据和引用字段不能在审阅时修改", 422, {"errors": [{"path": k, "message": "不可修改"} for k in locked]})

    # Merging into the stored content keeps earlier saves of other fields.
    revised = {**deepcopy(item.after_json), **deepcopy(fields)}
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
        fail("VALIDATION_FAILED", "修改后的内容不符合元素格式", 422, {"errors": details})

    # Compare-and-set as well, for databases that ignore FOR UPDATE.
    changed = db.execute(
        update(ModelingSessionRecord)
        .where(ModelingSessionRecord.id == session_id, ModelingSessionRecord.revision == expected_revision)
        .values(revision=expected_revision + 1)
    )
    if changed.rowcount != 1:
        db.rollback()
        fail("SESSION_REVISION_CHANGED", "草稿已更新，请刷新后重试")

    # Drop stored edges to proposals the old content referenced and the new one no longer does.
    before_refs, after_refs = set(_strings(item.after_json)), set(_strings(revised))
    by_id = {i.id: i for i in items}
    dropped = [
        dep for dep in dependencies.get(item.id, [])
        if dep in by_id and by_id[dep].target_id in before_refs and by_id[dep].target_id not in after_refs
    ]
    if dropped:
        db.execute(
            delete(ProposalItemDependencyRecord).where(
                ProposalItemDependencyRecord.item_id == item.id,
                ProposalItemDependencyRecord.depends_on_item_id.in_(dropped),
            )
        )

    item.after_json = revised
    item.fingerprint = item_fingerprint(item.operation, item.target_kind, item.target_id, revised)
    # Display differences are derived from before/after on read.
    item.field_changes_json = []
    db.commit()
    return {"proposal_id": item.id, "session_revision": expected_revision + 1}
