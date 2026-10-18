"""Compute the same bounded publication and session synchronization for both routes."""

from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import (
    affected_metrics,
    reference_index,
    rewrite_references,
    strict_equal,
)
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.publish_preview import three_way


def element_scope(draft, kind, element_id):
    scope = {c: set() for c in COLLECTIONS.values()}
    scope[COLLECTIONS[ElementKind(kind)]].add(element_id)
    if kind == "object_type":
        scope["properties"] = {
            p["id"] for p in draft["properties"] if p["owner_type_id"] == element_id
        }
        scope["mappings"] = {
            m["id"] for m in draft["mappings"] if m["type_id"] == element_id
        }
    owners = {kind: {element_id}, "property": scope["properties"]}
    scope["rules"] = {
        r["id"]
        for r in draft["rules"]
        if r["owner_id"] in owners.get(r["owner_kind"], set())
    }
    return scope


def _scope_error():
    raise ServiceError(
        "保存包含无关修改或确认清单不完整，请重新预检",
        code="ELEMENT_SCOPE_INVALID",
        status_code=422,
    )


def _check_member_boundaries(before, after, kind, element_id):
    start, end = [element_scope(s, kind, element_id) for s in (before, after)]
    # Existing members may be deleted, but cannot cross aggregate boundaries.
    for collection in COLLECTIONS.values():
        existing = {e["id"] for e in before[collection]} & {
            e["id"] for e in after[collection]
        }
        if (start[collection] ^ end[collection]) & existing:
            _scope_error()


def _copy_target(destination, source, kind, element_id):
    """Copy only the selected aggregate, including additions and removals."""
    result = deepcopy(destination)
    scopes = [element_scope(s, kind, element_id) for s in (destination, source)]
    for collection in COLLECTIONS.values():
        selected = scopes[0][collection] | scopes[1][collection]
        replacements = {e["id"]: e for e in source[collection] if e["id"] in selected}
        result[collection] = [
            deepcopy(replacements.pop(e["id"], e))
            for e in destination[collection]
            if e["id"] not in selected or e["id"] in replacements
        ]
        result[collection].extend(deepcopy(list(replacements.values())))
    return result


def _rewrite(before, candidate):
    return rewrite_references(
        CoreDraft.model_validate(before), CoreDraft.model_validate(candidate)
    ).model_dump(mode="json")


def _target_candidate(original, edited, kind, element_id):
    if edited.get("workspace_id") != original["workspace_id"]:
        raise ServiceError("草稿空间不匹配", code="WORKSPACE_MISMATCH", status_code=422)
    edited = CoreDraft.model_validate(edited).model_dump(mode="json")
    collection = COLLECTIONS[ElementKind(kind)]
    if not any(e["id"] == element_id for e in edited[collection]):
        raise ServiceError(
            "没有找到要保存的元素", code="ELEMENT_NOT_FOUND", status_code=422
        )
    start, end = [element_scope(s, kind, element_id) for s in (original, edited)]
    _check_member_boundaries(original, edited, kind, element_id)
    expected = _rewrite(original, _copy_target(original, edited, kind, element_id))
    for c in COLLECTIONS.values():
        old, submitted, required = (
            {e["id"]: e for e in snap[c]} for snap in (original, edited, expected)
        )
        for identity in old.keys() | submitted.keys():
            if identity in start[c] | end[c]:
                continue
            # The client may omit automatic rewrites, or send precisely that rewrite.
            if not any(
                strict_equal(submitted.get(identity), allowed)
                for allowed in (old.get(identity), required.get(identity))
            ):
                _scope_error()
    return expected


@dataclass
class ElementSaveCalculation:
    merged: dict
    session_draft: dict
    affected_items: list[dict]


def _include_missing_upstream(synced, merged, kind, element_id):
    """Import missing dependencies without replacing existing session drafts."""
    graph = CoreDraft.model_validate(merged)
    index = DraftIndex(graph)
    refs = reference_index(graph)
    inheritance_owners = (
        set(index.lineage(UUID(element_id))) if kind == "object_type" else set()
    )
    available = {
        UUID(e["id"]) for collection in COLLECTIONS.values() for e in synced[collection]
    }
    published = {
        UUID(e["id"]): (collection, e)
        for collection in COLLECTIONS.values()
        for e in merged[collection]
    }
    scope = element_scope(merged, kind, element_id)
    pending = [UUID(identity) for ids in scope.values() for identity in ids]
    imported = set()
    visited = set()
    while pending:
        owner = pending.pop()
        if owner in visited:
            continue
        visited.add(owner)
        dependencies = {ref.target_id for ref in refs[owner]}
        if owner in inheritance_owners:
            # Inheritance exposes definitions and effective bindings even when
            # no expression explicitly references them. Never import descendants.
            dependencies.update(index.ancestors(owner))
            dependencies.update(p.id for p in index.effective_properties(owner))
            dependencies.update(link.id for link in index.effective_links(owner))
            dependencies.update(rule.id for rule in index.effective_rules(owner))
        if owner in index.objects:
            # Navigated objects need their effective bindings and source datasets.
            dependencies.update(m.id for m in resolve_binding(graph, owner).mappings)
        for dependency in sorted(dependencies, key=str):
            pending.append(dependency)
            if dependency in available:
                continue
            collection, element = published[dependency]
            synced[collection].append(deepcopy(element))
            available.add(dependency)
            imported.add(element["id"])
    return imported


