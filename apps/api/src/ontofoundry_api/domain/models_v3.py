"""Frozen v3 element contracts. The sole draft model lives in models.py.

Native strings are never normalized. ``native_presence`` lists the original
JSON object's keys (including containers flattened into collections); absence
from this list means absent, even if a stored convenience default exists.
``position`` is the zero-based index in the original parent/slot array.
Nested native JSON uses its own keys, nulls and array indices without metadata.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_serializer,
    model_validator,
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Native(Contract):
    native_presence: list[str] = Field(default_factory=list)
    position: int | None = Field(default=None, ge=0)
    origin: Literal["platform", "imported", "migrated"] = "platform"

    @model_validator(mode="after")
    def unique_presence(self):
        if len(set(self.native_presence)) != len(self.native_presence):
            raise ValueError("native_presence 字段重复")
        if self.origin == "imported" and self.position is None:
            raise ValueError("导入的原生节点必须记录 position")
        return self


class ClientRef(Contract):
    client_ref: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


class ConceptRef(Contract):
    kind: Literal["object_type", "value_type", "builtin", "any"]
    ref: UUID | str | ClientRef

    @model_validator(mode="after")
    def reference_type(self):
        if isinstance(self.ref, ClientRef):
            if self.kind not in ("object_type", "value_type"):
                raise ValueError("内置概念不能使用 client_ref")
            return self
        if self.kind in ("object_type", "value_type"):
            self.ref = UUID(str(self.ref))
        elif self.kind == "any" and self.ref != "Any":
            raise ValueError("any 引用只能是 Any")
        elif self.kind == "builtin" and self.ref not in {
            "String", "Integer", "Decimal", "Float", "Boolean", "Date", "DateTime",
        }:
            raise ValueError("未知 Ossie 内置值概念")
        return self


class RoleRef(Native):
    id: UUID
    name: str | None = None
    concept: ConceptRef
    # Proposal resolution removes client_ref before persisting a draft.
    client_ref: str | None = None


class ConceptDefinition(Native):
    id: UUID
    concept: str
    description: str | None = None
    extends: list[ConceptRef] = Field(default_factory=list)
    identify_by: list[str] = Field(default_factory=list)
    # Expressions are stored only as Rule elements, addressed in source order.
    requires: list[UUID] = Field(default_factory=list)
    derived_by: list[UUID] = Field(default_factory=list)
    name: str = ""
    technical_name: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence: list[JsonValue] = Field(default_factory=list)


class ObjectTypeV3(ConceptDefinition):
    pass


class ValueTypeDefinition(ConceptDefinition):
    pass


class LinkTypeV3(Native):
    id: UUID
    name: str
    technical_name: str = ""
    description: str | None = None
    owner_ref: ConceptRef
    roles: list[RoleRef] = Field(default_factory=list)
    multiplicity: Literal["ManyToOne", "OneToOne"] | None = None
    verbalizes: list[str] = Field(default_factory=list)
    requires: list[UUID] = Field(default_factory=list)
    derived_by: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    evidence: list[JsonValue] = Field(default_factory=list)
    # Direction of the v2 endpoint view, never a rewrite of the native roles.
    endpoint_direction: Literal["forward", "reverse"] = "forward"
    identifier: bool = False
    owner_role_name: str | None = None
    legacy_multiplicity: Literal["one_to_one", "many_to_one", "one_to_many", "many_to_many"] | None = None

    @property
    def owner_type_id(self) -> UUID:
        return self.owner_ref.ref

    @property
    def owner_role_id(self) -> UUID:
        return uuid5(self.id, "role:owner")

    @property
    def source_type_id(self) -> UUID | None:
        if len(self.roles) != 1 or self.owner_ref.kind != "object_type" or self.roles[0].concept.kind != "object_type":
            return None
        return self.owner_ref.ref if self.endpoint_direction == "forward" else self.roles[0].concept.ref

    @property
    def target_type_id(self) -> UUID | None:
        if self.source_type_id is None:
            return None
        return self.roles[0].concept.ref if self.endpoint_direction == "forward" else self.owner_ref.ref

    @property
    def target_role_name(self) -> str | None:
        if self.source_type_id is None:
            return None
        return self.roles[0].name if self.endpoint_direction == "forward" else self.owner_role_name

    @property
    def source_role_name(self) -> str | None:
        if self.source_type_id is None:
            return None
        return self.owner_role_name if self.endpoint_direction == "forward" else self.roles[0].name

    @model_validator(mode="after")
    def unique_roles(self):
        ids = [r.id for r in self.roles]
        if len(set(ids)) != len(ids) or self.owner_role_id in ids:
            raise ValueError("关系角色 id 重复")
        return self


class PropertyV3(LinkTypeV3):
    @property
    def value_concept(self):
        role = self.roles[0]
        return role.concept.ref if role.concept.kind == "builtin" else None

    @property
    def target_role_name(self):
        return self.roles[0].name

    required: bool = False
    value_kind: str = "string"

    @model_validator(mode="after")
    def value_role(self):
        if len(self.roles) != 1 or self.roles[0].concept.kind not in ("value_type", "builtin"):
            raise ValueError("属性必须且只能引用一个值概念角色")
        return self


class RuleV3(Native):
    id: UUID
    owner_kind: Literal["object_type", "value_type", "property", "link_type", "action"]
    owner_id: UUID
    rule_kind: Literal["constraint", "derivation"]
    expression: str
    name: str = ""
    technical_name: str = ""
    description: str = ""
    verbalizes: list[str] = Field(default_factory=list)
    evidence: list[JsonValue] = Field(default_factory=list)


class RoleValue(Contract):
    role_id: UUID
    object_id: UUID | None = None
    value: JsonValue = None

    @model_validator(mode="after")
    def one_value(self):
        if self.object_id is not None and self.value is not None:
            raise ValueError("角色值不能同时指定 object_id 与 value")
        return self


class MaterialLinkV3(Contract):
    id: UUID
    type_id: UUID
    source_id: UUID | None = None
    target_id: UUID | None = None
    role_values: list[RoleValue]
    evidence: list[JsonValue] = Field(default_factory=list)


AIContext = str | dict[str, JsonValue] | None
Datatype = Literal["String", "Integer", "Decimal", "Float", "Boolean", "Date", "Time", "DateTime", "DateTimeTz", "Opaque"]


class CustomExtension(Contract):
    vendor_name: str
    # Keep the JSON string as text, including whitespace and vendor duplicates.
    data: str


class DialectExpression(Contract):
    dialect: Literal["ANSI_SQL", "SNOWFLAKE", "MDX", "TABLEAU", "DATABRICKS", "MAQL", "BIGQUERY"]
    expression: str


class SemanticExpression(Contract):
    dialects: list[DialectExpression] = Field(min_length=1)


class Dimension(Contract):
    is_time: bool | None = None

    @model_serializer
    def preserve_presence(self):
        return {"is_time": self.is_time} if "is_time" in self.model_fields_set else {}


class SemanticNode(Native):
    id: UUID
    name: str
    description: str | None = None
    ai_context: AIContext = None
    custom_extensions: list[CustomExtension] = Field(default_factory=list)


class SemanticModel(SemanticNode):
    map_name: str | None = None
    map_description: str | None = None
    # The enclosing OntologyMap and SemanticModel have distinct key sets.
    map_presence: list[str] = Field(default_factory=list)
    concept_mappings_position: int | None = Field(default=None, ge=0)


class Dataset(SemanticNode):
    semantic_model_id: UUID
    source: str
    primary_key: list[str] = Field(default_factory=list)
    unique_keys: list[list[str]] = Field(default_factory=list)


class DatasetField(SemanticNode):
    dataset_id: UUID
    expression: SemanticExpression
    dimension: Dimension | None = None
    label: str | None = None
    datatype: Datatype | None = None


class DatasetRelationship(Native):
    id: UUID
    semantic_model_id: UUID
    name: str
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    from_columns: list[str] = Field(min_length=1)
    to_columns: list[str] = Field(min_length=1)
    ai_context: AIContext = None
    custom_extensions: list[CustomExtension] = Field(default_factory=list)

    @model_validator(mode="after")
    def paired_columns(self):
        if len(self.from_columns) != len(self.to_columns):
            raise ValueError("连接列的数量不一致")
        return self


class Metric(SemanticNode):
    semantic_model_id: UUID
    expression: SemanticExpression
    datatype: Datatype | None = None


class ConceptMapping(Native):
    id: UUID
    semantic_model_id: UUID
    concept_id: ConceptRef


class MappingNode(Native):
    id: UUID
    concept_mapping_id: UUID
    parent_id: UUID | None = None
    slot: Literal["object_mappings", "link_mappings", "object_mapping", "children", "referent_mappings"]
    kind: Literal["object", "link", "referent"]
    relationship: str | None = None
    concept: ConceptRef | None = None
    expression: str | None = None

    @model_validator(mode="after")
    def node_shape(self):
        expected = {"object_mappings": "object", "link_mappings": "link", "object_mapping": "object", "children": "link", "referent_mappings": "referent"}
        if self.kind != expected[self.slot]:
            raise ValueError("mapping_nodes.slot 与 kind 不匹配")
        if self.kind == "referent" and self.relationship is None:
            raise ValueError("referent 节点必须有 relationship")
        if self.kind == "link" and (self.concept is not None or self.expression is not None):
            raise ValueError("link 的 concept/expression 属于 object 子节点")
        if self.kind == "object" and self.relationship is not None:
            raise ValueError("object 节点不能有 relationship")
        if self.kind == "referent" and self.concept is not None:
            raise ValueError("referent 节点不能有 concept")
        return self


class ConceptContext(Contract):
    synonyms: list[str] = Field(default_factory=list)
    instructions: str | None = None


class ExtensionEdit(Contract):
    """Only undo a recorded export edit if the current value is its written value."""
    path: str  # RFC 6901 pointer
    was_present: bool
    original: JsonValue
    written: JsonValue


class PlatformExtensionV4(Contract):
    version: Literal["4"] = "4"
    ids: dict[str, UUID] = Field(default_factory=dict)
    concept_context: dict[UUID, ConceptContext] = Field(default_factory=dict)
    display_names: dict[UUID, str] = Field(default_factory=dict)
    tags: dict[UUID, list[str]] = Field(default_factory=dict)
    required_properties: list[UUID] = Field(default_factory=list)
    rule_metadata: dict[UUID, dict[str, JsonValue]] = Field(default_factory=dict)
    actions: list[dict[str, JsonValue]] = Field(default_factory=list)
    # Original extension text remains in ai_context/custom_extensions; these
    # are only edits contributed by this export, including container creation.
    export_edits: list[ExtensionEdit] = Field(default_factory=list)
    # Provenance only; mapping IDs are retired, never reused for a new kind.
    legacy_mapping_ids: dict[UUID, UUID] = Field(default_factory=dict)


V3_COLLECTION_MODELS = {
    "object_types": ObjectTypeV3, "value_types": ValueTypeDefinition,
    "properties": PropertyV3, "link_types": LinkTypeV3, "rules": RuleV3,
    "material_links": MaterialLinkV3, "semantic_models": SemanticModel,
    "datasets": Dataset, "dataset_fields": DatasetField,
    "dataset_relationships": DatasetRelationship, "metrics": Metric,
    "concept_mappings": ConceptMapping, "mapping_nodes": MappingNode,
}
V3_ONLY_FIELDS = frozenset({
    "hash_algorithm", "ossie_version", "ossie_name", "ossie_description", "ai_context",
    "native_presence", "document_origin", "core_version", "core_presence",
    "extension_v4", "value_types", "semantic_models", "datasets", "dataset_fields",
    "dataset_relationships", "metrics", "concept_mappings", "mapping_nodes",
})


def validate_v3_graph(draft) -> None:
    """Reference and tree checks, without an importer, compiler or database."""
    groups = {name: getattr(draft, name) for name in V3_COLLECTION_MODELS}
    groups.update(actions=draft.actions, material_objects=draft.material_objects)
    items = [item for group in groups.values() for item in group]
    ids = [item.id for item in items]
    roles = [role for link in [*draft.link_types, *draft.properties] for role in link.roles]
    ids.extend(role.id for role in roles)
    ids.extend(link.owner_role_id for link in [*draft.link_types, *draft.properties])
    if len(ids) != len(set(ids)):
        raise ValueError("v3 模型项或角色标识重复")
    def positions(items, scope):
        seen = set()
        for item in items:
            if item.position is None:
                continue
            key = (scope(item), item.position)
            if key in seen:
                raise ValueError("原生数组同一作用域 position 重复")
            seen.add(key)

    positions([*draft.object_types, *draft.value_types], lambda _: "ontology")
    positions([*draft.properties, *draft.link_types], lambda i: (i.owner_ref.kind, str(i.owner_ref.ref)))
    positions(draft.semantic_models, lambda _: "ontology_mappings")
    for group in (draft.datasets, draft.metrics, draft.dataset_relationships, draft.concept_mappings):
        positions(group, lambda i: i.semantic_model_id)
    positions(draft.dataset_fields, lambda i: i.dataset_id)
    concepts = {"object_type": {i.id for i in draft.object_types}, "value_type": {i.id for i in draft.value_types}}

    def check(ref):
        if ref is not None and isinstance(ref.ref, ClientRef):
            raise ValueError("持久化概念引用不能保留未解析的 client_ref")
        if ref is not None and ref.kind in concepts and ref.ref not in concepts[ref.kind]:
            raise ValueError("概念引用不存在或类型不符")

    for item in [*draft.object_types, *draft.value_types]:
        for ref in item.extends:
            check(ref)
    for item in draft.object_types:
        if any(r.kind not in {"object_type", "any"} for r in item.extends):
            raise ValueError("EntityType 只能继承实体概念")
    for item in draft.value_types:
        if any(r.kind not in {"value_type", "builtin"} for r in item.extends):
            raise ValueError("ValueType 只能继承值概念")
    concept_by_id = {i.id: i for i in [*draft.object_types, *draft.value_types]}
    import re
    for item in draft.object_types:
        if item.origin != "imported" and (not item.name.strip() or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item.technical_name)):
            raise ValueError("平台对象名称不能为空，技术名只能包含 ASCII 字母、数字和下划线")
    platform_labels = [i.name for i in draft.object_types if i.origin != "imported"]
    if len(set(platform_labels)) != len(platform_labels):
        raise ValueError("工作空间中存在同名业务对象")
    platform_keys = [i.technical_name.casefold() for i in draft.object_types if i.origin != "imported"]
    if len(set(platform_keys)) != len(platform_keys):
        raise ValueError("工作空间中存在技术名冲突的业务对象")
    names = [i.concept for i in concept_by_id.values()]
    if len(set(names)) != len(names):
        raise ValueError("概念名称重复")
    for item in concept_by_id.values():
        pending = [r.ref for r in item.extends if r.kind in concepts]
        seen = set()
        while pending:
            ref_id = pending.pop()
            if ref_id == item.id:
                raise ValueError("概念继承形成循环")
            if ref_id in seen:
                continue
            seen.add(ref_id)
            pending.extend(r.ref for r in concept_by_id[ref_id].extends if r.kind in concepts)
    owners = {item.id: name for name, group in groups.items() for item in group}
    owner_kind_collection = {"object_type": "object_types", "value_type": "value_types", "property": "properties", "link_type": "link_types", "action": "actions"}
    rules = {r.id: r for r in draft.rules}
    for rule in draft.rules:
        if owners.get(rule.owner_id) != owner_kind_collection[rule.owner_kind]:
            raise ValueError("规则归属不存在或类型不符")
    for item in [*draft.object_types, *draft.value_types, *draft.properties, *draft.link_types]:
        for field, kind in (("requires", "constraint"), ("derived_by", "derivation")):
            for ref_id in getattr(item, field):
                r = rules.get(ref_id)
                if r is None or r.owner_id != item.id or r.rule_kind != kind:
                    raise ValueError("原生规则引用无效")
    for link in [*draft.properties, *draft.link_types]:
        if link.owner_ref.kind not in {"object_type", "value_type"}:
            raise ValueError("关系 owner 必须是文档中声明的实体或值概念")
        check(link.owner_ref)
        for index, role in enumerate(link.roles):
            if role.position is not None and role.position != index:
                raise ValueError("roles 的 position 必须与有序列表一致")
            check(role.concept)
            if role.client_ref is not None:
                raise ValueError("持久化角色不能保留未解析的 client_ref")
    relationship_names = set()
    for link in [*draft.properties, *draft.link_types]:
        key = (link.owner_ref.kind, link.owner_ref.ref, link.technical_name or link.name)
        if key in relationship_names:
            raise ValueError("同一 owner 的关系名称重复")
        relationship_names.add(key)
    models = {i.id for i in draft.semantic_models}
    datasets = {i.id: i for i in draft.datasets}
    mappings = {i.id: i for i in draft.concept_mappings}
    for item in [*draft.datasets, *draft.dataset_relationships, *draft.metrics, *draft.concept_mappings]:
        if item.semantic_model_id not in models:
            raise ValueError("semantic_model_id 不存在")
    for field in draft.dataset_fields:
        if field.dataset_id not in datasets:
            raise ValueError("dataset_id 不存在")
    for model_id in models:
        for group in (draft.datasets, draft.dataset_relationships, draft.metrics):
            names = [i.name for i in group if i.semantic_model_id == model_id]
            if len(set(names)) != len(names):
                raise ValueError("语义模型作用域内名称重复")
    for dataset_id in datasets:
        names = [i.name for i in draft.dataset_fields if i.dataset_id == dataset_id]
        if len(set(names)) != len(names):
            raise ValueError("dataset 字段名称重复")
    for cm in draft.concept_mappings:
        check(cm.concept_id)
    for rel in draft.dataset_relationships:
        names = {i.name for i in draft.datasets if i.semantic_model_id == rel.semantic_model_id}
        if rel.from_ not in names or rel.to not in names:
            raise ValueError("dataset 连接端点不存在")
    nodes = {i.id: i for i in draft.mapping_nodes}
    slots = set()
    for node in nodes.values():
        if node.concept_mapping_id not in mappings:
            raise ValueError("concept_mapping_id 不存在")
        check(node.concept)
        parent = nodes.get(node.parent_id)
        if node.parent_id is None:
            if node.slot not in ("object_mappings", "link_mappings"):
                raise ValueError("映射根节点 slot 无效")
        else:
            if parent is None or parent.concept_mapping_id != node.concept_mapping_id:
                raise ValueError("映射父节点不存在或不属于同一映射")
            permitted = {"link": {"object_mapping", "children"}, "object": {"referent_mappings"}, "referent": {"referent_mappings"}}
            if node.slot not in permitted[parent.kind]:
                raise ValueError("映射子节点 slot 无效")
        if node.position is not None:
            key = (node.concept_mapping_id, node.parent_id, node.slot, node.position)
            if key in slots:
                raise ValueError("映射同一 slot 的 position 重复")
            slots.add(key)
        seen = {node.id}
        ancestor = parent
        while ancestor:
            if ancestor.id in seen:
                raise ValueError("映射树存在循环")
            seen.add(ancestor.id)
            ancestor = nodes.get(ancestor.parent_id)
        if node.kind == "link":
            children = [i for i in nodes.values() if i.parent_id == node.id and i.slot == "object_mapping"]
            if len(children) != 1:
                raise ValueError("link 节点必须有且只有一个 object 子节点")
    # Existing Action and document-fact checks also apply to native drafts.
    from ontofoundry_api.domain.models import expression_references
    action_keys = [a.technical_name.casefold() for a in draft.actions]
    if len(set(action_keys)) != len(action_keys):
        raise ValueError("工作空间中存在技术名冲突的 Action")
    for action in draft.actions:
        if action.input_type_id not in concepts["object_type"]:
            raise ValueError("Action 输入对象类型不存在")
        if any(r not in rules for r in action.precondition_rule_ids):
            raise ValueError("Action 引用了不存在的前置规则")
        usable = draft.effective_properties(action.input_type_id)
        input_key = concept_by_id[action.input_type_id].technical_name
        for effect in action.effects:
            if any(c != input_key or n not in {p.technical_name for p in usable}
                   for c, n in expression_references(effect.expression)):
                raise ValueError("Action 的效果表达式只能引用输入对象的属性")
            if effect.property_id is not None and effect.property_id not in {p.id for p in usable}:
                raise ValueError("Action 效果引用了输入对象上不存在的属性")
            if effect.link_type_id is not None and effect.link_type_id not in {link.id for link in draft.link_types}:
                raise ValueError("Action 效果引用了不存在的关系")
    # Instance role values include the implicit owner role, never only extras.
    objects = {i.id: i for i in draft.material_objects}
    for obj in objects.values():
        if obj.type_id not in concepts["object_type"]:
            raise ValueError("材料实例类型不存在")
        if set(obj.values) - {p.technical_name for p in draft.effective_properties(obj.type_id)}:
            raise ValueError("实例含未定义的属性")
    links = {i.id: i for i in draft.link_types}

    def bases(ref, seen=None):
        if ref.kind == "builtin":
            return {ref.ref}
        if ref.kind != "value_type":
            return set()
        seen = set() if seen is None else seen
        if ref.ref in seen:
            return set()
        seen.add(ref.ref)
        return set().union(*(bases(r, seen) for r in concept_by_id[ref.ref].extends))

    def check_value(value, ref):
        if value is None:
            return
        from datetime import date, datetime

        for base in bases(ref):
            valid = True
            if base == "Integer":
                valid = type(value) is int
            elif base in {"Decimal", "Float"}:
                valid = type(value) in {int, float}
                if type(value) is float:
                    import math
                    valid = math.isfinite(value)
            elif base == "Boolean":
                valid = type(value) is bool
            elif base in {"String", "Date", "DateTime"}:
                valid = isinstance(value, str)
                if valid and base in {"Date", "DateTime"}:
                    try:
                        (date.fromisoformat if base == "Date" else datetime.fromisoformat)(value)
                    except ValueError:
                        valid = False
            if not valid:
                raise ValueError("实例角色值类型不匹配")

    cardinality = {}
    inverse = {}
    for index, fact in enumerate(draft.material_links):
        link = links.get(fact.type_id)
        if link is None:
            raise ValueError("实例关系类型不存在")
        from ontofoundry_api.domain.fact_views import binary_fact_view

        fact = MaterialLinkV3.model_validate(binary_fact_view(link.model_dump(mode="json"), fact.model_dump(mode="json")))
        draft.material_links[index] = fact
        expected = {link.owner_role_id: link.owner_ref, **{r.id: r.concept for r in link.roles}}
        actual = [v.role_id for v in fact.role_values]
        if len(set(actual)) != len(actual) or set(actual) != set(expected):
            raise ValueError("实例角色值必须覆盖全部角色且不能重复")
        for val in fact.role_values:
            ref = expected[val.role_id]
            if ref.kind in ("object_type", "any"):
                obj = objects.get(val.object_id)
                if obj is None or val.value is not None:
                    raise ValueError("实体角色必须指定有效 object_id")
                if ref.kind == "object_type":
                    lineage = {obj.type_id}
                    pending = [obj.type_id]
                    while pending:
                        current = concept_by_id.get(pending.pop())
                        for base in current.extends if current else []:
                            if base.kind == "object_type" and base.ref not in lineage:
                                lineage.add(base.ref)
                                pending.append(base.ref)
                    if ref.ref not in lineage:
                        raise ValueError("实例角色对象类型不匹配")
            elif val.object_id is not None:
                raise ValueError("值角色不能指定 object_id")
            else:
                check_value(val.value, ref)
        if link.multiplicity is not None:
            from ontofoundry_api.domain.canonical import jcs

            values = {v.role_id: jcs(str(v.object_id)) if v.object_id else jcs(v.value) for v in fact.role_values}
            owner_value = values[link.owner_role_id]
            targets = tuple(values[r.id] for r in link.roles)
            key = (link.id, owner_value)
            if key in cardinality and cardinality[key] != targets:
                raise ValueError("实例角色值违反 ManyToOne 基数")
            cardinality[key] = targets
            key = (link.id, targets)
            if link.multiplicity == "OneToOne" and key in inverse and inverse[key] != owner_value:
                raise ValueError("实例角色值违反 OneToOne 基数")
            inverse[key] = owner_value
    # The extension envelope is an export projection of these same elements,
    # never an independently editable second truth for display data/actions.
    by_id = {i.id: i for i in items}
    ext = draft.extension_v4
    for element_id, label in ext.display_names.items():
        item = by_id.get(element_id)
        if item is None or getattr(item, "name", None) != label:
            raise ValueError("扩展显示名必须与元素集合一致")
    for element_id, tags in ext.tags.items():
        item = by_id.get(element_id)
        if item is None or getattr(item, "tags", None) != tags:
            raise ValueError("扩展标签必须与元素集合一致")
    props = {p.id: p for p in draft.properties}
    for prop_id in ext.required_properties:
        if prop_id not in props or not props[prop_id].required:
            raise ValueError("扩展必填属性必须与元素集合一致")
    if ext.actions and ext.actions != [a.model_dump(mode="json") for a in draft.actions]:
        raise ValueError("扩展 Action 必须与 actions 集合一致")
    for rule_id, metadata in ext.rule_metadata.items():
        rule = rules.get(rule_id)
        if rule is None:
            raise ValueError("扩展规则元数据引用不存在的规则")
        for field in ("name", "technical_name", "description"):
            if field in metadata and metadata[field] != getattr(rule, field):
                raise ValueError("扩展规则元数据必须与 rules 集合一致")
    for concept_id in ext.concept_context:
        if concept_id not in concept_by_id:
            raise ValueError("概念上下文引用不存在的概念")
    if draft.mappings:
        raise ValueError("v3 mappings 是派生视图，不能持久化")
