"""Instance content validation and revision-bound baseline hashes (IS-04/09/11)."""

from uuid import UUID

from ontofoundry_api.domain.canonical import domain_sha256
from ontofoundry_api.domain.core import MaterialLink, MaterialObject
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.instance_validation import value_issues
from ontofoundry_api.domain.models import INSTANCE_COLLECTIONS, OntologyDraft

INSTANCE_KINDS = frozenset(k.value for k in INSTANCE_COLLECTIONS)


def instance_hash(element, revision):
    return domain_sha256({"instance": element, "revision": revision})


def baseline_elements(baseline):
    return {
        item["target_id"]: (item["target_kind"], item["element"])
        for item in (baseline or {}).get("items", [])
        if item["state"] != "deleted"
    }


def combined_snapshot(draft, baseline):
    result = {**draft, **{c: [] for c in INSTANCE_COLLECTIONS.values()}}
    for kind, element in baseline_elements(baseline).values():
        result[INSTANCE_COLLECTIONS[kind]].append(element)
    return result


def definitions(snapshot):
    return {k: v for k, v in snapshot.items() if k not in INSTANCE_COLLECTIONS.values()}


def validate_instances(draft, objects, links):
    model = (
        draft
        if isinstance(draft, OntologyDraft)
        else OntologyDraft.model_validate(
            draft.model_dump(mode="json") if hasattr(draft, "model_dump") else draft
        )
    )
    index = DraftIndex(model)
    objects = {UUID(str(o["id"])): MaterialObject.model_validate(o) for o in objects}
    for obj in objects.values():
        if obj.type_id not in index.objects:
            raise ValueError("实例对象类型不存在")
        if index.children(obj.type_id) and not any(
            m.type_id == obj.type_id for m in model.mappings
        ):
            raise ValueError("虚拟父对象不能保存直接实例")
        names = {p.name for p in index.effective_properties(obj.type_id)}
        if set(obj.values) - names:
            raise ValueError("实例引用了无效属性")
        issues = value_issues(model, obj.type_id, obj.values, str(obj.id))
        if any(i["severity"] == "error" for i in issues):
            raise ValueError("实例属性值类型不符")
    for value in links:
        link = MaterialLink.model_validate(value)
        definition = index.links.get(link.type_id)
        if definition is None:
            raise ValueError("关系实例类型不存在")
        if link.source_id not in objects or link.target_id not in objects:
            raise ValueError("关系实例端点不存在")
        if not (
            index.is_a(objects[link.source_id].type_id, definition.source_type_id)
            and index.is_a(objects[link.target_id].type_id, definition.target_type_id)
        ):
            raise ValueError("关系实例端点类型不兼容")
    return model


def interpretation(draft, kind, element, objects):
    """Only instance-interpreting definitions, excluding labels and descriptions."""
    index = DraftIndex(draft)
    if kind == "material_object":
        type_id = UUID(element["type_id"])
        if type_id not in index.objects:
            raise ValueError("实例类型不存在")
        properties = {p.name: p for p in index.effective_properties(type_id)}
        return {
            "type_id": str(type_id),
            "properties": {
                name: [
                    str(properties[name].id),
                    properties[name].name,
                    properties[name].value_kind.value,
                    str(properties[name].value_type_id)
                    if properties[name].value_type_id
                    else None,
                ]
                for name in element["values"]
            },
        }
    link = index.links[UUID(element["type_id"])]
    return {
        "link": [str(link.id), str(link.source_type_id), str(link.target_type_id)],
        "source": interpretation(
            draft, "material_object", objects[element["source_id"]], objects
        ),
        "target": interpretation(
            draft, "material_object", objects[element["target_id"]], objects
        ),
    }


def instance_references(draft, objects, links):
    from ontofoundry_api.domain.dependencies import Reference

    index = DraftIndex(draft)
    result = {}
    for element in objects:
        identity = UUID(element["id"])
        refs = [Reference(identity, UUID(element["type_id"]), "type_id")]
        for name in element["values"]:
            prop = index.property_by_name(UUID(element["type_id"]), name)
            if prop:
                refs.append(Reference(identity, prop.id, "values." + name))
        result[identity] = tuple(refs)
    for element in links:
        identity = UUID(element["id"])
        result[identity] = tuple(
            Reference(identity, UUID(element[name]), name)
            for name in ("type_id", "source_id", "target_id")
        )
    return result
