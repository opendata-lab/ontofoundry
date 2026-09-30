"""The B/L/D merge behind preview, conflict resolution and publish (design §9).

One function computes what would be published; preview shows it, publish
recomputes it inside its transaction and refuses (PREVIEW_OUTDATED) unless the
session revision, the workspace's current version and the merged snapshot hash
are exactly what the user previewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.domain.snapshot import empty_snapshot

from .element_diff import element_changes, element_label
from .merge import merge_snapshots

COLLECTION_KIND = {collection: kind.value for kind, collection in COLLECTIONS.items()}
# Fields whose values are sets: both sides' additions can be kept together.
SET_FIELDS = {"tags", "extends", "precondition_rule_ids", "ontology_requires"}


@dataclass
class Merge:
    base: dict[str, Any]
    latest: dict[str, Any]
    draft: dict[str, Any]
    merged: dict[str, Any]
    conflicts: list[dict[str, Any]]

    @property
    def merged_sha256(self) -> str:
        return snapshot_sha256(self.merged)


def three_way(
    base: dict | None,
    latest: dict | None,
    draft: dict,
    workspace_id: str,
    resolutions: dict[str, Any] | None = None,
) -> Merge:
    base = base or empty_snapshot(workspace_id)
    latest = latest or empty_snapshot(workspace_id)
    merged, raw = merge_snapshots(base, latest, draft, resolutions)
    elements = {
        str(e["id"]): (COLLECTION_KIND[c], e)
        for snap in (base, latest, draft)
        for c in COLLECTIONS.values()
        for e in snap.get(c) or []
    }
    return Merge(base, latest, draft, merged, [_conflict(c, elements) for c in raw])


def _conflict(raw: dict[str, Any], elements: dict[str, tuple[str, dict]]) -> dict[str, Any]:
    """Structure a raw path conflict (frontend contract MergeConflict)."""
    parts = [p for p in raw["path"].split("/") if p]
    collection = parts[0] if parts else ""
    element_id = parts[1] if len(parts) > 1 and collection in COLLECTION_KIND else ""
    field = "/".join(parts[2:])
    kind_value, element = elements.get(element_id, ("", {}))
    whole_element = element_id and not field
    if whole_element:
        kind = "delete_modify"
        allowed = ["latest", "draft"]
    else:
        kind = "field"
        allowed = ["latest", "draft", "custom"]
        if field.split("/")[0] in SET_FIELDS or (not element_id and collection in SET_FIELDS):
            allowed.append("both")
    return {
        "key": raw["path"],
        "element_kind": kind_value or None,
        "element_id": element_id or None,
        "element_label": element_label(kind_value, element, elements) if element else collection,
        "path": field or collection,
        "kind": kind,
        "base": raw["base"],
        "latest": raw["current"],
        "draft": raw["draft"],
        "allowed": allowed,
    }


def auto_merged(merge: Merge) -> list[dict[str, Any]]:
    """Changes other sessions published since this session's base, which the
    merge carries into the new version (side = latest, or both if the draft
    changed the same element too)."""
    theirs = element_changes(merge.base, merge.latest)
    mine = {c["element_id"] for c in element_changes(merge.base, merge.draft)}
    return [{**c, "side": "both" if c["element_id"] in mine else "latest"} for c in theirs]


def impacts(changes: list[dict[str, Any]], merged: dict[str, Any]) -> list[dict[str, Any]]:
    """Elements not changed themselves but depending on something that was."""
    changed = {c["element_id"] for c in changes}
    result = []
    references = {
        ElementKind.PROPERTY.value: ("owner_type_id",),
        ElementKind.LINK_TYPE.value: ("source_type_id", "target_type_id"),
        ElementKind.RULE.value: ("owner_id",),
        ElementKind.ACTION.value: ("input_type_id",),
        ElementKind.MAPPING.value: ("type_id",),
        ElementKind.MATERIAL_OBJECT.value: ("type_id",),
    }
    labels = {
        str(e["id"]): (COLLECTION_KIND[c], e)
        for c in COLLECTIONS.values()
        for e in merged.get(c) or []
    }
    for kind, collection in ((k.value, c) for k, c in COLLECTIONS.items()):
        for element in merged.get(collection) or []:
            if str(element["id"]) in changed:
                continue
            hits = [
                labels[str(element.get(field))][1].get("name", "")
                for field in references.get(kind, ())
                if str(element.get(field)) in changed and str(element.get(field)) in labels
            ]
            if hits:
                result.append(
                    {
                        "element_kind": kind,
                        "element_id": str(element["id"]),
                        "label": element_label(kind, element, labels),
                        "reason": "引用了已变更的 " + "、".join(hits),
                    }
                )
    return result
