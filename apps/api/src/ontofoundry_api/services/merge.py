"""Three-way JSON merge. UUID lists merge structurally; scalar lists are atomic."""

from copy import deepcopy

MISSING = object()


def merge_snapshots(
    base: dict, current: dict, draft: dict, resolutions: dict | None = None
) -> tuple[dict, list[dict]]:
    conflicts = []

    def merge(b, c, d, path):
        if c == d or b == d:
            return deepcopy(c) if c is not MISSING else MISSING
        if b == c:
            return deepcopy(d) if d is not MISSING else MISSING
        if all(isinstance(v, dict) for v in (b, c, d)):
            result = {}
            for key in sorted(b.keys() | c.keys() | d.keys()):
                value = merge(
                    b.get(key, MISSING),
                    c.get(key, MISSING),
                    d.get(key, MISSING),
                    path + "/" + key,
                )
                if value is not MISSING:
                    result[key] = value
            return result
        if all(isinstance(v, list) for v in (b, c, d)) and all(
            isinstance(x, dict) and "id" in x for values in (b, c, d) for x in values
        ):
            maps = [{x["id"]: x for x in values} for values in (b, c, d)]
            return list(merge(*maps, path).values())
        side = (resolutions or {}).get(path)
        # Legacy form: "current" | "draft". Current form:
        # {"choice": "latest" | "draft" | "custom" | "both", "value": ...}.
        choice = side.get("choice") if isinstance(side, dict) else side
        if choice in ("current", "latest", "draft"):
            chosen = d if choice == "draft" else c
            return deepcopy(chosen) if chosen is not MISSING else MISSING
        if choice == "custom":
            return deepcopy(side.get("value"))
        if choice == "both" and isinstance(c, list) and isinstance(d, list):
            return deepcopy(c) + [deepcopy(x) for x in d if x not in c]
        conflicts.append(
            {
                "path": path,
                "base": None if b is MISSING else b,
                "current": None if c is MISSING else c,
                "draft": None if d is MISSING else d,
            }
        )
        return deepcopy(d) if d is not MISSING else MISSING

    return merge(base, current, draft, ""), conflicts
