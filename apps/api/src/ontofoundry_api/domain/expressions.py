"""Resolve three expression namespaces without rewriting literals or parameters.

The SQL parser sees opaque identifiers for ontology paths, including reserved
words and explicit REVERSE/EXISTS navigation. References retain source spans and
stable IDs; ASTs and references are compilation projections, never stored data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import (
    CoreDraft,
    DataMapping,
    ExpressionMetric,
    Multiplicity,
    Rule,
    RuleOwnerKind,
)
from ontofoundry_api.domain.graph import DraftIndex

_TOKEN = re.compile(
    r"(?P<space>\s+)|(?P<comment>--[^\n]*|/\*[\s\S]*?\*/)|"
    r"(?P<string>'(?:''|\\.|[^'\\])*')|"
    r'(?P<quoted>"(?:""|[^"])*"|`(?:``|[^`])*`)|'
    r"(?P<param>:[A-Za-z_]\w*|@[A-Za-z_]\w*|\$[A-Za-z_0-9]\w*)|"
    r"(?P<word>[A-Za-z_]\w*)|(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|"
    r"(?P<symbol>.)"
)


# These functions describe scalar semantics; metric preview has its own engine
# support and execution whitelist. Unknown metric functions can still be saved.
SCALAR_FUNCTIONS = frozenset(
    {
        "ABS",
        "ROUND",
        "FLOOR",
        "CEIL",
        "CEILING",
        "COALESCE",
        "NULLIF",
        "IF",
        "IFNULL",
        "LOWER",
        "UPPER",
        "LENGTH",
        "CHAR_LENGTH",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "CONCAT",
        "CONCAT_WS",
        "SUBSTRING",
        "REPLACE",
        "LEFT",
        "RIGHT",
        "POW",
        "POWER",
        "SQRT",
        "DATE",
        "YEAR",
        "MONTH",
        "DAY",
        "DATE_ADD",
        "DATE_SUB",
        "DATEDIFF",
        "EXTRACT",
        "CAST",
        "TRY_CAST",
        "CASE",
        "STR_TO_DATE",
        "DATE_TRUNC",
        "TIME_TO_STR",
    }
)


class ExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    start: int
    end: int

    @property
    def name(self) -> str:
        if self.kind == "quoted":
            return self.text[1:-1].replace(self.text[0] * 2, self.text[0])
        return self.text


@dataclass(frozen=True)
class ExpressionReference:
    context: str
    start: int
    end: int
    root_id: UUID | None = None
    property_id: UUID | None = None
    links: tuple[tuple[UUID, str], ...] = ()
    dataset_id: UUID | None = None
    column: str | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class ResolvedExpression:
    text: str
    ast: exp.Expression
    references: tuple[ExpressionReference, ...]


def _tokens(text: str) -> list[Token]:
    return [
        Token(m.lastgroup, m.group(), m.start(), m.end())
        for m in _TOKEN.finditer(text)
        if m.lastgroup not in {"space", "comment"}
    ]


def _path(tokens: list[Token], start: int) -> tuple[list[tuple[str, str]], int]:
    """Return names/directions for an explicit dotted path."""
    if tokens[start].kind not in {"word", "quoted"}:
        return [], start
    parts = [(tokens[start].name, "forward")]
    end = start + 1
    while end + 1 < len(tokens) and tokens[end].text == ".":
        part = tokens[end + 1]
        if part.name.upper() == "REVERSE" and end + 4 < len(tokens):
            if tokens[end + 2].text != "(" or tokens[end + 4].text != ")":
                raise ExpressionError("REVERSE 必须包含一个关系技术名")
            name = tokens[end + 3]
            if name.kind not in {"word", "quoted"}:
                raise ExpressionError("REVERSE 的关系技术名无效")
            parts.append((name.name, "reverse"))
            end += 5
        elif part.kind in {"word", "quoted"}:
            parts.append((part.name, "forward"))
            end += 2
        else:
            raise ExpressionError("路径必须引用明确的属性或列，不能使用通配符")
    return parts, end


def _link(index: DraftIndex, type_id: UUID, name: str, direction: str):
    candidates = (
        index.outgoing_links(type_id)
        if direction == "forward"
        else index.incoming_links(type_id)
    )
    found = [
        link for link in candidates if link.technical_name.casefold() == name.casefold()
    ]
    if len(found) != 1:
        raise ExpressionError(f"关系路径不存在或有歧义：{name}")
    return found[0]


def resolve_path(
    index: DraftIndex,
    type_id: UUID,
    links: list[tuple[UUID, str]],
    property_id: UUID | None,
    *,
    scalar: bool = True,
) -> UUID:
    """Validate an ID-based path and return its endpoint object type."""
    if type_id not in index.objects:
        raise ExpressionError("路径上下文对象不存在")
    for link_id, direction in links:
        link = index.links.get(link_id)
        if link is None:
            raise ExpressionError("路径引用了不存在的关系")
        origin = link.source_type_id if direction == "forward" else link.target_type_id
        if not index.is_a(type_id, origin):
            raise ExpressionError("关系路径方向或端点不符")
        if scalar and (
            link.multiplicity == Multiplicity.MANY_TO_MANY
            or (direction == "reverse" and link.multiplicity != Multiplicity.ONE_TO_ONE)
        ):
            raise ExpressionError("集合关系不能作为标量，请使用显式 EXISTS")
        type_id = link.target_type_id if direction == "forward" else link.source_type_id
    if property_id is not None and property_id not in {
        p.id for p in index.effective_properties(type_id)
    }:
        raise ExpressionError("路径属性不属于有效端点对象")
    return type_id


def _ontology_reference(index, context, parts, first, last, *, existence=False):
    root = index.objects[context]
    if parts[0][0].casefold() != root.technical_name.casefold():
        raise ExpressionError(f"路径必须从上下文对象 {root.technical_name} 出发")
    current = context
    hops: list[tuple[UUID, str]] = []
    navigation = parts[1:] if existence else parts[1:-1]
    for name, direction in navigation:
        link = _link(index, current, name, direction)
        hops.append((link.id, direction))
        current = resolve_path(
            index, current, [(link.id, direction)], None, scalar=not existence
        )
    prop = None if existence else index.property_by_name(current, parts[-1][0])
    if not existence and (prop is None or parts[-1][1] != "forward"):
        raise ExpressionError(f"路径属性不存在：{parts[-1][0]}")
    if existence and not hops:
        raise ExpressionError("EXISTS 必须包含关系路径")
    return ExpressionReference(
        "ontology",
        first.start,
        last.end,
        context,
        prop.id if prop else None,
        tuple(hops),
    )


def _check_ast(
    text: str, references, replacements, *, aggregate: bool
) -> ResolvedExpression:
    parsed = text
    for start, end, placeholder in reversed(replacements):
        parsed = parsed[:start] + placeholder + parsed[end:]
    try:
        statements = sqlglot.parse(parsed)
    except SqlglotError as error:
        raise ExpressionError("表达式语法无效") from error
    if len(statements) != 1 or statements[0] is None:
        raise ExpressionError("只能保存一条非空表达式")
    ast = statements[0]
    forbidden = (
        exp.Query,
        exp.DDL,
        exp.DML,
        exp.Command,
        exp.Table,
        exp.Window,
        exp.Alias,
        exp.Into,
    )
    scalar_roots = (
        exp.Condition,
        exp.Func,
        exp.Binary,
        exp.Unary,
        exp.Literal,
        exp.Boolean,
        exp.Null,
        exp.Paren,
        exp.Placeholder,
        exp.Parameter,
    )
    if aggregate:
        scalar_roots += (exp.Filter, exp.WithinGroup)
    if not isinstance(ast, scalar_roots) or any(
        isinstance(node, forbidden) for node in ast.walk()
    ):
        raise ExpressionError("表达式不能包含查询、额外作用域、窗口或语句")
    if not aggregate and any(isinstance(node, exp.AggFunc) for node in ast.walk()):
        raise ExpressionError("本体和同行表达式不能包含聚合")
    if not aggregate:
        for function in ast.find_all(exp.Func):
            if isinstance(function, (exp.Binary, exp.Unary)):
                continue
            name = (
                function.name.upper()
                if isinstance(function, exp.Anonymous)
                else function.sql_name()
            )
            if name not in SCALAR_FUNCTIONS:
                raise ExpressionError(f"本体和同行表达式仅支持已知标量函数：{name}")
    placeholders = {
        item[2]: ref for item, ref in zip(replacements, references, strict=True)
    }
    for column in ast.find_all(exp.Column):
        if column.name not in placeholders or column.table:
            raise ExpressionError(f"无法解析列或路径：{column.sql()}")
        column.meta["core_reference"] = placeholders[column.name]
    # Bare '*' is not a scalar. COUNT(*) remains a valid metric expression.
    for star in ast.find_all(exp.Star):
        if not aggregate or not isinstance(star.parent, exp.Count):
            raise ExpressionError("通配符只能用于指标 COUNT(*)")
    return ResolvedExpression(text, ast, tuple(references))


def _resolve(
    text: str,
    draft: CoreDraft,
    *,
    context: UUID | None = None,
    mapping: DataMapping | None = None,
    dataset_id: UUID | None = None,
    membership: bool = False,
) -> ResolvedExpression:
    if not text.strip():
        raise ExpressionError("表达式不能为空")
    index = DraftIndex(draft)
    tokens = _tokens(text)
    references: list[ExpressionReference] = []
    replacements: list[tuple[int, int, str]] = []
    sources = resolve_binding(draft, mapping.type_id).sources if mapping else {}
    # A mapping under construction need not already be attached to the draft.
    if mapping:
        sources.update({source.id: source for source in mapping.sources})
    dataset = index.datasets.get(dataset_id) if dataset_id is not None else None
    if dataset_id is not None and dataset is None:
        raise ExpressionError("指标数据集不存在")
    placeholder_prefix = "__core_ref_"
    while placeholder_prefix in text:
        placeholder_prefix += "_"
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.kind not in {"word", "quoted"}:
            i += 1
            continue
        existence = (
            token.name.upper() == "EXISTS"
            and i + 1 < len(tokens)
            and tokens[i + 1].text == "("
        )
        if existence:
            if not membership:
                raise ExpressionError("EXISTS 仅用于成员表达式的显式关系路径")
            start = i + 2
            parts, end = _path(tokens, start) if start < len(tokens) else ([], start)
            if not parts or end >= len(tokens) or tokens[end].text != ")":
                raise ExpressionError("EXISTS 只接受关系路径，不接受子查询")
            ref = _ontology_reference(
                index, context, parts, tokens[start], tokens[end - 1], existence=True
            )
            references.append(ref)
            replacements.append(
                (token.start, tokens[end].end, f"{placeholder_prefix}{len(references)}")
            )
            i = end + 1
            continue
        parts, end = _path(tokens, i)
        if len(parts) < 2:
            i += 1
            continue
        if context is not None:
            ref = _ontology_reference(index, context, parts, token, tokens[end - 1])
        else:
            if len(parts) != 2 or any(direction != "forward" for _, direction in parts):
                raise ExpressionError("列引用只能使用本来源或本数据集的两段路径")
            qualifier, column = parts[0][0], parts[1][0]
            if mapping:
                source = sources.get(qualifier)
                if source is None:
                    raise ExpressionError(f"未知映射来源：{qualifier}")
                target = index.datasets.get(source.dataset_id)
            else:
                if qualifier != dataset.name:
                    raise ExpressionError("指标只能引用本数据集的列")
                target = dataset
            if target is None:
                raise ExpressionError("列引用的数据集不存在")
            if target.columns and column not in {c.name for c in target.columns}:
                raise ExpressionError(f"数据集 {target.name} 不存在列 {column}")
            ref = ExpressionReference(
                "field" if mapping else "metric",
                token.start,
                tokens[end - 1].end,
                dataset_id=target.id,
                column=column,
                source_id=qualifier if mapping else None,
            )
        references.append(ref)
        replacements.append((ref.start, ref.end, f"{placeholder_prefix}{len(references)}"))
        i = end
    return _check_ast(text, references, replacements, aggregate=dataset_id is not None)


def rule_context(draft: CoreDraft, rule: Rule) -> UUID:
    index = DraftIndex(draft)
    try:
        if rule.owner_kind == RuleOwnerKind.OBJECT_TYPE:
            return index.objects[rule.owner_id].id
        if rule.owner_kind == RuleOwnerKind.PROPERTY:
            return index.properties[rule.owner_id].owner_type_id
        return index.links[rule.owner_id].source_type_id
    except KeyError as error:
        raise ExpressionError("规则归属不存在") from error


def resolve_rule_expression(draft: CoreDraft, rule: Rule) -> ResolvedExpression:
    return _resolve(rule.expression, draft, context=rule_context(draft, rule))


def resolve_derived_expression(
    draft: CoreDraft, parent_id: UUID, text: str
) -> ResolvedExpression:
    return _resolve(text, draft, context=parent_id, membership=True)


def resolve_field_expression(
    draft: CoreDraft, mapping: DataMapping, text: str
) -> ResolvedExpression:
    return _resolve(text, draft, mapping=mapping)


def resolve_metric_expression(
    draft: CoreDraft, metric: ExpressionMetric
) -> ResolvedExpression:
    return _resolve(metric.expression, draft, dataset_id=metric.dataset_id)


def _quoted(name: str) -> str:
    return (
        name if re.fullmatch(r"[A-Za-z_]\w*", name) else '"' + name.replace('"', '""') + '"'
    )


def render_references(resolved: ResolvedExpression, draft: CoreDraft) -> str:
    """Render only recorded spans against a candidate graph; preserve all else."""
    index = DraftIndex(draft)
    text = resolved.text
    for ref in reversed(resolved.references):
        try:
            if ref.context == "ontology":
                parts = [index.objects[ref.root_id].technical_name]
                for link_id, direction in ref.links:
                    name = index.links[link_id].technical_name
                    parts.append(f"REVERSE({name})" if direction == "reverse" else name)
                if ref.property_id is not None:
                    parts.append(index.properties[ref.property_id].technical_name)
            else:
                parts = [
                    ref.source_id
                    if ref.context == "field"
                    else _quoted(index.datasets[ref.dataset_id].name),
                    _quoted(ref.column),
                ]
            text = text[: ref.start] + ".".join(parts) + text[ref.end :]
        except KeyError as error:
            raise ExpressionError("表达式引用的元素已删除，须同时修订引用") from error
    return text
