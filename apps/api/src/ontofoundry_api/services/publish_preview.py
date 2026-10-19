"""The B/L/D merge behind preview, conflict resolution and publish (design §9).

One function computes what would be published; preview shows it, publish
recomputes it inside its transaction and refuses (PREVIEW_OUTDATED) unless the
session revision, the workspace's current version and the merged snapshot hash
are exactly what the user previewed.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.core import LinkType
from ontofoundry_api.domain.models import COLLECTIONS
from ontofoundry_api.domain.snapshot import empty_snapshot, read_snapshot_json

from .element_diff import element_changes, element_label
from .merge import merge_snapshots

COLLECTION_KIND = {collection: kind.value for kind, collection in COLLECTIONS.items()}
# Fields whose values are sets: both sides' additions can be kept together.
SET_FIELDS = {"tags", "synonyms"}


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
    base = (
        read_snapshot_json(base, workspace_id)
        if base is not None
        else empty_snapshot(workspace_id)
    )
    latest = (
        read_snapshot_json(latest, workspace_id)
        if latest is not None
        else empty_snapshot(workspace_id)
    )
    # Published snapshots are complete graphs; an editing draft can still have
    # semantic errors. Merge its traversable structure and report those errors
    # in preview, then enforce the final graph at publication.
    if draft.get("schema_version") != "core-1" or str(draft.get("workspace_id")) != str(
        workspace_id
    ):
        from ontofoundry_api.services.errors import ServiceError

        raise ServiceError("草稿格式或空间无效", code="VALIDATION_FAILED", status_code=422)
    draft = deepcopy(draft)
    draft["link_types"] = [LinkType.read_previous_names(link) for link in draft.get("link_types", [])]
    for collection in COLLECTIONS.values():
        draft.setdefault(collection, [])
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
        if field.split("/")[0] in SET_FIELDS or (
            not element_id and collection in SET_FIELDS
        ):
            allowed.append("both")
    return {
        "key": raw["path"],
        "element_kind": kind_value or None,
        "element_id": element_id or None,
        "element_label": element_label(kind_value, element, elements)
        if element
        else collection,
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


def element_labels(*snapshots: dict[str, Any]) -> dict[str, str]:
    """Display labels by element id, so the preview names references in any
    of the snapshots, including ones only the latest version or the merge has."""
    labels: dict[str, str] = {}
    for snapshot in snapshots:
        elements = {
            str(e["id"]): (kind.value, e)
            for kind, collection in COLLECTIONS.items()
            for e in snapshot.get(collection) or []
        }
        for element_id, (kind, element) in elements.items():
            labels[element_id] = element_label(kind, element, elements)
    return labels


def impacts(changes, merged):
    from uuid import UUID

    from ontofoundry_api.domain.core import CoreDraft
    from ontofoundry_api.domain.dependencies import reverse_dependencies

    changed = {UUID(c["element_id"]) for c in changes}
    try:
        draft = CoreDraft.model_validate(merged)
        affected = reverse_dependencies(draft, changed)
    except (ValueError, KeyError):
        return []
    labels = element_labels(merged)
    kinds = {
        str(e.id): kind.value
        for kind, collection in COLLECTIONS.items()
        for e in getattr(draft, collection)
    }
    return [
        {
            "element_kind": kinds[str(i)],
            "element_id": str(i),
            "label": labels[str(i)],
            "reason": "引用了已变更的定义",
        }
        for i in sorted(affected)
    ]
