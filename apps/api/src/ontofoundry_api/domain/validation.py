"""Pure core-1 graph validation, separate from execution and readiness."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime
from uuid import UUID

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import (
    COLLECTIONS,
    NUMERIC_KINDS,
    Aggregation,
    BindingMode,
    ColumnBinding,
    CoreDraft,
    DataJoin,
    DataMapping,
    DerivedExpression,
    DirectJoin,
    ExpressionBinding,
    ExpressionMetric,
    MappingKey,
    Multiplicity,
    Operator,
    RatioMetric,
    RuleOwnerKind,
    SimpleMetric,
    ValueKind,
)
from ontofoundry_api.domain.expressions import (
    resolve_derived_expression,
    resolve_field_expression,
    resolve_metric_expression,
    resolve_path,
    resolve_rule_expression,
)
from ontofoundry_api.domain.graph import DraftIndex


class GraphValidationError(ValueError):
    """Domain error; HTTP/service translation belongs at the caller boundary."""

    def __init__(self, message: str, *, path: str = "", code: str = "invalid_core_graph"):
        self.code = code
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise GraphValidationError(message)


def physical_value_kind(physical_type: str | None) -> ValueKind | None:
    """Classify registered metadata without consulting bindings or a database."""
    name = re.split(r"[\s(]", (physical_type or "").strip().lower())[0]
    if name in {"boolean", "bool"}:
        return ValueKind.BOOLEAN
    if name in {
        "tinyint",
        "smallint",
        "mediumint",
        "int",
        "integer",
        "bigint",
        "int2",
        "int4",
        "int8",
        "largeint",
    }:
        return ValueKind.INTEGER
    if name in {"decimal", "numeric", "number", "money"}:
        return ValueKind.DECIMAL
    if name in {"float", "double", "real", "float4", "float8"}:
        return ValueKind.FLOAT
    if name == "date":
        return ValueKind.DATE
    if name in {"datetime", "datetime2", "timestamp", "timestamptz"}:
        return ValueKind.DATETIME
    if name in {
        "char",
        "varchar",
        "nvarchar",
        "nchar",
        "text",
        "string",
        "uuid",
        "character",
    }:
        return ValueKind.STRING
    return None


def _column(index: DraftIndex, dataset_id: UUID, name: str) -> ValueKind | None:
    dataset = index.datasets.get(dataset_id)
    _require(dataset is not None, "引用的数据集不存在")
    if not dataset.columns:
        return None
    column = next((column for column in dataset.columns if column.name == name), None)
    _require(column is not None, f"数据集 {dataset.name} 不存在列 {name}")
    return physical_value_kind(column.physical_type)


def check_scalar(value, kind: ValueKind | None) -> bool:
    if value is None or kind is None:
        return True
    if kind == ValueKind.STRING:
        return isinstance(value, str)
    if kind == ValueKind.BOOLEAN:
        return isinstance(value, bool)
    if kind == ValueKind.INTEGER:
        return type(value) is int
    if kind in {ValueKind.DECIMAL, ValueKind.FLOAT}:
        return type(value) in {int, float} and math.isfinite(value)
    if not isinstance(value, str):
        return False
    try:
        if kind == ValueKind.DATE:
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and bool(
                date.fromisoformat(value)
            )
        datetime.fromisoformat(value)
        return "T" in value or " " in value
    except ValueError:
        return False


def _condition(operator, values, kind):
    _require(
        all(check_scalar(value, kind) for value in values), "条件值与列或属性类型不匹配"
    )
    if operator in {Operator.GT, Operator.GE, Operator.LT, Operator.LE, Operator.BETWEEN}:
        _require(kind != ValueKind.BOOLEAN, "布尔值不能使用大小比较")
        _require(all(value is not None for value in values), "大小比较不能包含 null")


def metric_value_kind(
    draft: CoreDraft, metric, index: DraftIndex | None = None
) -> ValueKind | None:
    index = index or DraftIndex(draft)
    if isinstance(metric, RatioMetric):
        return ValueKind.DECIMAL
    if isinstance(metric, ExpressionMetric):
        return metric.value_kind
    if metric.aggregation in {Aggregation.COUNT, Aggregation.COUNT_DISTINCT}:
        return ValueKind.INTEGER
    if metric.aggregation in {Aggregation.AVG, Aggregation.MEDIAN}:
        return ValueKind.DECIMAL
    if metric.measure is None:
        return None
    return _column(index, metric.dataset_id, metric.measure.column)


def _names(items, label, *, technical=True):
    names = [
        item.name.casefold()
        if technical
        else unicodedata.normalize("NFKC", item.name).strip()
        for item in items
    ]
    _require(
        len(names) == len(set(names)),
        f"{label}英文标识重复（含继承）" if technical else f"{label}名称重复",
    )


def _unique_key(index: DraftIndex, type_id: UUID, ids: list[UUID]) -> bool:
    properties = {p.id: p for p in index.effective_properties(type_id)}
    if len(set(ids)) != len(ids) or any(pid not in properties for pid in ids):
        return False
    return (len(ids) == 1 and properties[ids[0]].unique) or (
        bool(ids) and set(ids) == {p.id for p in index.identifier(type_id)}
    )


def _join(draft, index, link, join: DataJoin, *, source_type_id=None):
    source_type_id = source_type_id or link.source_type_id
    if isinstance(join, DirectJoin):
        _require(link.multiplicity != Multiplicity.MANY_TO_MANY, "多对多关系必须使用映射表")
        for type_id, ids in [
            (source_type_id, join.source_property_ids),
            (link.target_type_id, join.target_property_ids),
        ]:
            _require(len(set(ids)) == len(ids), "关联属性组不能重复")
            _require(
                set(ids) <= {p.id for p in index.effective_properties(type_id)},
                "关联引用了无效属性",
            )
            fields = resolve_binding(draft, type_id).fields
            for pid in ids:
                _require(
                    not isinstance(
                        fields.get(index.properties[pid].name), ExpressionBinding
                    ),
                    "计算表达式不能作为关联键",
                )
        _require(
            _unique_key(index, link.target_type_id, join.target_property_ids),
            "直接关联目标必须是唯一属性或完整标识",
        )
        if link.multiplicity == Multiplicity.ONE_TO_ONE:
            _require(
                _unique_key(index, source_type_id, join.source_property_ids),
                "一对一关系源端必须是唯一属性或完整标识",
            )
    else:
        _require(join.dataset_id in index.datasets, "关联映射表数据集不存在")
        for type_id, columns, key in [
            (source_type_id, join.source_columns, join.source_key),
            (link.target_type_id, join.target_columns, join.target_key),
        ]:
            _require(len(set(columns)) == len(columns), "映射表键列不能重复")
            for column in columns:
                _column(index, join.dataset_id, column)
            if isinstance(key, MappingKey):
                main = resolve_binding(draft, type_id).main
                if main and main.key_columns:
                    _require(
                        len(columns) == len(main.key_columns),
                        "映射表列数与来源逻辑键宽不符",
                    )
            else:
                _require(
                    _unique_key(index, type_id, key.property_ids),
                    "映射表端点必须引用唯一属性或完整标识",
                )
                fields = resolve_binding(draft, type_id).fields
                _require(
                    all(
                        not isinstance(
                            fields.get(index.properties[pid].name),
                            ExpressionBinding,
                        )
                        for pid in key.property_ids
                    ),
                    "计算表达式不能作为关联键",
                )


def _mappings(draft: CoreDraft, index: DraftIndex):
    by_type: dict[UUID, DataMapping] = {}
    for mapping in draft.mappings:
        _require(mapping.type_id in index.objects, "映射对象不存在")
        _require(mapping.type_id not in by_type, "每个对象只能有一个映射")
        by_type[mapping.type_id] = mapping
    for mapping in draft.mappings:
        obj = index.objects[mapping.type_id]
        bound_ancestors = [oid for oid in index.ancestors(obj.id) if oid in by_type]
        if bound_ancestors:
            _require(
                mapping.binding_mode == BindingMode.SHARED_PARENT,
                "父对象有绑定时子对象只能共用父绑定",
            )
        else:
            _require(
                mapping.binding_mode == BindingMode.INDEPENDENT,
                "共用父绑定必须有已绑定祖先",
            )
        parent_binding = resolve_binding(draft, obj.extends) if obj.extends else None
        if parent_binding and parent_binding.mappings:
            _require(
                not ({s.id for s in mapping.sources} & parent_binding.sources.keys()),
                "本地来源 id 不能遮蔽祖先来源",
            )
        effective = resolve_binding(draft, obj.id)
        main = effective.main
        for source in mapping.sources:
            _require(source.dataset_id in index.datasets, "映射来源数据集不存在")
            _require(
                len(source.key_columns) == len(set(source.key_columns)),
                "来源逻辑键不能有重复列",
            )
            for column in source.key_columns:
                _column(index, source.dataset_id, column)
            if main and main.key_columns and source.key_columns:
                _require(
                    len(main.key_columns) == len(source.key_columns),
                    "附来源逻辑键宽必须与主来源一致",
                )
        props = {p.name: p for p in index.effective_properties(obj.id)}
        for name, binding in mapping.fields.items():
            _require(name in props, f"映射引用了无效属性 {name}")
            if bound_ancestors:
                _require(
                    props[name].owner_type_id == obj.id, "不能覆盖有绑定祖先的继承属性"
                )
            if isinstance(binding, ColumnBinding):
                source = effective.sources.get(binding.source_id)
                _require(source is not None, "属性绑定来源不存在")
                _column(index, source.dataset_id, binding.column)
            else:
                resolve_field_expression(draft, mapping, binding.expression)
        for link_id, join in mapping.inherited_link_bindings.items():
            link = index.links.get(link_id)
            _require(
                not bound_ancestors and obj.extends is not None,
                "只有虚拟父的具体子对象能绑定继承关系",
            )
            _require(
                link is not None and link.source_type_id in index.ancestors(obj.id),
                "只能绑定从虚拟祖先继承的关系",
            )
            _join(draft, index, link, join, source_type_id=obj.id)


def _value_types(draft: CoreDraft, index: DraftIndex) -> None:
    from ontofoundry_api.domain.value_types import RESERVED_NAMES

    _names(draft.value_types, "值类型")
    _names([*draft.object_types, *draft.value_types], "实体类型与值类型共享英文标识")
    for value_type in draft.value_types:
        _require(
            value_type.name.casefold() not in RESERVED_NAMES,
            f"值类型英文标识不能使用内置类型名：{value_type.name}",
        )
    for prop in draft.properties:
        if prop.value_type_id is None:
            continue
        value_type = index.value_types.get(prop.value_type_id)
        _require(value_type is not None, f"属性 {prop.name} 引用的值类型不存在，请先改绑或一并保留值类型")
        _require(
            prop.value_kind == value_type.value_kind,
            f"属性 {prop.name} 的基础类型须与值类型 {value_type.name} 一致（{value_type.value_kind}）",
        )
    for rule in draft.rules:
        if rule.owner_kind == RuleOwnerKind.VALUE_TYPE:
            _require(rule.owner_id in index.value_types, "规则归属的值类型不存在")


def validate_core_graph(draft: CoreDraft) -> CoreDraft:
    """Raise on known invalid structure; missing physical metadata stays valid."""
    ids = [
        element.id for collection in COLLECTIONS for element in getattr(draft, collection)
    ]
    _require(len(ids) == len(set(ids)), "模型元素 UUID 重复")
    evidence_ids = [
        e.id
        for collection in COLLECTIONS
        for item in getattr(draft, collection)
        for e in getattr(item, "evidence", [])
    ]
    _require(
        len(set(ids + evidence_ids)) == len(ids) + len(evidence_ids),
        "证据 UUID 重复或与元素冲突",
    )
    index = DraftIndex(draft)
    _names(draft.object_types, "对象")
    _names(draft.datasets, "数据集", technical=False)
    _names(draft.metrics, "指标")
    for obj in draft.object_types:
        seen = {obj.id}
        current = obj
        while current.extends is not None:
            _require(current.extends in index.objects, "继承父对象不存在")
            _require(current.extends not in seen, "继承关系不能成环")
            seen.add(current.extends)
            current = index.objects[current.extends]
    _value_types(draft, index)
    for prop in draft.properties:
        _require(prop.owner_type_id in index.objects, "属性归属对象不存在")
    for link in draft.link_types:
        _require(
            link.source_type_id in index.objects and link.target_type_id in index.objects,
            "关系端点不存在",
        )
    for obj in draft.object_types:
        props = index.effective_properties(obj.id)
        _names([*props, *index.outgoing_links(obj.id)], "属性与关系共享命名空间")
        if obj.title_property_id is not None:
            _require(
                obj.title_property_id in {p.id for p in props},
                "标题属性必须属于本对象或祖先",
            )
        identifiers = index.identifier(obj.id)
        if len(identifiers) == 1:
            _require(identifiers[0].unique, "单属性标识必须声明 unique")
        if obj.extends and index.identifier(obj.extends):
            _require(
                not any(p.identifier and p.owner_type_id == obj.id for p in props),
                "子对象不能增加已有父标识",
            )
        for branch in obj.derived_by:
            if isinstance(branch, DerivedExpression):
                resolve_derived_expression(draft, obj.extends, branch.expression)
            else:
                for condition in branch.conditions:
                    resolve_path(
                        index,
                        obj.extends,
                        [(s.link_type_id, s.direction) for s in condition.path.links],
                        condition.path.property_id,
                    )
                    _condition(
                        condition.operator,
                        condition.values,
                        index.properties[condition.path.property_id].value_kind,
                    )
    rule_keys = set()
    for rule in draft.rules:
        key = (rule.owner_kind, rule.owner_id, rule.name.casefold())
        _require(key not in rule_keys, "同一归属下规则英文标识重复")
        rule_keys.add(key)
        resolve_rule_expression(draft, rule)
    _mappings(draft, index)
    for link in draft.link_types:
        if link.data_join is not None:
            _join(draft, index, link, link.data_join)
    for dataset in draft.datasets:
        if dataset.snapshot_date_column:
            kind = _column(index, dataset.id, dataset.snapshot_date_column)
            _require(
                kind is None or kind in {ValueKind.DATE, ValueKind.DATETIME},
                "快照日期列必须是日期类",
            )
    metrics = {metric.id: metric for metric in draft.metrics}
    for metric in draft.metrics:
        if isinstance(metric, RatioMetric):
            components = [
                metrics.get(metric.numerator_id),
                metrics.get(metric.denominator_id),
            ]
            _require(
                all(isinstance(m, SimpleMetric) for m in components),
                "比率分量必须是 simple 指标",
            )
            _require(
                components[0].dataset_id == components[1].dataset_id,
                "比率分量必须属于同一数据集",
            )
            _require(
                all(
                    metric_value_kind(draft, m, index) in {*NUMERIC_KINDS, None}
                    for m in components
                ),
                "比率分量必须是数值型",
            )
            continue
        _require(metric.dataset_id in index.datasets, "指标数据集不存在")
        if metric.time_field:
            kind = _column(index, metric.dataset_id, metric.time_field.column)
            _require(
                kind is None or kind in {ValueKind.DATE, ValueKind.DATETIME},
                "指标时间字段必须是日期类",
            )
        if isinstance(metric, ExpressionMetric):
            resolve_metric_expression(draft, metric)
        else:
            if metric.measure:
                kind = _column(index, metric.dataset_id, metric.measure.column)
                if metric.aggregation in {
                    Aggregation.SUM,
                    Aggregation.AVG,
                    Aggregation.MEDIAN,
                }:
                    _require(kind is None or kind in NUMERIC_KINDS, "该聚合要求数值列")
                if metric.aggregation in {Aggregation.MIN, Aggregation.MAX}:
                    _require(kind != ValueKind.BOOLEAN, "min/max 不接受布尔列")
            for condition in metric.filters:
                kind = _column(index, metric.dataset_id, condition.column.column)
                _condition(condition.operator, condition.values, kind)
    facts = {fact.id: fact for fact in draft.material_objects}
    mappings = {m.type_id for m in draft.mappings}
    for fact in draft.material_objects:
        _require(fact.type_id in index.objects, "事实对象类型不存在")
        _require(
            not (fact.type_id not in mappings and index.children(fact.type_id)),
            "虚拟父对象不能保存直接事实",
        )
        props = {p.name: p for p in index.effective_properties(fact.type_id)}
        for name, value in fact.values.items():
            _require(name in props, "事实引用了无效属性")
            _require(check_scalar(value, props[name].value_kind), "事实属性值类型不符")
    for fact in draft.material_links:
        link = index.links.get(fact.type_id)
        _require(link is not None, "事实关系类型不存在")
        _require(fact.source_id in facts and fact.target_id in facts, "事实关系端点不存在")
        _require(
            index.is_a(facts[fact.source_id].type_id, link.source_type_id)
            and index.is_a(facts[fact.target_id].type_id, link.target_type_id),
            "事实关系端点类型不兼容",
        )
    return draft
