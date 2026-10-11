"""The editable aggregate of one type, excluding unrelated session changes."""

from copy import deepcopy

from ontofoundry_api.services.errors import ServiceError


def element_scope(draft: dict, kind: str, element_id: str) -> dict[str, set[str]]:
    scope = {key: set() for key in (
        "object_types", "properties", "link_types", "rules", "actions",
        "material_objects", "material_links", "mappings",
    )}
    if draft.get("schema_version") == "3":
        scope["value_types"] = set()
    collection = {"object_type": "object_types", "value_type": "value_types", "link_type": "link_types"}[kind]
    scope[collection].add(element_id)
    if kind == "link_type" and draft.get("schema_version") == "3":
        link = next((link for link in draft["link_types"] if link["id"] == element_id), None)
        if link and link["owner_ref"]["kind"] == "object_type":
            scope["object_types"].add(link["owner_ref"]["ref"])
    if kind == "object_type":
        scope["properties"] = {
            p["id"] for p in draft["properties"] if p.get("owner_type_id", p.get("owner_ref", {}).get("ref")) == element_id
        }
        if draft.get("schema_version") == "3":
            scope["value_types"] = {r["concept"]["ref"] for p in draft["properties"] if p["id"] in scope["properties"]
                                    for r in p["roles"] if r["concept"]["kind"] == "value_type"}
        scope["actions"] = {
            a["id"] for a in draft["actions"] if a["input_type_id"] == element_id
        }
        if draft.get("schema_version") == "2":
            scope["mappings"] = {m["id"] for m in draft["mappings"] if m["type_id"] == element_id}
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
    if original.get("schema_version") == "3":
        for collection in ("semantic_models", "datasets", "dataset_fields", "dataset_relationships", "metrics", "concept_mappings", "mapping_nodes"):
            if edited.get(collection) != original.get(collection):
                raise ServiceError("请通过现有映射表单修改映射", status_code=422, code="ELEMENT_SCOPE_INVALID")
    before, after = element_scope(original, kind, element_id), element_scope(edited, kind, element_id)
    baseline = element_scope(base, kind, element_id)
    result = deepcopy(base)
    if original.get('schema_version') == '3':
        for field in original['extension_v4']:
            if field != 'concept_context' and edited['extension_v4'].get(field) != original['extension_v4'][field]:
                raise ServiceError('请勿在元素保存中修改扩展注册信息', status_code=422, code='ELEMENT_SCOPE_INVALID')
        old_context = original['extension_v4']['concept_context']
        new_context = edited['extension_v4']['concept_context']
        changed_context = {key for key in old_context.keys() | new_context.keys() if old_context.get(key) != new_context.get(key)}
        allowed_context = {element_id} if kind in ('object_type', 'value_type') else set()
        if changed_context - allowed_context:
            raise ServiceError('概念上下文包含其他元素的修改', status_code=422, code='ELEMENT_SCOPE_INVALID')
        for key in allowed_context:
            if key in new_context:
                result['extension_v4']['concept_context'][key] = deepcopy(new_context[key])
            else:
                result['extension_v4']['concept_context'].pop(key, None)
    collection = {"object_type": "object_types", "value_type": "value_types", "link_type": "link_types"}[kind]
    if not any(e["id"] == element_id for e in edited[collection]):
        raise ServiceError("没有找到要保存的元素", status_code=422, code="ELEMENT_NOT_FOUND")
    for key in before:
        allowed = before[key] | after[key] | baseline[key]
        old = {e["id"]: e for e in original[key]}
        new = {e["id"]: e for e in edited[key]}
        changed = {i for i in old.keys() | new.keys() if old.get(i) != new.get(i)}
        if kind == "link_type" and original.get("schema_version") == "3" and key == "object_types":
            for item_id in changed:
                if item_id not in allowed or item_id not in old or item_id not in new:
                    raise ServiceError("关系保存不能新增或删除对象", status_code=422, code="ELEMENT_SCOPE_INVALID")
                fields = set(old[item_id]) | set(new[item_id])
                if any(old[item_id].get(f) != new[item_id].get(f) for f in fields - {"identify_by", "native_presence"}):
                    raise ServiceError("关系保存只能更新所属概念的标识引用", status_code=422, code="ELEMENT_SCOPE_INVALID")
        # Existing elements outside this aggregate cannot be pulled into it
        # by changing their owner in a crafted request.
        if changed - allowed or ((changed & old.keys()) - before[key] and not (kind == "link_type" and key == "object_types" and original.get("schema_version") == "3")):
            raise ServiceError("保存包含其他元素的修改，请重新打开当前元素", status_code=422,
                               code="ELEMENT_SCOPE_INVALID")
        replacements = {i: new[i] for i in allowed if i in new}
        # Preserve collection order as well as the identities of untouched elements.
        result[key] = [replacements.pop(e["id"], e) for e in base[key]
                       if e["id"] not in allowed or e["id"] in new]
        result[key].extend(replacements.values())
    return result
