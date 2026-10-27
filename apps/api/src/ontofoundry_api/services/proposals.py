"""Store atomic proposal batches and read persisted review decisions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.contracts.proposals import SCHEMA_VERSION, ParsedBatch
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.instances import definitions
from ontofoundry_api.domain.models import COLLECTIONS, PROPOSAL_COLLECTIONS, ElementKind


def store_batch(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    task_id: str | None,
    manifest: dict[str, Any],
    parsed: ParsedBatch,
    settings,
) -> ProposalBatchRecord:
    """Insert a validated batch and its dependencies in the caller's transaction."""
    if manifest.get("invalidated"):
        from ontofoundry_api.services.errors import ServiceError
        raise ServiceError("运行固定上下文已失效，请重新运行", code="RUN_CONTEXT_INVALIDATED", status_code=409)
    existing = db.scalar(
        select(ProposalBatchRecord).where(
            ProposalBatchRecord.workspace_id == workspace_id,
            ProposalBatchRecord.session_id == session_id,
            ProposalBatchRecord.run_token == manifest["run_token"],
        )
    )
    if existing is not None:
        return existing
    from ontofoundry_api.services.errors import ConflictError
    from ontofoundry_api.services.proposal_apply import trial_apply
    from ontofoundry_api.services.session_gate import has_pending, lock_session
    session = lock_session(db, workspace_id, session_id)
    if has_pending(db, session):
        raise ConflictError("请先处理完待审提案", code="PENDING_PROPOSALS")
    parsed.items = trial_apply(db, workspace_id, session, parsed.items, settings).items
    batch = ProposalBatchRecord(
        id=parsed.id,
        workspace_id=workspace_id,
        session_id=session_id,
        dataagent_task_id=task_id,
        run_token=manifest["run_token"],
        schema_version=SCHEMA_VERSION,
        base_version_id=manifest.get("base_version_id"),
        base_version_sha256=manifest["base_version_sha256"],
        source_session_revision=manifest["source_session_revision"],
        source_draft_sha256=manifest["source_draft_sha256"],
        material_manifest_json=manifest.get("materials") or [],
        producer_json=manifest.get("producer") or {},
        result_sha256=parsed.result_sha256,
        status="available",
        created_at=utc_now(),
    )
    db.add(batch)
    db.flush()
    for item in parsed.items:
        db.add(
            ProposalItemRecord(
                id=item.id,
                batch_id=batch.id,
                workspace_id=workspace_id,
                session_id=session_id,
                ordinal=item.ordinal,
                client_ref=item.client_ref,
                fingerprint=item.fingerprint,
                atomic_group_id=item.atomic_group_id,
                operation=item.operation,
                target_kind=item.target_kind,
                target_id=item.target_id,
                expected_target_hash=item.expected_target_hash,
                expected_instance_revision=item.expected_instance_revision,
                before_json=item.before,
                after_json=item.after,
                field_changes_json=item.field_changes,
                evidence_json=item.evidence,
                reason=item.reason,
                status=item.status,
                status_reason=item.status_reason or None,
                created_at=utc_now(),
            )
        )
    db.flush()
    for item in parsed.items:
        for dependency in item.depends_on:
            db.add(
                ProposalItemDependencyRecord(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    batch_id=batch.id,
                    item_id=item.id,
                    depends_on_item_id=dependency,
                )
            )
    return batch



# --- run context ----------------------------------------------------------------


def proposal_header(manifest: dict[str, Any]) -> dict[str, Any]:
    """The literal result header a proposals run must return."""
    return {
        "schema_version": SCHEMA_VERSION,
        "run_token": manifest["run_token"],
        "workspace_id": manifest["workspace_id"],
        "session_id": manifest["session_id"],
        "base_version_id": manifest["base_version_id"],
        "base_version_sha256": manifest["base_version_sha256"],
        "source_session_revision": manifest["source_session_revision"],
        "source_draft_sha256": manifest["source_draft_sha256"],
        "items": [],
    }


