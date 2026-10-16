"""core-1: the ontology draft model.

The single definition of the core-1 draft and its elements. Every element has a
stable UUID and lives in a flat top-level collection; ownership is a reference.
This module holds element shapes and the checks that need only one element.
Checks across elements (references, inheritance, bindings, metric datasets)
live in `domain/validation.py`.

Design: docs/design/2026-10-14-core-model-and-format-adapters.md §3.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "core-1"

TECHNICAL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SOURCE_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Strict(BaseModel):
    """Stored shapes reject unknown fields: hashing and diffs see every field."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def _display_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError("名称不能为空")
    return normalized


def _technical_name(value: str) -> str:
    value = value.strip()
    if not TECHNICAL_NAME_RE.fullmatch(value):
        raise ValueError("技术名只能包含 ASCII 字母、数字和下划线，且不能以数字开头")
    return value


Name = Annotated[str, Field(min_length=1, max_length=240), AfterValidator(_display_name)]
TechnicalName = Annotated[
    str, Field(min_length=1, max_length=240), AfterValidator(_technical_name)
]
Description = Annotated[str, Field(default="", max_length=8000)]
Labels = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=120)]],
    Field(default_factory=list, max_length=50),
]
Expression = Annotated[str, Field(min_length=1, max_length=4000)]
Scalar = str | int | float | bool | None


class ValueKind(StrEnum):
    """Ossie's seven built-in value types; core-1 adds no others."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


NUMERIC_KINDS = frozenset({ValueKind.INTEGER, ValueKind.DECIMAL, ValueKind.FLOAT})


# --- evidence ---------------------------------------------------------------


class EvidenceLocator(Strict):
    heading: str | None = Field(default=None, max_length=240)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> EvidenceLocator:
        if self.line_end < self.line_start:
            raise ValueError("证据的结束行不能早于起始行")
        return self


class MaterialEvidence(Strict):
    kind: Literal["material"] = "material"
    id: UUID
    material_id: str = Field(min_length=1, max_length=64)
    material_sha256: str
    locator: EvidenceLocator
    quote: str = Field(default="", max_length=2000)

    @field_validator("material_sha256")
    @classmethod
    def check_sha(cls, value: str) -> str:
        if not SHA256_RE.fullmatch(value):
            raise ValueError("material_sha256 必须是 64 位小写十六进制")
        return value


class ManualEvidence(Strict):
    """A member vouching for a fact. Author and time are written by the server."""

    kind: Literal["manual"] = "manual"
    id: UUID
    note: str = Field(default="", max_length=2000)
    created_by: str = Field(min_length=1, max_length=64)
    created_at: datetime


Evidence = Annotated[MaterialEvidence | ManualEvidence, Field(discriminator="kind")]


def _unique_evidence(items: list) -> list:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("同一元素的证据 id 重复")
    return items


EvidenceList = Annotated[
    list[Evidence],
    Field(default_factory=list, max_length=50),
    AfterValidator(_unique_evidence),
]


# --- conditions -------------------------------------------------------------


class Operator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"


def check_operator_values(operator: Operator, values: list[Scalar]) -> None:
    """Value count per operator; not_in may not hold null (NOT IN with NULL is never true)."""
    count = len(values)
    if operator in (Operator.IS_NULL, Operator.NOT_NULL):
        ok = count == 0
    elif operator == Operator.BETWEEN:
        ok = count == 2
    elif operator in (Operator.IN, Operator.NOT_IN):
        ok = count >= 1
    else:
        ok = count == 1
    if not ok:
        raise ValueError(f"运算符 {operator.value} 的取值个数不对")
    if operator == Operator.NOT_IN and any(value is None for value in values):
        raise ValueError("not_in 的取值不能包含 null")


class LinkStep(Strict):
    link_type_id: UUID
    direction: Literal["forward", "reverse"]


class Path(Strict):
    """From a context object, through links, to one property. Ontology rules and
    membership conditions only; metrics never use paths."""

    links: list[LinkStep] = Field(default_factory=list, max_length=8)
    property_id: UUID


class PathCondition(Strict):
    path: Path
    operator: Operator
    values: list[Scalar] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def check_values(self) -> PathCondition:
        check_operator_values(self.operator, self.values)
        return self


class DerivedSimple(Strict):
    """One membership branch: every condition must hold (AND)."""

    kind: Literal["simple"]
    conditions: list[PathCondition] = Field(min_length=1, max_length=50)


class DerivedExpression(Strict):
    kind: Literal["expression"]
    expression: Expression


DerivedBranch = Annotated[DerivedSimple | DerivedExpression, Field(discriminator="kind")]


# --- ontology ---------------------------------------------------------------


class ObjectType(Strict):
    id: UUID
    name: Name
    technical_name: TechnicalName
    description: Description = ""
    synonyms: Labels
    tags: Labels
    extends: UUID | None = None
    title_property_id: UUID | None = None
    # Branches are OR-ed; each branch narrows the parent's members.
    derived_by: list[DerivedBranch] = Field(default_factory=list, max_length=20)
    evidence: EvidenceList

    @model_validator(mode="after")
    def derived_needs_parent(self) -> ObjectType:
        if self.derived_by and self.extends is None:
            raise ValueError("派生条件只能用于有父对象的子对象")
        if self.extends == self.id:
            raise ValueError("对象不能继承自身")
        return self


class Property(Strict):
    id: UUID
    owner_type_id: UUID
    name: Name
    technical_name: TechnicalName
    description: Description = ""
    value_kind: ValueKind
    required: bool = False
    identifier: bool = False
    unique: bool = False
    synonyms: Labels
    evidence: EvidenceList


class Multiplicity(StrEnum):
    """No one_to_many: a one-to-many link is built from the many side."""

    ONE_TO_ONE = "one_to_one"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class MappingKey(Strict):
    """The end object's main source `key_columns`."""

    kind: Literal["mapping_key"]


