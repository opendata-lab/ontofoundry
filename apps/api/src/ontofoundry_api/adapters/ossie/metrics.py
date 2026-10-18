"""Single-dataset metric translation with conservative AST shape recognition."""

from __future__ import annotations

import math
from collections import Counter

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ontofoundry_api.domain.core import (
    Condition,
    ExpressionMetric,
    RatioMetric,
    SimpleMetric,
)

from .ids import display_name, technical_name


def unwrap(ast):
    while isinstance(ast, exp.Paren):
        ast = ast.this
    return ast


def literal(ast):
    ast = unwrap(ast)
    if isinstance(ast, exp.Null):
        return None
    if isinstance(ast, exp.Boolean):
        return ast.this
    if isinstance(ast, exp.Neg):
        value = literal(ast.this)
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError("不是数值常量")
        return -value
    if isinstance(ast, exp.Literal):
        if ast.is_string:
            return ast.this
        value = (
            float(ast.this) if any(c in ast.this.lower() for c in ".e") else int(ast.this)
        )
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("非有限数值")
        return value
    raise ValueError("条件值不是标量常量")


def column_reference(ast, dataset):
    ast = unwrap(ast)
    if not isinstance(ast, exp.Column) or ast.table != dataset.name or ast.db:
        raise ValueError("不是本数据集直接列")
    return {"dataset_id": dataset.id, "column": ast.name}


def fixed_filters(ast, dataset):
    ast = unwrap(ast)
    if isinstance(ast, exp.And):
        return [*fixed_filters(ast.this, dataset), *fixed_filters(ast.expression, dataset)]
    operator = None
    values = []
    column = None
    negated = isinstance(ast, exp.Not)
    if negated:
        ast = unwrap(ast.this)
    if isinstance(ast, exp.Is) and isinstance(ast.expression, exp.Null):
        operator = "not_null" if negated else "is_null"
        column = ast.this
    elif isinstance(ast, exp.In) and not ast.args.get("query"):
        operator = "not_in" if negated else "in"
        column = ast.this
        values = [literal(v) for v in ast.expressions]
    elif not negated and isinstance(ast, exp.Between):
        operator = "between"
        column = ast.this
        values = [literal(ast.args["low"]), literal(ast.args["high"])]
    elif not negated:
        mapping = {
            exp.EQ: "eq",
            exp.NEQ: "ne",
            exp.GT: "gt",
            exp.GTE: "ge",
            exp.LT: "lt",
            exp.LTE: "le",
        }
        operator = mapping.get(type(ast))
        if operator:
            column = ast.this
            values = [literal(ast.expression)]
    if not operator:
        raise ValueError("条件超出固定 AND 子集")
    return [
        Condition(
            column=column_reference(column, dataset), operator=operator, values=values
        )
    ]


def filtered_value(ast, dataset):
    ast = unwrap(ast)
    if not isinstance(ast, exp.Case):
        return ast, []
    cases = ast.args.get("ifs", [])
    default = ast.args.get("default")
    if (
        ast.this
        or len(cases) != 1
        or (default is not None and not isinstance(default, exp.Null))
    ):
        raise ValueError("不是单 WHEN 且 ELSE NULL 的固定 CASE")
    return unwrap(cases[0].args["true"]), fixed_filters(cases[0].this, dataset)


def row_counter(ast, dataset):
    ast = unwrap(ast)
    if not isinstance(ast, exp.Case) or ast.this:
        return False
    cases = ast.args.get("ifs", [])
    if len(cases) != 1:
        return False
    condition = cases[0].this
    try:
        if not isinstance(condition, exp.Is) or not isinstance(
            condition.expression, exp.Null
        ):
            return False
        column_reference(condition.this, dataset)
        return (
            isinstance(cases[0].args["true"], exp.Literal)
            and isinstance(ast.args.get("default"), exp.Literal)
            and not cases[0].args["true"].is_string
            and not ast.args["default"].is_string
            and literal(cases[0].args["true"]) == 1
            and literal(ast.args["default"]) == 1
        )
    except (ValueError, AttributeError):
        return False


