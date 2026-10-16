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
