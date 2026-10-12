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

from ontofoundry_api.domain.canonical import canonical

# The file is first read into the v1 nested shape, which mirrors Ossie's own
# nesting (relationships inside concepts), then lifted to v2 in one place.
from ontofoundry_api.domain.legacy_v1 import (
    AttributeDefinition,
    DataMapping,
    LinkTypeDefinition,
    Multiplicity,
    ObjectTypeDefinition,
    OntologyDraftV1,
    ValueKind,
)
from ontofoundry_api.domain.models import (
    OntologyDraft,
    RuleDefinition,
)
from ontofoundry_api.domain.snapshot import legacy_rule_id, normalize_v1

from .compiler import (
    EXTENSION_KEY,
    OSSIE_VERSION,
    VALUE_BASES,
    attribute_verbalizations,
    link_verbalizations,
)
from .coverage import unsupported_constructs
from .mappings import parse_joins, parse_mappings
from .validator import validate_schema

MAX_COMPONENTS = 2000
# Every extension version this platform has exported. v1 differs from v2 only in
# laying attribute mappings out flat, which parse_mappings reads as well, so
# files exported before the bump — and published versions exported from them —
# still import. Listed explicitly: bumping EXTENSION_VERSION must not drop
# the version it replaces.
READABLE_EXTENSION_VERSIONS = ("1", "2", "3")
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
        # Imported element id -> its Ossie path ("concept" or "concept.name"),
        # used to find rule identities kept in extension v3.
        self.paths: dict[str, str] = {}

    def skip(self, path: str, reason: str) -> None:
        self.skipped.append({"path": path, "reason": reason})

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


class _PropertyView:
    """What parse_mappings needs of a property while types are still v1-shaped."""

    def __init__(self, owner_type_id: UUID, technical_name: str) -> None:
        self.owner_type_id = owner_type_id
        self.technical_name = technical_name


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
) -> tuple[
    list[ObjectTypeDefinition],
    list[LinkTypeDefinition],
    list[DataMapping],
    list[str],
    Report,
]:
    """Turn a schema-valid Ossie document into internal types plus a report."""
    if not isinstance(document, dict):
        raise OssieImportError("文件内容不是 JSON 对象")
    for path, reason in unsupported_constructs(document):
        raise OssieImportError(f"{path}：不支持的 Ossie 构造：{reason}")
    components = document.get("ontology")
    if not isinstance(components, list) or not components:
        raise OssieImportError("文件缺少 ontology 组件列表")
    if len(components) > MAX_COMPONENTS:
        raise OssieImportError(f"概念数量超过 {MAX_COMPONENTS} 个上限")

    report = Report()
    context = document.get("ai_context") or {}
    for key in context:
        if key != EXTENSION_KEY:
            report.note(
                f"ai_context.{key}：内置模型只读取 OntoFoundry 扩展，"
                "此上下文不保存；导出时重新生成 instructions/synonyms"
            )
    for index, entry in enumerate(document.get("ontology_mappings") or []):
        path = f"ontology_mappings[{index}]"
        model = entry.get("semantic_model") or {}
        if model.get("datasets"):
            report.note(
                f"{path}.semantic_model.datasets：仅保存已导入对象的表、键列与属性列；"
                "导出按每个对象重建 dataset，未使用的数据集、逻辑字段名称与其元数据不保留"
            )
        if entry.get("description"):
            report.note(f"{path}.description：映射描述不保存，导出时按数据源名称生成")
        if model.get("name") != (entry.get("name") or model.get("name")):
            report.note(f"{path}.semantic_model.name：导出时改用数据源名称")
        for key in ("description", "ai_context", "metrics"):
            if model.get(key):
                report.note(f"{path}.semantic_model.{key}：内置数据映射没有承载位置，不保存")
        for dataset_index, dataset in enumerate(model.get("datasets") or []):
            dataset_path = f"{path}.semantic_model.datasets[{dataset_index}]"
            if dataset.get("description"):
                report.note(f"{dataset_path}.description：导出时改用业务对象描述")
            if dataset.get("ai_context"):
                report.note(f"{dataset_path}.ai_context：内置数据映射没有承载位置，不保存")
            if any(
                set(field) - {"name", "expression"}
                for field in dataset.get("fields") or []
            ):
                report.note(
                    f"{dataset_path}.fields：字段仅保留可映射的单列表达式；"
                    "datatype、description、ai_context 等字段元数据不保存"
                )
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
                    # Export writes the attribute's description onto its value
                    # concept, so a concept that says something of its own is
                    # overwritten on the way back out.
                    own = str(values.get(target, {}).get("description") or "")
                    if own and own != str(relationship.get("description") or ""):
                        report.note(
                            f"值概念 {target} 的描述与属性 {concept}.{name} 不同："
                            "内置模型只保留属性描述，导出时值概念改用属性描述"
                        )
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
                    value_concept=(
                        target
                        if target in values
                        or (identifier and target in VALUE_KIND_BY_CONCEPT)
                        else None
                    ),
                    target_role_name=str(role.get("name")) if role.get("name") else None,
                    multiplicity=MULTIPLICITY_BY_OSSIE.get(
                        str(relationship.get("multiplicity") or "")
                    ),
                    requires=_expressions(relationship, "requires"),
                    derived_by=_expressions(relationship, "derived_by"),
                )
                attribute.verbalizes = _keep_verbalizations(
                    verbalizes,
                    attribute_verbalizations(attribute, technical_name, target),
                )
                attributes.append(attribute)
                report.paths[str(attribute.id)] = key
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
        report.paths[str(object_types[-1].id)] = concept

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
        report.paths[str(candidate.id)] = f"{link['source']}.{link['name']}"
    # Mappings need the finished types, so they are read last — and joins need
    # the mappings, because a relation can only be joined when both of its
    # endpoints are backed by a table.
    mappings = parse_mappings(
        document,
        object_types,
        [
            _PropertyView(owner_type_id=item.id, technical_name=attribute.technical_name)
            for item in object_types
            for attribute in item.attributes
        ],
        workspace_id,
        report.skip,
    )
    parse_joins(
        document,
        object_types,
        link_types,
        {mapping.type_id for mapping in mappings},
        report.skip,
    )
    return object_types, link_types, mappings, ontology_requires, report


