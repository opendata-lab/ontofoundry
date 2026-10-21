"""Element-level changes between two v2 snapshots (frontend contract §4).

Used for a session's `base_diff` and for the publish preview. Changes are
grouped per element, addressed by stable id, and carry enough (label, before)
to render an element that no longer exists in the newer snapshot.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ontofoundry_api.domain.canonical import canonical
from ontofoundry_api.domain.core import CoreDraft, MaterialObject
from ontofoundry_api.domain.instance_display import document_display_text
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind


def _index(snapshot):
    return {
        str(e["id"]): (kind.value, e)
        for kind, collection in COLLECTIONS.items()
        for e in snapshot.get(collection, [])
    }


def element_label(kind, element, snapshot_elements):
    if kind in {"material_object", "material_link"}:
        # A review context may contain deleted elements or only part of a batch.
        draft = CoreDraft.model_validate(
            {
                "workspace_id": str(UUID(int=0)),
                **{
                    collection: [
                        e for k, e in snapshot_elements.values() if k == member.value
                    ]
                    for member, collection in COLLECTIONS.items()
                    if member.value in {"object_type", "property"}
                },
            }
        )

        def fact_label(fact):
            return document_display_text(draft, MaterialObject.model_validate(fact))

        if kind == "material_object":
            return fact_label(element)
        labels = []
        for side in ("source_id", "target_id"):
            identity = str(element.get(side, ""))
            found = snapshot_elements.get(identity)
            labels.append(fact_label(found[1]) if found else identity)
        return " → ".join(labels)
    if kind == "mapping":
        owner = snapshot_elements.get(str(element.get("type_id")), ("", {}))[1]
        return str(owner.get("display_name") or owner.get("name") or element.get("id"))
    return str(element.get("display_name") or element.get("name") or element.get("id"))


def owner_label(
    kind: str, element: dict, elements: dict[str, tuple[str, dict]]
) -> str | None:
    owner = None
    if kind == ElementKind.PROPERTY.value:
        owner = element.get("owner_type_id", element.get("owner_ref", {}).get("ref"))
    elif kind == ElementKind.RULE.value:
        owner = element.get("owner_id")
    elif kind in (ElementKind.MATERIAL_OBJECT.value, ElementKind.MAPPING.value):
        owner = element.get("type_id")
    if owner is None:
        return None
    found = elements.get(str(owner))
    return str(found[1].get("display_name") or found[1].get("name")) if found else None


def field_changes(before: dict, after: dict) -> list[dict[str, Any]]:
    changes = []
    for key in sorted(before.keys() | after.keys()):
        if key == "id":
            continue
        old, new = before.get(key), after.get(key)
        if canonical(old, key) != canonical(new, key):
            changes.append({"path": key, "before": old, "after": new})
    return changes


def element_changes(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    """What changed from `left` to `right`, one entry per element."""
    old, new = _index(left), _index(right)
    both = {**old, **new}
    result = []
    for element_id in sorted(old.keys() | new.keys()):
        before = old.get(element_id)
        after = new.get(element_id)
        if before and after and canonical(before[1]) == canonical(after[1]):
            continue
        kind = (after or before)[0]
        element = (after or before)[1]
        change = "created" if before is None else "deleted" if after is None else "updated"
        result.append(
            {
                "element_kind": kind,
                "element_id": element_id,
                "label": element_label(kind, element, old if after is None else both),
                "owner_label": owner_label(kind, element, both),
                "change": change,
                "field_changes": field_changes(before[1], after[1])
                if change == "updated"
                else [],
                "before": before[1] if before else None,
                "after": after[1] if after else None,
            }
        )
    return result
