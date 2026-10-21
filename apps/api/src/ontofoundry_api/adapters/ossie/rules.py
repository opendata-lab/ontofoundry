"""Bind ontology references before validating rules and whole membership definitions."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ontofoundry_api.adapters.documents import escape_pointer
from ontofoundry_api.domain.core import (
    DerivedExpression,
    DerivedSimple,
    LinkType,
    ObjectType,
    PathCondition,
    Property,
    Rule,
    ValueType,
)
from ontofoundry_api.domain.expressions import resolve_derived_expression
from ontofoundry_api.domain.graph import DraftIndex

from .metrics import literal, unwrap

TOKEN = re.compile(
    r"""(?P<string>'(?:''|[^'])*')|(?P<quoted>"(?:""|[^"])*")|(?P<word>[A-Za-z_]\w*)|(?P<space>\s+)|(?P<symbol>.)"""
)


def rewrite_expression(importer, text):
    # Rewrite only identifier tokens in resolved-looking ontology paths. The core
    # parser remains authoritative for semantics and unsupported role syntax.
    t = importer.t
    tokens = [m for m in TOKEN.finditer(text) if m.lastgroup != "space"]
    edits = []

    def name(token):
        return (
            token.group()[1:-1].replace('""', '"')
            if token.lastgroup == "quoted"
            else token.group()
        )

    def member(owner, wanted, reverse=False):
        obj = t.objects[owner]
        if reverse:
            targets = set(DraftIndex(t.model).lineage(obj.id))
            matches = [
                item
                for (_source, original), item in t.members.items()
                if original == wanted
                and isinstance(item, LinkType)
                and item.target_type_id in targets
            ]
            return matches[0] if len(matches) == 1 else None
        for oid in DraftIndex(t.model).lineage(obj.id):
            source = next(n for n, o in t.objects.items() if o.id == oid)
            item = t.members.get((source, wanted))
            if item:
                return item
        return None

    i = 0
    while i < len(tokens):
        token = tokens[i]
        owner = name(token)
        if (
            token.lastgroup not in {"word", "quoted"}
            or owner not in t.objects
            or i + 1 >= len(tokens)
            or tokens[i + 1].group() != "."
        ):
            i += 1
            continue
        edits.append((token.start(), token.end(), t.objects[owner].name))
        j = i + 2
        while j < len(tokens):
            reverse = name(tokens[j]).upper() == "REVERSE"
            at = (
                j + 2
                if reverse and j + 3 < len(tokens) and tokens[j + 1].group() == "("
                else j
            )
            if at >= len(tokens):
                break
            item = member(owner, name(tokens[at]), reverse)
            if item is None:
                break
            edits.append((tokens[at].start(), tokens[at].end(), item.name))
            after = at + 2 if reverse else at + 1
            if isinstance(item, LinkType):
                target = item.source_type_id if reverse else item.target_type_id
                owner = next(n for n, o in t.objects.items() if o.id == target)
            if after >= len(tokens) or tokens[after].group() != ".":
                break
            j = after + 1
        i = max(i + 1, j)
    for start, end, replacement in reversed(sorted(set(edits))):
        text = text[:start] + replacement + text[end:]
    return text


def reified_expression(importer, element, text):
    bindings = importer.role_bindings.get(element.id)
    if bindings is None:
        return rewrite_expression(importer, text)
    statements = sqlglot.parse(text)
    if len(statements) != 1 or statements[0] is None:
        raise ValueError("多元规则必须是一个表达式")
    ast = statements[0]
    for column in list(ast.find_all(exp.Column)):
        property_name = bindings.get((column.table, column.name))
        if property_name:
            column.replace(exp.column(property_name, table=element.name))
    return ast.sql()


