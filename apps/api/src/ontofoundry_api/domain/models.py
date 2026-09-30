"""Ontology draft, schema v2: every ontology element is a top-level item with a
stable id.

Object Types, Properties, Link Types, Rules, Actions, Material Objects/Links and
Mappings each live in their own top-level collection and are addressed only by
id, so proposals, diffs and three-way merges never depend on array positions.
Ownership is a reference (`owner_type_id`, `owner_kind`/`owner_id`), not nesting.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

TECHNICAL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Action effect expressions name their parameters as `:technical_name`;
# `::type` casts and text inside '...' literals are not parameters.
PARAMETER_RE = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")
SQL_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def expression_parameters(expression: str) -> set[str]:
    return set(PARAMETER_RE.findall(SQL_LITERAL_RE.sub("''", expression)))


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


class ElementKind(StrEnum):
    """Everything a proposal may create, update or delete."""

    OBJECT_TYPE = "object_type"
    PROPERTY = "property"
    LINK_TYPE = "link_type"
    RULE = "rule"
    ACTION = "action"
    MATERIAL_OBJECT = "material_object"
    MATERIAL_LINK = "material_link"
    MAPPING = "mapping"


# Draft collection that stores each element kind.
COLLECTIONS: dict[ElementKind, str] = {
    ElementKind.OBJECT_TYPE: "object_types",
    ElementKind.PROPERTY: "properties",
    ElementKind.LINK_TYPE: "link_types",
    ElementKind.RULE: "rules",
    ElementKind.ACTION: "actions",
    ElementKind.MATERIAL_OBJECT: "material_objects",
    ElementKind.MATERIAL_LINK: "material_links",
    ElementKind.MAPPING: "mappings",
}


# --- evidence ---------------------------------------------------------------


class EvidenceLocator(BaseModel):
    heading: str | None = Field(default=None, max_length=240)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> EvidenceLocator:
        if self.line_end < self.line_start:
            raise ValueError("证据的结束行不能早于起始行")
        return self


class MaterialEvidence(BaseModel):
    kind: Literal["material"] = "material"
    id: UUID
    material_id: str = Field(min_length=1, max_length=64)
    # Required for new evidence (checked when a proposal is accepted or a draft
    # saved). Evidence normalized from a v1 snapshot predates the field.
    material_sha256: str | None = None
    locator: EvidenceLocator
    quote: str = Field(default="", max_length=2000)

    @field_validator("material_sha256")
    @classmethod
    def check_sha(cls, value: str | None) -> str | None:
        if value is not None and not SHA256_RE.fullmatch(value):
            raise ValueError("material_sha256 必须是 64 位小写十六进制")
        return value


class ManualEvidence(BaseModel):
    """A member vouching for a fact. Author and time are written by the server."""

    kind: Literal["manual"] = "manual"
    id: UUID
    note: str = Field(default="", max_length=2000)
    created_by: str = Field(min_length=1, max_length=64)
    created_at: datetime


Evidence = Annotated[MaterialEvidence | ManualEvidence, Field(discriminator="kind")]
EvidenceList = Annotated[list[Evidence], Field(default_factory=list, max_length=50)]


# --- definitions ------------------------------------------------------------


class ObjectTypeDefinition(BaseModel):
    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    # Ossie `extends`: supertypes. A child holds only what it adds; inherited
    # properties and relationships are read through the chain.
    extends: list[UUID] = Field(default_factory=list, max_length=8)
    evidence: EvidenceList

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)


class PropertyDefinition(BaseModel):
    id: UUID
    owner_type_id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    value_kind: ValueKind = ValueKind.STRING
    required: bool = False
    identifier: bool = False
    # Name of the Ossie value concept this property points at. Empty means the
    # compiler decides: the built-in value type, or a generated one for an
    # identifier. Keeping the name means an imported concept — including one
    # shared by several properties — is written back under its own name.
    value_concept: str | None = None
    # Ossie readings address a named value role as {concept:role}.
    target_role_name: str | None = Field(default=None, max_length=240)
    # Keep a file's stated cardinality; None lets the compiler infer it.
    multiplicity: Multiplicity | None = None
    # Empty verbalizes means "generate the standard reading".
    verbalizes: Verbalizations
    evidence: EvidenceList

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

    @field_validator("multiplicity")
    @classmethod
    def check_value_multiplicity(cls, value: Multiplicity | None) -> Multiplicity | None:
        if value not in (None, Multiplicity.ONE_TO_ONE, Multiplicity.MANY_TO_ONE):
            raise ValueError("属性的基数只能是一对一或多对一")
        return value


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
    verbalizes: Verbalizations
    tags: list[str] = Field(default_factory=list)
    data_join: DataJoin | None = None
    evidence: EvidenceList

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


class RuleKind(StrEnum):
    CONSTRAINT = "constraint"  # compiles to Ossie `requires`
    DERIVATION = "derivation"  # compiles to Ossie `derived_by`


class RuleOwnerKind(StrEnum):
    # No workspace-level owner: a rule always belongs to a concrete element.
    OBJECT_TYPE = "object_type"
    PROPERTY = "property"
    LINK_TYPE = "link_type"
    ACTION = "action"


class RuleDefinition(BaseModel):
    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    owner_kind: RuleOwnerKind
    owner_id: UUID
    rule_kind: RuleKind
    expression: Expression
    verbalizes: Verbalizations
    evidence: EvidenceList

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)


class ActionParameter(BaseModel):
    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    value_kind: ValueKind = ValueKind.STRING
    required: bool = False

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)


class ActionEffectKind(StrEnum):
    SET_PROPERTY = "set_property"
    CREATE_LINK = "create_link"
    DELETE_LINK = "delete_link"


class ActionEffect(BaseModel):
    """What an action would change. A definition only: nothing executes it.

    `expression` is ANSI SQL text over the action's parameters (`:param`) and the
    input object's properties, stored and displayed like any Ossie expression.
    """

    id: UUID
    kind: ActionEffectKind
    property_id: UUID | None = None
    link_type_id: UUID | None = None
    expression: str = Field(default="", max_length=480)

    @model_validator(mode="after")
    def target_matches_kind(self) -> ActionEffect:
        if self.kind == ActionEffectKind.SET_PROPERTY:
            if self.property_id is None or self.link_type_id is not None:
                raise ValueError("set_property 效果必须且只能指定 property_id")
        elif self.link_type_id is None or self.property_id is not None:
            raise ValueError(f"{self.kind.value} 效果必须且只能指定 link_type_id")
        return self


class ActionDefinition(BaseModel):
    """An action contract. Only modeled and versioned; there is no executor."""

    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    input_type_id: UUID
    parameters: list[ActionParameter] = Field(default_factory=list, max_length=40)
    precondition_rule_ids: list[UUID] = Field(default_factory=list, max_length=40)
    effects: list[ActionEffect] = Field(default_factory=list, max_length=40)
    evidence: EvidenceList

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)

    @model_validator(mode="after")
    def unique_parameters(self) -> ActionDefinition:
        keys = [p.technical_name.casefold() for p in self.parameters]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.name} 的参数技术名重复")
        declared = {p.technical_name for p in self.parameters}
        for effect in self.effects:
            unknown = expression_parameters(effect.expression) - declared
            if unknown:
                raise ValueError(
                    f"{self.name} 的效果表达式引用了未声明的参数：{'、'.join(sorted(unknown))}"
                )
        return self


# --- instances and mappings -------------------------------------------------


class MaterialObject(BaseModel):
    id: UUID
    type_id: UUID
    name: NonEmptyText
    values: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence: EvidenceList


class MaterialLink(BaseModel):
    id: UUID
    type_id: UUID
    source_id: UUID
    target_id: UUID
    evidence: EvidenceList


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


# --- the draft ----------------------------------------------------------------


class OntologyDraft(BaseModel):
    schema_version: Literal["2"] = "2"
    workspace_id: UUID
    # Ossie ontology-level `requires` carried over from v1 and imported files.
    # Not a Rule element: rules must belong to a concrete element, so these stay
    # a plain field that merges atomically and is not a proposal target.
    ontology_requires: Expressions
    object_types: list[ObjectTypeDefinition] = Field(default_factory=list)
    properties: list[PropertyDefinition] = Field(default_factory=list)
    link_types: list[LinkTypeDefinition] = Field(default_factory=list)
    rules: list[RuleDefinition] = Field(default_factory=list)
    actions: list[ActionDefinition] = Field(default_factory=list)
    material_objects: list[MaterialObject] = Field(default_factory=list)
    material_links: list[MaterialLink] = Field(default_factory=list)
    mappings: list[DataMapping] = Field(default_factory=list)

    # -- lookups ---------------------------------------------------------------

    def type_by_id(self) -> dict[UUID, ObjectTypeDefinition]:
        return {item.id: item for item in self.object_types}

    def properties_of(self, type_id: UUID) -> list[PropertyDefinition]:
        """Own properties of a type, in draft order."""
        return [p for p in self.properties if p.owner_type_id == type_id]

    def rules_of(self, owner_id: UUID, kind: RuleKind | None = None) -> list[RuleDefinition]:
        return [
            r
            for r in self.rules
            if r.owner_id == owner_id and (kind is None or r.rule_kind == kind)
        ]

    def expressions_of(self, owner_id: UUID, kind: RuleKind) -> list[str]:
        return [r.expression for r in self.rules_of(owner_id, kind)]

    def ancestors(self, type_id: UUID) -> list[ObjectTypeDefinition]:
        """Supertypes closest first, without repeats or infinite loops.

        A type reachable from itself is returned too, so a cycle is visible to
        the validator instead of being silently skipped.
        """
        by_id = self.type_by_id()
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

    def effective_properties(self, type_id: UUID) -> list[PropertyDefinition]:
        """Own properties plus everything inherited through `extends`."""
        if type_id not in self.type_by_id():
            return []
        items = self.properties_of(type_id)
        for parent in self.ancestors(type_id):
            items.extend(self.properties_of(parent.id))
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

    def element_kind_of(self) -> dict[UUID, ElementKind]:
        return {
            item.id: kind
            for kind, collection in COLLECTIONS.items()
            for item in getattr(self, collection)
        }

    # -- invariants ------------------------------------------------------------

    @model_validator(mode="after")
    def validate_graph(self) -> OntologyDraft:
        kinds = self.element_kind_of()
        total = sum(len(getattr(self, c)) for c in COLLECTIONS.values())
        if total != len(kinds):
            raise ValueError("模型项标识重复")
        object_ids = {item.id for item in self.object_types}

        object_names = [normalize_display_name(item.name) for item in self.object_types]
        object_keys = [item.technical_name.casefold() for item in self.object_types]
        if len(object_names) != len(set(object_names)):
            raise ValueError("工作空间中存在同名业务对象")
        if len(object_keys) != len(set(object_keys)):
            raise ValueError("工作空间中存在技术名冲突的业务对象")

        for prop in self.properties:
            if prop.owner_type_id not in object_ids:
                raise ValueError(f"属性 {prop.name} 归属的业务对象不存在")
        for item in self.object_types:
            own = self.properties_of(item.id)
            if len({normalize_display_name(p.name) for p in own}) != len(own):
                raise ValueError(f"{item.name} 中存在同名属性")
            if len({p.technical_name.casefold() for p in own}) != len(own):
                raise ValueError(f"{item.name} 中存在技术名冲突的属性")

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
        # properties and relations, and inherited by subtypes.
        for item in self.object_types:
            lineage = {item.id} | {p.id for p in self.ancestors(item.id)}
            owned = [link for link in self.link_types if link.owner_type_id in lineage]
            entries = [*self.effective_properties(item.id), *owned]
            if len({normalize_display_name(e.name) for e in entries}) != len(entries):
                raise ValueError(f"{item.name} 的属性与关系中存在同名项（含继承）")
            if len({e.technical_name.casefold() for e in entries}) != len(entries):
                raise ValueError(f"{item.name} 的属性与关系中存在技术名冲突（含继承）")

        # A named value concept is one concept in the exported document, so every
        # property pointing at it must agree on the base type, and the name may
        # not collide with a business object.
        kinds_by_concept: dict[str, ValueKind] = {}
        for prop in self.properties:
            concept = prop.value_concept
            if not concept:
                continue
            if concept.casefold() in set(object_keys):
                raise ValueError(f"值概念 {concept} 与业务对象的技术名冲突")
            known = kinds_by_concept.setdefault(concept, prop.value_kind)
            if known != prop.value_kind:
                raise ValueError(f"值概念 {concept} 被用于两种不同的值类型")

        owner_collections = {
            RuleOwnerKind.OBJECT_TYPE: ElementKind.OBJECT_TYPE,
            RuleOwnerKind.PROPERTY: ElementKind.PROPERTY,
            RuleOwnerKind.LINK_TYPE: ElementKind.LINK_TYPE,
            RuleOwnerKind.ACTION: ElementKind.ACTION,
        }
        rule_keys: set[tuple[UUID, str]] = set()
        for rule in self.rules:
            if kinds.get(rule.owner_id) != owner_collections[rule.owner_kind]:
                raise ValueError(f"规则 {rule.name} 的归属元素不存在或类型不符")
            key = (rule.owner_id, rule.technical_name.casefold())
            if key in rule_keys:
                raise ValueError(f"规则 {rule.name} 与同一归属下的规则技术名冲突")
            rule_keys.add(key)

        action_keys = [a.technical_name.casefold() for a in self.actions]
        if len(action_keys) != len(set(action_keys)):
            raise ValueError("工作空间中存在技术名冲突的 Action")
        link_ids = {link.id for link in self.link_types}
        for action in self.actions:
            if action.input_type_id not in object_ids:
                raise ValueError(f"Action {action.name} 的输入对象类型不存在")
            for rule_id in action.precondition_rule_ids:
                if kinds.get(rule_id) != ElementKind.RULE:
                    raise ValueError(f"Action {action.name} 引用了不存在的前置规则")
            usable = {p.id for p in self.effective_properties(action.input_type_id)}
            for effect in action.effects:
                if effect.property_id is not None and effect.property_id not in usable:
                    raise ValueError(f"Action {action.name} 的效果引用了输入对象上不存在的属性")
                if effect.link_type_id is not None and effect.link_type_id not in link_ids:
                    raise ValueError(f"Action {action.name} 的效果引用了不存在的关系")

        instances = {o.id: o for o in self.material_objects}
        relations = {r.id: r for r in self.link_types}
        for obj in self.material_objects:
            if obj.type_id not in object_ids:
                raise ValueError("材料实例必须绑定已存在的业务对象类型")
            keys = {p.technical_name for p in self.effective_properties(obj.type_id)}
            if set(obj.values) - keys:
                raise ValueError("实例含未定义的属性")
        for link in self.material_links:
            relation = relations.get(link.type_id)
            source, target = instances.get(link.source_id), instances.get(link.target_id)
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
            attrs = {p.technical_name for p in self.effective_properties(mapping.type_id)}
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


class PublishRequest(BaseModel):
    message: str = Field(default="", max_length=240)
    draft: OntologyDraft


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9-]*$")
    description: str = Field(default="", max_length=1200)

    _normalize_name = field_validator("name")(normalize_display_name)
