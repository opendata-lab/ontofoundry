"""Compile one metric per core metric, preserving dataset scopes and NULL behavior."""

import sqlglot
from sqlglot import exp

from ontofoundry_api.domain.core import ExpressionMetric, RatioMetric, SimpleMetric
from ontofoundry_api.domain.expressions import resolve_metric_expression


def value_sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def condition_sql(column, condition):
    op, values = str(condition.operator), condition.values
    if op in {"is_null", "not_null"}:
        return column + (" IS NULL" if op == "is_null" else " IS NOT NULL")
    if op == "between":
        return f"{column} BETWEEN {value_sql(values[0])} AND {value_sql(values[1])}"
    if op in {"in", "not_in"}:
        return (
            column
            + (" IN (" if op == "in" else " NOT IN (")
            + ", ".join(value_sql(v) for v in values)
            + ")"
        )
    operator = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}[op]
    return f"{column} {operator} {value_sql(values[0])}"


def row_counter(writer, dataset_id):
    dataset = writer.index.datasets[dataset_id]
    if not dataset.columns:
        raise ValueError("行计数没有可引用的登记列，不能保留统计来源")
    column = writer.ref(dataset_id, dataset.columns[0].name)
    return f"COUNT(CASE WHEN {column} IS NULL THEN 1 ELSE 1 END)"


def simple_sql(writer, metric):
    if str(metric.aggregation) == "count":
        raw = row_counter(writer, metric.dataset_id)
        argument = raw[len("COUNT(") : -1]
    else:
        argument = writer.ref(metric.dataset_id, metric.measure.column)
    if metric.filters:
        condition = " AND ".join(
            "(" + condition_sql(writer.ref(metric.dataset_id, c.column.column), c) + ")"
            for c in metric.filters
        )
        argument = f"CASE WHEN {condition} THEN {argument} END"
    name = str(metric.aggregation)
    return (
        f"COUNT(DISTINCT {argument})"
        if name == "count_distinct"
        else f"{name.upper()}({argument})"
    )


def expression_sql(writer, metric):
    resolved = resolve_metric_expression(writer.model, metric)
    text = resolved.text
    for ref in reversed(resolved.references):
        text = text[: ref.start] + writer.ref(ref.dataset_id, ref.column) + text[ref.end :]
    # Replacing a COUNT node changes no literal, NULL branch or sibling algorithm.
    ast = sqlglot.parse_one(text)
    for count in list(ast.find_all(exp.Count)):
        if isinstance(count.this, exp.Star):
            count.replace(sqlglot.parse_one(row_counter(writer, metric.dataset_id)))
    if not resolved.references and not any(isinstance(n, exp.Column) for n in ast.walk()):
        raise ValueError("无列引用的表达式无法在外部保留已声明统计来源")
    return ast.sql()


def export_metrics(writer):
    by_id = {m.id: m for m in writer.model.metrics}
    for index, metric in enumerate(writer.model.metrics):
        path = f"/metrics/{index}"
        try:
            if isinstance(metric, SimpleMetric):
                text = simple_sql(writer, metric)
                dataset_id = metric.dataset_id
            elif isinstance(metric, RatioMetric):
                numerator, denominator = (
                    by_id[metric.numerator_id],
                    by_id[metric.denominator_id],
                )
                # MySQL's unspecified DECIMAL has zero scale and rounds the numerator.
                text = f"CAST(({simple_sql(writer, numerator)}) AS DECIMAL(38, 12)) / NULLIF(({simple_sql(writer, denominator)}), 0)"
                dataset_id = numerator.dataset_id
                if (
                    numerator.filters
                    or denominator.filters
                    or numerator.time_field
                    or denominator.time_field
                ):
                    writer.report.issue(
                        path,
                        "converted",
                        "MetricConvention",
                        "RT-58",
                        "两个分量分别过滤、归周期并聚合后相除；零分母为空",
                        element=metric,
                        severity="warning",
                    )
            else:
                text = expression_sql(writer, metric)
                dataset_id = metric.dataset_id
            description = metric.description
            if getattr(metric, "time_field", None):
                description += (
                    ("\n\n" if description else "")
                    + "指标时间字段："
                    + metric.time_field.column
                )
                writer.report.issue(
                    path + "/time_field",
                    "dropped",
                    "MetricTime",
                    "RT-60",
                    "时间字段写入指标说明和扩展文件；导入扩展包时恢复，单独的 Ossie 文件中不保留结构",
                    element=metric,
                )
            value = {"name": metric.name, "expression": writer.expression(text)}
            if metric.synonyms:
                value["ai_context"] = {"synonyms": metric.synonyms}
            if description:
                value["description"] = description
            if isinstance(metric, ExpressionMetric) and metric.value_kind:
                value["datatype"] = {
                    "string": "String",
                    "integer": "Integer",
                    "decimal": "Decimal",
                    "float": "Float",
                    "boolean": "Boolean",
                    "date": "Date",
                    "datetime": "DateTime",
                }[str(metric.value_kind)]
            writer.maps[writer.scope(dataset_id)]["semantic_model"]["metrics"].append(value)
            writer.report.issue(
                path,
                "converted",
                "metrics",
                "RT-47",
                "一项核心指标输出一项外部指标，保持数据集列与算法",
                element=metric,
            )
        except (ValueError, KeyError, sqlglot.errors.SqlglotError) as error:
            writer.report.issue(
                path,
                "error",
                "metrics",
                "RT-61",
                "指标不能完整导出：" + str(error),
                element=metric,
                completion=True,
            )