def simple_shape(ast, dataset):
    ast = unwrap(ast)
    aggregations = {
        exp.Sum: "sum",
        exp.Avg: "avg",
        exp.Median: "median",
        exp.Min: "min",
        exp.Max: "max",
    }
    if isinstance(ast, exp.Count):
        arg = unwrap(ast.this)
        if isinstance(arg, exp.Distinct):
            if len(arg.expressions) != 1:
                raise ValueError("多列去重保留完整算法")
            value, filters = filtered_value(arg.expressions[0], dataset)
            return {
                "aggregation": "count_distinct",
                "measure": column_reference(value, dataset),
                "filters": filters,
            }
        if isinstance(arg, exp.Star) or row_counter(arg, dataset):
            return {"aggregation": "count", "filters": []}
        value, filters = filtered_value(arg, dataset)
        if row_counter(value, dataset):
            return {"aggregation": "count", "filters": filters}
        raise ValueError("COUNT(列) 不等价于行计数")
    aggregation = aggregations.get(type(ast))
    if not aggregation:
        raise ValueError("不是固定聚合")
    value, filters = filtered_value(ast.this, dataset)
    return {
        "aggregation": aggregation,
        "measure": column_reference(value, dataset),
        "filters": filters,
    }


def variant(raw):
    value = raw["expression"]
    if isinstance(value, str):
        return value, None
    variants = value["dialects"]
    chosen = next(
        (v for v in variants if v["dialect"] == "ANSI_SQL"),
        variants[0] if variants else None,
    )
    if chosen is None:
        raise ValueError("指标缺少表达式")
    return chosen["expression"], None if chosen["dialect"] == "ANSI_SQL" else chosen[
        "dialect"
    ].lower()


def normalize(ast, scope):
    sources = set()
    for c in list(ast.find_all(exp.Column)):
        if c.db or c.catalog:
            raise ValueError("指标列引用不是数据集字段两段路径")
        if c.table:
            candidates = [scope.datasets[c.table]] if c.table in scope.datasets else []
        else:
            candidates = [d for d in scope.datasets.values() if c.name in d.fields]
        if len(candidates) != 1 or c.name not in candidates[0].fields:
            raise ValueError(f"字段 {c.sql()} 不能唯一解析来源")
        info = candidates[0]
        sources.add(info.raw["name"])
        replacement = info.fields[c.name].copy()
        for physical in replacement.find_all(exp.Column):
            physical.set("table", exp.to_identifier(info.model.name, quoted=True))
        c.replace(replacement)
    return sources


def component_shape(ast, dataset):
    ast = unwrap(ast)
    if isinstance(ast, exp.Cast):
        allowed = {"DECIMAL", "DOUBLE", "FLOAT", "REAL", "BIGDECIMAL"}
        if str(ast.args["to"].this).split(".")[-1] not in allowed:
            raise ValueError("不识别改变整数算法的 CAST")
        ast = unwrap(ast.this)
    return simple_shape(ast, dataset)


def ratio_components(ast, dataset):
    ast = unwrap(ast)
    if not isinstance(ast, exp.Div):
        raise ValueError("不是固定比率")
    denominator = unwrap(ast.expression)
    if not isinstance(denominator, exp.Nullif) or literal(denominator.expression) != 0:
        raise ValueError("缺少 NULLIF 零分母约定")
    return component_shape(ast.this, dataset), component_shape(denominator.this, dataset)


def shape_key(shape):
    measure = shape.get("measure")
    if measure and hasattr(measure, "model_dump"):
        measure = measure.model_dump()
    return (
        str(shape["aggregation"]),
        (str(measure["dataset_id"]), measure["column"]) if measure else None,
        tuple(f.model_dump_json() for f in shape.get("filters", [])),
    )


