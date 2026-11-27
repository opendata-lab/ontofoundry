"""Calculate bounded human edits against the session draft, without publication."""

from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import (
    affected_metrics,
    rewrite_references,
    strict_equal,
)
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.domain.validation import validate_core_graph
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
    if kind == "value_type":
        # A base-kind change revises every referencing property and action parameter (VT-09/VT-14).
        scope["properties"] = {
            p["id"] for p in draft["properties"] if p.get("value_type_id") == element_id
        }
        scope["actions"] = {
            a["id"]
            for a in draft.get("actions", [])
            if any(p.get("value_type_id") == element_id for p in a.get("parameters", []))
        }
    owners = {kind: {element_id}, "property": scope["properties"] if kind != "value_type" else set()}
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
    if kind == "value_type":
        # Only the inherited base kind of referencing properties and action parameters may change.
        def without_kind(prop):
            return {k: v for k, v in prop.items() if k != "value_kind"}

        old = {p["id"]: p for p in before["properties"]}
        for prop in after["properties"]:
            if (
                prop["id"] in end["properties"]
                and prop["id"] in old
                and without_kind(prop) != without_kind(old[prop["id"]])
            ):
                _scope_error()

        def action_without_param_kind(action):
            return {
                **action,
                "parameters": [
                    {k: v for k, v in p.items() if k != "value_kind"}
                    if p.get("value_type_id") == element_id
                    else p
                    for p in action.get("parameters", [])
                ],
            }

        old_actions = {a["id"]: a for a in before.get("actions", [])}
        for action in after.get("actions", []):
            if (
                action["id"] in end["actions"]
                and action["id"] in old_actions
                and action_without_param_kind(action)
                != action_without_param_kind(old_actions[action["id"]])
            ):
                _scope_error()
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
    session_draft: dict
    affected_items: list[dict]


def calculate_element_save(original, edited, kind, element_id, *, affected_items=None):
    """Derive the aggregate and automatic rewrites from this session alone."""
    original = CoreDraft.model_validate(original).model_dump(mode="json")
    candidate = _target_candidate(original, edited, kind, element_id)
    candidate = validate_core_graph(CoreDraft.model_validate(candidate)).model_dump(mode="json")
    scopes = [element_scope(s, kind, element_id) for s in (original, candidate)]
    dataset_metrics = (
        affected_metrics(CoreDraft.model_validate(original), CoreDraft.model_validate(candidate))
        if kind == "dataset" else set()
    )
    required = []
    for target_kind, collection in COLLECTIONS.items():
        local = scopes[0][collection] | scopes[1][collection]
        after = {e["id"]: e for e in candidate[collection]}
        for previous in original[collection]:
            identity = previous["id"]
            if identity in local:
                continue
            if strict_equal(previous, after.get(identity)) and UUID(identity) not in dataset_metrics:
                continue
            required.append({
                "target_kind": target_kind.value,
                "target_id": identity,
                "expected_target_hash": element_sha256(previous, collection=collection),
                "reason": "数据集变更影响指标口径，请确认依赖"
                if UUID(identity) in dataset_metrics else "当前元素修改需要同步此依赖的定义或引用",
            })
    required.sort(key=lambda entry: (entry["target_kind"], entry["target_id"]))
    if affected_items is not None:
        check_confirmations(required, affected_items)
    return ElementSaveCalculation(candidate, required)


def check_confirmations(required, submitted):
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
            raise ServiceError("受影响项已变化，请重新预检", code="PREVIEW_OUTDATED", status_code=409)