def _lift(
    workspace_id: str,
    objects: list[ObjectTypeDefinition],
    links: list[LinkTypeDefinition],
    mappings: list[DataMapping],
    requires: list[str],
    extension: dict[str, Any],
    report: Report,
) -> dict[str, Any]:
    """The parsed file as a v2 draft dict, with extension-v3 identities restored."""
    lifted = normalize_v1(
        OntologyDraftV1(
            workspace_id=UUID(str(workspace_id)),
            requires=requires,
            object_types=objects,
            link_types=links,
            mappings=[m.model_dump(mode="json") for m in mappings],
        ).model_dump(mode="json")
    )
    kept = extension.get("rules") if isinstance(extension.get("rules"), dict) else {}
    for rule in lifted["rules"]:
        path = report.paths.get(rule["owner_id"])
        match = next(
            (
                entry
                for entry in kept.get(path or "", [])
                if isinstance(entry, dict)
                and entry.get("rule_kind") == rule["rule_kind"]
                and entry.get("expression") == rule["expression"]
            ),
            None,
        )
        if match:
            rule.update(
                id=str(match.get("id") or rule["id"]),
                name=str(match.get("name") or rule["name"]),
                technical_name=str(match.get("technical_name") or rule["technical_name"]),
                description=str(match.get("description") or ""),
            )
    lifted["actions"], action_rules = _parse_actions(lifted, extension, report)
    lifted["rules"].extend(action_rules)
    return lifted


