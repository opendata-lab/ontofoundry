"""Compile core object sources into bounded, read-only instance selections."""

import hashlib
import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import (
    String,
    and_,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import ColumnElement
from sqlglot import Dialect

from ontofoundry_api.domain.bindings import MEMBERS_MISSING, resolve_binding
from ontofoundry_api.domain.core import (
    ColumnBinding,
    DerivedSimple,
    DirectJoin,
    PropertiesKey,
)
from ontofoundry_api.domain.expressions import (
    resolve_derived_expression,
    resolve_field_expression,
)
from ontofoundry_api.domain.graph import draft_index
from ontofoundry_api.domain.instance_display import database_display_text
from ontofoundry_api.services.dataset_sources import resolve_dataset
from ontofoundry_api.services.errors import NotFoundError, ServiceError
from ontofoundry_api.services.readonly import connect_readonly


def fail(message, code="BINDING_NOT_READY"):
    raise ServiceError(message, code=code, status_code=422)


def typed_key(values):
    result = []
    for value in values:
        if value is None:
            fail("来源逻辑键含空值，不能定位实例")
        if type(value) is bool:
            kind, value = "boolean", value
        elif type(value) is int:
            kind, value = "integer", str(value)
        elif isinstance(value, Decimal):
            kind, value = "decimal", str(value)
        elif type(value) is float:
            kind, value = "float", value
        elif isinstance(value, datetime):
            kind, value = "datetime", value.isoformat()
        elif isinstance(value, date):
            kind, value = "date", value.isoformat()
        else:
            kind, value = "string", str(value)
        result.append({"type": kind, "value": value})
    return result


def key_values(parts):
    try:
        values = []
        for part in parts:
            if set(part) != {"type", "value"}:
                raise ValueError()
            kind, value = part["type"], part["value"]
            if kind in {"integer", "decimal"}:
                if not isinstance(value, str):
                    raise ValueError()
                value = int(value) if kind == "integer" else Decimal(value)
                if kind == "decimal" and not value.is_finite():
                    raise ValueError()
            elif kind == "date":
                value = date.fromisoformat(value)
            elif kind == "datetime":
                value = datetime.fromisoformat(value)
            elif kind == "string":
                if not isinstance(value, str):
                    raise ValueError()
            elif kind == "boolean":
                if type(value) is not bool:
                    raise ValueError()
            elif kind == "float":
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError()
            else:
                raise ValueError()
            values.append(value)
        return values
    except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as exc:
        raise ServiceError(
            "实例键类型无效", code="INVALID_OBJECT_REF", status_code=422
        ) from exc


def condition(column, operator, values):
    if operator == "eq":
        return column == values[0]
    if operator == "ne":
        return column != values[0]
    if operator == "gt":
        return column > values[0]
    if operator == "ge":
        return column >= values[0]
    if operator == "lt":
        return column < values[0]
    if operator == "le":
        return column <= values[0]
    if operator == "in":
        return column.in_(values)
    if operator == "not_in":
        return column.not_in(values)
    if operator == "between":
        return column.between(*values)
    if operator == "is_null":
        return column.is_(None)
    return column.is_not(None)


class ResolvedScalar(ColumnElement):
    """Render resolved scalar syntax inside the enclosing SQLAlchemy context.

    Navigation stays a clause tree until the outer SELECT is compiled, so
    EXISTS/scalar subqueries can correlate with that SELECT's FROM clauses.
    """

    inherit_cache = False

    def __init__(self, tree, values):
        self.tree, self.values = tree, values

    @property
    def _from_objects(self):
        return [table for value in self.values.values() for table in value._from_objects]


@compiles(ResolvedScalar)
def compile_resolved_scalar(element, compiler, **kwargs):
    dialect = "postgres" if compiler.dialect.name == "postgresql" else compiler.dialect.name
    base = Dialect.get_or_raise(dialect).generator_class

    class ScalarGenerator(base):
        def literal_sql(self, expression):
            if expression.is_string:
                return compiler.process(literal(expression.this), **kwargs)
            return super().literal_sql(expression)

        def mod_sql(self, expression):
            operator = "%%" if compiler.preparer._double_percents else "%"
            return self.binary(expression, operator)

        def column_sql(self, expression):
            value = element.values[expression.name]
            return "(" + compiler.process(value, **kwargs) + ")"

    # This also handles a reference occupying the AST root, without node.replace().
    return ScalarGenerator(dialect=dialect, comments=False).generate(element.tree)


class InstancePlan:
    def __init__(
        self,
        db,
        workspace_id,
        draft,
        type_id,
        connection,
        connection_id,
        *,
        snapshot_date=None,
        depth=0,
    ):
        if depth > 8:
            fail("关联成员条件超出预览深度")
        self.db, self.workspace_id, self.draft, self.type_id = (
            db,
            workspace_id,
            draft,
            UUID(str(type_id)),
        )
        self.connection, self.connection_id, self.snapshot_date, self.depth = (
            connection,
            connection_id,
            snapshot_date,
            depth,
        )
        self.index = draft_index(draft)
        self.binding = resolve_binding(draft, self.type_id)
        if self.binding.main is None:
            fail("对象尚无主来源", "MAPPING_REQUIRED")
        if any(not s.key_columns for s in self.binding.sources.values()):
            fail("来源逻辑键待补全")
        self.tables, self.dates = {}, []
        for name, source in self.binding.sources.items():
            self.tables[name] = self.dataset_table(
                source.dataset_id,
                f"t_{self.type_id.hex}_{depth}_{hashlib.sha256(name.encode()).hexdigest()[:8]}",
            )
            if any(c not in self.tables[name].c for c in source.key_columns):
                fail("来源键列不存在", "JOIN_COLUMN_NOT_FOUND")
        main = self.tables["main"]
        keys = self.binding.main.key_columns
        self.keys = [main.c[c] for c in keys]
        self.from_clause = main
        self.membership_matches = {}
        self.where = []
        memberships = {
            m.membership_source_id for m in self.binding.mappings if m.membership_source_id
        }
        for name, source in self.binding.sources.items():
            if name == "main":
                continue
            if len(source.key_columns) != len(keys):
                fail("主附来源键宽不一致")
            table = self.tables[name]
            match = and_(
                *(
                    a == table.c[b]
                    for a, b in zip(self.keys, source.key_columns, strict=True)
                )
            )
            if name in memberships:
                self.membership_matches[name] = match
                self.where.append(
                    exists(select(1).select_from(table).where(match).correlate(main))
                )
            else:
                self.from_clause = self.from_clause.outerjoin(table, match)
        self.fields = {}
        for prop in self.index.effective_properties(self.type_id):
            binding = self.binding.fields.get(prop.name)
            if isinstance(binding, ColumnBinding):
                table = self.tables.get(binding.source_id)
                if table is None or binding.column not in table.c:
                    fail("属性绑定列不存在", "JOIN_COLUMN_NOT_FOUND")
                self.fields[prop.name] = self.source_value(
                    binding.source_id, binding.column
                )
            elif binding:
                mapping = next(
                    m for m in reversed(self.binding.mappings) if prop.name in m.fields
                )
                resolved = resolve_field_expression(draft, mapping, binding.expression)
                self.fields[prop.name] = self.compile_expression(resolved)
        mapped = {m.type_id for m in self.binding.mappings}
        for ancestor in reversed(self.index.lineage(self.type_id)):
            obj = self.index.objects[ancestor]
            mapping = next(
                (m for m in self.binding.mappings if m.type_id == ancestor), None
            )
            # Below the mapped root every level reads the parent's rows; without
            # its own mapping it shares them implicitly (the record is derivable).
            shares = any(a in mapped for a in self.index.ancestors(ancestor))
            if mapping is None and not shares:
                continue
            if (
                (mapping is None or mapping.binding_mode == "shared_parent")
                and not obj.derived_by
                and not (mapping and mapping.membership_source_id)
            ):
                fail(f"{obj.display_name or obj.name}{MEMBERS_MISSING}")
            branches = []
            for branch in obj.derived_by:
                if isinstance(branch, DerivedSimple):
                    branches.append(
                        and_(
                            *(
                                self.path_condition(c.path, c.operator, c.values)
                                for c in branch.conditions
                            )
                        )
                    )
                else:
                    resolved = resolve_derived_expression(
                        draft, obj.extends, branch.expression
                    )
                    branches.append(self.compile_expression(resolved))
            if branches:
                self.where.append(or_(*branches))

    def dataset_table(self, dataset_id, alias):
        dataset = self.index.datasets[dataset_id]
        source = resolve_dataset(self.db, self.workspace_id, dataset)
        if source.connection.id != self.connection_id:
            fail("对象来源跨连接，不能执行 JOIN")
        from ontofoundry_api.services.dataset_sources import dataset_relation

        table = dataset_relation(
            self.db, self.workspace_id, dataset, self.connection, alias, source=source
        )
        if dataset.snapshot_date_column:
            if dataset.snapshot_date_column not in table.c:
                fail("快照日期列不存在", "JOIN_COLUMN_NOT_FOUND")
            column = table.c[dataset.snapshot_date_column]
            chosen = (
                self.snapshot_date
                or self.connection.execute(select(func.max(column))).scalar()
            )
            self.dates.append(
                {
                    "dataset_id": str(dataset.id),
                    "date": str(chosen) if chosen is not None else None,
                }
            )
            table = select(table).where(column == chosen).subquery(alias)
        return table

    def source_value(self, source_id, column):
        table = self.tables.get(source_id)
        if table is None or column not in table.c:
            fail("计算列引用不存在", "JOIN_COLUMN_NOT_FOUND")
        if source_id in self.membership_matches:
            return (
                select(table.c[column])
                .where(self.membership_matches[source_id])
                .correlate(self.tables["main"])
                .scalar_subquery()
            )
        return table.c[column]

    def path_value(self, links, property_id):
        if not links:
            if property_id is None:
                return True
            prop = self.index.properties[property_id]
            if prop.name not in self.fields:
                fail("成员属性未绑定")
            return self.fields[prop.name]
        link_id, direction = links[0]
        link = self.index.links[link_id]
        forward = direction == "forward"
        target_id = link.target_type_id if forward else link.source_type_id
        target = InstancePlan(
            self.db,
            self.workspace_id,
            self.draft,
            target_id,
            self.connection,
            self.connection_id,
            snapshot_date=self.snapshot_date,
            depth=self.depth + 1,
        )
        join = self.binding.link_bindings.get(link.id, link.data_join)
        match, bridge = relation_match(self, target, join, forward)
        self.dates.extend(target.dates)
        value = target.path_value(links[1:], property_id)
        query = (
            select(value)
            .select_from(target.from_clause)
            .where(match, *target.where)
            .correlate(self.from_clause)
        )
        if bridge is not None:
            query = query.select_from(bridge)
        return exists(query) if property_id is None else query.scalar_subquery()

    def compile_expression(self, resolved):
        from sqlglot import exp

        values = {}
        for node in resolved.ast.find_all(exp.Column):
            reference = node.meta["core_reference"]
            values[node.name] = (
                self.source_value(reference.source_id, reference.column)
                if reference.context == "field"
                else self.path_value(reference.links, reference.property_id)
            )
        return ResolvedScalar(resolved.ast, values)

    def subquery(self):
        return (
            select(
                *[c.label(f"__key_{i}") for i, c in enumerate(self.keys)],
                *[c.label(n) for n, c in self.fields.items()],
            )
            .select_from(self.from_clause)
            .where(*self.where)
            .subquery()
        )

    def path_condition(self, path, operator, values):
        if not path.links:
            prop = self.index.properties[path.property_id]
            if prop.name not in self.fields:
                fail("成员条件属性尚未绑定")
            return condition(self.fields[prop.name], operator, values)
        step = path.links[0]
        link = self.index.links[step.link_type_id]
        forward = step.direction == "forward"
        target_id = link.target_type_id if forward else link.source_type_id
        target_plan = InstancePlan(
            self.db,
            self.workspace_id,
            self.draft,
            target_id,
            self.connection,
            self.connection_id,
            snapshot_date=self.snapshot_date,
            depth=self.depth + 1,
        )
        join = self.binding.link_bindings.get(link.id, link.data_join)
        match, bridge = relation_match(self, target_plan, join, forward)
        next_path = path.model_copy(update={"links": path.links[1:]})
        where = target_plan.path_condition(next_path, operator, values)
        query = (
            select(1)
            .select_from(target_plan.from_clause)
            .where(match, *target_plan.where, where)
        )
        if bridge is not None:
            query = query.select_from(bridge)
        return exists(query)


def relation_match(source, target, join, forward=True):
    if join is None:
        fail("关系尚未绑定")

    def properties(plan, ids):
        result = []
        for pid in ids:
            prop = plan.index.properties[pid]
            if prop.name not in plan.fields:
                fail("关系属性尚未绑定")
            result.append(plan.fields[prop.name])
        return result

    if isinstance(join, DirectJoin):
        a, b = (
            (join.source_property_ids, join.target_property_ids)
            if forward
            else (join.target_property_ids, join.source_property_ids)
        )
        return and_(
            *(
                x == y
                for x, y in zip(properties(source, a), properties(target, b), strict=True)
            )
        ), None
    bridge = source.dataset_table(join.dataset_id, f"bridge_{source.depth}")
    a_cols, b_cols = (
        (join.source_columns, join.target_columns)
        if forward
        else (join.target_columns, join.source_columns)
    )
    a_key, b_key = (
        (join.source_key, join.target_key)
        if forward
        else (join.target_key, join.source_key)
    )
    a = (
        properties(source, a_key.property_ids)
        if isinstance(a_key, PropertiesKey)
        else source.keys
    )
    b = (
        properties(target, b_key.property_ids)
        if isinstance(b_key, PropertiesKey)
        else target.keys
    )
    if (
        len(a) != len(a_cols)
        or len(b) != len(b_cols)
        or any(c not in bridge.c for c in [*a_cols, *b_cols])
    ):
        fail("映射表关联列不存在或宽度不匹配", "JOIN_COLUMN_NOT_FOUND")
    return and_(
        *(x == bridge.c[c] for x, c in zip(a, a_cols, strict=True)),
        *(x == bridge.c[c] for x, c in zip(b, b_cols, strict=True)),
    ), bridge


def query_instances(
    db,
    workspace_id,
    draft,
    type_id,
    settings,
    *,
    key=None,
    q="",
    offset=0,
    limit=20,
    snapshot_date=None,
):
    try:
        type_id = UUID(str(type_id))
    except ValueError:
        fail("对象类型引用无效", "INVALID_OBJECT_REF")
    if type_id not in draft_index(draft).objects:
        raise NotFoundError("对象类型不存在")
    values = key_values(key) if key is not None else None
    binding = resolve_binding(draft, type_id)
    if binding.main is None:
        if not binding.virtual_types:
            fail("对象尚无可用来源", "MAPPING_REQUIRED")
        if key is not None:
            fail("虚拟父类型不能精确定位实例，请指定具体类型", "INVALID_OBJECT_REF")
        items, dates = [], []
        for concrete in binding.virtual_types:
            data = query_instances(
                db,
                workspace_id,
                draft,
                concrete,
                settings,
                q=q,
                limit=offset + limit + 1,
                snapshot_date=snapshot_date,
            )
            items.extend(data["items"])
            dates.extend(data["snapshot_dates"])
        unique = {item["__ref"]: item for item in items}
        items = sorted(unique.values(), key=lambda v: v["__ref"])
        return {
            "items": items[offset : offset + limit],
            "has_more": len(items) > offset + limit,
            "source": "database",
            "snapshot_dates": dates,
        }
    source = resolve_dataset(
        db, workspace_id, draft_index(draft).datasets[binding.main.dataset_id]
    )
    with connect_readonly(source.connection, settings) as conn:
        plan = InstancePlan(
            db,
            workspace_id,
            draft,
            type_id,
            conn,
            source.connection.id,
            snapshot_date=snapshot_date,
        )
        query = (
            select(
                *[c.label(f"__key_{i}") for i, c in enumerate(plan.keys)],
                *[c.label(n) for n, c in plan.fields.items()],
            )
            .select_from(plan.from_clause)
            .where(*plan.where)
        )
        if key is not None:
            if len(values) != len(plan.keys):
                fail("实例键宽不匹配", "INVALID_OBJECT_REF")
            query = query.where(
                and_(*(c == v for c, v in zip(plan.keys, values, strict=True)))
            )
        if q:
            query = query.where(
                or_(
                    *(
                        cast(c, String).contains(q, autoescape=True)
                        for c in [*plan.keys, *plan.fields.values()]
                    )
                )
            )
        query = query.order_by(*plan.keys).offset(offset).limit(limit + 1)
        rows = list(conn.execute(query).mappings())
        if key is not None and len(rows) > 1:
            fail("实例定位不唯一", "INSTANCE_NOT_UNIQUE")
        from ontofoundry_api.services.instance_query import db_ref

        items = []
        for row in rows[:limit]:
            typed = typed_key([row[f"__key_{i}"] for i in range(len(plan.keys))])
            values = {
                n: str(row[n]) if isinstance(row[n], Decimal) else row[n]
                for n in plan.fields
            }
            items.append(
                {
                    "__key": typed,
                    "__type_id": str(type_id),
                    "__ref": db_ref(type_id, typed),
                    "values": values,
                    "display_text": database_display_text(draft, type_id, values, typed),
                }
            )
        return {
            "items": items,
            "has_more": len(rows) > limit,
            "source": "database",
            "snapshot_dates": plan.dates,
        }
