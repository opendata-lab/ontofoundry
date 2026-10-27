"""Explicitly revise pending fact creation into an update with appended evidence."""

from uuid import UUID

from ontofoundry_api.contracts.proposals import (
    walk_references,
)
from ontofoundry_api.db_models import ProposalItemRecord, utc_now
from ontofoundry_api.domain.canonical import canonical
from ontofoundry_api.domain.evidence import EvidenceError
from ontofoundry_api.services import instance_store
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposals import (
    batch_items,
    dependency_map,
    effective_statuses,
)


def revise_fact(db, workspace_id, session_id, proposal_id, body, actor, settings):
    def fail(code, message, status=409):
        raise ServiceError(message, code=code, status_code=status)

    from ontofoundry_api.services.proposal_apply import (
        save_pending,
        stored_items,
        trial_apply,
    )
    from ontofoundry_api.services.session_gate import (
        lock_session,
        require_current_batch,
        require_idle,
    )
    session = lock_session(db, workspace_id, session_id)
    require_idle(session)
    if session.revision != body.expected_session_revision:
        fail("SESSION_REVISION_CHANGED", "草稿已更新")
    item = db.get(ProposalItemRecord, proposal_id)
    if item is None or item.workspace_id != workspace_id or item.session_id != session_id:
        fail("PROPOSAL_NOT_FOUND", "提案不属于当前会话", 422)
    require_current_batch(db, session, item.batch_id)
    items = batch_items(db, [item.batch_id], workspace_id, session_id)
    dependencies = dependency_map(db, [item.batch_id], workspace_id, session_id)
    instance_baseline = instance_store.baseline(db, workspace_id, session_id)
    statuses = effective_statuses(items, dependencies, session.draft_json, instance_baseline)
    if (
        statuses[item.id][0] != "pending"
        or item.target_kind != "material_object"
        or item.operation != "create"
    ):
        fail("PROPOSAL_NOT_DECIDABLE", "只允许修订当前有效的事实新增提案")
    entry = next((e for e in instance_baseline["items"] if e["target_id"] == body.target_id
                  and e["target_kind"] == "material_object"), None)
    target = entry["element"] if entry else None
    if (
        target is None
        or body.after.id != UUID(body.target_id)
        or str(body.after.type_id) != item.after_json["type_id"]
        or target["type_id"] != item.after_json["type_id"]
    ):
        fail("VALIDATION_FAILED", "事实目标、类型或 after.id 不匹配", 422)
    if entry["hash"] != body.expected_target_hash:
        fail("PROPOSAL_TARGET_CHANGED", "事实目标已变化")
    after = body.after.model_dump(mode="json")
    supplied = {e["id"]: e for e in after["evidence"]}
    for e in [*target["evidence"], *item.after_json["evidence"]]:
        if e["id"] not in supplied or canonical(e) != canonical(supplied[e["id"]]):
            fail("EVIDENCE_INVALID", "必须保留原事实和选定提案的证据 UUID 与内容", 422)
    try:
        after = instance_store.reconcile_evidence(target, after, "material_object",
            lookup=material_lookup(db, settings, workspace_id), actor=actor.id, now=utc_now())
    except EvidenceError as exc:
        raise ServiceError(str(exc), code=exc.code, status_code=422) from exc
    pending = stored_items([i for i in items if i.status == "pending"], dependencies)
    for proposal in pending:
        if proposal.id == item.id:
            proposal.operation = "update"
            proposal.target_id = body.target_id
            proposal.before, proposal.after = target, after
            proposal.expected_target_hash = body.expected_target_hash
            proposal.expected_instance_revision = entry["revision"]
            proposal.reason = body.reason or proposal.reason
        elif proposal.after:
            proposal.after = walk_references(proposal.target_kind, proposal.after,
                lambda value: body.target_id if str(value) == item.target_id else value)
    trial = trial_apply(db, workspace_id, session, pending, settings)
    save_pending(db, session, item.batch_id, trial)
    session.revision += 1
    db.commit()
    return item.batch_id
