from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

TECHNICAL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_display_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError("名称不能为空")
    return normalized


def validate_technical_name(value: str) -> str:
    value = value.strip()
    if not TECHNICAL_NAME_RE.fullmatch(value):
        raise ValueError("技术名只能包含 ASCII 字母、数字和下划线，且不能以数字开头")
    return value


NonEmptyText = Annotated[str, Field(min_length=1, max_length=240)]
# Ossie expressions are ANSI SQL text. The platform stores and reference-checks
# them through the official lint; it never executes them.
Expression = Annotated[str, Field(min_length=1, max_length=480)]
Expressions = Annotated[list[Expression], Field(default_factory=list, max_length=20)]
Verbalizations = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=480)]],
    Field(default_factory=list, max_length=8),
]


class ValueKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


class Multiplicity(StrEnum):
    ONE_TO_ONE = "one_to_one"
    MANY_TO_ONE = "many_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"


class AttributeDefinition(BaseModel):
    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    value_kind: ValueKind = ValueKind.STRING
    required: bool = False
    identifier: bool = False
    # Name of the Ossie value concept this attribute points at. Empty means the
    # compiler decides: the built-in value type, or a generated one for an
    # identifier. Keeping the name means an imported concept — including one
    # shared by several attributes — is written back under its own name, so
    # verbalizations that mention it stay valid without being rewritten.
    value_concept: str | None = None
    # Compiles to a relationship, so it carries the same Ossie fields a
    # relationship does. Empty verbalizes means "generate the standard reading".
    requires: Expressions
    derived_by: Expressions
    verbalizes: Verbalizations

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)

    @field_validator("value_concept")
    @classmethod
    def check_value_concept(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 240:
            raise ValueError("值概念名称过长")
        return value


class ObjectTypeDefinition(BaseModel):
    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    # Ossie `extends`: supertypes of this concept. A child holds only what it
    # adds; inherited attributes and relationships are read through the chain.
    extends: list[UUID] = Field(default_factory=list, max_length=8)
    requires: Expressions
    derived_by: Expressions
    attributes: list[AttributeDefinition] = Field(default_factory=list)

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)

    @model_validator(mode="after")
    def ensure_unique_attributes(self) -> ObjectTypeDefinition:
        names = [normalize_display_name(item.name) for item in self.attributes]
        keys = [item.technical_name.casefold() for item in self.attributes]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.name} 中存在同名属性")
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.name} 中存在技术名冲突的属性")
        return self


class DataJoin(BaseModel):
    source_column: str = Field(min_length=1, max_length=240)
    target_column: str = Field(min_length=1, max_length=240)


class LinkTypeDefinition(BaseModel):
    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    source_type_id: UUID
    target_type_id: UUID
    multiplicity: Multiplicity = Multiplicity.MANY_TO_ONE
    source_role_name: str | None = None
    target_role_name: str | None = None
    # Referent identification: the object is identified through this relation,
    # e.g. an order line identified by its order plus a line number.
    identifier: bool = False
    requires: Expressions
    derived_by: Expressions
    verbalizes: Verbalizations
    tags: list[str] = Field(default_factory=list)
    data_join: DataJoin | None = None

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)

    @property
    def owner_type_id(self) -> UUID:
        """Concept the compiled relationship hangs under (its first role).

        Ossie has no OneToMany, so a one-to-many link is written from the many
        side; everything else is written from its source.
        """
        return (
            self.target_type_id
            if self.multiplicity == Multiplicity.ONE_TO_MANY
            else self.source_type_id
        )

    @model_validator(mode="after")
    def ensure_identifier_is_functional(self) -> LinkTypeDefinition:
        if self.identifier and self.multiplicity not in (
            Multiplicity.MANY_TO_ONE,
            Multiplicity.ONE_TO_ONE,
        ):
            raise ValueError(
                f"{self.name}：作为标识的关系必须是多对一或一对一，"
                "否则无法唯一确定被标识的对象"
            )
        return self


