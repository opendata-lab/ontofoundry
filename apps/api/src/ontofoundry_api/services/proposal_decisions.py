"""Atomic proposal decisions across ontology definitions and instance revisions."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ontofoundry_api.api.modeling import session_response
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalDecisionItemRecord,
    ProposalDecisionRequestRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.instances import INSTANCE_KINDS, definitions
from ontofoundry_api.domain.models import PROPOSAL_COLLECTIONS, ElementKind, OntologyDraft
from ontofoundry_api.domain.snapshot import draft_sha256
from ontofoundry_api.services import instance_proposals, instance_store
from ontofoundry_api.services.core_validation import validation_report
from ontofoundry_api.services.errors import ConflictError, ServiceError
from ontofoundry_api.services.identities import check_identities, element_kinds
from ontofoundry_api.services.proposals import batch_items as _batch_items
from ontofoundry_api.services.proposals import (
    dependency_group,
    dependency_map,
    dependent_group,
    effective_statuses,
)


def _fail(status, code, message, **details):
    return ServiceError(message, code=code, status_code=status, details=details)


def _session_elements(draft):
    return {
        e["id"]: (kind.value, e)
        for kind, c in PROPOSAL_COLLECTIONS.items()
        for e in draft.get(c, [])
    }


def _request_sha256(body) -> str:
    payload = body.model_dump()
    payload["decisions"] = sorted(
        payload["decisions"], key=lambda d: (d["proposal_id"], d["decision"])
    )
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _apply(draft, item):
    collection = PROPOSAL_COLLECTIONS[ElementKind(item.target_kind)]
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


def _check_undo(draft, item, compatibility, undo_context):
    found = _session_elements(draft).get(item.target_id)
    collection = PROPOSAL_COLLECTIONS[ElementKind(item.target_kind)]
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


def decide(db: Session, workspace_id: str, session_id: str, body, actor_id: str, settings):
    instance_store.lock_workspace(db, workspace_id)
    # 1. Lock the session row.
    session = db.scalar(
        select(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == session_id,
            ModelingSessionRecord.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if session.abandoned_at is not None:
        raise _fail(409, "SESSION_ABANDONED", "会话已放弃")
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
            "decisions": [
                type(body.decisions[0])(proposal_id=i, decision=d)
                for i, d in expanded.items()
            ]
        }
    )
    draft = instance_store.session_snapshot(
        db, workspace_id, session_id, deepcopy(session.draft_json)
    )
    statuses = effective_statuses(
        batch_items,
        dependencies,
        draft,
        instance_store.baseline(db, workspace_id, session_id),
    )
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
        if item.target_kind in INSTANCE_KINDS:
            instance_proposals.check_undo(db, workspace_id, session_id, item)
        else:
            _check_undo(draft, item, {}, {})
        _apply(draft, _inverse(item, {}))
    for item in accepted_items:
        _apply(draft, item)
    changed_items = [*undone_items, *accepted_items]
    if changed_items:
        try:
            model = OntologyDraft.model_validate(definitions(draft))
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
            definitions(before_mapping_write),
            checked_draft,
            settings,
        )
        check_identities(
            db,
            workspace_id,
            {
                item.target_id: item.target_kind
                for item in accepted_items
                if item.operation == "create" and item.target_kind not in INSTANCE_KINDS
            },
        )
        from ontofoundry_api.services.materials_lookup import material_lookup

        checked_draft = instance_proposals.apply_changes(
            db,
            workspace_id,
            session_id,
            draft,
            accepted_items,
            undone_items,
            actor_id,
            material_lookup(db, settings, workspace_id),
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
        item.decided_by, item.decided_at = actor_id, now
    db.flush()
    after_statuses = effective_statuses(
        _batch_items(db, batch_ids, workspace_id, session_id),
        dependencies,
        session.draft_json,
        instance_store.baseline(db, workspace_id, session_id),
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
            "validation": validation_report(deepcopy(session.draft_json)),
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
        actor_id=actor_id,
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