def add_rule(importer, element, text, path, key, kind, *, description=""):
    t = importer.t
    owner_kind = (
        "object_type"
        if isinstance(element, ObjectType)
        else "property"
        if isinstance(element, Property)
        else "value_type"
        if isinstance(element, ValueType)
        else "link_type"
    )
    position = (
        sum(r.owner_id == element.id and r.rule_kind == kind for r in t.model.rules) + 1
    )
    try:
        owner_path = element.name
        if isinstance(element, (Property, LinkType)):
            owner_id = (
                element.owner_type_id
                if isinstance(element, Property)
                else element.source_type_id
            )
            owner_path = (
                next(obj.name for obj in t.model.object_types if obj.id == owner_id)
                + "."
                + element.name
            )
        metadata = next(
            (
                (key, value)
                for key, value in importer.extension.data.get("rules", {}).items()
                if value["owner"] == owner_path
                and value["kind"] == kind
                and value["position"] == int(path.rsplit("/", 1)[-1])
            ),
            None,
        )
        rule_key = metadata[0] if metadata else None
        if metadata:
            description = metadata[1].get("description", "")
        rule = Rule(
            id=t.id(key),
            display_name=importer.extension.name("rule:" + rule_key, None)
            if rule_key
            else None,
            name=rule_key.rsplit(".", 1)[-1] if rule_key else f"{kind}_{position}",
            description=description,
            owner_kind=owner_kind,
            owner_id=element.id,
            rule_kind=kind,
            expression=text,
        )
    except ValueError as error:
        t.issue(
            path,
            "error",
            "Rule",
            "RT-31",
            f"规则未形成合法核心定义：{error}",
            completion=True,
        )
        return
    t.accept(
        "rules",
        rule,
        path,
        rule="RT-24" if description else "RT-31",
        message="规则引用已闭合并通过核心校验",
    )


def membership_branch(model, parent_id, text):
    resolved = resolve_derived_expression(model, parent_id, text)

    def condition(ast):
        ast = unwrap(ast)
        if isinstance(ast, exp.And):
            return [*condition(ast.this), *condition(ast.expression)]
        negative = isinstance(ast, exp.Not)
        if negative:
            ast = unwrap(ast.this)
        values = []
        column = None
        operator = None
        if isinstance(ast, exp.Is) and isinstance(ast.expression, exp.Null):
            operator = "not_null" if negative else "is_null"
            column = ast.this
        elif isinstance(ast, exp.In) and not ast.args.get("query"):
            operator = "not_in" if negative else "in"
            column = ast.this
            values = [literal(v) for v in ast.expressions]
        elif isinstance(ast, exp.Between) and not negative:
            operator = "between"
            column = ast.this
            values = [literal(ast.args["low"]), literal(ast.args["high"])]
        elif not negative:
            operator = {
                exp.EQ: "eq",
                exp.NEQ: "ne",
                exp.GT: "gt",
                exp.GTE: "ge",
                exp.LT: "lt",
                exp.LTE: "le",
            }.get(type(ast))
            if operator:
                column = ast.this
                values = [literal(ast.expression)]
        reference = (
            column.meta.get("core_reference") if isinstance(column, exp.Column) else None
        )
        if not operator or reference is None or reference.property_id is None:
            raise ValueError("使用完整成员表达式")
        return [
            PathCondition(
                path={
                    "links": [
                        {"link_type_id": lid, "direction": direction}
                        for lid, direction in reference.links
                    ],
                    "property_id": reference.property_id,
                },
                operator=operator,
                values=values,
            )
        ]

    try:
        return DerivedSimple(kind="simple", conditions=condition(resolved.ast))
    except ValueError:
        return DerivedExpression(kind="expression", expression=text)


