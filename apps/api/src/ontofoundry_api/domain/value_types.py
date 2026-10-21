"""Value type constraints: one scalar variable (the type's name), boolean result."""

from __future__ import annotations

import re
from uuid import UUID

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ontofoundry_api.domain.core import CoreDraft, Rule, RuleKind, RuleOwnerKind
from ontofoundry_api.domain.expressions import (
    SCALAR_FUNCTIONS,
    ExpressionError,
    ExpressionReference,
    ResolvedExpression,
)

# Built-in Ossie concept names; a value type may not shadow them.
RESERVED_NAMES = frozenset(
    {"string", "integer", "decimal", "float", "boolean", "date", "datetime", "datetimetz", "any"}
)
_BOOLEAN_ROOTS = (
    exp.Predicate,
    exp.Connector,
    exp.Not,
    exp.Boolean,
    exp.In,
    exp.Between,
    exp.RegexpLike,
    exp.Paren,
)
_ALLOWED = (
    exp.Column,
    exp.Identifier,
    exp.Literal,
    exp.Boolean,
    exp.Null,
    exp.Paren,
    exp.Predicate,
    exp.Connector,
    exp.Not,
    exp.In,
    exp.Between,
    exp.Binary,
    exp.Unary,
    exp.Case,
    exp.If,
    exp.Func,
    exp.Tuple,
    exp.DataType,
)
# Constant patterns only; no backreferences, lookarounds or inline flags.
_UNSAFE_REGEX = re.compile(r"\\[1-9]|\(\?[=!<a-zA-Z]")


def _spans(ast, name: str) -> list[tuple[int, int]]:
    """Source positions of the bare value variable, taken from parsed columns."""
    spans = []
    for column in ast.find_all(exp.Column):
        meta = column.this.meta
        if not column.table and column.name.casefold() == name.casefold() and "start" in meta:
            spans.append((meta["start"], meta["end"] + 1))
    return sorted(spans)


def resolve_value_type_rule(draft: CoreDraft, rule: Rule) -> ResolvedExpression:
    value_type = next((v for v in draft.value_types if v.id == rule.owner_id), None)
    if value_type is None:
        raise ExpressionError("规则归属的值类型不存在")
    if rule.rule_kind != RuleKind.CONSTRAINT:
        raise ExpressionError("值类型只能有约束规则")
    text = rule.expression
    if not text.strip():
        raise ExpressionError("表达式不能为空")
    try:
        ast = sqlglot.parse_one(text)
    except SqlglotError as error:
        raise ExpressionError("值类型约束无法解析") from error
    spans = _spans(ast, value_type.name)
    if not spans:
        raise ExpressionError(f"值类型约束必须引用当前值 {value_type.name}")
    if not isinstance(ast, _BOOLEAN_ROOTS) or isinstance(ast, exp.Paren) and not isinstance(
        ast.unnest(), _BOOLEAN_ROOTS
    ):
        raise ExpressionError("值类型约束必须是条件表达式")
    for node in ast.walk():
        if not isinstance(node, _ALLOWED) or isinstance(node, (exp.AggFunc, exp.Query, exp.Window)):
            raise ExpressionError("值类型约束只能使用标量比较、条件和受限函数")
        if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
            raise ExpressionError("值类型约束不判断空值；是否必填在属性上设置")
        if isinstance(node, exp.Column) and (
            node.table or node.name.casefold() != value_type.name.casefold()
        ):
            raise ExpressionError(f"值类型约束只能引用当前值 {value_type.name}：{node.sql()}")
        if isinstance(node, exp.RegexpLike):
            pattern = node.expression
            if not (isinstance(pattern, exp.Literal) and pattern.is_string):
                raise ExpressionError("REGEXP_LIKE 的模式必须是字符串常量")
            if _UNSAFE_REGEX.search(pattern.this):
                raise ExpressionError("正则不支持反向引用、环视或内联模式")
            try:
                re.compile(pattern.this)
            except re.error as error:
                raise ExpressionError("正则语法错误") from error
        elif isinstance(node, exp.Func) and not isinstance(node, (exp.Binary, exp.Unary)):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name()
            if name not in SCALAR_FUNCTIONS:
                raise ExpressionError(f"值类型约束仅支持已知标量函数：{name}")
    references = tuple(
        ExpressionReference("value_type", start, end, root_id=value_type.id) for start, end in spans
    )
    return ResolvedExpression(text, ast, references)


def value_type_rules(draft: CoreDraft, value_type_id: UUID) -> list[Rule]:
    return [
        r
        for r in draft.rules
        if r.owner_kind == RuleOwnerKind.VALUE_TYPE and r.owner_id == value_type_id
    ]


def usages(draft: CoreDraft, value_type_id: UUID):
    """Properties referencing the type, derived on read and never stored."""
    return [p for p in draft.properties if p.value_type_id == value_type_id]
