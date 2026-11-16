"""Shared proposal/acceptance checks and transactional human saves (AI-09)."""

from copy import deepcopy
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from ontofoundry_api.contracts.proposals import ParsedItem, item_fingerprint
from ontofoundry_api.db_models import (
    ElementSaveRequestRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalDecisionItemRecord,
    ProposalDecisionRequestRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import canonical, element_sha256
from ontofoundry_api.domain.evidence import EvidenceError, reconcile_draft_evidence
from ontofoundry_api.domain.instances import definitions
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.domain.snapshot import draft_sha256
from ontofoundry_api.services import change_log
from ontofoundry_api.services.element_diff import element_changes, field_changes
from ontofoundry_api.services.element_save import (
    calculate_element_save,
    check_confirmations,
)
from ontofoundry_api.services.errors import ConflictError, ServiceError
from ontofoundry_api.services.import_integrity import payload_sha256
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposal_apply import trial_apply
from ontofoundry_api.services.session_gate import lock_session, require_draft_edit


def check_proposal(db, workspace_id, session, items, settings, **kwargs):
    """Structure, references, graph and boolean conditions, allowing incompleteness."""
    return trial_apply(db, workspace_id, session, items, settings, **kwargs)


def check_accept(db, workspace_id, session, items, settings, **kwargs):
    """The proposal checks plus the existing AC acceptance rules."""
    return trial_apply(db, workspace_id, session, items, settings, accepting=True, **kwargs)


def _items(before, after):
    items = []
    for ordinal, change in enumerate(element_changes(before, after)):
        kind, identity = change["element_kind"], change["element_id"]
        old, new = change["before"], change["after"]
        operation = {"created": "create", "updated": "update", "deleted": "delete"}[change["change"]]
        items.append(ParsedItem(
            id=str(uuid4()), ordinal=ordinal, client_ref=None,
            operation=operation, target_kind=kind, target_id=identity,
            expected_target_hash=element_sha256(old, collection=COLLECTIONS[ElementKind(kind)]) if old else None,
            before=old, after=new, field_changes=change["field_changes"], evidence=[],
            reason="人工保存并自动接受",
            fingerprint=item_fingerprint(operation, kind, identity, new),
        ))
    # One editor save accepts the aggregate and its automatic rewrites together.
    # In particular, a value type and its effective property kinds cannot pass
    # the proposal validator as independent prefixes.
    if len(items) > 1:
        group = str(uuid4())
        for item in items:
            item.atomic_group_id = group
    return items


def _calculate(db, workspace_id, session, body, settings, actor):
    if session.revision != body.expected_session_revision:
        raise ConflictError("草稿已更新，请重新打开后再保存", code="SESSION_REVISION_CHANGED")
    require_draft_edit(db, session)
    try:
        if body.draft.get("schema_version") != "core-1":
            raise ValueError("只接受 core-1 草稿")
        calculation = calculate_element_save(
            session.draft_json, body.draft, body.target_kind, body.target_id,
        )
        # Reconcile only the bounded candidate, so unrelated evidence cannot be
        # silently rewritten or used to mask an out-of-scope client edit.
        calculation.session_draft = reconcile_draft_evidence(
            session.draft_json, calculation.session_draft,
            lookup=material_lookup(db, settings, workspace_id), actor_id=actor, now=utc_now(),
        )
        return calculation
    except EvidenceError as exc:
        raise ServiceError(str(exc), code=exc.code, status_code=422) from exc
    except (ValueError, KeyError) as exc:
        raise ServiceError("内容校验失败：" + str(exc), code="ELEMENT_VALIDATION_FAILED", status_code=422) from exc


def preview_element_save(db, workspace_id, session_id, body, settings, actor):
    session = lock_session(db, workspace_id, session_id)
    calculation = _calculate(db, workspace_id, session, body, settings, actor)
    return {"session_revision": session.revision, "affected_items": calculation.affected_items}


def _intervening_change(db, session, row):
    # Decision receipts retain accepts even after their rows have been undone,
    # so returning to identical content still breaks the human edit chain.
    newer = db.scalar(select(ProposalItemRecord.id).where(
        ProposalItemRecord.workspace_id == session.workspace_id,
        ProposalItemRecord.session_id == session.id,
        ProposalItemRecord.target_id == row.target_id,
        ProposalItemRecord.id != row.id,
        ProposalItemRecord.accepted_revision > row.accepted_revision,
    ).limit(1))
    if newer:
        return True
    return db.scalar(select(ProposalDecisionItemRecord.item_id)
        .join(ProposalDecisionRequestRecord, ProposalDecisionRequestRecord.id == ProposalDecisionItemRecord.request_id)
        .join(ProposalItemRecord, ProposalItemRecord.id == ProposalDecisionItemRecord.item_id)
        .where(
            ProposalItemRecord.workspace_id == session.workspace_id,
            ProposalItemRecord.session_id == session.id,
            ProposalItemRecord.target_id == row.target_id,
            ProposalDecisionItemRecord.decision == "accept",
            ProposalDecisionRequestRecord.result_session_revision > row.accepted_revision,
            ProposalDecisionRequestRecord.result_session_revision > ProposalDecisionRequestRecord.expected_session_revision,
        ).limit(1)) is not None


def _human_batch(db, session):
    batch = db.get(ProposalBatchRecord, session.human_batch_id) if session.human_batch_id else None
    if batch is None:
        from ontofoundry_api.contracts.proposals import SCHEMA_VERSION

        identity = str(uuid4())
        batch = ProposalBatchRecord(
            id=identity, workspace_id=session.workspace_id, session_id=session.id,
            run_token="human:" + identity, schema_version=SCHEMA_VERSION,
            base_version_id=session.base_version_id, base_version_sha256=session.base_version_sha256,
            source_session_revision=session.revision, source_draft_sha256=session.draft_sha256,
            producer_json={"kind": "human"}, result_sha256=payload_sha256(identity), status="available",
        )
        db.add(batch)
        db.flush()
        session.human_batch_id = batch.id
    return batch


def _record_human_changes(db, session, trial, actor, revision):
    batch = _human_batch(db, session)
    rows = list(db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.batch_id == batch.id)))
    ordinal = max((r.ordinal for r in rows), default=-1) + 1
    item_ids = {}
    groups = {}
    reverted_ids = set()
    now = utc_now()
    for item in trial.items:
        candidates = [r for r in rows if r.target_id == item.target_id and r.status == "accepted"]
        previous = max(candidates, key=lambda r: r.accepted_revision or -1, default=None)
        reusable = (
            previous is not None and previous.accepted_revision is not None
            and canonical(previous.after_json) == canonical(item.before)
            and not _intervening_change(db, session, previous)
        )
        previous_snapshot = (
            change_log.proposal_snapshot(
                status=previous.status,
                operation=previous.operation,
                before=previous.before_json,
                after=previous.after_json,
            )
            if reusable
            else None
        )
        row = previous if reusable else ProposalItemRecord(
            id=item.id, workspace_id=session.workspace_id, session_id=session.id,
            batch_id=batch.id, ordinal=ordinal, target_kind=item.target_kind, target_id=item.target_id,
        )
        if not reusable:
            ordinal += 1
            row.before_json = deepcopy(item.before)
            db.add(row)
            rows.append(row)
        item_ids[item.id] = row.id
        draft_action = (
            "removed" if item.after is None else ("added" if item.before is None else "updated")
        )
        if canonical(row.before_json) == canonical(item.after):
            # Keep the rejected proposal as the prior change's review record.
            row.status, row.accepted_revision = "rejected", None
            row.decided_at, row.decided_by = now, actor
            row.atomic_group_id = None
            reverted_ids.add(row.id)
            proposal_event = change_log.record_proposal_event(
                db,
                workspace_id=session.workspace_id,
                session_id=session.id,
                actor_id=actor,
                actor_kind="human",
                action="rejected",
                target_kind=row.target_kind,
                target_id=row.target_id,
                proposal_id=row.id,
                batch_id=batch.id,
                before=previous_snapshot,
                after=change_log.proposal_snapshot(
                    status="rejected",
                    operation=row.operation,
                    before=row.before_json,
                    after=row.after_json,
                ),
                at=now,
            )
            change_log.record_draft_event(
                db,
                workspace_id=session.workspace_id,
                session_id=session.id,
                actor_id=actor,
                actor_kind="human",
                action=draft_action,
                target_kind=item.target_kind,
                target_id=item.target_id,
                proposal_id=row.id,
                batch_id=batch.id,
                before=item.before,
                after=item.after,
                cause_id=proposal_event.id,
                at=now,
            )
            continue
        row.after_json = deepcopy(item.after)
        row.operation = "create" if row.before_json is None else "delete" if item.after is None else "update"
        row.expected_target_hash = (
            element_sha256(row.before_json, collection=COLLECTIONS[ElementKind(item.target_kind)])
            if row.before_json else None
        )
        row.field_changes_json = field_changes(row.before_json, row.after_json) if row.before_json and row.after_json else []
        row.evidence_json, row.reason = [], item.reason
        # Distinct positions in the undo chain can propose the same after-image.
        row.fingerprint = payload_sha256([row.id, item_fingerprint(row.operation, row.target_kind, row.target_id, row.after_json)])
        row.status, row.accepted_revision = "accepted", revision
        row.decided_by, row.decided_at = actor, now
        row.atomic_group_id = row.atomic_group_id or item.atomic_group_id
        if item.atomic_group_id:
            groups.setdefault(item.atomic_group_id, []).append(row)
        proposal_event = change_log.record_proposal_event(
            db,
            workspace_id=session.workspace_id,
            session_id=session.id,
            actor_id=actor,
            actor_kind="human",
            action="revised" if reusable else "created",
            target_kind=row.target_kind,
            target_id=row.target_id,
            proposal_id=row.id,
            batch_id=batch.id,
            before=previous_snapshot,
            after=change_log.proposal_snapshot(
                status="accepted",
                operation=row.operation,
                before=row.before_json,
                after=row.after_json,
            ),
            at=now,
        )
        change_log.record_draft_event(
            db,
            workspace_id=session.workspace_id,
            session_id=session.id,
            actor_id=actor,
            actor_kind="human",
            action=draft_action,
            target_kind=item.target_kind,
            target_id=item.target_id,
            proposal_id=row.id,
            batch_id=batch.id,
            before=item.before,
            after=item.after,
            cause_id=proposal_event.id,
            at=now,
        )
    # A later save can overlap several existing groups. Preserve their active
    # peers even when those peers were not edited in this save.
    for members in groups.values():
        group_ids = {row.atomic_group_id for row in members}
        group_id = members[0].atomic_group_id
        for row in rows:
            if row.status == "accepted" and row.atomic_group_id in group_ids:
                row.atomic_group_id = group_id
    db.flush()
    # A revised target's outgoing edges come from the newly checked candidate.
    changed_ids = list(item_ids.values())
    db.execute(delete(ProposalItemDependencyRecord).where(
        ProposalItemDependencyRecord.batch_id == batch.id,
        or_(
            ProposalItemDependencyRecord.item_id.in_(changed_ids),
            ProposalItemDependencyRecord.depends_on_item_id.in_(reverted_ids),
        ),
    ))
    for item in trial.items:
        if item_ids[item.id] in reverted_ids:
            continue
        for dependency in item.depends_on:
            if item_ids[dependency] in reverted_ids:
                continue
            db.add(ProposalItemDependencyRecord(
                workspace_id=session.workspace_id, session_id=session.id, batch_id=batch.id,
                item_id=item_ids[item.id], depends_on_item_id=item_ids[dependency],
            ))
    batch.source_session_revision = revision
    batch.result_sha256 = payload_sha256([[r.id, r.fingerprint, r.status] for r in rows])
    return batch.id


