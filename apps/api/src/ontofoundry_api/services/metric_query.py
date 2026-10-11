"""Read-only execution projections of native Ossie metrics; never edit the model."""

import json
import math
from dataclasses import dataclass

import sqlglot
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import Dialect, exp
from sqlglot.errors import ErrorLevel, SqlglotError

from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.semantic_views import connection_alias
from ontofoundry_api.services.errors import NotFoundError, ServiceError
from ontofoundry_api.services.ontology_context import synonyms
from ontofoundry_api.services.ontology_query import snapshot_of

# Exact classes: allowing Func/Expression subclasses would admit UDFs or queries.
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
DIALECTS = {
    "POSTGRES": "postgres",
    "POSTGRESQL": "postgres",
    "MYSQL": "mysql",
    "DORIS": "mysql",
    "SQLITE": "sqlite",
    "ANSI_SQL": "",
}
OPERATORS = {
    "=": exp.EQ,
    "!=": exp.NEQ,
    "<": exp.LT,
    "<=": exp.LTE,
    ">": exp.GT,
    ">=": exp.GTE,
}


def invalid(message, code="METRIC_QUERY_INVALID"):
    return ServiceError(message, code=code, status_code=422)


def expression_for(expression, target):
    dialects = expression.dialects
    chosen = next((d for d in dialects if DIALECTS.get(d.dialect.upper()) == target), None)
    chosen = chosen or next((d for d in dialects if d.dialect.upper() == "ANSI_SQL"), None)
    if chosen is None:
        raise invalid("没有目标方言或 ANSI_SQL 表达式", "METRIC_DIALECT_UNSUPPORTED")
    return parse_expression(chosen.expression, DIALECTS[chosen.dialect.upper()])


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


def vendor_parameters(item):
    result = {}
    for extension in item.custom_extensions:
        if extension.vendor_name != "ONTOFOUNDRY":
            continue
        try:
            data = json.loads(extension.data)
        except (ValueError, TypeError):
            continue  # unrelated opaque vendor payloads remain untouched
        if not isinstance(data, dict):
            continue
        for key in ("time_semantics", "time_field"):
            if key in data:
                if key in result and result[key] != data[key]:
                    raise invalid("平台时间参数存在重复键冲突", "METRIC_TIME_INVALID")
                result[key] = data[key]
    return result


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


@dataclass
class MetricPlan:
    sql: str
    parameters: dict
    columns: list[str]
    limit: int


