"""Proposal batches: storing a parsed result, and reading items with their
effective status (design §7.3).

Stored item status is only the decision: pending | accepted | rejected |
superseded. `stale` and `conflict` are computed on every read from the current
draft and never written, so an item whose target is edited back becomes
pending again by itself.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ontofoundry_api.contracts.proposals import SCHEMA_VERSION, ParsedBatch
from ontofoundry_api.db_models import (
    ProposalBatchRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind


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
        db.execute(
            update(ProposalItemRecord)
            .where(
                ProposalItemRecord.workspace_id == workspace_id,
                ProposalItemRecord.session_id == session_id,
                ProposalItemRecord.status == "pending",
                ProposalItemRecord.target_id.in_(targets),
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
                operation=item.operation,
                target_kind=item.target_kind,
                target_id=item.target_id,
                expected_target_hash=item.expected_target_hash,
                before_json=item.before,
                after_json=item.after,
                field_changes_json=item.field_changes,
                evidence_json=item.evidence,
                reason=item.reason,
                status="pending",
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
    return {
        "run": {key: manifest[key] for key in ("run_token", "base_version_id", "source_session_revision")},
        "draft": draft,
        "element_hashes": {
            str(element["id"]): element_sha256(element)
            for collection in COLLECTIONS.values()
            for element in draft.get(collection) or []
        },
    }


# --- reading ------------------------------------------------------------------


def _elements(draft: dict[str, Any]) -> dict[str, tuple[str, dict]]:
    return {
        str(element["id"]): (kind.value, element)
        for kind, collection in COLLECTIONS.items()
        for element in draft.get(collection) or []
    }


def effective_statuses(
    items: list[ProposalItemRecord],
    dependencies: dict[str, list[str]],
    draft: dict[str, Any],
) -> dict[str, tuple[str, str]]:
    """item id -> (effective status, reason). Pure; see module docstring."""
    elements = _elements(draft)
    by_id = {item.id: item for item in items}
    result: dict[str, tuple[str, str]] = {}

    def own(item: ProposalItemRecord) -> tuple[str, str]:
        if item.status != "pending":
            return item.status, ""
        found = elements.get(item.target_id)
        if item.operation == "create":
            if found is not None:
                return "conflict", "目标 id 已被草稿中的元素占用"
            return "pending", ""
        if found is None or found[0] != item.target_kind:
            return "conflict", "目标元素已被删除或类型已改变"
        if element_sha256(found[1]) != item.expected_target_hash:
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
                if dep_status == "accepted" and dep.target_id not in elements and dep.operation != "delete":
                    status, reason = "conflict", f"依赖 {label} 接受后已被删除"
                    break
                if dep_status in ("stale", "conflict"):
                    status = dep_status
                    reason = f"依赖 {label} {'已过期' if dep_status == 'stale' else '冲突'}"
                    break
        result[item_id] = (status, reason)
        return result[item_id]

    for item in items:
        resolve(item.id)
    return result


def dependency_map(db: Session, batch_ids: list[str]) -> dict[str, list[str]]:
    rows = db.scalars(
        select(ProposalItemDependencyRecord).where(
            ProposalItemDependencyRecord.batch_id.in_(batch_ids)
        )
    ).all() if batch_ids else []
    result: dict[str, list[str]] = {}
    for row in rows:
        result.setdefault(row.item_id, []).append(row.depends_on_item_id)
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


KIND_LABELS = {
    ElementKind.OBJECT_TYPE.value: "实体",
    ElementKind.PROPERTY.value: "属性",
    ElementKind.LINK_TYPE.value: "关系",
    ElementKind.RULE.value: "规则",
    ElementKind.ACTION.value: "Action",
    ElementKind.MATERIAL_OBJECT.value: "材料实例",
    ElementKind.MATERIAL_LINK.value: "材料关系",
    ElementKind.MAPPING.value: "映射",
}


def batch_items(db: Session, batch_ids: list[str]) -> list[ProposalItemRecord]:
    if not batch_ids:
        return []
    return list(
        db.scalars(
            select(ProposalItemRecord)
            .where(ProposalItemRecord.batch_id.in_(batch_ids))
            .order_by(ProposalItemRecord.batch_id, ProposalItemRecord.ordinal)
        ).all()
    )


def pending_summary(db: Session, workspace_id: str, session_id: str, draft: dict) -> dict[str, Any]:
    """`pending_proposal_count` and `latest_batch_id` for session responses."""
    ids = list(
        db.scalars(
            select(ProposalBatchRecord.id)
            .where(
                ProposalBatchRecord.workspace_id == workspace_id,
                ProposalBatchRecord.session_id == session_id,
            )
            .order_by(ProposalBatchRecord.created_at.desc(), ProposalBatchRecord.id.desc())
        ).all()
    )
    items = batch_items(db, ids)
    statuses = effective_statuses(items, dependency_map(db, ids), draft)
    return {
        "pending_proposal_count": sum(1 for s in statuses.values() if s[0] == "pending"),
        "latest_batch_id": ids[0] if ids else None,
    }
