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

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)


class ObjectTypeDefinition(BaseModel):
    id: UUID
    name: NonEmptyText
    technical_name: NonEmptyText
    description: str = ""
    tags: list[str] = Field(default_factory=list)
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
    tags: list[str] = Field(default_factory=list)
    data_join: DataJoin | None = None

    _normalize_name = field_validator("name")(normalize_display_name)
    _validate_technical_name = field_validator("technical_name")(validate_technical_name)


class OntologyDraft(BaseModel):
    schema_version: str = "1"
    workspace_id: UUID
    object_types: list[ObjectTypeDefinition] = Field(default_factory=list)
    link_types: list[LinkTypeDefinition] = Field(default_factory=list)
    objects: list[DocumentObject] = Field(default_factory=list)
    links: list[DocumentLink] = Field(default_factory=list)
    mappings: list[DataMapping] = Field(default_factory=list)

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
        link_names = [normalize_display_name(item.name) for item in self.link_types]
        link_keys = [item.technical_name.casefold() for item in self.link_types]

        if len(object_names) != len(set(object_names)):
            raise ValueError("工作空间中存在同名业务对象")
        if len(object_keys) != len(set(object_keys)):
            raise ValueError("工作空间中存在技术名冲突的业务对象")
        if len(link_names) != len(set(link_names)):
            raise ValueError("工作空间中存在同名本体关系")
        if len(link_keys) != len(set(link_keys)):
            raise ValueError("工作空间中存在技术名冲突的本体关系")

        missing = {
            endpoint
            for item in self.link_types
            for endpoint in (item.source_type_id, item.target_type_id)
            if endpoint not in object_ids
        }
        if missing:
            raise ValueError("本体关系引用了不存在的业务对象")
        type_by_id = {t.id: t for t in self.object_types}
        instances = {o.id: o for o in self.objects}
        relations = {r.id: r for r in self.link_types}
        for item in self.objects:
            if item.type_id not in object_ids:
                raise ValueError("文档实例必须绑定已存在的业务对象类型")
            keys = {a.technical_name for a in type_by_id[item.type_id].attributes}
            if set(item.values) - keys:
                raise ValueError("实例含未定义的属性")
        for item in self.links:
            relation = relations.get(item.type_id)
            source, target = instances.get(item.source_id), instances.get(item.target_id)
            if not relation or not source or not target:
                raise ValueError("实例关系引用无效")
            if (
                source.type_id != relation.source_type_id
                or target.type_id != relation.target_type_id
            ):
                raise ValueError("实例关系端点类型不匹配")
        mapped_ids = [m.type_id for m in self.mappings]
        if len(mapped_ids) != len(set(mapped_ids)):
            raise ValueError("每个业务对象只允许一个数据映射")
        for mapping in self.mappings:
            if mapping.type_id not in object_ids:
                raise ValueError("映射引用了不存在的业务对象")
            attrs = {a.technical_name for a in type_by_id[mapping.type_id].attributes}
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
    id: UUID
    type_id: UUID
    connection_id: UUID
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