def import_metrics(importer, scope):
    t = importer.t
    used = {m.technical_name.casefold() for m in t.model.metrics}
    labels = {m.name.casefold() for m in t.model.metrics}
    pending = []
    names = Counter(
        raw.get("name")
        for raw in scope.raw["semantic_model"].get("metrics", [])
        if isinstance(raw, dict)
    )
    for i, raw in enumerate(scope.raw["semantic_model"].get("metrics", [])):
        path = scope.path + f"/semantic_model/metrics/{i}"
        if not t.valid(path):
            continue
        if names[raw["name"]] > 1:
            t.issue(
                path,
                "error",
                "Metric",
                None,
                "同一作用域指标名重复，不能任取第一项",
                completion=True,
            )
            continue
        try:
            text, dialect = variant(raw)
            statements = sqlglot.parse(text, read=dialect)
            if len(statements) != 1 or statements[0] is None:
                raise ValueError("指标只能是一个非空表达式")
            ast = statements[0]
            if any(
                isinstance(
                    n,
                    (
                        exp.Query,
                        exp.Table,
                        exp.Join,
                        exp.Window,
                        exp.DDL,
                        exp.DML,
                        exp.Command,
                    ),
                )
                for n in ast.walk()
            ):
                t.issue(
                    path,
                    "error",
                    "Metric",
                    "RT-69",
                    "指标包含查询、窗口或额外作用域，不进入 core-1",
                    completion=True,
                )
                continue
            sources = normalize(ast, scope)
            if len(sources) > 1:
                t.issue(
                    path,
                    "error",
                    "Metric",
                    "RT-69",
                    "指标引用多个数据集："
                    + "、".join(sorted(sources))
                    + "；需要业务改写，未形成核心指标",
                    completion=True,
                )
                continue
            if not sources:
                t.issue(
                    path,
                    "error",
                    "Metric",
                    "RT-47",
                    "指标没有可确定的列来源，请选择数据集；候选："
                    + "、".join(scope.datasets),
                    completion=True,
                )
                continue
            dataset = scope.datasets[next(iter(sources))].model
            common = {
                "id": t.id("metric:" + scope.key + "." + raw["name"]),
                "name": display_name(
                    importer.extension.name("metric:" + raw["name"], raw["name"]), labels
                ),
                "technical_name": technical_name(raw["name"], used),
                "description": raw.get("description", ""),
                "synonyms": importer.extension.labels("synonyms", "metric:" + raw["name"]),
            }
            if dialect:
                common["description"] = "\n\n".join(
                    filter(None, [common["description"], "来源表达式方言：" + dialect])
                )
                t.issue(
                    path,
                    "converted",
                    "MetricDialect",
                    "RT-45",
                    "按来源方言解析并保留方言说明，未把来源标记为 ANSI_SQL",
                    targets=[common["id"]],
                    severity="warning",
                )
            try:
                shape = simple_shape(ast, dataset)
                metric = SimpleMetric(
                    **common, kind="simple", dataset_id=dataset.id, **shape
                )
                rule = (
                    "RT-50"
                    if shape["aggregation"] == "count_distinct"
                    else "RT-55"
                    if shape.get("filters")
                    else "RT-47"
                )
                if t.accept("metrics", metric, path, rule=rule):
                    pending.append((metric, ast, dataset, path, None))
            except ValueError:
                # Keep algorithms (including nullable COUNT, ELSE 0 and complex
                # DISTINCT) as one metric. No invented ratio components.
                metric = ExpressionMetric(
                    **common,
                    kind="expression",
                    dataset_id=dataset.id,
                    expression=ast.sql(),
                    value_kind={
                        "Integer": "integer",
                        "Decimal": "decimal",
                        "Float": "float",
                        "Boolean": "boolean",
                        "String": "string",
                        "Date": "date",
                        "DateTime": "datetime",
                    }.get(raw.get("datatype")),
                )
                if t.accept(
                    "metrics",
                    metric,
                    path,
                    rule="RT-56" if ast.find(exp.DPipe) else "RT-49",
                ):
                    pending.append((metric, ast, dataset, path, common))
        except (ValueError, SqlglotError) as error:
            t.issue(
                path,
                "error",
                "Metric",
                "RT-47",
                f"指标来源或表达式未闭合：{error}",
                completion=True,
            )
    # All declared simple components exist before ratio recognition.
    for _metric, ast, dataset, path, common in pending:
        if common is None:
            continue
        try:
            numerator, denominator = ratio_components(ast, dataset)
            matches = []
            for shape in (numerator, denominator):
                matching = [
                    m
                    for m in t.model.metrics
                    if isinstance(m, SimpleMetric)
                    and m.dataset_id == dataset.id
                    and shape_key(
                        {
                            "aggregation": m.aggregation,
                            "measure": m.measure.model_dump() if m.measure else None,
                            "filters": m.filters,
                        }
                    )
                    == shape_key(
                        {
                            "aggregation": shape["aggregation"],
                            "measure": shape.get("measure"),
                            "filters": shape.get("filters", []),
                        }
                    )
                ]
                if len(matching) != 1:
                    raise ValueError("比率分量没有唯一对应的已登记 simple 指标")
                matches.append(matching[0])
            ratio = RatioMetric(
                **common,
                kind="ratio",
                numerator_id=matches[0].id,
                denominator_id=matches[1].id,
            )
            t.replace(
                "metrics",
                ratio,
                path,
                rule="RT-55",
                message="复用已登记的同数据集聚合分量，不生成辅助指标",
            )
        except ValueError:
            continue
