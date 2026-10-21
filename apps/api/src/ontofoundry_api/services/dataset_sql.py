"""Pure SELECT validation and physical lineage shared by every dataset consumer."""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from ontofoundry_api.services.errors import DatasetSourceError

# Exact classes intentionally exclude anonymous functions, DDL, DML, locks,
# parameters, SELECT INTO, table functions and engine-specific side effects.
QUERY_NODES = {
    "Select", "Union", "Intersect", "Except", "Subquery", "With", "CTE",
    "From", "Table", "TableAlias", "Join", "Where", "Group", "Having",
    "Order", "Ordered", "Limit", "Offset", "Alias", "Distinct", "Star",
    "Column", "Identifier", "Literal", "Null", "Boolean", "Paren", "Tuple",
    "Case", "If", "Add", "Sub", "Mul", "Div", "Mod", "Neg", "EQ", "NEQ",
    "LT", "LTE", "GT", "GTE", "And", "Or", "Not", "Is", "In", "Between",
    "Like", "ILike", "Escape", "Exists", "DPipe", "Concat", "Coalesce",
    "Nullif", "Cast", "TryCast", "DataType", "DataTypeParam", "Lower", "Upper",
    "Trim", "Length", "Abs", "Round", "Ceil", "Floor", "Count", "Sum", "Avg",
    "Min", "Max", "Stddev", "StddevPop", "StddevSamp", "Variance", "VariancePop",
    "Date", "DateTrunc", "TimestampTrunc", "Extract", "Var", "Interval",
    "DateAdd", "DateSub", "TsOrDsToDate", "TimeToStr", "StrToDate", "CurrentDate",
    "CurrentTimestamp", "Window", "WindowSpec", "RowNumber", "Rank", "DenseRank",
    "Lag", "Lead", "FirstValue", "LastValue", "Filter", "NullSafeEQ",
}


def dialect_for(kind):
    return {"postgresql": "postgres", "doris": "mysql", "ANSI_SQL": ""}.get(kind, kind or "")


def fail(message, code="SQL_UNSUPPORTED", **details):
    raise DatasetSourceError(message, code=code, details=details)


def parse_query(sql, dialect=None):
    if not sql or len(sql.encode()) > 65536:
        fail("SQL 为空或超过 64 KiB")
    try:
        statements = sqlglot.parse(sql, read=dialect_for(dialect))
    except (SqlglotError, RecursionError) as exc:
        raise DatasetSourceError("SQL 无法解析", code="SQL_UNSUPPORTED") from exc
    if len(statements) != 1 or statements[0] is None:
        fail("只允许一条 SELECT，禁止多语句", "SQL_MULTIPLE_STATEMENTS")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        fail("来源只能是只读 SELECT", "SQL_NOT_READ_ONLY")
    nodes = list(tree.walk())
    if len(nodes) > 10000:
        fail("SQL 超过安全复杂度限制")
    for node in nodes:
        if isinstance(node, exp.With) and node.args.get("recursive"):
            fail("首版不支持递归 CTE")
        if type(node).__name__ not in QUERY_NODES:
            fail("SQL 包含非只读或未支持构造：" + type(node).__name__, "SQL_NOT_READ_ONLY")
        if isinstance(node, exp.Var) and not isinstance(node.parent, (exp.Extract, exp.Interval, exp.DateTrunc, exp.TimestampTrunc)):
            fail("SQL 包含不支持的变量")
        if isinstance(node, exp.Table) and not isinstance(node.this, exp.Identifier):
            fail("不支持表函数或动态来源")
    return tree


@dataclass(frozen=True)
class TableReference:
    schema: str | None
    name: str
    catalog: str | None = None


def physical_tables(tree):
    result = set()
    for scope in traverse_scope(tree):
        for _, source in scope.selected_sources.values():
            if isinstance(source, exp.Table):
                result.add(TableReference(source.db or None, source.name, source.catalog or None))
    return sorted(result, key=lambda t: (t.catalog or "", t.schema or "", t.name))


def qualified_query(tree, default_schema, dialect):
    tree = tree.copy()
    for scope in traverse_scope(tree):
        for _, source in scope.selected_sources.values():
            if isinstance(source, exp.Table) and not source.db and default_schema:
                source.set("db", exp.to_identifier(default_schema, quoted=True))
    return tree.sql(dialect=dialect_for(dialect), identify=True, comments=False)