class MetricCompiler:
    def __init__(self, draft, metric, dialect=""):
        self.draft, self.metric, self.dialect = draft, metric, dialect
        self.model = next(
            m for m in draft.semantic_models if m.id == metric.semantic_model_id
        )
        self.datasets = {
            d.name: d for d in draft.datasets if d.semantic_model_id == self.model.id
        }
        self.tree = expression_for(metric.expression, dialect)
        check_ast(self.tree, aggregate=True)
        references = list(self.tree.find_all(exp.Column))
        if any(len(c.parts) != 2 or c.table not in self.datasets for c in references):
            raise invalid(
                "指标字段必须引用同一语义模型内的 dataset.field", "METRIC_FIELD_INVALID"
            )
        names = list(dict.fromkeys(c.table for c in references))
        self.involved = [self.datasets[n] for n in names]
        for column in references:
            if not any(
                f.dataset_id == self.datasets[column.table].id and f.name == column.name
                for f in draft.dataset_fields
            ):
                raise invalid(
                    "指标引用了不存在的字段：" + column.sql(), "METRIC_FIELD_INVALID"
                )
        self.dataset = self.involved[0] if len(self.involved) == 1 else None
        self.fields = {
            f.name: f
            for f in draft.dataset_fields
            if self.dataset and f.dataset_id == self.dataset.id
        }
        self.table = None
        self.time_semantics, self.time_field = None, None
        if self.dataset:
            try:
                tables = Dialect.get_or_raise("").parse_into(exp.Table, self.dataset.source)
                if len(tables) != 1 or tables[0] is None:
                    raise ValueError("not one table")
                table = tables[0]
                if (
                    any(type(n) not in {exp.Table, exp.Identifier} for n in table.walk())
                    or not table.name
                ):
                    raise ValueError("not a table")
                self.table = table
            except (SqlglotError, ValueError, RecursionError) as exc:
                raise invalid(
                    "数据集 source 必须是限定物理表名", "METRIC_SOURCE_UNSUPPORTED"
                ) from exc
            parameters = {**vendor_parameters(self.dataset), **vendor_parameters(metric)}
            self.time_semantics = parameters.get(
                "time_semantics", "snapshot" if "snapshot_date" in self.fields else "event"
            )
            self.time_field = parameters.get(
                "time_field", "snapshot_date" if "snapshot_date" in self.fields else None
            )
            if (
                self.time_semantics not in ("snapshot", "rolling", "event")
                or (
                    self.time_field is not None
                    and (
                        not isinstance(self.time_field, str)
                        or self.time_field not in self.fields
                    )
                )
                or (self.time_semantics != "event" and self.time_field is None)
            ):
                raise invalid(
                    "时间参数必须指定合法语义及当前数据集时间字段", "METRIC_TIME_INVALID"
                )
            # Validate only referenced fields here; unused complex fields do not
            # make an otherwise executable metric read-only.
            self.rewritten = self.tree.transform(
                lambda n: self.field(n.name) if isinstance(n, exp.Column) else n
            )
            if self.time_semantics in ("snapshot", "rolling"):
                self.field(self.time_field)

    def field_name(self, name):
        prefix = self.dataset.name + "."
        name = name[len(prefix) :] if name.startswith(prefix) else name
        if name not in self.fields:
            raise invalid("字段不属于当前数据集：" + name, "METRIC_FIELD_INVALID")
        return name

    def field(self, name):
        tree = expression_for(self.fields[name].expression, self.dialect)
        check_ast(tree, aggregate=False)
        for column in tree.find_all(exp.Column):
            qualifiers = [p.name for p in column.parts[:-1]]
            table_parts = [p.name for p in self.table.parts]
            if qualifiers and qualifiers not in (
                [self.dataset.name],
                table_parts,
                [self.table.name],
            ):
                raise invalid(
                    "字段表达式引用了其他表：" + column.sql(), "METRIC_FIELD_INVALID"
                )
            column.set("table", exp.to_identifier("__metric_source", quoted=True))
            column.set("db", None)
            column.set("catalog", None)
            column.set("this", exp.to_identifier(column.name, quoted=True))
        return exp.Paren(this=tree)

    def explanation(self):
        names = {d.name for d in self.involved}
        joins = [
            {
                "name": r.name,
                "from": r.from_,
                "to": r.to,
                "from_columns": list(r.from_columns),
                "to_columns": list(r.to_columns),
            }
            for r in self.draft.dataset_relationships
            if r.semantic_model_id == self.model.id and r.from_ in names and r.to in names
        ]
        return {
            "datasets": [
                {"id": str(d.id), "name": d.name, "source": d.source} for d in self.involved
            ],
            "dataset_relationships": joins,
            "reason": "指标引用多个数据集，P4 暂只解释、不执行"
            if len(names) > 1
            else "指标没有显式引用数据集，无法确定数据源",
        }

    def compile(self, *, group_by=None, filters=None, limit=100, as_of=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise invalid("limit 必须为 1 到 1000 的整数")
        group_by, filters = group_by or [], filters or []
        if (
            not isinstance(group_by, list)
            or len(group_by) > 100
            or any(not isinstance(f, str) for f in group_by)
        ):
            raise invalid("group_by 必须为当前数据集字段列表")
        names = [self.field_name(n) for n in group_by]
        if len(names) != len(set(names)) or self.metric.name in names:
            raise invalid("分组列重复或与指标名相同")
        if not isinstance(filters, list) or len(filters) > 100:
            raise invalid("filters 必须为结构化条件列表，最多 100 项")
        params, conditions, time_filters = {}, [], []

        def bind(value):
            if value is None or not isinstance(value, (str, int, float, bool)):
                raise invalid("过滤值必须为非空标量；空值请使用 is_null/not_null")
            if isinstance(value, float) and not math.isfinite(value):
                raise invalid("过滤数值必须为有限数")
            key = "p" + str(len(params))
            params[key] = value
            return exp.Placeholder(this=key)

        for f in filters:
            if (
                not isinstance(f, dict)
                or set(f) - {"field", "op", "value"}
                or not isinstance(f.get("field"), str)
            ):
                raise invalid("过滤条件必须包含 field、op 和需要的 value")
            name = self.field_name(f["field"])
            field, op, value = self.field(name), f.get("op"), f.get("value")
            if not isinstance(op, str):
                raise invalid("过滤运算符必须为字符串")
            if name == self.time_field:
                time_filters.append(f)
            if op in OPERATORS:
                condition = OPERATORS[op](this=field, expression=bind(value))
            elif op == "in":
                if not isinstance(value, list) or not 1 <= len(value) <= 1000:
                    raise invalid("in 需要 1 到 1000 个标量值")
                condition = exp.In(this=field, expressions=[bind(v) for v in value])
            elif op == "between":
                if not isinstance(value, list) or len(value) != 2:
                    raise invalid("between 需要两个标量值")
                condition = exp.Between(this=field, low=bind(value[0]), high=bind(value[1]))
            elif op in ("is_null", "not_null"):
                if "value" in f and value is not None:
                    raise invalid("空值条件不接受 value")
                condition = exp.Is(this=field, expression=exp.Null())
                if op == "not_null":
                    condition = exp.Not(this=condition)
            else:
                raise invalid("不支持的过滤运算符")
            conditions.append(condition)

        if self.time_semantics in ("snapshot", "rolling"):
            if as_of is not None:
                if time_filters or not isinstance(as_of, str) or not as_of.strip():
                    raise invalid(
                        "as_of 必须为日期字符串，且不能同时过滤时间字段",
                        "METRIC_TIME_INVALID",
                    )
                date = self.field(self.time_field)
                latest = (
                    exp.select(exp.Max(this=date.copy()))
                    .from_(self.table.copy().as_("__metric_source"))
                    .where(exp.LTE(this=date.copy(), expression=bind(as_of)))
                )
                conditions.append(exp.EQ(this=date, expression=exp.Subquery(this=latest)))
            elif len(time_filters) != 1 or time_filters[0].get("op") != "=":
                raise invalid(
                    f"快照/滚动指标不能跨快照聚合，请对 {self.time_field} 等值过滤或提供 as_of",
                    "METRIC_SNAPSHOT_REQUIRED",
                )
        elif as_of is not None:
            raise invalid(
                "事件指标请使用时间字段 filters，不能使用 as_of", "METRIC_TIME_INVALID"
            )
        query = exp.select(
            *[self.field(n).as_(n, quoted=True) for n in names],
            self.rewritten.copy().as_(self.metric.name, quoted=True),
        ).from_(self.table.copy().as_("__metric_source"))
        if conditions:
            query = query.where(exp.and_(*conditions))
        if names:
            query = query.group_by(*[self.field(n) for n in names]).order_by(
                *[exp.column(n, quoted=True) for n in names]
            )
        query = query.limit(limit + 1)
        return MetricPlan(
            serialize(query, self.dialect), params, names + [self.metric.name], limit
        )


def connection_for(db, workspace_id, model):
    return db.scalar(
        select(ConnectionRecord).where(
            ConnectionRecord.workspace_id == workspace_id,
            ConnectionRecord.name == connection_alias(model),
        )
    )


def target_dialect(connection):
    return DIALECTS.get(connection.kind.upper(), "") if connection else ""


def list_metrics(db, version, *, query="", semantic_model=None):
    draft = OntologyDraft.model_validate(snapshot_of(version))
    items = []
    for metric in draft.metrics:
        model = next(m for m in draft.semantic_models if m.id == metric.semantic_model_id)
        if semantic_model and semantic_model not in (
            str(model.id),
            model.name,
            model.map_name,
        ):
            continue
        aliases = synonyms(metric.ai_context)
        display = draft.extension_v4.display_names.get(str(metric.id)) or next(
            iter(aliases), metric.name
        )
        if (
            query.casefold()
            not in " ".join(
                [metric.name, display, metric.description or "", *aliases]
            ).casefold()
        ):
            continue
        item = dict(
            id=str(metric.id),
            name=metric.name,
            technical_name=metric.name,
            display_name=display,
            synonyms=aliases,
            description=metric.description,
            semantic_model={"id": str(model.id), "name": model.name},
            connection_alias=connection_alias(model),
            executable=False,
            reason=None,
            datasets=[],
            group_by_fields=[],
            filter_fields=[],
        )
        try:
            connection = connection_for(db, version.workspace_id, model)
            declared = expression_for(metric.expression, target_dialect(connection))
            names = {c.table for c in declared.find_all(exp.Column) if len(c.parts) == 2}
            item["datasets"] = [
                dict(id=str(d.id), name=d.name, source=d.source)
                for d in draft.datasets
                if d.semantic_model_id == model.id and d.name in names
            ]
            compiler = MetricCompiler(draft, metric, target_dialect(connection))
            item.update(compiler.explanation())
            if compiler.dataset:
                fields = []
                for field in compiler.fields.values():
                    try:
                        compiler.field(field.name)
                    except ServiceError:
                        continue
                    fields.append(
                        dict(
                            name=field.name,
                            datatype=field.datatype,
                            synonyms=synonyms(field.ai_context),
                            dimension=field.dimension,
                        )
                    )
                item.update(
                    executable=connection is not None,
                    reason=None
                    if connection
                    else "尚未配置数据集对应的数据连接，仅可生成 SQL",
                    group_by_fields=fields,
                    filter_fields=fields,
                    time_semantics=compiler.time_semantics,
                    time_field=compiler.time_field,
                    requires_snapshot_filter=compiler.time_semantics
                    in ("snapshot", "rolling"),
                )
        except ServiceError as exc:
            item.update(reason=exc.message, reason_code=exc.code)
        items.append(item)
    return {"version_id": version.id, "items": items}


def query_metric(db, version, settings, metric_id, **arguments):
    draft = OntologyDraft.model_validate(snapshot_of(version))
    metric = next((m for m in draft.metrics if str(m.id) == metric_id), None)
    if metric is None:
        raise NotFoundError("已发布版本中不存在此指标")
    model = next(m for m in draft.semantic_models if m.id == metric.semantic_model_id)
    connection = connection_for(db, version.workspace_id, model)
    compiler = MetricCompiler(draft, metric, target_dialect(connection))
    value = dict(
        metric_id=metric_id,
        version_id=version.id,
        sql=None,
        columns=[],
        rows=[],
        truncated=False,
        warnings=[],
        executable=False,
        dialect=target_dialect(connection) or "ANSI_SQL",
        connection_alias=connection_alias(model),
        datasets=compiler.explanation()["datasets"],
    )
    if compiler.dataset is None:
        return {**value, **compiler.explanation()}
    plan = compiler.compile(**arguments)
    value.update(sql=plan.sql, parameters=plan.parameters, columns=plan.columns)
    if connection is None:
        return {**value, "reason": "尚未配置数据集对应的数据连接，仅返回 SQL，不执行"}
    from ontofoundry_api.api.connections import connect_readonly

    try:
        with connect_readonly(
            connection, settings, timeout_ms=settings.metric_query_timeout_seconds * 1000
        ) as sql:
            rows = sql.exec_driver_sql(plan.sql, plan.parameters).fetchmany(plan.limit + 1)
    except (SQLAlchemyError, HTTPException) as exc:
        underlying = getattr(exc, "orig", None) or getattr(exc, "__cause__", None)
        underlying = getattr(underlying, "orig", underlying)
        if (
            getattr(underlying, "sqlstate", None) == "57014"
            or (getattr(underlying, "args", ()) and underlying.args[0] in (3024, 1205))
            or isinstance(underlying, TimeoutError)
        ):
            raise invalid("指标查询超时，请缩小查询范围", "METRIC_QUERY_TIMEOUT") from exc
        raise invalid(
            "指标只读查询失败，请检查连接、物理字段和字段类型", "METRIC_QUERY_FAILED"
        ) from exc
    value.update(
        executable=True,
        rows=[dict(zip(plan.columns, row, strict=True)) for row in rows[: plan.limit]],
        truncated=len(rows) > plan.limit,
    )
    if value["truncated"]:
        value["warnings"].append(f"结果超过 limit={plan.limit}，仅返回前 {plan.limit} 行")
    return value
