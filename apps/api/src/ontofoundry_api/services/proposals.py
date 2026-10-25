"""Proposal batches: storing a parsed result, and reading items with their
effective status (design §7.3).

Stored item status is only the decision: pending | accepted | rejected |
superseded | unacceptable. `stale` and `conflict` are computed on every read from the current
draft and never written, so an item whose target is edited back becomes
pending again by itself.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ontofoundry_api.contracts.proposals import SCHEMA_VERSION, ParsedBatch
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import (
    domain_sha256,
    element_sha256,
)
from ontofoundry_api.domain.instances import INSTANCE_KINDS, definitions, instance_hash
from ontofoundry_api.domain.models import COLLECTIONS, PROPOSAL_COLLECTIONS, ElementKind


def store_batch(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    task_id: str | None,
    manifest: dict[str, Any],
    parsed: ParsedBatch,
) -> ProposalBatchRecord:
    """Insert batch, items and dependencies in the caller's transaction.

    Idempotent per run: a batch for the same run token is returned as is.
    Older pending items aimed at a target this batch also proposes to change
    are superseded; history is kept.
    """
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
    targets = [item.target_id for item in parsed.items]
    if targets:
        older_groups = set(
            db.scalars(
                select(ProposalItemRecord.atomic_group_id).where(
                    ProposalItemRecord.workspace_id == workspace_id,
                    ProposalItemRecord.session_id == session_id,
                    ProposalItemRecord.status == "pending",
                    ProposalItemRecord.target_id.in_(targets),
                    ProposalItemRecord.atomic_group_id.is_not(None),
                )
            )
        )
        db.execute(
            update(ProposalItemRecord)
            .where(
                ProposalItemRecord.workspace_id == workspace_id,
                ProposalItemRecord.session_id == session_id,
                ProposalItemRecord.status == "pending",
                or_(
                    ProposalItemRecord.target_id.in_(targets),
                    ProposalItemRecord.atomic_group_id.in_(older_groups),
                ),
            )
            .values(status="superseded")
        )
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


def store_failed_batch(
    db: Session,
    *,
    workspace_id: str,
    session_id: str,
    task_id: str | None,
    manifest: dict[str, Any],
    result_sha256: str,
    code: str,
    message: str,
) -> None:
    """Keep a rejected result visible in the proposals tab, with its reason."""
    exists = db.scalar(
        select(ProposalBatchRecord.id).where(
            ProposalBatchRecord.workspace_id == workspace_id,
            ProposalBatchRecord.session_id == session_id,
            ProposalBatchRecord.run_token == manifest["run_token"],
        )
    )
    if exists:
        return
    from ontofoundry_api.contracts.proposals import batch_id_for

    db.add(
        ProposalBatchRecord(
            id=batch_id_for(session_id, manifest["run_token"]),
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
            result_sha256=result_sha256,
            status="failed",
            error_json={"code": code, "message": message},
            created_at=utc_now(),
        )
    )


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
    """item id -> (effective status, reason). Pure; see module docstring."""
    from ontofoundry_api.domain.instances import baseline_elements
    elements = _elements(draft)
    elements.update(baseline_elements(instance_baseline))
    revisions = {i["target_id"]: i["revision"] for i in (instance_baseline or {}).get("items", [])}
    by_id = {item.id: item for item in items}
    result: dict[str, tuple[str, str]] = {}

    def own(item: ProposalItemRecord) -> tuple[str, str]:
        if item.status != "pending":
            return item.status, item.status_reason or ""
        found = elements.get(item.target_id)
        if item.operation == "create":
            if found is not None:
                return "conflict", "目标 id 已被草稿中的元素占用"
            return "pending", ""
        if found is None or found[0] != item.target_kind:
            return "conflict", "目标元素已被删除或类型已改变"
        collection = PROPOSAL_COLLECTIONS[ElementKind(found[0])]
        current_hash = (instance_hash(found[1], revisions[item.target_id])
            if found[0] in INSTANCE_KINDS and item.target_id in revisions
            else element_sha256(found[1], collection=collection))
        if current_hash != item.expected_target_hash:
            previous = item.before_json
            legacy_unchanged = (
                item.target_kind == "link_type"
                and isinstance(previous, dict)
                and "name" in previous
                and domain_sha256(previous) == item.expected_target_hash
                and element_sha256(previous, collection=collection) == current_hash
            )
            if not legacy_unchanged:
                return "stale", "目标在提案生成后已被修改"
        return "pending", ""

    def resolve(item_id: str, trail: tuple[str, ...] = ()) -> tuple[str, str]:
        if item_id in result:
            return result[item_id]
        item = by_id[item_id]
        status, reason = own(item)
        if status == "pending":
            for dep_id in dependencies.get(item_id, []):
                if dep_id in trail or dep_id not in by_id:
                    continue
                dep = by_id[dep_id]
                dep_status, _ = resolve(dep_id, (*trail, item_id))
                label = dep.client_ref or dep.target_id
                if dep_status in ("rejected", "superseded"):
                    status, reason = "conflict", f"依赖 {label} 已被拒绝或取代"
                    break
                if (
                    dep_status == "accepted"
                    and dep.target_id not in elements
                    and dep.operation != "delete"
                ):
                    status, reason = "conflict", f"依赖 {label} 接受后已被删除"
                    break
                if dep_status in ("stale", "conflict", "unacceptable"):
                    status = dep_status
                    reason = f"依赖 {label} {'已过期' if dep_status == 'stale' else '冲突'}"
                    break
        result[item_id] = (status, reason)
        return result[item_id]

    for item in items:
        resolve(item.id)
    return result


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