def proposal_context(manifest: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """What the agent reads: the pinned draft and the hash of every element,
    which update and delete proposals must quote as expected_target_hash."""
    elements = draft
    return {
        "run": {k: v for k, v in proposal_header(manifest).items() if k != "items"},
        "draft": draft,
        "instance_baseline": manifest.get("instance_baseline", {"change_sequence": 0, "items": []}),
        "element_hashes": {
            str(element["id"]): element_sha256(element, collection=collection)
            for collection in COLLECTIONS.values()
            for element in elements.get(collection) or []
        },
    }


# --- reading ------------------------------------------------------------------


def _elements(draft: dict[str, Any]) -> dict[str, tuple[str, dict]]:
    return {
        str(element["id"]): (kind.value, element)
        for kind, collection in PROPOSAL_COLLECTIONS.items()
        for element in draft.get(collection) or []
    }


def effective_statuses(
    items: list[ProposalItemRecord],
    dependencies: dict[str, list[str]],
    draft: dict[str, Any],
    instance_baseline: dict | None = None,
) -> dict[str, tuple[str, str]]:
    return {item.id: (item.status, item.status_reason or "") for item in items}


def dependency_map(
    db: Session, batch_ids: list[str], workspace_id: str, session_id: str
) -> dict[str, list[str]]:
    """Dependencies of the given batches, always within one workspace and
    session (design §7.2: never trust a bare global id)."""
    if not batch_ids:
        return {}
    rows = db.scalars(
        select(ProposalItemDependencyRecord).where(
            ProposalItemDependencyRecord.batch_id.in_(batch_ids),
            ProposalItemDependencyRecord.workspace_id == workspace_id,
            ProposalItemDependencyRecord.session_id == session_id,
        )
    ).all()
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row.item_id, []).append(row.depends_on_item_id)
    # Rebuild dependency edges from the current candidate, preserving explicit
    # edges from the immutable proposal report. Invalid/stale drafts keep those
    # edges and expose their conflict through effective_statuses.
    session = db.get(ModelingSessionRecord, session_id)
    if session is not None:
        items = batch_items(db, batch_ids, workspace_id, session_id)
        by_target = {i.target_id: i for i in items}
        from ontofoundry_api.services.instance_store import session_snapshot
        candidate = deepcopy(session_snapshot(db, workspace_id, session_id, session.draft_json))
        for item in items:
            if item.status in {"pending", "accepted"}:
                collection = PROPOSAL_COLLECTIONS[ElementKind(item.target_kind)]
                candidate[collection] = [
                    e for e in candidate[collection] if e["id"] != item.target_id
                ]
                if item.after_json is not None:
                    candidate[collection].append(item.after_json)
        try:
            from ontofoundry_api.domain.core import CoreDraft
            from ontofoundry_api.domain.dependencies import reference_index
            from ontofoundry_api.domain.instances import instance_references
            model = CoreDraft.model_validate(definitions(candidate))
            references = {**reference_index(model), **instance_references(model, candidate["material_objects"], candidate["material_links"])}
            for owner, refs in references.items():
                item = by_target.get(str(owner))
                if item is None:
                    continue
                for ref in refs:
                    parent = by_target.get(str(ref.target_id))
                    if (
                        parent
                        and parent.id != item.id
                        and (
                            not item.atomic_group_id
                            or parent.atomic_group_id != item.atomic_group_id
                        )
                    ):
                        result.setdefault(item.id, []).append(parent.id)
        except (ValueError, KeyError):
            pass
    result = {key: sorted(set(value)) for key, value in result.items()}
    return result


def dependency_group(item_id: str, dependencies: dict[str, list[str]]) -> list[str]:
    """The item and everything it transitively depends on."""
    seen, stack = [], [item_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.append(current)
        stack.extend(dependencies.get(current, []))
    return seen


def dependent_group(item_id: str, dependencies: dict[str, list[str]]) -> list[str]:
    """The item and everything that transitively depends on it."""
    reverse: dict[str, list[str]] = {}
    for child, parents in dependencies.items():
        for parent in parents:
            reverse.setdefault(parent, []).append(child)
    return dependency_group(item_id, reverse)


KIND_LABELS = {
    ElementKind.OBJECT_TYPE.value: "实体",
    ElementKind.PROPERTY.value: "属性",
    ElementKind.LINK_TYPE.value: "关系",
    ElementKind.RULE.value: "规则",
    ElementKind.MATERIAL_OBJECT.value: "材料实例",
    ElementKind.MATERIAL_LINK.value: "材料关系",
    ElementKind.MAPPING.value: "映射",
    ElementKind.DATASET.value: "数据集",
    ElementKind.METRIC.value: "指标",
}


def batch_items(
    db: Session, batch_ids: list[str], workspace_id: str, session_id: str
) -> list[ProposalItemRecord]:
    if not batch_ids:
        return []
    items = list(
        db.scalars(
            select(ProposalItemRecord)
            .where(
                ProposalItemRecord.batch_id.in_(batch_ids),
                ProposalItemRecord.workspace_id == workspace_id,
                ProposalItemRecord.session_id == session_id,
            )
            .order_by(ProposalItemRecord.batch_id, ProposalItemRecord.ordinal)
        ).all()
    )
    return items


def proposal_state(db: Session, workspace_id: str, session_id: str) -> tuple:
    """Every batch and item status of a session: a cheap fingerprint that
    changes whenever a decision or a new batch could change the summary."""
    batches = db.execute(
        select(ProposalBatchRecord.id, ProposalBatchRecord.status).where(
            ProposalBatchRecord.workspace_id == workspace_id,
            ProposalBatchRecord.session_id == session_id,
        )
    ).all()
    items = db.execute(
        select(ProposalItemRecord.id, ProposalItemRecord.status).where(
            ProposalItemRecord.workspace_id == workspace_id,
            ProposalItemRecord.session_id == session_id,
        )
    ).all()
    from ontofoundry_api.services.instance_store import change_sequence
    return tuple(sorted(map(tuple, batches))), tuple(sorted(map(tuple, items))), change_sequence(db, workspace_id)


def pending_summary(
    db: Session, workspace_id: str, session_id: str, draft: dict
) -> dict[str, Any]:
    """`pending_proposal_count` and `latest_batch_id` for session responses."""
    batches = db.execute(
        select(ProposalBatchRecord.id, ProposalBatchRecord.status)
        .where(
            ProposalBatchRecord.workspace_id == workspace_id,
            ProposalBatchRecord.session_id == session_id,
        )
        .order_by(ProposalBatchRecord.created_at.desc(), ProposalBatchRecord.id.desc())
    ).all()
    ids = [row.id for row in batches]
    items = batch_items(db, ids, workspace_id, session_id)
    statuses = effective_statuses(
        items, dependency_map(db, ids, workspace_id, session_id), draft,
        __import__("ontofoundry_api.services.instance_store", fromlist=["baseline"]).baseline(db, workspace_id, session_id)
    )
    # The batch to show by default: the newest one that can be acted on.
    available = [row.id for row in batches if row.status == "available"]
    return {
        "pending_proposal_count": sum(1 for s in statuses.values() if s[0] == "pending"),
        "latest_batch_id": (available or ids or [None])[0],
    }
