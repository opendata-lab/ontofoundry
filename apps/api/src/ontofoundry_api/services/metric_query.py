"""Bounded aggregate previews over registered core datasets."""

from decimal import Decimal

import sqlglot
from sqlglot import Dialect, exp
from sqlglot.errors import ErrorLevel, SqlglotError

from ontofoundry_api.domain.core import RatioMetric, SimpleMetric
from ontofoundry_api.domain.expressions import resolve_metric_expression
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.validation import physical_value_kind
from ontofoundry_api.services.dataset_sources import resolve_dataset
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.readonly import connect_readonly

SCALARS = {
    exp.Column,
    exp.Identifier,
    exp.Literal,
    exp.Null,
    exp.Boolean,
    exp.Paren,
    exp.Case,
    exp.If,
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.Mod,
    exp.Neg,
    exp.EQ,
    exp.NEQ,
    exp.LT,
    exp.LTE,
    exp.GT,
    exp.GTE,
    exp.And,
    exp.Or,
    exp.Not,
    exp.Is,
    exp.In,
    exp.Between,
    exp.DPipe,
    exp.Concat,
    exp.Coalesce,
    exp.Nullif,
    exp.Cast,
    exp.DataType,
    exp.DataTypeParam,
    exp.Lower,
    exp.Upper,
    exp.Trim,
    exp.Length,
    exp.Abs,
    exp.Round,
    exp.Ceil,
    exp.Floor,
}
AGGREGATES = {
    exp.Count,
    exp.Sum,
    exp.Avg,
    exp.Min,
    exp.Max,
    exp.Stddev,
    exp.StddevPop,
    exp.StddevSamp,
    exp.Variance,
    exp.VariancePop,
}
CAST_TYPES = {
    "TINYINT",
    "SMALLINT",
    "INT",
    "BIGINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "TEXT",
    "VARCHAR",
    "CHAR",
    "BOOLEAN",
    "DATE",
    "TIME",
    "TIMESTAMP",
    "TIMESTAMPTZ",
}


def invalid(message, code="expression_unsupported"):
    return ServiceError(message, code=code, status_code=422)


def parse_expression(value, dialect):
    try:
        if len(value) > 100_000:
            raise invalid("表达式超过安全执行大小限制")
        trees = sqlglot.parse(value, read=dialect)
        if len(trees) != 1 or trees[0] is None:
            raise invalid("指标表达式只能包含一个表达式，禁止多语句")
        return trees[0]
    except (SqlglotError, RecursionError) as exc:
        raise invalid("指标表达式无法解析", "METRIC_EXPRESSION_UNSUPPORTED") from exc


def check_ast(tree, *, aggregate):
    allowed = SCALARS | (AGGREGATES | {exp.Distinct, exp.Star} if aggregate else set())
    nodes = list(tree.walk())
    if len(nodes) > 5000:
        raise invalid("表达式超过安全执行复杂度限制")
    for node in nodes:
        if type(node) not in allowed:
            raise invalid(
                "表达式包含不支持的 SQL 构造或函数：" + type(node).__name__,
                "METRIC_EXPRESSION_UNSUPPORTED",
            )
        if isinstance(node, exp.DataType) and node.this.name not in CAST_TYPES:
            raise invalid("不支持该 CAST 类型", "METRIC_EXPRESSION_UNSUPPORTED")
        if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
            raise invalid("仅 COUNT(*) 可以使用星号", "METRIC_EXPRESSION_UNSUPPORTED")
        if isinstance(node, exp.Column) and node.is_star:
            raise invalid("禁止限定星号字段", "METRIC_FIELD_INVALID")
    if aggregate and not any(type(n) in AGGREGATES for n in nodes):
        raise invalid("仅支持聚合指标", "METRIC_EXPRESSION_UNSUPPORTED")
    if aggregate:
        for column in tree.find_all(exp.Column):
            parents = []
            parent = column.parent
            while parent is not None:
                parents.append(parent)
                parent = parent.parent
            if not any(type(p) in AGGREGATES for p in parents):
                raise invalid("指标字段必须位于聚合函数内", "METRIC_EXPRESSION_UNSUPPORTED")
        for node in nodes:
            if type(node) in AGGREGATES:
                parent = node.parent
                while parent is not None:
                    if type(parent) in AGGREGATES:
                        raise invalid("禁止嵌套聚合函数", "METRIC_EXPRESSION_UNSUPPORTED")
                    parent = parent.parent