class PropertiesKey(Strict):
    """A single unique property or the end object's complete identifier."""

    kind: Literal["properties"]
    property_ids: list[UUID] = Field(min_length=1, max_length=16)


JoinKey = Annotated[MappingKey | PropertiesKey, Field(discriminator="kind")]
Columns = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=240)]],
    Field(min_length=1, max_length=16),
]


class DirectJoin(Strict):
    """Source properties equal target properties, pair by pair."""

    kind: Literal["direct"]
    source_property_ids: list[UUID] = Field(min_length=1, max_length=16)
    target_property_ids: list[UUID] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def paired(self) -> DirectJoin:
        if len(self.source_property_ids) != len(self.target_property_ids):
            raise ValueError("直接关联两端的属性个数必须相同")
        return self


class MappingTableJoin(Strict):
    kind: Literal["mapping_table"]
    dataset_id: UUID
    source_columns: Columns
    target_columns: Columns
    source_key: JoinKey
    target_key: JoinKey

    @model_validator(mode="after")
    def key_widths(self) -> MappingTableJoin:
        for side, columns, key in (
            ("源", self.source_columns, self.source_key),
            ("目标", self.target_columns, self.target_key),
        ):
            if isinstance(key, PropertiesKey) and len(columns) != len(key.property_ids):
                raise ValueError(f"映射表{side}端的列数必须与引用键的属性个数相同")
        return self


DataJoin = Annotated[DirectJoin | MappingTableJoin, Field(discriminator="kind")]


class LinkType(Strict):
    id: UUID
    name: Name
    technical_name: TechnicalName
    description: Description = ""
    inverse_name: Annotated[str, AfterValidator(_display_name)] | None = None
    synonyms: Labels
    source_type_id: UUID
    target_type_id: UUID
    multiplicity: Multiplicity
    tags: Labels
    data_join: DataJoin | None = None
    evidence: EvidenceList

    @model_validator(mode="after")
    def distinct_readings(self) -> LinkType:
        if self.inverse_name is not None and self.inverse_name == self.name:
            raise ValueError("反向名称不能与关系名称相同")
        return self


class RuleKind(StrEnum):
    CONSTRAINT = "constraint"
    DERIVATION = "derivation"


class RuleOwnerKind(StrEnum):
    OBJECT_TYPE = "object_type"
    PROPERTY = "property"
    LINK_TYPE = "link_type"


class Rule(Strict):
    id: UUID
    name: Name
    technical_name: TechnicalName
    description: Description = ""
    owner_kind: RuleOwnerKind
    owner_id: UUID
    rule_kind: RuleKind
    expression: Expression
    evidence: EvidenceList


# --- metrics ----------------------------------------------------------------


class ColumnReference(Strict):
    dataset_id: UUID
    column: str = Field(min_length=1, max_length=240)


class Condition(Strict):
    column: ColumnReference
    operator: Operator
    values: list[Scalar] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def check_values(self) -> Condition:
        check_operator_values(self.operator, self.values)
        return self


class Aggregation(StrEnum):
    SUM = "sum"
    AVG = "avg"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"


class _MetricBase(Strict):
    id: UUID
    name: Name
    technical_name: TechnicalName
    description: Description = ""
    synonyms: Labels
    evidence: EvidenceList


def _same_dataset(dataset_id: UUID, references: list[ColumnReference | None]) -> None:
    for reference in references:
        if reference is not None and reference.dataset_id != dataset_id:
            raise ValueError("指标只能引用自己数据集的列")


class SimpleMetric(_MetricBase):
    """value_kind is derived on read and not accepted as input."""

    kind: Literal["simple"]
    dataset_id: UUID
    aggregation: Aggregation
    measure: ColumnReference | None = None
    filters: list[Condition] = Field(default_factory=list, max_length=50)
    time_field: ColumnReference | None = None

    @model_validator(mode="after")
    def check_shape(self) -> SimpleMetric:
        if self.aggregation == Aggregation.COUNT:
            if self.measure is not None:
                raise ValueError("计数统计行数，不能指定度量列")
        elif self.measure is None:
            raise ValueError(f"{self.aggregation.value} 必须指定度量列")
        _same_dataset(
            self.dataset_id,
            [self.measure, self.time_field, *(f.column for f in self.filters)],
        )
        return self