def import_rules(importer):
    t = importer.t
    for name, obj in list(t.objects.items()):
        c = importer.concepts[name]
        path = importer.paths[name]
        for i, text in enumerate(c.get("requires", [])):
            add_rule(
                importer,
                obj,
                rewrite_expression(importer, text),
                path + f"/requires/{i}",
                f"rule:object:{name}:constraint:{i}",
                "constraint",
            )
        derived = c.get("derived_by", [])
        if derived and obj.extends:
            try:
                branches = [
                    membership_branch(
                        t.model, obj.extends, rewrite_expression(importer, text)
                    )
                    for text in derived
                ]
                t.replace(
                    "object_types",
                    obj.model_copy(update={"derived_by": branches}),
                    path + "/derived_by",
                    rule="RT-67",
                    message="全部成员分支按父范围解析；分支并集和方向已保留",
                )
            except ValueError as error:
                t.issue(
                    path + "/derived_by",
                    "error",
                    "DerivedBy",
                    "RT-31",
                    f"成员定义不能完整闭合：{error}",
                    completion=True,
                )
        elif derived:
            for i, text in enumerate(derived):
                add_rule(
                    importer,
                    obj,
                    rewrite_expression(importer, text),
                    path + f"/derived_by/{i}",
                    f"rule:object:{name}:derivation:{i}",
                    "derivation",
                )
        title = importer.extension.data.get("title_properties", {}).get(name)
        if title:
            prop = next(
                (
                    p
                    for p in DraftIndex(t.model).effective_properties(obj.id)
                    if p.name == title or t.members.get((name, title)) is p
                ),
                None,
            )
            if prop:
                t.replace(
                    "object_types",
                    t.objects[name].model_copy(update={"title_property_id": prop.id}),
                    importer.extension.source_path
                    + "/title_properties/"
                    + escape_pointer(name),
                    message="标题引用有效属性",
                )
            else:
                t.issue(
                    importer.extension.source_path
                    + "/title_properties/"
                    + escape_pointer(name),
                    "dropped",
                    "TitleProperty",
                    "RT-03",
                    "标题属性不存在或未转换",
                )
    for element, raw, path, key in importer.origins:
        for field, kind in [("requires", "constraint"), ("derived_by", "derivation")]:
            for i, text in enumerate(raw.get(field, [])):
                try:
                    translated = reified_expression(importer, element, text)
                except (ValueError, SqlglotError) as error:
                    t.issue(
                        path + f"/{field}/{i}",
                        "error",
                        "Rule",
                        "RT-31",
                        f"角色规则未能完整解析：{error}",
                        completion=True,
                    )
                    continue
                add_rule(
                    importer,
                    element,
                    translated,
                    path + f"/{field}/{i}",
                    f"rule:{key}:{kind}:{i}",
                    kind,
                )

    # A diamond value-type ancestry contributes each source constraint once.
    def ancestors(name, seen):
        if name in seen or name not in importer.concepts:
            return []
        seen.add(name)
        c = importer.concepts[name]
        return [*sum((ancestors(p, seen) for p in c.get("extends", [])), []), (name, c)]

    # Constraints stay on the shared value type; ancestors fold into it (VT-08).
    for name, value_type in importer.value_types.items():
        for source, c in ancestors(name, set()):
            for i, text in enumerate(c.get("requires", [])):
                pointer = importer.paths[source] + f"/requires/{i}"
                try:
                    ast = sqlglot.parse_one(text)
                    matched = False
                    for column in list(ast.find_all(exp.Column)):
                        if not column.table and column.name == source:
                            column.replace(exp.column(value_type.name))
                            matched = True
                    if not matched:
                        raise ValueError("约束没有可绑定的值变量")
                    expression = ast.sql()
                except (ValueError, SqlglotError) as error:
                    t.issue(
                        pointer,
                        "error",
                        "ValueConstraint",
                        "RT-24",
                        f"不能把约束绑定到值类型：{error}",
                        completion=True,
                    )
                    continue
                add_rule(
                    importer,
                    value_type,
                    expression,
                    pointer,
                    f"value-type-rule:{value_type.id}:{importer.paths[source]}:{i}",
                    "constraint",
                    description="" if source == name else f"来自祖先值类型 {source} 的约束",
                )