def serialize(tree, dialect):
    # Render driver-native named binds from AST nodes. Do not replace text inside
    # literals, and do not feed SQLAlchemy.text literals containing ':name'.
    base = Dialect.get_or_raise(dialect).generator_class

    class BoundGenerator(base):
        MOD_OPERATOR = "%%" if dialect in ("postgres", "mysql") else base.MOD_OPERATOR

        def literal_sql(self, expression):
            result = super().literal_sql(expression)
            return result.replace("%", "%%") if dialect in ("postgres", "mysql") else result

        def identifier_sql(self, expression):
            result = super().identifier_sql(expression)
            return result.replace("%", "%%") if dialect in ("postgres", "mysql") else result

        def placeholder_sql(self, expression):
            name = expression.name
            return f"%({name})s" if dialect in ("postgres", "mysql") else f":{name}"

    try:
        return BoundGenerator(
            dialect=dialect,
            identify=True,
            comments=False,
            unsupported_level=ErrorLevel.RAISE,
        ).generate(tree)
    except SqlglotError as exc:
        raise invalid("表达式无法无损转译到目标方言", "METRIC_DIALECT_UNSUPPORTED") from exc


def dataset_for(draft, metric):
    if isinstance(metric, RatioMetric):
        metric = next(m for m in draft.metrics if m.id == metric.numerator_id)
    return DraftIndex(draft).datasets[metric.dataset_id]


def value_kind(draft, metric):
    if isinstance(metric, RatioMetric):
        return "decimal"
    if not isinstance(metric, SimpleMetric):
        return metric.value_kind
    if metric.aggregation in {"count", "count_distinct"}:
        return "integer"
    if metric.aggregation in {"avg", "median"}:
        return "decimal"
    dataset = dataset_for(draft, metric)
    column = next(
        (c for c in dataset.columns or [] if c.name == metric.measure.column), None
    )
    return physical_value_kind(column.physical_type) if column else None


