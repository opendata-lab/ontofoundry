"""Stable-ID comparison with model references, without exposing unrelated facts."""


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
        inherited = {
            tid for tid, t in types.items() if affected.intersection(t.get("extends", []))
        }
        if inherited <= affected:
            break
        affected.update(inherited)
    mappings = {
        m["id"]: m for snapshot in (left, right) for m in snapshot.get("mappings", [])
    }
    for mapping in mappings.values():
        if any(
            mapping["type_id"] in affected or mapping["id"] in item["path"]
            for item in changes
        ):
            impacts.append(
                {"kind": "mapping", "id": mapping["id"], "label": mapping["table_name"]}
            )
    links = {
        r["id"]: r for snapshot in (left, right) for r in snapshot.get("link_types", [])
    }
    for link in links.values():
        if any(
            link["id"] in item["path"]
            or bool(affected.intersection([link["source_type_id"], link["target_type_id"]]))
            for item in changes
        ):
            impacts.append({"kind": "link_type", "id": link["id"], "label": link["name"]})
    return {"changes": changes, "impacts": impacts}
