"""Stable-ID comparison with model references, without exposing unrelated facts."""

from uuid import UUID

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import reference_index
from ontofoundry_api.domain.models import COLLECTIONS

# Collections whose elements are reported in `impacts` when an object type changes.
IMPACT_COLLECTIONS = ("mappings", "link_types", "actions")


def _action_references(snapshots) -> dict[str, set[str]]:
    refs_by_action: dict[str, set[str]] = {}
    for snapshot in snapshots:
        if not snapshot or not snapshot.get("actions"):
            continue
        try:
            draft = CoreDraft.model_validate(snapshot)
        except ValueError:
            continue
        action_ids = {action.id for action in draft.actions}
        for owner_id, refs in reference_index(draft, owner_ids=action_ids).items():
            refs_by_action.setdefault(str(owner_id), set()).update(
                str(ref.target_id) for ref in refs
            )
    return refs_by_action


def compare_snapshots(left, right):
    changes = []

    def walk(a, b, path):
        if a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                walk(a.get(key), b.get(key), f"{path}.{key}")
        elif (
            (isinstance(a, list) or a is None)
            and (isinstance(b, list) or b is None)
            and all(
                isinstance(item, dict) and "id" in item for item in [*(a or []), *(b or [])]
            )
        ):
            old, new = ({item["id"]: item for item in (rows or [])} for rows in (a, b))
            for key in sorted(old.keys() | new.keys()):
                walk(old.get(key), new.get(key), f"{path}[{key}]")
        else:
            changes.append(
                {
                    "path": path,
                    "kind": "added" if a is None else "removed" if b is None else "changed",
                    "before": a,
                    "after": b,
                }
            )

    walk(left, right, "$")
    # Only explicit model references are claimed, not unknown external consumers.
    impacts = []
    types = {
        t["id"]: t for snapshot in (left, right) for t in snapshot.get("object_types", [])
    }
    affected = {tid for tid in types if any(tid in item["path"] for item in changes)}
    while True:
        inherited = {tid for tid, t in types.items() if t.get("extends") in affected}
        if inherited <= affected:
            break
        affected.update(inherited)
    indexed = {
        collection: {
            item["id"]: item
            for snapshot in (left, right)
            for item in snapshot.get(collection, [])
        }
        for collection in IMPACT_COLLECTIONS
    }
    for mapping in indexed["mappings"].values():
        if any(
            mapping["type_id"] in affected or mapping["id"] in item["path"]
            for item in changes
        ):
            impacts.append({"kind": "mapping", "id": mapping["id"], "label": mapping["id"]})
    for link in indexed["link_types"].values():
        if any(
            link["id"] in item["path"]
            or bool(affected.intersection([link["source_type_id"], link["target_type_id"]]))
            for item in changes
        ):
            impacts.append({"kind": "link_type", "id": link["id"], "label": link.get("display_name") or link["name"]})
    all_ids = {
        item["id"]
        for snapshot in (left, right)
        for collection in COLLECTIONS.values()
        for item in snapshot.get(collection, [])
        if isinstance(item, dict) and "id" in item
    }
    changed_ids = {
        eid for eid in all_ids if any(eid in item["path"] for item in changes)
    }
    action_refs = _action_references((left, right))
    for action in indexed["actions"].values():
        aid = action["id"]
        if aid in changed_ids or bool(action_refs.get(aid, set()) & (changed_ids | affected)):
            impacts.append({"kind": "action", "id": aid, "label": action.get("display_name") or action["name"]})
    return {"changes": changes, "impacts": impacts}