class MetricCompiler:
    def __init__(
        self, draft, metric, *, db=None, workspace_id=None, source=None, time_range=None
    ):
        self.draft, self.metric = draft, metric
        self.db, self.workspace_id = db, workspace_id
        self.dataset = dataset_for(draft, metric)
        self.source = source or resolve_dataset(db, workspace_id, self.dataset)
        self.dialect = (
            "postgres"
            if self.source.connection.kind == "postgresql"
            else "mysql"
            if self.source.connection.kind in {"mysql", "doris"}
            else self.source.connection.kind
        )
        self.params = {}
        self.time_range = time_range
        self.snapshot_column = self.dataset.snapshot_date_column
        if not self.dataset.columns:
            raise invalid("数据集列清单尚未就绪，无法预览", "binding_not_ready")
        self.known = {c.name for c in self.dataset.columns}

    def identifier(self, name):
        return serialize(exp.to_identifier(name, quoted=True), self.dialect)

    def column(self, name):
        if name not in self.known:
            raise invalid("指标列未登记", "binding_not_ready")
        return "d." + self.identifier(name)

    def bind(self, value):
        name = f"p{len(self.params)}"
        self.params[name] = value
        return f"%({name})s" if self.dialect in {"mysql", "postgres"} else ":" + name

    def table(self):
        if self.dataset.source_kind == "query":
            from ontofoundry_api.services.dataset_sources import relation_sql
            tree = parse_expression(relation_sql(self.db, self.workspace_id, self.dataset, source=self.source), self.dialect)
            return "(" + serialize(tree, self.dialect) + ")"
        schema = self.source.schema
        if self.dialect == "sqlite":
            schema = None
        return (self.identifier(schema) + "." if schema else "") + self.identifier(
            self.dataset.table_name
        )

    def month(self, value):
        if self.dialect == "postgres":
            return f"DATE_TRUNC('month', {value})"
        if self.dialect == "mysql":
            return f"DATE_FORMAT({value}, '%%Y-%%m-01')"
        if self.dialect == "sqlite":
            return f"strftime('%Y-%m-01', {value})"
        raise invalid("当前引擎不支持月趋势", "dialect_unsupported")

    def range_predicate(self, column):
        if not self.time_range:
            return []
        return [
            f"{column} >= {self.bind(self.time_range['start'])}",
            f"{column} < {self.bind(self.time_range['end'])}",
        ]

    def predicate(self, cond):
        column, values, op = self.column(cond.column.column), cond.values, cond.operator
        if op in {"is_null", "not_null"}:
            return column + (" IS NULL" if op == "is_null" else " IS NOT NULL")
        if op in {"in", "not_in"}:
            return (
                f"{column} {'NOT IN' if op == 'not_in' else 'IN'} ("
                + ", ".join(self.bind(v) for v in values)
                + ")"
            )
        if op == "between":
            return f"{column} BETWEEN {self.bind(values[0])} AND {self.bind(values[1])}"
        if values[0] is None and op in {"eq", "ne"}:
            return column + (" IS NULL" if op == "eq" else " IS NOT NULL")
        operators = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
        return f"{column} {operators[op]} {self.bind(values[0])}"

    def aggregate(self, metric):
        if isinstance(metric, SimpleMetric):
            if metric.aggregation == "count":
                return "COUNT(*)"
            measure = self.column(metric.measure.column)
            if metric.aggregation == "count_distinct":
                return f"COUNT(DISTINCT {measure})"
            if metric.aggregation == "median":
                if self.dialect != "postgres":
                    raise invalid("当前引擎不支持中位数预览", "dialect_unsupported")
                return f"PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {measure})"
            return f"{metric.aggregation.upper()}({measure})"
        resolve_metric_expression(self.draft, metric)
        tree = parse_expression(metric.expression, "")
        check_ast(tree, aggregate=True)
        for column in tree.find_all(exp.Column):
            self.column(column.name)
            column.set("table", exp.to_identifier("d"))
            column.set("this", exp.to_identifier(column.name, quoted=True))
        for node in list(tree.find_all(exp.Literal)):
            if not node.is_string:
                continue
            name = f"p{len(self.params)}"
            self.params[name] = node.this if node.is_string else Decimal(node.this)
            node.replace(exp.Placeholder(this=name))
        return serialize(tree, self.dialect)

    def component(self, metric, trend):
        aggregate = self.aggregate(metric)
        table = self.table()
        where = (
            [self.predicate(f) for f in metric.filters]
            if isinstance(metric, SimpleMetric)
            else []
        )
        time = self.column(metric.time_field.column) if metric.time_field else None
        snap = self.column(self.snapshot_column) if self.snapshot_column else None
        if self.time_range and not time and not snap:
            raise invalid("指标没有时间字段，无法应用范围", "time_field_required")
        period = self.month(time) if trend and time else None
        if trend and period is None:
            raise invalid("指标没有时间字段，无法生成趋势", "time_field_required")
        if snap:
            global_column = self.identifier(self.snapshot_column)
            selection = self.range_predicate(global_column)
            selection_sql = " WHERE " + " AND ".join(selection) if selection else ""
            if trend and metric.time_field.column == self.snapshot_column:
                global_month = self.month(global_column)
                where.append(
                    f"{snap} IN (SELECT MAX({global_column}) FROM {table} AS snapshot_source{selection_sql} GROUP BY {global_month})"
                )
            else:
                where.append(
                    f"{snap} = (SELECT MAX({global_column}) FROM {table} AS snapshot_source{selection_sql})"
                )
        elif time:
            where += self.range_predicate(time)
        select_fields = (period + " AS period, " if trend else "") + aggregate + " AS value"
        if snap:
            select_fields += f", MAX({snap}) AS snapshot_date"
        return (
            "SELECT "
            + select_fields
            + f" FROM {table} AS d"
            + (" WHERE " + " AND ".join(where) if where else "")
            + (f" GROUP BY {period}" if trend else "")
        )

    def compile(self, trend=False):
        if isinstance(self.metric, RatioMetric):
            components = [
                next(m for m in self.draft.metrics if m.id == mid)
                for mid in (self.metric.numerator_id, self.metric.denominator_id)
            ]
            numerator, denominator = [self.component(m, trend) for m in components]
            if trend:
                dates = (
                    ", n.snapshot_date AS numerator_snapshot_date, d.snapshot_date AS denominator_snapshot_date"
                    if self.snapshot_column
                    else ""
                )
                sql = f"WITH n AS ({numerator}), d AS ({denominator}), periods AS (SELECT period FROM n UNION SELECT period FROM d) SELECT periods.period, 1.0*n.value/NULLIF(d.value,0) AS value{dates} FROM periods LEFT JOIN n ON n.period=periods.period LEFT JOIN d ON d.period=periods.period ORDER BY periods.period"
            else:
                sql = (
                    f"WITH n AS ({numerator}), d AS ({denominator}) SELECT 1.0*n.value/NULLIF(d.value,0) AS value"
                    + (", n.snapshot_date AS snapshot_date" if self.snapshot_column else "")
                    + " FROM n CROSS JOIN d"
                )
        else:
            sql = self.component(self.metric, trend) + (" ORDER BY period" if trend else "")
        # Only generated SELECT statements reach the executor; user expressions
        # have already passed the exact AST and dataset-column allowlists.
        return {
            "sql": sql,
            "params": dict(self.params),
            "dialect": self.dialect,
            "database": self.source.database,
        }