def save_element(db, workspace_id, session_id, body, settings, actor):
    from ontofoundry_api.services.sessions import session_response

    session = lock_session(db, workspace_id, session_id, allow_abandoned=True)
    request_hash = payload_sha256(body.model_dump(mode="json"))

    def receipt():
        previous = db.scalar(select(ElementSaveRequestRecord).where(
            ElementSaveRequestRecord.workspace_id == workspace_id,
            ElementSaveRequestRecord.session_id == session_id,
            ElementSaveRequestRecord.idempotency_key == body.idempotency_key,
        ))
        if previous is None:
            return None
        if previous.request_sha256 != request_hash or previous.actor_id != actor:
            raise ConflictError("同一幂等键已用于不同的请求", code="IDEMPOTENCY_MISMATCH")
        return deepcopy(previous.response_json)

    previous = receipt()
    if previous is not None:
        return previous
    try:
        calculation = _calculate(db, workspace_id, session, body, settings, actor)
        check_confirmations(calculation.affected_items, body.affected_items)
        items = _items(session.draft_json, calculation.session_draft)
        accepted = check_accept(db, workspace_id, session, items, settings)
        if items:
            revision = session.revision + 1
            batch_id = _record_human_changes(db, session, accepted, actor, revision)
            draft = definitions(accepted.candidate)
            changed = db.execute(update(ModelingSessionRecord).where(
                ModelingSessionRecord.id == session.id,
                ModelingSessionRecord.revision == body.expected_session_revision,
            ).values(
                draft_json=draft, draft_sha256=draft_sha256(draft), revision=revision,
                human_batch_id=batch_id, updated_at=utc_now(),
            ))
            if changed.rowcount != 1:
                raise ConflictError("草稿已更新，请重新打开后再保存", code="SESSION_REVISION_CHANGED")
        db.flush()
        db.refresh(session)
        response = jsonable_encoder(session_response(db, session))
        db.add(ElementSaveRequestRecord(
            id=str(uuid4()), workspace_id=workspace_id, session_id=session_id,
            idempotency_key=body.idempotency_key, request_sha256=request_hash,
            response_json=response, actor_id=actor,
        ))
        db.commit()
        return response
    except IntegrityError as exc:
        db.rollback()
        winner = receipt()
        if winner is not None:
            return winner
        raise ConflictError("草稿已更新，请重新打开后再保存", code="SESSION_REVISION_CHANGED") from exc
    except ConflictError as exc:
        db.rollback()
        if exc.code == "SESSION_REVISION_CHANGED":
            winner = receipt()
            if winner is not None:
                return winner
        raise
    except Exception:
        db.rollback()
        raise