class OntologyDraft(BaseModel):
    schema_version: str = "1"
    workspace_id: UUID
    # Ossie ontology-level `requires`: constraints over the whole population.
    requires: Expressions
    object_types: list[ObjectTypeDefinition] = Field(default_factory=list)
    link_types: list[LinkTypeDefinition] = Field(default_factory=list)
    objects: list[DocumentObject] = Field(default_factory=list)
    links: list[DocumentLink] = Field(default_factory=list)
    mappings: list[DataMapping] = Field(default_factory=list)

    def ancestors(self, type_id: UUID) -> list[ObjectTypeDefinition]:
        """Supertypes closest first, without repeats or infinite loops.

        A type reachable from itself is returned too, so a cycle is visible to
        the validator instead of being silently skipped.
        """
        by_id = {item.id: item for item in self.object_types}
        ordered: list[ObjectTypeDefinition] = []
        seen: set[UUID] = set()
        frontier = list(by_id[type_id].extends) if type_id in by_id else []
        while frontier:
            parent_id = frontier.pop(0)
            if parent_id in seen or parent_id not in by_id:
                continue
            seen.add(parent_id)
            parent = by_id[parent_id]
            ordered.append(parent)
            frontier.extend(parent.extends)
        return ordered

    def effective_attributes(self, type_id: UUID) -> list[AttributeDefinition]:
        """Own attributes plus everything inherited through `extends`."""
        by_id = {item.id: item for item in self.object_types}
        if type_id not in by_id:
            return []
        items = list(by_id[type_id].attributes)
        for parent in self.ancestors(type_id):
            items.extend(parent.attributes)
        return items

    def descendants(self, type_id: UUID) -> set[UUID]:
        """The type itself and every type that extends it, directly or not."""
        found = {type_id}
        changed = True
        while changed:
            changed = False
            for item in self.object_types:
                if item.id in found:
                    continue
                if found & set(item.extends):
                    found.add(item.id)
                    changed = True
        return found

    @model_validator(mode="after")
    def validate_graph(self) -> OntologyDraft:
        object_ids = {item.id for item in self.object_types}
        ids = [
            item.id
            for item in [
                *self.object_types,
                *self.link_types,
                *self.objects,
                *self.links,
                *self.mappings,
            ]
        ]
        ids += [a.id for t in self.object_types for a in t.attributes]
        if len(ids) != len(set(ids)):
            raise ValueError("模型项标识重复")
        object_names = [normalize_display_name(item.name) for item in self.object_types]
        object_keys = [item.technical_name.casefold() for item in self.object_types]

        if len(object_names) != len(set(object_names)):
            raise ValueError("工作空间中存在同名业务对象")
        if len(object_keys) != len(set(object_keys)):
            raise ValueError("工作空间中存在技术名冲突的业务对象")

        missing = {
            endpoint
            for item in self.link_types
            for endpoint in (item.source_type_id, item.target_type_id)
            if endpoint not in object_ids
        }
        if missing:
            raise ValueError("本体关系引用了不存在的业务对象")
        for item in self.object_types:
            for parent_id in item.extends:
                if parent_id not in object_ids:
                    raise ValueError(f"{item.name} 继承了不存在的业务对象")
                if parent_id == item.id:
                    raise ValueError(f"{item.name} 不能继承自己")
            if item.id in {parent.id for parent in self.ancestors(item.id)}:
                raise ValueError(f"{item.name} 的继承关系形成了循环")

        # Ossie keeps one relationship namespace per concept, shared by
        # attributes and relations, and inherited by subtypes.
        for item in self.object_types:
            owned = [
                link
                for link in self.link_types
                if link.owner_type_id == item.id
                or link.owner_type_id in {p.id for p in self.ancestors(item.id)}
            ]
            names = [
                normalize_display_name(entry.name)
                for entry in [*self.effective_attributes(item.id), *owned]
            ]
            keys = [
                entry.technical_name.casefold()
                for entry in [*self.effective_attributes(item.id), *owned]
            ]
            if len(names) != len(set(names)):
                raise ValueError(f"{item.name} 的属性与关系中存在同名项（含继承）")
            if len(keys) != len(set(keys)):
                raise ValueError(f"{item.name} 的属性与关系中存在技术名冲突（含继承）")

        # A named value concept is one concept in the exported document, so every
        # attribute pointing at it must agree on the base type, and the name may
        # not collide with a business object.
        kinds_by_concept: dict[str, ValueKind] = {}
        for item in self.object_types:
            for attribute in item.attributes:
                concept = attribute.value_concept
                if not concept:
                    continue
                if concept.casefold() in {
                    entry.technical_name.casefold() for entry in self.object_types
                }:
                    raise ValueError(f"值概念 {concept} 与业务对象的技术名冲突")
                known = kinds_by_concept.setdefault(concept, attribute.value_kind)
                if known != attribute.value_kind:
                    raise ValueError(f"值概念 {concept} 被用于两种不同的值类型")

        instances = {o.id: o for o in self.objects}
        relations = {r.id: r for r in self.link_types}
        for item in self.objects:
            if item.type_id not in object_ids:
                raise ValueError("文档实例必须绑定已存在的业务对象类型")
            keys = {a.technical_name for a in self.effective_attributes(item.type_id)}
            if set(item.values) - keys:
                raise ValueError("实例含未定义的属性")
        for item in self.links:
            relation = relations.get(item.type_id)
            source, target = instances.get(item.source_id), instances.get(item.target_id)
            if not relation or not source or not target:
                raise ValueError("实例关系引用无效")
            # A subtype object is usable wherever its supertype is expected.
            if source.type_id not in self.descendants(
                relation.source_type_id
            ) or target.type_id not in self.descendants(relation.target_type_id):
                raise ValueError("实例关系端点类型不匹配")
        mapped_ids = [m.type_id for m in self.mappings]
        if len(mapped_ids) != len(set(mapped_ids)):
            raise ValueError("每个业务对象只允许一个数据映射")
        for mapping in self.mappings:
            if mapping.type_id not in object_ids:
                raise ValueError("映射引用了不存在的业务对象")
            attrs = {a.technical_name for a in self.effective_attributes(mapping.type_id)}
            if set(mapping.fields) - attrs:
                raise ValueError("映射引用了未定义的属性")
            if "__key" in mapping.fields:
                raise ValueError("__key 是实例查询的保留字段名")
        for relation in self.link_types:
            if relation.data_join and not {
                relation.source_type_id,
                relation.target_type_id,
            } <= set(mapped_ids):
                raise ValueError("配置关系映射前，请先配置两端业务对象的数据映射")
        return self


class Evidence(BaseModel):
    material_id: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    quote: str = ""


class DocumentObject(BaseModel):
    id: UUID
    type_id: UUID
    name: NonEmptyText
    values: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)


class DocumentLink(BaseModel):
    id: UUID
    type_id: UUID
    source_id: UUID
    target_id: UUID
    evidence: list[Evidence] = Field(default_factory=list)


class DataMapping(BaseModel):
    """Where an object type's data sits, not which connection reads it.

    The model names a data source (`connection_alias`) plus the table, key column
    and field columns. Which credentials serve that alias is workspace
    configuration, resolved at query time, so a published version carries no
    connection identifiers or secrets and stays portable between environments.
    """

    id: UUID
    type_id: UUID
    connection_alias: str = Field(min_length=1, max_length=120)
    table_name: str = Field(min_length=1, max_length=240)
    schema_name: str | None = None
    key_column: str = Field(min_length=1, max_length=240)
    fields: dict[str, str] = Field(default_factory=dict)


OntologyDraft.model_rebuild()


class PublishRequest(BaseModel):
    message: str = Field(default="", max_length=240)
    draft: OntologyDraft


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9-]*$")
    description: str = Field(default="", max_length=1200)

    _normalize_name = field_validator("name")(normalize_display_name)
