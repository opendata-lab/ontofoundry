"""Element-level changes between two v2 snapshots (frontend contract §4).

Used for a session's `base_diff` and for the publish preview. Changes are
grouped per element, addressed by stable id, and carry enough (label, before)
to render an element that no longer exists in the newer snapshot.
"""

from __future__ import annotations

from typing import Any

from ontofoundry_api.domain.canonical import canonical
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind


def _index(snapshot: dict[str, Any]) -> dict[str, tuple[str, dict]]:
    return {
        str(element["id"]): (kind.value, element)
        for kind, collection in COLLECTIONS.items()
        for element in snapshot.get(collection) or []
    }


def element_label(kind: str, element: dict, snapshot_elements: dict[str, tuple[str, dict]]) -> str:
    if kind == ElementKind.MAPPING.value:
        return f"{element.get('connection_alias', '')} · {element.get('table_name', '')}"
    if kind == ElementKind.MATERIAL_LINK.value:
        names = [
            snapshot_elements.get(str(element.get(key)), ("", {}))[1].get("name", "?")
            for key in ("source_id", "target_id")
        ]
        return " → ".join(names)
    return str(element.get("name") or element.get("technical_name") or element.get("id"))


def owner_label(kind: str, element: dict, elements: dict[str, tuple[str, dict]]) -> str | None:
    owner = None
    if kind == ElementKind.PROPERTY.value:
        owner = element.get("owner_type_id")
    elif kind == ElementKind.RULE.value:
        owner = element.get("owner_id")
    elif kind in (ElementKind.MATERIAL_OBJECT.value, ElementKind.MAPPING.value):
        owner = element.get("type_id")
    if owner is None:
        return None
    found = elements.get(str(owner))
    return str(found[1].get("name") or found[1].get("technical_name")) if found else None


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
                "label": element_label(kind, element, both),
                "owner_label": owner_label(kind, element, both),
                "change": change,
                "field_changes": field_changes(before[1], after[1]) if change == "updated" else [],
                "before": before[1] if before else None,
                "after": after[1] if after else None,
            }
        )
    return result
