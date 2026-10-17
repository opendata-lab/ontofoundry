"""Restrict immediate publication to one explicitly selected core aggregate."""

from copy import deepcopy
from uuid import UUID

from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import reverse_dependencies, rewrite_references
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.services.errors import ServiceError


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


def scoped_draft(base, original, edited, kind, element_id, affected_items=()):
    if edited["workspace_id"] != original["workspace_id"]:
        raise ServiceError("草稿空间不匹配", code="WORKSPACE_MISMATCH", status_code=422)
    before = CoreDraft.model_validate(original)
    candidate = rewrite_references(before, CoreDraft.model_validate(edited)).model_dump(
        mode="json"
    )
    old = {e["id"]: (c, e) for c in COLLECTIONS.values() for e in original[c]}
    affected = reverse_dependencies(before, {UUID(element_id)})
    explicit = set()
    for entry in affected_items:
        entry = entry.model_dump() if hasattr(entry, "model_dump") else entry
        target = entry["target_id"]
        found = old.get(target)
        if (
            UUID(target) not in affected
            or not found
            or found[0] != COLLECTIONS[ElementKind(entry["target_kind"])]
        ):
            raise ServiceError(
                "受影响项不是当前元素的依赖", code="ELEMENT_SCOPE_INVALID", status_code=422
            )
        if element_sha256(found[1], collection=found[0]) != entry["expected_target_hash"]:
            raise ServiceError("受影响项已变化", code="VERSION_CHANGED", status_code=409)
        explicit.add(target)
    start, end = (
        element_scope(original, kind, element_id),
        element_scope(candidate, kind, element_id),
    )
    baseline = element_scope(base, kind, element_id)
    collection = COLLECTIONS[ElementKind(kind)]
    if not any(e["id"] == element_id for e in candidate[collection]):
        raise ServiceError(
            "没有找到要保存的元素", code="ELEMENT_NOT_FOUND", status_code=422
        )
    result = deepcopy(base)
    for c in start:
        old_items, new_items = (
            {e["id"]: e for e in snap[c]} for snap in (original, candidate)
        )
        changed = {
            i
            for i in old_items.keys() | new_items.keys()
            if old_items.get(i) != new_items.get(i)
        }
        allowed = (
            start[c]
            | end[c]
            | baseline[c]
            | (explicit & (old_items.keys() | new_items.keys()))
        )
        if changed - allowed or ((changed & old_items.keys()) - start[c] - explicit):
            raise ServiceError(
                "保存包含其他元素的修改或未确认的引用改写",
                code="ELEMENT_SCOPE_INVALID",
                status_code=422,
            )
        replacements = {i: new_items[i] for i in allowed if i in new_items}
        result[c] = [
            replacements.pop(e["id"], e)
            for e in base[c]
            if e["id"] not in allowed or e["id"] in new_items
        ]
        result[c].extend(replacements.values())
    return result


def sync_saved_scope(edited, merged, kind, element_id, affected_items):
    """Copy the published aggregate and confirmed dependents into the session."""
    result = deepcopy(edited)
    scopes = [element_scope(s, kind, element_id) for s in (edited, merged)]
    for entry in affected_items:
        entry = entry.model_dump() if hasattr(entry, "model_dump") else entry
        scopes[0][COLLECTIONS[ElementKind(entry["target_kind"])]].add(entry["target_id"])
    for collection in COLLECTIONS.values():
        selected = scopes[0][collection] | scopes[1][collection]
        replacements = {e["id"]: e for e in merged[collection] if e["id"] in selected}
        result[collection] = [
            deepcopy(replacements.pop(e["id"], e))
            for e in edited[collection]
            if e["id"] not in selected or e["id"] in replacements
        ]
        result[collection].extend(deepcopy(list(replacements.values())))
    from ontofoundry_api.domain.validation import validate_core_graph

    validate_core_graph(CoreDraft.model_validate(result))
    return result


def save_impacts(base, original, edited, kind, element_id):
    """Derive required confirmations and hashes from the server editing baseline."""
    from ontofoundry_api.domain.dependencies import affected_metrics
    from ontofoundry_api.domain.validation import validate_core_graph

    if edited.get("workspace_id") != original["workspace_id"]:
        raise ServiceError("草稿空间不匹配", code="WORKSPACE_MISMATCH", status_code=422)
    before = CoreDraft.model_validate(original)
    candidate = rewrite_references(before, CoreDraft.model_validate(edited))
    raw = candidate.model_dump(mode="json")
    dependent = reverse_dependencies(before, {UUID(element_id)})
    scopes = [element_scope(s, kind, element_id) for s in (original, raw, base)]
    affected = []
    dataset_metrics = affected_metrics(before, candidate) if kind == "dataset" else set()
    for target_kind, collection in COLLECTIONS.items():
        local = set.union(*(s[collection] for s in scopes))
        after = {e["id"]: e for e in raw[collection]}
        for previous in original[collection]:
            identity = previous["id"]
            if identity in local or UUID(identity) not in dependent:
                continue
            if previous == after.get(identity) and UUID(identity) not in dataset_metrics:
                continue
            affected.append(
                {
                    "target_kind": target_kind.value,
                    "target_id": identity,
                    "expected_target_hash": element_sha256(previous, collection=collection),
                    "reason": "数据集变更影响指标口径，请确认依赖"
                    if UUID(identity) in dataset_metrics
                    else "当前元素修改需要同步此依赖的定义或引用",
                }
            )
    confirmations = [
        {k: v for k, v in entry.items() if k != "reason"} for entry in affected
    ]
    scoped = scoped_draft(base, original, edited, kind, element_id, confirmations)
    validate_core_graph(CoreDraft.model_validate(scoped))
    return sorted(affected, key=lambda entry: (entry["target_kind"], entry["target_id"]))


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
        affected = save_impacts(
            base, original, body.draft, body.target_kind, body.target_id
        )
    except (ValueError, KeyError) as exc:
        raise ServiceError(
            "内容校验失败：" + str(exc), code="ELEMENT_VALIDATION_FAILED", status_code=422
        ) from exc
    return {
        "current_version_id": space.current_version_id,
        "session_revision": body.expected_session_revision,
        "affected_items": affected,
    }