def calculate_element_save(
    base, latest, original, edited, kind, element_id, *, affected_items=None
):
    """Simulate publication and synchronization without mutating any input.

    None means preflight; saving must pass the submitted list, even when empty.
    Confirmations never grant edit permission: only server-derived rewrites do.
    """
    candidate = _target_candidate(original, edited, kind, element_id)
    # Staging a reassignment must not authorize it for bounded publication.
    _check_member_boundaries(base, candidate, kind, element_id)
    # Merge only the aggregate first. Derive external rewrites against latest,
    # including dependencies introduced after the session's historical base.
    scoped = _copy_target(base, candidate, kind, element_id)
    merge = three_way(base, latest, scoped, original["workspace_id"])
    if merge.conflicts:
        raise ServiceError(
            "此元素与最新内容存在冲突，请重新打开后核对",
            code="MERGE_CONFLICTS",
            status_code=409,
            details={"conflicts": merge.conflicts},
        )
    merged = _copy_target(_rewrite(latest, merge.merged), merge.merged, kind, element_id)
    merged = validate_core_graph(CoreDraft.model_validate(merged)).model_dump(mode="json")
    # A newer target definition can require rewrites even when this edit did not
    # rename anything. Re-resolve those references while retaining unrelated edits.
    synchronized_target = _copy_target(candidate, merged, kind, element_id)
    synced = _copy_target(
        _rewrite(candidate, synchronized_target), synchronized_target, kind, element_id
    )
    imported = _include_missing_upstream(synced, merged, kind, element_id)
    validate_core_graph(CoreDraft.model_validate(synced))
    scopes = [element_scope(s, kind, element_id) for s in (original, candidate, synced)]
    dataset_metrics = (
        affected_metrics(
            CoreDraft.model_validate(original), CoreDraft.model_validate(synced)
        )
        | affected_metrics(
            CoreDraft.model_validate(latest), CoreDraft.model_validate(merged)
        )
        if kind == "dataset"
        else set()
    )
    required = []
    for target_kind, collection in COLLECTIONS.items():
        local = set.union(*(s[collection] for s in scopes))
        after = {e["id"]: e for e in synced[collection]}
        published = {e["id"]: e for e in merged[collection]}
        current = {e["id"]: e for e in latest[collection]}
        baseline = {e["id"]: e for e in latest[collection]}
        baseline.update({e["id"]: e for e in original[collection]})
        for previous in baseline.values():
            identity = previous["id"]
            if identity in local:
                continue
            if (
                (identity not in after or strict_equal(previous, after[identity]))
                and strict_equal(current.get(identity), published.get(identity))
                and UUID(identity) not in dataset_metrics
                and identity not in imported
            ):
                continue
            required.append(
                {
                    "target_kind": target_kind.value,
                    "target_id": identity,
                    "expected_target_hash": element_sha256(previous, collection=collection),
                    "reason": "数据集变更影响指标口径，请确认依赖"
                    if UUID(identity) in dataset_metrics
                    else "当前元素修改需要同步此依赖的定义或引用",
                }
            )
    required.sort(key=lambda entry: (entry["target_kind"], entry["target_id"]))
    if affected_items is not None:
        _check_confirmations(required, affected_items)
    return ElementSaveCalculation(merged, synced, required)


def _check_confirmations(required, submitted):
    expected = {(e["target_kind"], e["target_id"]): e for e in required}
    seen = set()
    entries = []
    for item in submitted:
        entry = item.model_dump() if hasattr(item, "model_dump") else item
        identity = (entry["target_kind"], entry["target_id"])
        if identity in seen or identity not in expected:
            _scope_error()
        seen.add(identity)
        entries.append((identity, entry))
    if seen != expected.keys():
        _scope_error()
    for identity, entry in entries:
        if entry["expected_target_hash"] != expected[identity]["expected_target_hash"]:
            raise ServiceError("受影响项已变化", code="VERSION_CHANGED", status_code=409)


def preview_element_save(db, workspace_id, body):
    """Read-only preflight; publication repeats every version/revision/hash guard."""
    from ontofoundry_api.db_models import ModelingSessionRecord
    from ontofoundry_api.domain.snapshot import empty_snapshot
    from ontofoundry_api.services.ontology_query import current_version, snapshot_of
    from ontofoundry_api.services.workspaces import get_workspace

    space = get_workspace(db, workspace_id)
    if space.current_version_id != body.expected_current_version_id:
        raise ServiceError(
            "发布版已更新，请重新读取", code="VERSION_CHANGED", status_code=409
        )
    if bool(body.session_id) != (body.expected_session_revision is not None):
        raise ServiceError(
            "会话和 revision 必须同时给出", code="ELEMENT_SCOPE_INVALID", status_code=422
        )
    latest = (
        snapshot_of(current_version(db, workspace_id))
        if space.current_version_id
        else empty_snapshot(workspace_id)
    )
    original = base = latest
    if body.session_id:
        session = db.get(ModelingSessionRecord, body.session_id)
        if session is None or session.workspace_id != workspace_id:
            raise ServiceError("会话不存在", code="SESSION_NOT_FOUND", status_code=404)
        if session.revision != body.expected_session_revision:
            raise ServiceError(
                "草稿已更新", code="SESSION_REVISION_CHANGED", status_code=409
            )
        original = session.draft_json
        base = (
            snapshot_of(current_version(db, workspace_id, session.base_version_id))
            if session.base_version_id
            else empty_snapshot(workspace_id)
        )
    try:
        calculation = calculate_element_save(
            base, latest, original, body.draft, body.target_kind, body.target_id
        )
    except (ValueError, KeyError) as exc:
        raise ServiceError(
            "内容校验失败：" + str(exc), code="ELEMENT_VALIDATION_FAILED", status_code=422
        ) from exc
    return {
        "current_version_id": space.current_version_id,
        "session_revision": body.expected_session_revision,
        "affected_items": calculation.affected_items,
    }
