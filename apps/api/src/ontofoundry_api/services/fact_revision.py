"""Explicitly revise pending fact creation into an update with appended evidence."""

from copy import deepcopy
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select

from ontofoundry_api.contracts.proposals import (
    ParsedBatch,
    ParsedItem,
    group_items,
    item_fingerprint,
    walk_references,
)
from ontofoundry_api.db_models import ModelingSessionRecord, ProposalItemRecord, utc_now
from ontofoundry_api.domain.canonical import canonical, domain_sha256
from ontofoundry_api.domain.evidence import EvidenceError
from ontofoundry_api.services import instance_store
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposals import (
    batch_items,
    dependency_map,
    effective_statuses,
    store_batch,
)


def revise_fact(db, workspace_id, session_id, proposal_id, body, actor, settings):
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
    from ontofoundry_api.services.instance_store import require_open_session
    require_open_session(session)
    if session.revision != body.expected_session_revision:
        fail("SESSION_REVISION_CHANGED", "草稿已更新")
    item = db.get(ProposalItemRecord, proposal_id)
    if item is None or item.workspace_id != workspace_id or item.session_id != session_id:
        fail("PROPOSAL_NOT_FOUND", "提案不属于当前会话", 422)
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
        fail("PROPOSAL_STALE", "事实目标已变化")
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
    selected = {item.id}
    changed = True
    while changed:
        old = set(selected)
        groups = {
            i.atomic_group_id for i in items if i.id in selected and i.atomic_group_id
        }
        selected.update(
            i.id
            for i in items
            if i.atomic_group_id in groups
            or any(d in selected for d in dependencies.get(i.id, []))
        )
        # Migrate pending upstream proposals needed by the selected downstream
        # graph. Already accepted dependencies remain satisfied in the session.
        selected.update(
            d
            for identity in tuple(selected)
            for d in dependencies.get(identity, [])
            if statuses[d][0] == "pending"
        )
        changed = selected != old
    if any(i.status != "pending" for i in items if i.id in selected):
        fail("PROPOSAL_CONFLICT", "不能部分修订已决定的依赖组")
    if any(
        statuses[d][0] != "accepted"
        for identity in selected
        for d in dependencies.get(identity, [])
        if d not in selected
    ):
        fail("PROPOSAL_CONFLICT", "修订依赖已失效，请先处理依赖提案")
    batch_id = str(uuid4())
    parsed = []
    id_map = {i.id: str(uuid5(UUID(batch_id), i.id)) for i in items if i.id in selected}
    for i in items:
        if i.id not in selected:
            continue
        new_after = deepcopy(i.after_json)
        target_id = i.target_id
        before = deepcopy(i.before_json)
        operation = i.operation
        expected = i.expected_target_hash
        if i.id == item.id:
            target_id = body.target_id
            before = target
            new_after = after
            operation = "update"
            expected = body.expected_target_hash
        elif new_after:
            new_after = walk_references(
                i.target_kind,
                new_after,
                lambda value: body.target_id if str(value) == item.target_id else value,
            )
        parsed.append(
            ParsedItem(
                id_map[i.id],
                len(parsed),
                i.client_ref,
                operation,
                i.target_kind,
                target_id,
                expected,
                before,
                new_after,
                [],
                i.evidence_json or [],
                body.reason or i.reason or "",
                item_fingerprint(operation, i.target_kind, target_id, new_after),
                # Accepted upstream changes already live in the session baseline.
                [id_map[d] for d in dependencies.get(i.id, []) if d in selected],
            )
        )
    try:
        for old_item, new_item in zip([i for i in items if i.id in selected], parsed, strict=True):
            new_item.expected_instance_revision = old_item.expected_instance_revision
            if new_item.target_id == body.target_id:
                new_item.expected_instance_revision = entry["revision"]
        group_items(instance_store.session_snapshot(db, workspace_id, session_id, session.draft_json), parsed)
    except ValueError as exc:
        fail("VALIDATION_FAILED", str(exc), 422)
    manifest = {
        "run_token": "revision:" + batch_id,
        "base_version_id": session.base_version_id,
        "base_version_sha256": session.base_version_sha256,
        "source_session_revision": session.revision,
        "source_draft_sha256": session.draft_sha256,
        "producer": {"kind": "manual_revision", "proposal_id": item.id},
    }
    store_batch(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        task_id=None,
        manifest=manifest,
        parsed=ParsedBatch(batch_id, domain_sha256({"revision": batch_id}), parsed),
    )
    for i in items:
        if i.id in selected:
            i.status = "superseded"
    db.commit()
    return batch_id
