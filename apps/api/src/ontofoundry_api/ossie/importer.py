"""Read Apache Ossie ontology JSON into the internal model.

The internal model carries the Ossie constructs it can: entity inheritance,
identifying relations, constraints, derivations and hand-written readings all
survive a round trip. What remains outside it — n-ary and unary relationships,
value concepts as first-class concepts, `Any`, ontology_mappings — is reported
rather than guessed at, so the user reviewing the draft sees what was left
behind. See section 9.1 of the design document for the full correspondence.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any
from uuid import UUID, uuid5

from ontofoundry_api.domain.models import (
    AttributeDefinition,
    LinkTypeDefinition,
    Multiplicity,
    ObjectTypeDefinition,
    OntologyDraft,
    ValueKind,
)

from .compiler import (
    EXTENSION_KEY,
    VALUE_BASES,
    attribute_verbalizations,
    link_verbalizations,
)
from .validator import validate_schema

MAX_COMPONENTS = 2000
VALUE_KIND_BY_CONCEPT = {name: kind for kind, name in VALUE_BASES.items()}
MULTIPLICITY_BY_OSSIE = {
    "OneToOne": Multiplicity.ONE_TO_ONE,
    "ManyToOne": Multiplicity.MANY_TO_ONE,
}
NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_]+")


class OssieImportError(ValueError):
    """Raised when the document cannot be read at all."""


def _sanitize(raw: str) -> str:
    ascii_form = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    cleaned = NON_IDENTIFIER_RE.sub("_", ascii_form).strip("_")
    if not cleaned:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
        return f"c_{digest}"
    return f"c_{cleaned}" if cleaned[0].isdigit() else cleaned


def _unique(candidate: str, taken: set[str], separator: str = "_") -> str:
    if candidate.casefold() not in taken:
        taken.add(candidate.casefold())
        return candidate
    index = 2
    while f"{candidate}{separator}{index}".casefold() in taken:
        index += 1
    value = f"{candidate}{separator}{index}"
    taken.add(value.casefold())
    return value


def _identity(workspace_id: str, key: str) -> UUID:
    return uuid5(UUID(str(workspace_id)), key)


class Report:
    """Collects what came in and what could not be represented."""

    def __init__(self) -> None:
        self.skipped: list[dict[str, str]] = []
        self.notes: list[str] = []

    def skip(self, path: str, reason: str) -> None:
        self.skipped.append({"path": path, "reason": reason})

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


def _extension(document: dict[str, Any]) -> dict[str, Any]:
    context = document.get("ai_context")
    extension = context.get(EXTENSION_KEY) if isinstance(context, dict) else None
    return extension if isinstance(extension, dict) else {}


def _resolve_value_kind(
    concept: str,
    values: dict[str, dict[str, Any]],
    seen: set[str] | None = None,
) -> tuple[ValueKind, str | None]:
    """Walk `extends` until a built-in value concept is reached."""
    if concept in VALUE_KIND_BY_CONCEPT:
        return VALUE_KIND_BY_CONCEPT[concept], None
    seen = seen or set()
    if concept in seen:
        return ValueKind.STRING, f"值概念 {concept} 的继承链存在循环，按 string 导入"
    seen.add(concept)
    component = values.get(concept)
    if component is None:
        return ValueKind.STRING, f"值概念 {concept} 未在文件中定义，按 string 导入"
    for parent in component.get("extends") or []:
        kind, problem = _resolve_value_kind(str(parent), values, seen)
        if problem is None:
            return kind, None
    return (
        ValueKind.STRING,
        f"值概念 {concept} 没有追溯到内置值类型，按 string 导入",
    )


def _parents(
    concept: str, entities: dict[str, dict[str, Any]], report: Report
) -> list[str]:
    """Entity supertypes that are actually defined in the file."""
    found: list[str] = []
    for parent in entities.get(concept, {}).get("extends") or []:
        parent_name = str(parent)
        if parent_name == "Any":  # implicit root, not a business object
            continue
        if parent_name not in entities:
            report.skip(
                f"{concept}.extends[{parent_name}]",
                "父概念未在文件中定义，继承未建立",
            )
            continue
        found.append(parent_name)
    return found


def _expressions(holder: dict[str, Any], field: str) -> list[str]:
    return [str(item) for item in holder.get(field) or [] if str(item).strip()]


def _keep_verbalizations(written: list[str], generated: list[str]) -> list[str]:
    """Readings are stored verbatim; the concepts they mention are kept too.

    Only a reading the compiler would produce anyway is dropped, so renaming an
    attribute in the workspace does not leave text stating the old name.
    """
    return [] if not written or written == generated else written


def _value_concept_loss(
    concept: str,
    values: dict[str, dict[str, Any]],
    kind: ValueKind,
) -> str | None:
    """What a named value concept loses on the way in.

    The name is kept, so a concept shared by several attributes is written back
    as the same single concept. What the internal model has no place for is the
    concept's own rules and any intermediate concept in its `extends` chain.
    """
    if concept in VALUE_KIND_BY_CONCEPT:
        return None
    component = values.get(concept, {})
    if component.get("requires") or component.get("derived_by"):
        return (
            f"值概念 {concept} 自带约束或派生规则：内置模型的属性只保留基础类型 "
            f"{kind.value}，这些表达式没有承载位置"
        )
    chain = [str(item) for item in component.get("extends") or []]
    if any(parent not in VALUE_KIND_BY_CONCEPT for parent in chain):
        return (
            f"值概念 {concept} 经 {'、'.join(chain)} 才继承到内置类型 {kind.value}："
            "中间的值概念不保留"
        )
    return None


def parse_ossie(
    document: dict[str, Any], *, workspace_id: str
) -> tuple[list[ObjectTypeDefinition], list[LinkTypeDefinition], list[str], Report]:
    """Turn a schema-valid Ossie document into internal types plus a report."""
    if not isinstance(document, dict):
        raise OssieImportError("文件内容不是 JSON 对象")
    components = document.get("ontology")
    if not isinstance(components, list) or not components:
        raise OssieImportError("文件缺少 ontology 组件列表")
    if len(components) > MAX_COMPONENTS:
        raise OssieImportError(f"组件数量超过 {MAX_COMPONENTS} 个上限")

    report = Report()
    by_concept: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        if not isinstance(component, dict) or not component.get("concept"):
            report.skip(f"ontology[{index}]", "组件缺少 concept 名称")
            continue
        name = str(component["concept"])
        if name in by_concept:
            report.skip(f"ontology[{index}].{name}", "概念名称重复，保留首次出现的定义")
            continue
        by_concept[name] = component
    entities = {k: v for k, v in by_concept.items() if v.get("type") == "EntityType"}
    values = {k: v for k, v in by_concept.items() if v.get("type") == "ValueType"}

    extension = _extension(document)
    display_names = extension.get("display_names")
    display_names = display_names if isinstance(display_names, dict) else {}
    tag_map = extension.get("tags") if isinstance(extension.get("tags"), dict) else {}
    required_keys = set(extension.get("required_attributes") or [])
    if extension:
        report.note("文件带有 OntoFoundry 扩展信息，已恢复中文名称、标签与必填标记")
    elif entities:
        report.note("文件没有中文显示名，业务名称先使用 concept 名称，可在草稿里修改")

    ontology_requires = _expressions(document, "requires")
    if document.get("ontology_mappings"):
        report.skip(
            "ontology_mappings",
            f"{len(document['ontology_mappings'])} 组 ontology_mappings（逻辑模型映射）暂不导入，"
            "数据映射请在“数据映射”页按连接配置",
        )

    object_types: list[ObjectTypeDefinition] = []
    by_concept_id: dict[str, UUID] = {}
    parents_by_concept: dict[str, list[str]] = {}
    pending_links: list[dict[str, Any]] = []
    taken_object_names: set[str] = set()
    taken_object_keys: set[str] = set()

    for concept in sorted(entities):
        component = entities[concept]
        technical_name = _unique(_sanitize(concept), taken_object_keys)
        label = str(display_names.get(concept) or concept).strip() or concept
        identifiers = {str(item) for item in component.get("identify_by") or []}
        parents_by_concept[concept] = _parents(concept, entities, report)
        attributes: list[AttributeDefinition] = []
        taken_attribute_names: set[str] = set()
        taken_attribute_keys: set[str] = set()
        used_identifiers: set[str] = set()

        for relationship in component.get("relationships") or []:
            if not isinstance(relationship, dict):
                continue
            name = str(relationship.get("name") or "")
            path = f"{concept}.{name}"
            roles = relationship.get("roles") or []
            if len(roles) != 1:
                report.skip(
                    path,
                    f"{len(roles)} 个 role 的关系暂不支持，内置模型只有二元关系"
                    "（一个对象连一个值或另一个对象）",
                )
                continue
            role = roles[0] if isinstance(roles[0], dict) else {}
            target = str(role.get("concept") or "")
            key = f"{concept}.{name}"
            title = str(display_names.get(key) or name).strip() or name
            verbalizes = [
                str(item) for item in relationship.get("verbalizes") or [] if str(item)
            ]

            if target in VALUE_KIND_BY_CONCEPT or target in values:
                kind, problem = _resolve_value_kind(target, values)
                if problem:
                    report.note(problem)
                else:
                    loss = _value_concept_loss(target, values, kind)
                    if loss:
                        report.note(loss)
                attribute_key = _unique(_sanitize(name), taken_attribute_keys)
                identifier = name in identifiers
                attribute = AttributeDefinition(
                    id=_identity(workspace_id, f"attribute:{concept}.{name}"),
                    name=_unique(title, taken_attribute_names, "·"),
                    technical_name=attribute_key,
                    description=str(relationship.get("description") or ""),
                    value_kind=kind,
                    required=key in required_keys,
                    identifier=identifier,
                    # Keep the file's own value concept so it is written back
                    # under the same name and readings stay valid untouched.
                    value_concept=target if target in values else None,
                    requires=_expressions(relationship, "requires"),
                    derived_by=_expressions(relationship, "derived_by"),
                )
                attribute.verbalizes = _keep_verbalizations(
                    verbalizes,
                    attribute_verbalizations(attribute, technical_name, target),
                )
                attributes.append(attribute)
                used_identifiers.add(name)
                continue

            if target in entities:
                pending_links.append(
                    {
                        "source": concept,
                        "target": target,
                        "name": name,
                        "title": title,
                        "description": str(relationship.get("description") or ""),
                        "multiplicity": relationship.get("multiplicity"),
                        "role_name": role.get("name"),
                        "tags": tag_map.get(key),
                        "identifier": name in identifiers,
                        "requires": _expressions(relationship, "requires"),
                        "derived_by": _expressions(relationship, "derived_by"),
                        "verbalizes": verbalizes,
                    }
                )
                used_identifiers.add(name)
                continue

            report.skip(
                path,
                f"关系指向的概念 {target or '(缺失)'} 不是文件里的实体或值概念"
                + ("（Any 是内置实体，没有对应的业务对象）" if target == "Any" else ""),
            )

        for missing in sorted(identifiers - used_identifiers):
            report.skip(
                f"{concept}.identify_by[{missing}]",
                "identify_by 引用了未导入的关系，标识未设置",
            )

        tags = tag_map.get(concept)
        object_types.append(
            ObjectTypeDefinition(
                id=_identity(workspace_id, f"object:{concept}"),
                name=_unique(label, taken_object_names, "·"),
                technical_name=technical_name,
                description=str(component.get("description") or ""),
                tags=[str(tag) for tag in tags] if isinstance(tags, list) else [],
                requires=_expressions(component, "requires"),
                derived_by=_expressions(component, "derived_by"),
                attributes=attributes,
            )
        )
        by_concept_id[concept] = object_types[-1].id

    keys_by_concept = {
        concept: item.technical_name
        for concept, item in zip(sorted(entities), object_types, strict=True)
    }
    for concept, item in zip(sorted(entities), object_types, strict=True):
        item.extends = [
            by_concept_id[parent]
            for parent in parents_by_concept.get(concept, [])
            if parent in by_concept_id
        ]

    link_types: list[LinkTypeDefinition] = []
    # Relationship names are local to their concept in Ossie and in the internal
    # model alike, so names only need to be unique inside the owning concept.
    taken_by_owner: dict[str, tuple[set[str], set[str]]] = {}
    for link in pending_links:
        source_id = by_concept_id.get(link["source"])
        target_id = by_concept_id.get(link["target"])
        if source_id is None or target_id is None:  # pragma: no cover - guarded above
            continue
        multiplicity = MULTIPLICITY_BY_OSSIE.get(
            str(link["multiplicity"]), Multiplicity.MANY_TO_MANY
        )
        role_name = link["role_name"]
        if link["source"] == link["target"] and role_name == "related":
            role_name = None
        tags = link["tags"]
        names, keys = taken_by_owner.setdefault(link["source"], (set(), set()))
        identifier = bool(link["identifier"]) and multiplicity in (
            Multiplicity.MANY_TO_ONE,
            Multiplicity.ONE_TO_ONE,
        )
        if link["identifier"] and not identifier:
            report.skip(
                f"{link['source']}.identify_by[{link['name']}]",
                "作为标识的关系必须是多对一或一对一，文件里的基数无法唯一确定对象，标识未设置",
            )
        candidate = LinkTypeDefinition(
            id=_identity(workspace_id, f"link:{link['source']}.{link['name']}"),
            name=_unique(link["title"], names, "·"),
            technical_name=_unique(_sanitize(link["name"]), keys),
            description=link["description"],
            source_type_id=source_id,
            target_type_id=target_id,
            multiplicity=multiplicity,
            target_role_name=str(role_name) if role_name else None,
            identifier=identifier,
            requires=link["requires"],
            derived_by=link["derived_by"],
            tags=[str(tag) for tag in tags] if isinstance(tags, list) else [],
        )
        candidate.verbalizes = _keep_verbalizations(
            link["verbalizes"],
            link_verbalizations(
                candidate,
                keys_by_concept[link["source"]],
                keys_by_concept[link["target"]],
            ),
        )
        link_types.append(candidate)
    return object_types, link_types, ontology_requires, report


def _merge(
    base: OntologyDraft,
    objects: list[ObjectTypeDefinition],
    links: list[LinkTypeDefinition],
    report: Report,
) -> tuple[OntologyDraft, dict[str, int]]:
    """Add or update by technical name; never remove what the file omits."""
    counts = {
        "objects_added": 0,
        "objects_updated": 0,
        "links_added": 0,
        "links_updated": 0,
        "attributes_added": 0,
        "attributes_updated": 0,
    }
    merged = base.model_copy(deep=True)
    existing = {item.technical_name.casefold(): item for item in merged.object_types}
    names = {item.name.casefold() for item in merged.object_types}
    keys = set(existing)
    for imported in objects:
        current = existing.get(imported.technical_name.casefold())
        if current is None:
            imported.name = _unique(imported.name, names, "·")
            imported.technical_name = _unique(imported.technical_name, keys)
            merged.object_types.append(imported)
            existing[imported.technical_name.casefold()] = imported
            counts["objects_added"] += 1
            counts["attributes_added"] += len(imported.attributes)
            continue
        counts["objects_updated"] += 1
        if imported.description:
            current.description = imported.description
        current.tags = sorted({*current.tags, *imported.tags})
        if imported.requires:
            current.requires = imported.requires
        if imported.derived_by:
            current.derived_by = imported.derived_by
        # Keep the local business name: it is what the workspace already reads.
        attributes = {item.technical_name.casefold(): item for item in current.attributes}
        for attribute in imported.attributes:
            found = attributes.get(attribute.technical_name.casefold())
            if found is None:
                current.attributes.append(attribute)
                counts["attributes_added"] += 1
                continue
            found.value_kind = attribute.value_kind
            found.value_concept = attribute.value_concept
            found.identifier = attribute.identifier
            found.required = attribute.required
            found.requires = attribute.requires
            found.derived_by = attribute.derived_by
            found.verbalizes = attribute.verbalizes
            if attribute.description:
                found.description = attribute.description
            counts["attributes_updated"] += 1

    by_key = {item.technical_name.casefold(): item.id for item in merged.object_types}
    id_by_import = {item.id: item.technical_name.casefold() for item in objects}
    for imported in objects:
        current = existing.get(imported.technical_name.casefold())
        parents = [
            by_key[id_by_import[parent]]
            for parent in imported.extends
            if parent in id_by_import and id_by_import[parent] in by_key
        ]
        if current is not None and parents:
            current.extends = parents

    # Relationship names live inside their owning concept, so a file's `owned_by`
    # updates that concept's `owned_by` and never another concept's.
    def link_key(link: LinkTypeDefinition, owner: UUID) -> tuple[str, str]:
        return (str(owner), link.technical_name.casefold())

    link_index = {link_key(item, item.owner_type_id): item for item in merged.link_types}
    for imported in links:
        source = by_key.get(id_by_import.get(imported.source_type_id, ""))
        target = by_key.get(id_by_import.get(imported.target_type_id, ""))
        if source is None or target is None:  # pragma: no cover - endpoints always known
            report.skip(imported.technical_name, "关系两端的业务对象没有导入成功")
            continue
        imported.source_type_id, imported.target_type_id = source, target
        current = link_index.get(link_key(imported, imported.owner_type_id))
        if current is None:
            owned = [
                item
                for key, item in link_index.items()
                if key[0] == str(imported.owner_type_id)
            ]
            imported.name = _unique(
                imported.name, {item.name.casefold() for item in owned}, "·"
            )
            imported.technical_name = _unique(
                imported.technical_name,
                {item.technical_name.casefold() for item in owned},
            )
            merged.link_types.append(imported)
            link_index[link_key(imported, imported.owner_type_id)] = imported
            counts["links_added"] += 1
            continue
        counts["links_updated"] += 1
        current.source_type_id, current.target_type_id = source, target
        current.multiplicity = imported.multiplicity
        current.target_role_name = imported.target_role_name
        current.identifier = imported.identifier
        current.requires = imported.requires
        current.derived_by = imported.derived_by
        current.verbalizes = imported.verbalizes
        if imported.description:
            current.description = imported.description
        current.tags = sorted({*current.tags, *imported.tags})
    return merged, counts


def import_ossie(
    document: dict[str, Any],
    *,
    workspace_id: str,
    base: dict[str, Any] | None = None,
    mode: str = "merge",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the resulting draft and a report of everything the import changed."""
    schema_issues = validate_schema(document)
    if schema_issues:
        raise OssieImportError(
            "文件不符合 Apache Ossie 0.2.0.dev0 结构：" + schema_issues[0]["message"]
        )
    objects, links, requires, report = parse_ossie(document, workspace_id=workspace_id)
    if not objects:
        raise OssieImportError("文件里没有可导入的 EntityType 概念")

    base_draft = (
        OntologyDraft.model_validate(base)
        if base
        else OntologyDraft(workspace_id=UUID(str(workspace_id)))
    )
    if mode == "replace":
        counts = {
            "objects_added": len(objects),
            "objects_updated": 0,
            "links_added": len(links),
            "links_updated": 0,
            "attributes_added": sum(len(item.attributes) for item in objects),
            "attributes_updated": 0,
        }
        dropped = len(base_draft.objects) + len(base_draft.links) + len(base_draft.mappings)
        if dropped:
            report.note(
                "替换模式：文档实例、实例关系与数据映射不会保留，发布后当前模型将被文件内容整体替换"
            )
        elif base_draft.object_types:
            report.note("替换模式：文件之外的业务对象与关系会在发布时消失")
        draft = OntologyDraft(
            workspace_id=UUID(str(workspace_id)),
            requires=requires,
            object_types=objects,
            link_types=links,
        )
    else:
        draft, counts = _merge(base_draft, objects, links, report)
        draft.requires = [
            *draft.requires,
            *[item for item in requires if item not in draft.requires],
        ]
        report.note("合并模式：文件之外的已有对象、实例与数据映射保持不变")

    payload = draft.model_dump(mode="json")
    OntologyDraft.model_validate(payload)
    return payload, {
        "name": str(document.get("name") or ""),
        "description": str(document.get("description") or ""),
        "mode": mode,
        "counts": counts,
        "skipped": report.skipped,
        "notes": report.notes,
    }
