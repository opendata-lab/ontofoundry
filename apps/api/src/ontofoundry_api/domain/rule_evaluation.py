"""Evaluate constraint rules on one document instance at accept time (AC-07).

Only an allow-list of syntax is evaluated: comparisons, IN, BETWEEN, AND/OR/NOT,
arithmetic in exact Decimal, LIKE, REGEXP_LIKE and a few text functions. A rule
that reaches another object (any relation hop, a self-association included) or
uses anything else is reported as not checked and never blocks. Derivation
rules are not checked. A rule whose values are missing is not evaluated: AC-02
handles required values.

Rules are not translated to SQLite: it reads TRY_CAST('abc' AS INT) as not null,
turns DECIMAL into floats, and lacks REGEXP and LEFT, so it would silently give
wrong answers (Codex review, 2026-11-15).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlglot import exp

from ontofoundry_api.domain.core import CoreDraft, Rule, RuleKind, RuleOwnerKind, ValueKind
from ontofoundry_api.domain.expressions import ExpressionError, resolve_rule_expression
from ontofoundry_api.domain.graph import draft_index

NUMERIC = {ValueKind.INTEGER, ValueKind.DECIMAL, ValueKind.FLOAT}


class Unsupported(Exception):
    """Outside the allow-list: the rule is reported as not checked."""


class _Missing(Exception):
    """A referenced value is empty: the rule is not evaluated."""


@dataclass(frozen=True)
class RuleOutcome:
    rule: Rule
    passed: bool | None  # None: not checked
    values: dict[str, object]  # property label -> value, for the message
    reason: str = ""


def rule_label(rule: Rule) -> str:
    return f"{rule.display_name}（{rule.name}）" if rule.display_name else rule.name


def _number(value) -> Decimal:
    if isinstance(value, bool):
        raise Unsupported("布尔值不参与算术")
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise Unsupported("不是数字") from error


def _numeric(value) -> Decimal:
    """An operand of arithmetic: already a number, never text coerced to one."""
    if not isinstance(value, Decimal):
        raise Unsupported("算术只用于数字")
    return value


def _comparable(left, right):
    # Number against text is not coerced: engines disagree, and a guess could pass a wrong value.
    if type(left) is not type(right):
        raise Unsupported("比较两边的类型不同")
    return left, right


def _like(pattern: str) -> re.Pattern:
    out = []
    for char in pattern:
        out.append(".*" if char == "%" else "." if char == "_" else re.escape(char))
    return re.compile("".join(out), re.DOTALL)


COMPARISONS = {
    exp.EQ: lambda a, b: a == b, exp.NEQ: lambda a, b: a != b,
    exp.GT: lambda a, b: a > b, exp.GTE: lambda a, b: a >= b,
    exp.LT: lambda a, b: a < b, exp.LTE: lambda a, b: a <= b,
}
ARITHMETIC = {
    exp.Add: lambda a, b: a + b, exp.Sub: lambda a, b: a - b, exp.Mul: lambda a, b: a * b,
}


def evaluate(node: exp.Expression, lookup) -> object:
    """The value of ``node``; ``lookup(column)`` gives a referenced value."""
    if isinstance(node, exp.Paren):
        return evaluate(node.this, lookup)
    if isinstance(node, exp.Column):
        return lookup(node)
    if isinstance(node, exp.Literal):
        return node.this if node.is_string else _number(node.this)
    if isinstance(node, exp.Boolean):
        return node.this
    if isinstance(node, exp.And):
        return bool(evaluate(node.this, lookup)) and bool(evaluate(node.expression, lookup))
    if isinstance(node, exp.Or):
        return bool(evaluate(node.this, lookup)) or bool(evaluate(node.expression, lookup))
    if isinstance(node, exp.Not):
        return not evaluate(node.this, lookup)
    if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
        # Reached only with a value: an empty one stops evaluation first (AC-02's job).
        evaluate(node.this, lookup)
        return False
    for kind, compare in COMPARISONS.items():
        if type(node) is kind:
            return compare(*_comparable(evaluate(node.this, lookup), evaluate(node.expression, lookup)))
    if isinstance(node, exp.In):
        if node.args.get("query") or node.args.get("unnest") or node.args.get("field"):
            raise Unsupported("IN 只支持列出的值")
        value = evaluate(node.this, lookup)
        return any(a == b for a, b in (_comparable(value, evaluate(e, lookup)) for e in node.expressions))
    if isinstance(node, exp.Between):
        value = evaluate(node.this, lookup)
        low = _comparable(value, evaluate(node.args["low"], lookup))
        high = _comparable(value, evaluate(node.args["high"], lookup))
        return low[1] <= low[0] and high[0] <= high[1]
    for kind, apply in ARITHMETIC.items():
        if type(node) is kind:
            return apply(_numeric(evaluate(node.this, lookup)), _numeric(evaluate(node.expression, lookup)))
    if isinstance(node, exp.Div):
        divisor = _numeric(evaluate(node.expression, lookup))
        if divisor == 0:
            raise Unsupported("除数为零")
        return _numeric(evaluate(node.this, lookup)) / divisor
    if isinstance(node, exp.Neg):
        return -_numeric(evaluate(node.this, lookup))
    if isinstance(node, (exp.Like, exp.ILike)):
        value, pattern = evaluate(node.this, lookup), evaluate(node.expression, lookup)
        if not isinstance(value, str) or not isinstance(pattern, str) or node.args.get("escape"):
            raise Unsupported("LIKE 只比较文本")
        flags = re.IGNORECASE if isinstance(node, exp.ILike) else 0
        return re.fullmatch(_like(pattern).pattern, value, flags) is not None
    if isinstance(node, exp.RegexpLike):
        value, pattern = evaluate(node.this, lookup), node.expression
        if not isinstance(value, str) or not (isinstance(pattern, exp.Literal) and pattern.is_string) or node.args.get("flag"):
            raise Unsupported("REGEXP_LIKE 只比较文本与常量模式")
        return re.search(pattern.this, value) is not None
    if isinstance(node, (exp.Lower, exp.Upper, exp.Trim, exp.Length)):
        value = evaluate(node.this, lookup)
        if not isinstance(value, str) or (isinstance(node, exp.Trim) and (node.expression or node.args.get("position"))):
            raise Unsupported("文本函数只用于文本")
        if isinstance(node, exp.Lower):
            return value.lower()
        if isinstance(node, exp.Upper):
            return value.upper()
        if isinstance(node, exp.Trim):
            return value.strip()
        return Decimal(len(value))
    raise Unsupported(f"暂不支持 {type(node).__name__}")


def _typed(value, kind: ValueKind):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise _Missing
    if kind in NUMERIC:
        return _number(value)
    if kind == ValueKind.BOOLEAN:
        if not isinstance(value, bool):
            raise Unsupported("布尔属性的值不是布尔")
        return value
    return value if isinstance(value, str) else str(value)


def check_instance_rules(draft: CoreDraft, type_id: UUID, values: dict) -> list[RuleOutcome]:
    """Every constraint that applies to an instance of ``type_id``, evaluated or not."""
    index = draft_index(draft)
    type_id = UUID(str(type_id))
    properties = {p.id: p for p in index.effective_properties(type_id)}
    outcomes: list[RuleOutcome] = []
    for rule in index.effective_rules(type_id):
        if rule.rule_kind != RuleKind.CONSTRAINT:
            continue
        outcomes.append(_object_rule(draft, rule, properties, values))
    # Value type constraints hold for each property that uses the value type.
    for prop in properties.values():
        if prop.value_type_id is None:
            continue
        for rule in draft.rules:
            if (rule.owner_kind == RuleOwnerKind.VALUE_TYPE and rule.owner_id == prop.value_type_id
                    and rule.rule_kind == RuleKind.CONSTRAINT):
                outcomes.append(_value_rule(draft, rule, prop, values))
    return [o for o in outcomes if o is not None]


def _run(rule, ast, lookup, shown):
    try:
        return RuleOutcome(rule, bool(evaluate(ast, lookup)), shown)
    except _Missing:
        return None
    except Unsupported as reason:
        return RuleOutcome(rule, None, shown, f"用到暂不支持的写法（{reason}）")


def _label(prop) -> str:
    return f"{prop.display_name}（{prop.name}）" if prop.display_name else prop.name


def _object_rule(draft, rule, properties, values):
    if rule.owner_kind == RuleOwnerKind.LINK_TYPE:
        return RuleOutcome(rule, None, {}, "涉及其他对象")
    try:
        resolved = resolve_rule_expression(draft, rule)
    except ExpressionError:
        return RuleOutcome(rule, None, {}, "表达式无法解析")
    if any(ref.links or ref.property_id is None for ref in resolved.references):
        return RuleOutcome(rule, None, {}, "涉及其他对象")
    shown = {}

    def lookup(column):
        ref = column.meta.get("core_reference")
        prop = properties.get(ref.property_id) if ref else None
        if prop is None:
            raise Unsupported("引用不是本对象的属性")
        value = _typed(values.get(prop.name), prop.value_kind)
        shown[_label(prop)] = values.get(prop.name)
        return value

    return _run(rule, resolved.ast, lookup, shown)


def _value_rule(draft, rule, prop, values):
    try:
        resolved = resolve_rule_expression(draft, rule)
    except ExpressionError:
        return RuleOutcome(rule, None, {}, "表达式无法解析")
    shown = {}

    def lookup(_column):
        value = _typed(values.get(prop.name), prop.value_kind)
        shown[_label(prop)] = values.get(prop.name)
        return value

    return _run(rule, resolved.ast, lookup, shown)


def violation_message(where: str, outcome: RuleOutcome) -> str:
    stated = "、".join(f"{label}为 {value!r}" for label, value in outcome.values.items())
    return f"{where}：{stated}，不满足规则 {rule_label(outcome.rule)}（{outcome.rule.expression}）"


def unchecked_message(outcome: RuleOutcome) -> str:
    return f"规则未检查：{rule_label(outcome.rule)}，{outcome.reason}"


def only_says_required(draft: CoreDraft, rule: Rule) -> list[str]:
    """Properties a constraint only requires to be filled (``x IS NOT NULL``, possibly
    joined with AND). Required belongs on the property, where acceptance checks it;
    as a rule it would never be evaluated on an empty value. Empty when the rule
    says anything else, or reaches another object."""
    if rule.rule_kind != RuleKind.CONSTRAINT or rule.owner_kind == RuleOwnerKind.VALUE_TYPE:
        return []
    try:
        resolved = resolve_rule_expression(draft, rule)
    except ExpressionError:
        return []
    index = draft_index(draft)
    names = []

    def visit(node) -> bool:
        while isinstance(node, exp.Paren):
            node = node.this
        if isinstance(node, exp.And):
            return visit(node.this) and visit(node.expression)
        if not (isinstance(node, exp.Not) and isinstance(node.this, exp.Is) and isinstance(node.this.expression, exp.Null)):
            return False
        column = node.this.this
        ref = column.meta.get("core_reference") if isinstance(column, exp.Column) else None
        if ref is None or ref.links or ref.property_id not in index.properties:
            return False
        prop = index.properties[ref.property_id]
        names.append(_label(prop))
        return True

    return names if visit(resolved.ast) else []