class RatioMetric(_MetricBase):
    """dataset_id, time_field and value_kind come from the two components."""

    kind: Literal["ratio"]
    numerator_id: UUID
    denominator_id: UUID


class ExpressionMetric(_MetricBase):
    kind: Literal["expression"]
    dataset_id: UUID
    expression: Expression
    value_kind: ValueKind | None = None
    time_field: ColumnReference | None = None

    @model_validator(mode="after")
    def check_time_field(self) -> ExpressionMetric:
        _same_dataset(self.dataset_id, [self.time_field])
        return self


Metric = Annotated[
    SimpleMetric | RatioMetric | ExpressionMetric, Field(discriminator="kind")
]


# --- datasets and mappings --------------------------------------------------


class DatasetColumn(Strict):
    name: str = Field(min_length=1, max_length=240)
    physical_type: str | None = Field(default=None, max_length=120)
    comment: str = Field(default="", max_length=2000)


class Dataset(Strict):
    id: UUID
    name: str = Field(min_length=1, max_length=240)
    dialect: str | None = Field(default=None, max_length=40)
    schema_name: str | None = Field(default=None, max_length=240)
    table_name: str = Field(min_length=1, max_length=240)
    description: Description = ""
    snapshot_date_column: str | None = Field(default=None, min_length=1, max_length=240)
    # None: no column list was provided, which is not the same as "no columns".
    columns: list[DatasetColumn] | None = None

    @model_validator(mode="after")
    def unique_columns(self) -> Dataset:
        if self.columns is not None:
            names = [column.name for column in self.columns]
            if len(names) != len(set(names)):
                raise ValueError("数据集的列名重复")
        return self


SourceId = Annotated[str, Field(min_length=1, max_length=64, pattern=SOURCE_ID_RE.pattern)]
MAIN_SOURCE = "main"


class MappingSource(Strict):
    id: SourceId
    dataset_id: UUID
    # Ordered logical key at the chosen business time; empty means unfinished.
    key_columns: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=16
    )


class ColumnBinding(Strict):
    kind: Literal["column"]
    source_id: SourceId
    column: str = Field(min_length=1, max_length=240)


class ExpressionBinding(Strict):
    """A same-row expression over this object's own sources (`source.column`)."""

    kind: Literal["expression"]
    expression: Expression


FieldBinding = Annotated[ColumnBinding | ExpressionBinding, Field(discriminator="kind")]


class BindingMode(StrEnum):
    INDEPENDENT = "independent"
    SHARED_PARENT = "shared_parent"


class DataMapping(Strict):
    id: UUID
    type_id: UUID
    binding_mode: BindingMode
    sources: list[MappingSource] = Field(default_factory=list, max_length=64)
    # Property technical name → binding.
    fields: dict[str, FieldBinding] = Field(default_factory=dict)
    membership_source_id: SourceId | None = None
    # Only a concrete child of a virtual parent binds inherited links locally.
    inherited_link_bindings: dict[UUID, DataJoin] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_sources(self) -> DataMapping:
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("同一映射的来源 id 重复")
        if self.binding_mode == BindingMode.INDEPENDENT:
            if MAIN_SOURCE not in ids:
                raise ValueError("独立绑定必须有 id 为 main 的主来源")
            if self.membership_source_id is not None:
                raise ValueError("只有共用父表的子对象才能声明成员扩展来源")
        elif MAIN_SOURCE in ids:
            raise ValueError("共用父表的子对象沿用父主来源，不能另设 main 来源")
        if self.membership_source_id is not None and self.membership_source_id not in ids:
            raise ValueError("成员扩展来源必须是本映射的来源之一")
        return self


# --- facts ------------------------------------------------------------------


class MaterialObject(Strict):
    """A document fact. Its display text is derived on read, not stored."""

    id: UUID
    type_id: UUID
    values: dict[str, Scalar] = Field(default_factory=dict)
    evidence: EvidenceList


class MaterialLink(Strict):
    id: UUID
    type_id: UUID
    source_id: UUID
    target_id: UUID
    evidence: EvidenceList


# --- draft ------------------------------------------------------------------


class CoreDraft(Strict):
    schema_version: Literal["core-1"] = SCHEMA_VERSION
    workspace_id: UUID
    object_types: list[ObjectType] = Field(default_factory=list)
    properties: list[Property] = Field(default_factory=list)
    link_types: list[LinkType] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    datasets: list[Dataset] = Field(default_factory=list)
    mappings: list[DataMapping] = Field(default_factory=list)
    material_objects: list[MaterialObject] = Field(default_factory=list)
    material_links: list[MaterialLink] = Field(default_factory=list)


COLLECTIONS = (
    "object_types",
    "properties",
    "link_types",
    "rules",
    "metrics",
    "datasets",
    "mappings",
    "material_objects",
    "material_links",
)


def empty_draft(workspace_id: UUID) -> CoreDraft:
    return CoreDraft(workspace_id=workspace_id)