def compile_metric_reference(draft, metric, *, db, workspace_id):
    return MetricCompiler(draft, metric, db=db, workspace_id=workspace_id).compile()


def compile_metric_preview(
    draft, metric, *, db, workspace_id, time_range=None, trend=False
):
    return MetricCompiler(
        draft, metric, db=db, workspace_id=workspace_id, time_range=time_range
    ).compile(trend)


def scalar(value):
    if isinstance(value, Decimal):
        return str(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def execute_metric_preview(
    db, workspace_id, draft, metric, settings, *, time_range=None, trend=False
):
    source = resolve_dataset(db, workspace_id, dataset_for(draft, metric))
    total = compile_metric_preview(
        draft, metric, db=db, workspace_id=workspace_id, time_range=time_range
    )
    trend_query = (
        compile_metric_preview(
            draft,
            metric,
            db=db,
            workspace_id=workspace_id,
            time_range=time_range,
            trend=True,
        )
        if trend
        else None
    )
    with connect_readonly(source.connection, settings, timeout_ms=10000) as conn:
        rows = list(conn.exec_driver_sql(total["sql"], total["params"]).mappings())
        trend_rows = (
            list(conn.exec_driver_sql(trend_query["sql"], trend_query["params"]).mappings())
            if trend_query
            else []
        )
    result = {
        "status": "ok",
        "value": scalar(rows[0]["value"]) if rows else None,
        "value_kind": value_kind(draft, metric),
        "total_query": total,
        "trend_query": trend_query,
        "trend": [
            {"period": str(r["period"])[:10], "value": scalar(r["value"])}
            for r in trend_rows
        ]
        if trend
        else None,
        "snapshot_dates": [],
        "warnings": [],
    }
    for period, row in [(None, r) for r in rows] + [
        (str(r["period"])[:10], r) for r in trend_rows
    ]:
        for column in (
            "snapshot_date",
            "numerator_snapshot_date",
            "denominator_snapshot_date",
        ):
            if column in row and row[column] is not None:
                chosen = {
                    "dataset_id": str(dataset_for(draft, metric).id),
                    "period": period,
                    "date": scalar(row[column]),
                }
                if chosen not in result["snapshot_dates"]:
                    result["snapshot_dates"].append(chosen)
    return result


def metric_projection(draft, metric, *, db=None, workspace_id=None):
    result = {
        **metric.model_dump(mode="json"),
        "value_kind": value_kind(draft, metric),
        "binding_status": "unbound",
    }
    if isinstance(metric, RatioMetric):
        components = {str(m.id): m for m in draft.metrics}
        result.update(
            dataset_id=str(dataset_for(draft, metric).id),
            components={
                "numerator": components[str(metric.numerator_id)].model_dump(mode="json"),
                "denominator": components[str(metric.denominator_id)].model_dump(
                    mode="json"
                ),
            },
        )
    if db is not None:
        try:
            result["sql_reference"] = compile_metric_reference(
                draft, metric, db=db, workspace_id=workspace_id
            )
            result["binding_status"] = "bound"
        except ServiceError:
            pass
    return result