def _resolve_precondition(
    ref: Any,
    known_rules: list[dict[str, Any]],
    paths: dict[str, str],
    action_label: str,
    action_id: str,
) -> str | None:
    """A precondition by id if the file kept ids, else by owner path and
    technical name — never by technical name alone."""
    if not isinstance(ref, dict):
        return None
    if str(ref.get("id")) in {r["id"] for r in known_rules}:
        return str(ref["id"])
    owner = str(ref.get("owner") or "")
    matches = [
        r["id"]
        for r in known_rules
        if r["technical_name"] == ref.get("technical_name")
        and (
            (owner == f"action:{action_label}" and r["owner_id"] == action_id)
            or paths.get(r["owner_id"]) == owner
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _parse_actions(
    draft: dict[str, Any], extension: dict[str, Any], report: Report
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Action definitions from extension v3; unresolved references are reported."""
    entries = extension.get("actions")
    if not isinstance(entries, list):
        return [], []
    by_path = {path: element_id for element_id, path in report.paths.items()}
    types = {t["technical_name"]: t["id"] for t in draft["object_types"]}
    concept_ids = {
        path: element_id for path, element_id in by_path.items() if "." not in path
    }
    actions, rules = [], []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("technical_name") or f"actions[{index}]")
        input_type = concept_ids.get(str(entry.get("input_type"))) or types.get(
            str(entry.get("input_type"))
        )
        if not input_type:
            report.skip(f"actions.{label}", "Action 的输入对象类型没有导入")
            continue
        action_id = str(entry.get("id") or uuid5(UUID(draft["workspace_id"]), f"action:{label}"))
        own_rules = []
        for rule in entry.get("rules") or []:
            own_rules.append(
                {
                    "id": str(rule.get("id") or legacy_rule_id(
                        UUID(draft["workspace_id"]), "action", action_id,
                        str(rule.get("rule_kind")), str(rule.get("expression")),
                    )),
                    "name": str(rule.get("name") or rule.get("technical_name")),
                    "technical_name": str(rule.get("technical_name")),
                    "description": str(rule.get("description") or ""),
                    "owner_kind": "action",
                    "owner_id": action_id,
                    "rule_kind": str(rule.get("rule_kind")),
                    "expression": str(rule.get("expression")),
                    "verbalizes": [],
                    "evidence": [],
                }
            )
        known_rules = [*draft["rules"], *own_rules]
        effects, broken = [], False
        for effect in entry.get("effects") or []:
            prop = by_path.get(str(effect.get("property"))) if effect.get("property") else None
            link = by_path.get(str(effect.get("link"))) if effect.get("link") else None
            if (effect.get("property") and not prop) or (effect.get("link") and not link):
                broken = True
                break
            effects.append(
                {
                    "id": str(effect.get("id") or uuid5(UUID(action_id), f"effect:{len(effects)}")),
                    "kind": effect.get("kind"),
                    "property_id": prop,
                    "link_type_id": link,
                    "expression": str(effect.get("expression") or ""),
                }
            )
        preconditions = [
            _resolve_precondition(ref, known_rules, report.paths, label, action_id)
            for ref in entry.get("preconditions") or []
        ]
        if broken or None in preconditions:
            report.skip(f"actions.{label}", "Action 引用的属性、关系或前置规则没有导入")
            continue
        actions.append(
            {
                "id": action_id,
                "name": str(entry.get("name") or label),
                "technical_name": label,
                "description": str(entry.get("description") or ""),
                "input_type_id": input_type,
                "parameters": list(entry.get("parameters") or []),
                "precondition_rule_ids": preconditions,
                "effects": effects,
                "evidence": [],
            }
        )
        rules.extend(own_rules)
    return actions, rules


def _merge(
    base: OntologyDraft,
    imported: OntologyDraft,
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
        "mappings_added": 0,
    }
    workspace = base.workspace_id
    merged = base.model_copy(deep=True)
    remap: dict[UUID, UUID] = {}

    existing = {item.technical_name.casefold(): item for item in merged.object_types}
    names = {item.name.casefold() for item in merged.object_types}
    keys = set(existing)
    updated_types: set[UUID] = set()
    for incoming in imported.object_types:
        current = existing.get(incoming.technical_name.casefold())
        if current is None:
            incoming.name = _unique(incoming.name, names, "·")
            incoming.technical_name = _unique(incoming.technical_name, keys)
            merged.object_types.append(incoming)
            existing[incoming.technical_name.casefold()] = incoming
            remap[incoming.id] = incoming.id
            counts["objects_added"] += 1
            continue
        remap[incoming.id] = current.id
        updated_types.add(current.id)
        counts["objects_updated"] += 1
        if incoming.description:
            current.description = incoming.description
        current.tags = sorted({*current.tags, *incoming.tags})
    for incoming in imported.object_types:
        target = next(t for t in merged.object_types if t.id == remap[incoming.id])
        parents = [remap[p] for p in incoming.extends if p in remap]
        if target.id in updated_types and parents or target.id not in updated_types:
            target.extends = parents

    # Properties: by technical name inside their (remapped) owner.
    own = {
        (p.owner_type_id, p.technical_name.casefold()): p for p in merged.properties
    }
    for incoming in imported.properties:
        owner = remap[incoming.owner_type_id]
        found = own.get((owner, incoming.technical_name.casefold()))
        if found is None:
            incoming.owner_type_id = owner
            merged.properties.append(incoming)
            own[(owner, incoming.technical_name.casefold())] = incoming
            remap[incoming.id] = incoming.id
            counts["attributes_added"] += 1
            continue
        remap[incoming.id] = found.id
        for field in (
            "value_kind", "value_concept", "target_role_name", "multiplicity",
            "identifier", "required", "verbalizes",
        ):
            setattr(found, field, getattr(incoming, field))
        if incoming.description:
            found.description = incoming.description
        counts["attributes_updated"] += 1

    # Relationship names live inside their owning concept, so a file's link
    # updates that concept's link and never another concept's.
    link_index = {
        (link.owner_type_id, link.technical_name.casefold()): link
        for link in merged.link_types
    }
    updated_links: set[UUID] = set()
    for incoming in imported.link_types:
        incoming.source_type_id = remap[incoming.source_type_id]
        incoming.target_type_id = remap[incoming.target_type_id]
        current = link_index.get((incoming.owner_type_id, incoming.technical_name.casefold()))
        if current is None:
            owned = [
                item for key, item in link_index.items() if key[0] == incoming.owner_type_id
            ]
            incoming.name = _unique(incoming.name, {i.name.casefold() for i in owned}, "·")
            incoming.technical_name = _unique(
                incoming.technical_name, {i.technical_name.casefold() for i in owned}
            )
            merged.link_types.append(incoming)
            link_index[(incoming.owner_type_id, incoming.technical_name.casefold())] = incoming
            remap[incoming.id] = incoming.id
            counts["links_added"] += 1
            continue
        remap[incoming.id] = current.id
        updated_links.add(current.id)
        counts["links_updated"] += 1
        current.source_type_id, current.target_type_id = (
            incoming.source_type_id,
            incoming.target_type_id,
        )
        current.multiplicity = incoming.multiplicity
        current.target_role_name = incoming.target_role_name
        current.identifier = incoming.identifier
        current.verbalizes = incoming.verbalizes
        if incoming.description:
            current.description = incoming.description
        current.tags = sorted({*current.tags, *incoming.tags})

    # Rules follow v1 import semantics: a file restates the rules of every
    # property and link it carries; an object type's rules are replaced only
    # for a kind the file states. Same owner + kind + expression keeps its id.
    imported_rules: dict[tuple[UUID, str], list[RuleDefinition]] = {}
    for rule in imported.rules:
        if rule.owner_kind.value == "action":
            continue
        derived = legacy_rule_id(
            imported.workspace_id, rule.owner_kind.value, str(rule.owner_id),
            rule.rule_kind.value, rule.expression,
        )
        rule.owner_id = remap[rule.owner_id]
        if rule.id == derived:
            # No identity from the file: derive it from the owner it lands on.
            rule.id = legacy_rule_id(
                workspace, rule.owner_kind.value, str(rule.owner_id),
                rule.rule_kind.value, rule.expression,
            )
        imported_rules.setdefault((rule.owner_id, rule.rule_kind.value), []).append(rule)
    replaced: set[tuple[UUID, str]] = set(imported_rules)
    for element_id in {remap[p.id] for p in imported.properties} | {
        remap[link.id] for link in imported.link_types
    }:
        replaced |= {(element_id, "constraint"), (element_id, "derivation")}
    kept_rules = [r for r in merged.rules if (r.owner_id, r.rule_kind.value) not in replaced]
    previous = {
        (r.owner_id, r.rule_kind.value, r.expression): r
        for r in merged.rules
        if (r.owner_id, r.rule_kind.value) in replaced
    }
    rule_remap: dict[UUID, UUID] = {}
    for (owner_id, kind), rules in imported_rules.items():
        for rule in rules:
            old = previous.get((owner_id, kind, rule.expression))
            if old is not None:
                rule_remap[rule.id] = old.id
                rule.id, rule.name, rule.technical_name = old.id, old.name, old.technical_name
            kept_rules.append(rule)
    merged.rules = kept_rules

    # Actions: by technical name; the file's definition replaces the local one.
    actions = {a.technical_name.casefold(): a for a in merged.actions}
    for action in imported.actions:
        action.input_type_id = remap[action.input_type_id]
        # A precondition follows its rule when the rule kept its local id.
        action.precondition_rule_ids = [
            rule_remap.get(rule_id, rule_id) for rule_id in action.precondition_rule_ids
        ]
        for effect in action.effects:
            if effect.property_id:
                effect.property_id = remap[effect.property_id]
            if effect.link_type_id:
                effect.link_type_id = remap[effect.link_type_id]
        current = actions.get(action.technical_name.casefold())
        if current is not None:
            merged.rules = [
                r for r in merged.rules if not (r.owner_kind.value == "action" and r.owner_id == current.id)
            ]
            merged.actions = [a for a in merged.actions if a.id != current.id]
            old_id, action.id = action.id, current.id
        else:
            old_id = action.id
        for rule in imported.rules:
            if rule.owner_kind.value == "action" and rule.owner_id == old_id:
                rule.owner_id = action.id
                merged.rules.append(rule)
        merged.actions.append(action)

    # A workspace's own mapping points at tables it has already checked, so the
    # file only fills in objects that have none.
    mapped = {item.type_id for item in merged.mappings}
    for mapping in imported.mappings:
        type_id = remap.get(mapping.type_id)
        if type_id is None or type_id in mapped:
            continue
        mapping.type_id = type_id
        merged.mappings.append(mapping)
        mapped.add(type_id)
        counts["mappings_added"] += 1
    if counts["mappings_added"]:
        report.note(
            "数据映射按文件里的数据源名称导入；请在“数据映射”页确认这些名称已配置连接"
        )
    merged.ontology_requires = [
        *merged.ontology_requires,
        *[item for item in imported.ontology_requires if item not in merged.ontology_requires],
    ]
    # "Updated" means the content changed, judged the way the publish diff
    # judges it (canonical form: set order and empty fields do not count), not
    # that the name matched. A file imported twice reports nothing updated.
    for key, collection in (
        ("objects_updated", "object_types"),
        ("attributes_updated", "properties"),
        ("links_updated", "link_types"),
    ):
        before = {
            item.id: canonical(item.model_dump(mode="json")) for item in getattr(base, collection)
        }
        counts[key] = sum(
            1
            for item in getattr(merged, collection)
            if item.id in before and canonical(item.model_dump(mode="json")) != before[item.id]
        )
    return merged, counts


def import_ossie_v2(
    document: dict[str, Any],
    *,
    workspace_id: str,
    base: dict[str, Any] | None = None,
    mode: str = "merge",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the resulting v2 draft and a report of everything the import changed.

    `base` must already be a v2 snapshot (callers read it with read_snapshot).
    """
    version = document.get("version") if isinstance(document, dict) else None
    if version != OSSIE_VERSION:
        raise OssieImportError(
            f"OSSIE_VERSION_UNSUPPORTED: 仅支持 Apache Ossie {OSSIE_VERSION}，"
            f"文件版本为 {version!r}"
        )
    schema_issues = validate_schema(document)
    if schema_issues:
        raise OssieImportError(
            f"文件不符合 Apache Ossie {OSSIE_VERSION} 结构：" + schema_issues[0]["message"]
        )
    extension = _extension(document)
    context = document.get("ai_context")
    extension_present = isinstance(context, dict) and EXTENSION_KEY in context
    if extension_present and extension.get("version") not in READABLE_EXTENSION_VERSIONS:
        raise OssieImportError(
            "ONTOFOUNDRY_EXTENSION_VERSION_UNSUPPORTED: "
            f"仅支持 OntoFoundry 扩展版本 {'、'.join(READABLE_EXTENSION_VERSIONS)}，"
            f"文件版本为 {extension.get('version')!r}"
        )
    objects, links, mappings, requires, report = parse_ossie(
        document, workspace_id=workspace_id
    )
    if not objects:
        raise OssieImportError("文件里没有可导入的 EntityType 概念")
    imported = OntologyDraft.model_validate(
        _lift(workspace_id, objects, links, mappings, requires, extension, report)
    )

    base_draft = (
        OntologyDraft.model_validate(base)
        if base
        else OntologyDraft(workspace_id=UUID(str(workspace_id)))
    )
    if mode == "replace":
        counts = {
            "objects_added": len(imported.object_types),
            "objects_updated": 0,
            "links_added": len(imported.link_types),
            "links_updated": 0,
            "attributes_added": len(imported.properties),
            "attributes_updated": 0,
            "mappings_added": len(imported.mappings),
        }
        if base_draft.material_objects or base_draft.material_links:
            report.note(
                "替换模式：文档实例与实例关系不会保留，发布后当前模型将被文件内容整体替换"
            )
        elif base_draft.object_types:
            report.note("替换模式：文件之外的业务对象与关系会在发布时消失")
        if imported.mappings:
            report.note(
                "数据映射按文件里的数据源名称导入；请在“数据映射”页确认这些名称已配置连接"
            )
        draft = imported
    else:
        draft, counts = _merge(base_draft, imported, report)
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


def import_ossie(document, *, workspace_id, base=None, mode="merge", target_version="3"):
    """Native v3 import, enabled at the runtime cutover in M2."""
    if target_version == "2":
        return import_ossie_v2(document, workspace_id=workspace_id, base=base, mode=mode)
    if target_version != "3":
        raise OssieImportError("未知目标快照版本")
    from copy import deepcopy

    from ontofoundry_api.domain.canonical import V3_HASH_ALGORITHM
    from ontofoundry_api.domain.snapshot import as_v3_dict

    from .native import parse_native

    version = document.get("version") if isinstance(document, dict) else None
    if version != OSSIE_VERSION:
        raise OssieImportError(f"OSSIE_VERSION_UNSUPPORTED: 仅支持 Apache Ossie {OSSIE_VERSION}，文件版本为 {version!r}")
    issues = validate_schema(document)
    if issues:
        raise OssieImportError("文件不符合 Apache Ossie 结构：" + issues[0]["message"])
    for path, reason in unsupported_constructs(document):
        raise OssieImportError(f"{path}：不支持的 Ossie 构造：{reason}")
    try:
        imported = parse_native(document, workspace_id).model_dump(mode="json")
        existing = as_v3_dict(base, workspace_id)
        counts = dict(objects_added=0, objects_updated=0, links_added=0, links_updated=0,
                      attributes_added=0, attributes_updated=0, mappings_added=0, mappings_updated=0,
                      values_added=0, values_updated=0)
        remap = {}
        for collection, _prefix in (("object_types", "objects"), ("value_types", "values")):
            current = {i["concept"]: i for i in existing[collection]}
            for item in imported[collection]:
                old = current.get(item["concept"]) if mode != "replace" else None
                remap[item["id"]] = old["id"] if old else item["id"]
        for collection, _prefix in (("properties", "attributes"), ("link_types", "links")):
            current = {(i["owner_ref"]["ref"], i["technical_name"]): i for i in existing[collection]}
            for item in imported[collection]:
                old = current.get((remap.get(item["owner_ref"]["ref"], item["owner_ref"]["ref"]), item["technical_name"])) if mode != "replace" else None
                remap[item["id"]] = old["id"] if old else item["id"]
                if old:
                    for index, role in enumerate(item["roles"]):
                        if role["id"] not in {r["id"] for r in old["roles"]} and index < len(old["roles"]):
                            remap[role["id"]] = old["roles"][index]["id"]
        identifier_fields = {'id', 'owner_id', 'input_type_id', 'type_id', 'property_id', 'link_type_id', 'source_id', 'target_id',
                             'role_id', 'object_id', 'semantic_model_id', 'dataset_id', 'concept_mapping_id', 'parent_id', 'ref'}
        reference_lists = {'requires', 'derived_by', 'precondition_rule_ids'}
        def rewrite(value, field=None, depth=0):
            if field == 'ai_context':
                return deepcopy(value)  # native/vendor strings are never ID-rewritten
            if isinstance(value, dict):
                return {k: rewrite(v, k, depth + 1) for k, v in value.items()}
            if isinstance(value, list):
                return [rewrite(v, field, depth + 1) for v in value]
            return remap.get(value, value) if isinstance(value, str) and (field in identifier_fields or (field in reference_lists and depth > 1)) else value
        imported = rewrite(imported)
        imported['extension_v4']['concept_context'] = {remap.get(key, key): value for key, value in imported['extension_v4']['concept_context'].items()}
        if mode != "replace":
            previous_rules = {}
            for old in existing["rules"]:
                previous_rules.setdefault((old["owner_id"], old["rule_kind"], old["expression"]), []).append(old)
            rule_ids = {}
            for rule in imported["rules"]:
                matches = previous_rules.get((rule["owner_id"], rule["rule_kind"], rule["expression"]), [])
                if matches:
                    old = matches.pop(0)
                    rule_ids[rule["id"]] = old["id"]
                    for field in ("id", "name", "technical_name", "description"):
                        rule[field] = old[field]
            for collection in ("object_types", "value_types", "properties", "link_types"):
                for item in imported[collection]:
                    for field in ("requires", "derived_by"):
                        item[field] = [rule_ids.get(rid, rid) for rid in item[field]]
            for action in imported.get("actions", []):
                action["precondition_rule_ids"] = [rule_ids.get(rid, rid) for rid in action["precondition_rule_ids"]]
        draft = imported if mode == "replace" else deepcopy(existing)
        for collection, prefix in (("object_types", "objects"), ("value_types", "values"), ("properties", "attributes"), ("link_types", "links")):
            old = {i["id"]: i for i in existing[collection]}
            for item in imported[collection]:
                counts[prefix + ("_updated" if item["id"] in old else "_added")] += int(item["id"] not in old or canonical(old[item["id"]], hash_algorithm=V3_HASH_ALGORITHM) != canonical(item, hash_algorithm=V3_HASH_ALGORITHM))
            if mode != "replace":
                incoming_ids = {i["id"] for i in imported[collection]}
                kept = [i for i in draft[collection] if i["id"] not in incoming_ids]
                # Imported arrays retain positions; local-only elements follow.
                for i in kept:
                    i["position"] = None
                draft[collection] = imported[collection] + kept
        if mode != "replace":
            incoming_actions = {a["id"] for a in imported["actions"]}
            draft["actions"] = [a for a in draft["actions"] if a["id"] not in incoming_actions] + imported["actions"]
            owners = {i["id"] for c in ("object_types", "value_types", "properties", "link_types", "actions") for i in imported[c]}
            draft["rules"] = [r for r in draft["rules"] if r["owner_id"] not in owners] + imported["rules"]
            for key in ("semantic_models", "datasets", "dataset_fields", "dataset_relationships", "metrics", "concept_mappings", "mapping_nodes"):
                incoming = {i["id"] for i in imported[key]}
                draft[key] = [i for i in draft[key] if i["id"] not in incoming] + imported[key]
            for key in ("ossie_version", "ossie_name", "ossie_description", "ai_context", "native_presence", "document_origin", "ontology_requires"):
                draft[key] = imported[key]
        if mode != 'replace':
            from .extensions import extension_of
            source_extension = extension_of(document)
            if source_extension.get('version') == '4' and 'concept_context' in source_extension:
                for item in [*imported['object_types'], *imported['value_types']]:
                    draft['extension_v4']['concept_context'].pop(item['id'], None)
            draft['extension_v4']['concept_context'].update(imported['extension_v4']['concept_context'])
            draft['extension_v4']['legacy_mapping_ids'].update(imported['extension_v4']['legacy_mapping_ids'])
        previous = {i['id']: i for i in existing['concept_mappings']}
        counts['mappings_added'] = sum(i['id'] not in previous for i in imported['concept_mappings'])
        counts['mappings_updated'] = sum(i['id'] in previous and previous[i['id']] != i
                                        for i in imported['concept_mappings'])
        draft = OntologyDraft.model_validate(draft).model_dump(mode="json")
    except (ValueError, KeyError) as exc:
        raise OssieImportError(str(exc)) from exc
    from .extensions import extension_collisions
    from .native import compile_native
    collisions = extension_collisions(compile_native(OntologyDraft.model_validate(draft), '', ''))
    notes = ['已原生保留概念、角色、字段出现状态与数组顺序']
    if collisions:
        notes.append('平台扩展碰撞：' + '、'.join(collisions) + '；导出记录原值与平台新增内容，可逆恢复原文。')
    return draft, dict(name=document.get("name", ""), description=document.get("description", ""), mode=mode,
                       counts=counts, skipped=[], notes=notes)
