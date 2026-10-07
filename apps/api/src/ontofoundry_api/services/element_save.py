"""The editable aggregate of one type, excluding unrelated session changes."""

from copy import deepcopy

from ontofoundry_api.services.errors import ServiceError


def element_scope(draft: dict, kind: str, element_id: str) -> dict[str, set[str]]:
    scope = {key: set() for key in (
        "object_types", "properties", "link_types", "rules", "actions",
        "material_objects", "material_links", "mappings",
    )}
    collection = "object_types" if kind == "object_type" else "link_types"
    scope[collection].add(element_id)
    if kind == "object_type":
        scope["properties"] = {
            p["id"] for p in draft["properties"] if p["owner_type_id"] == element_id
        }
        scope["actions"] = {
            a["id"] for a in draft["actions"] if a["input_type_id"] == element_id
        }
        scope["mappings"] = {
            m["id"] for m in draft["mappings"] if m["type_id"] == element_id
        }
    owners = {
        kind: {element_id}, "property": scope["properties"], "action": scope["actions"],
    }
    scope["rules"] = {
        r["id"] for r in draft["rules"]
        if r["owner_id"] in owners.get(r["owner_kind"], set())
    }
    return scope


def scoped_draft(base: dict, original: dict, edited: dict, kind: str, element_id: str) -> dict:
    """Replace only the selected aggregate; reject an out-of-scope mutation."""
    if edited.get("workspace_id") != original["workspace_id"]:
        raise ServiceError("元素所属空间不匹配", status_code=422, code="WORKSPACE_MISMATCH")
    if edited.get("ontology_requires") != original.get("ontology_requires"):
        raise ServiceError("请在建模页修改空间约束", status_code=422, code="ELEMENT_SCOPE_INVALID")
    before, after = element_scope(original, kind, element_id), element_scope(edited, kind, element_id)
    baseline = element_scope(base, kind, element_id)
    result = deepcopy(base)
    collection = "object_types" if kind == "object_type" else "link_types"
    if not any(e["id"] == element_id for e in edited[collection]):
        raise ServiceError("没有找到要保存的元素", status_code=422, code="ELEMENT_NOT_FOUND")
    for key in before:
        allowed = before[key] | after[key] | baseline[key]
        old = {e["id"]: e for e in original[key]}
        new = {e["id"]: e for e in edited[key]}
        changed = {i for i in old.keys() | new.keys() if old.get(i) != new.get(i)}
        # Existing elements outside this aggregate cannot be pulled into it
        # by changing their owner in a crafted request.
        if changed - allowed or (changed & old.keys()) - before[key]:
            raise ServiceError("保存包含其他元素的修改，请重新打开当前元素", status_code=422,
                               code="ELEMENT_SCOPE_INVALID")
        replacements = {i: new[i] for i in allowed if i in new}
        # Preserve collection order as well as the identities of untouched elements.
        result[key] = [replacements.pop(e["id"], e) for e in base[key]
                       if e["id"] not in allowed or e["id"] in new]
        result[key].extend(replacements.values())
    return result
