"""Bounded direct and mapping-table neighborhood queries."""

from time import monotonic
from uuid import UUID

from sqlalchemy import and_, select

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.graph import draft_index
from ontofoundry_api.domain.instance_display import database_display_text
from ontofoundry_api.services.dataset_sources import resolve_dataset
from ontofoundry_api.services.errors import NotFoundError, ServiceError
from ontofoundry_api.services.instance_plan import (
    InstancePlan,
    key_values,
    query_instances,
    relation_match,
    typed_key,
)
from ontofoundry_api.services.instance_query import database_object
from ontofoundry_api.services.readonly import connect_readonly


def related_rows(
    db, wid, draft, settings, type_id, target_type, join, key, forward, snapshot_date
):
    values = key_values(key)
    source = resolve_binding(draft, UUID(str(type_id)))
    if source.main is None:
        raise ServiceError("对象尚无具体绑定", code="BINDING_NOT_READY", status_code=422)
    connection = resolve_dataset(
        db, wid, draft_index(draft).datasets[source.main.dataset_id]
    ).connection
    with connect_readonly(connection, settings) as conn:
        current = InstancePlan(
            db, wid, draft, type_id, conn, connection.id, snapshot_date=snapshot_date
        )
        target = InstancePlan(
            db,
            wid,
            draft,
            target_type,
            conn,
            connection.id,
            snapshot_date=snapshot_date,
            depth=1,
        )
        match, bridge = relation_match(current, target, join, forward)
        if len(current.keys) != len(values):
            raise ServiceError("实例键宽不符", code="INVALID_OBJECT_REF", status_code=422)
        where = [c == v for c, v in zip(current.keys, values, strict=True)]
        from_clause = (
            current.from_clause.join(target.from_clause, match)
            if bridge is None
            else current.from_clause.join(
                bridge, and_(*[c == v for c, v in zip(current.keys, values, strict=True)])
            ).join(target.from_clause, match)
        )
        query = (
            select(
                *[c.label(f"__key_{i}") for i, c in enumerate(target.keys)],
                *[c.label(n) for n, c in target.fields.items()],
            )
            .select_from(from_clause)
            .where(*where, *current.where, *target.where)
            .distinct()
            .order_by(*target.keys)
            .limit(101)
        )
        rows = list(conn.execute(query).mappings())
        result = []
        for row in rows[:100]:
            typed = typed_key([row[f"__key_{i}"] for i in range(len(target.keys))])
            fields = {n: row[n] for n in target.fields}
            result.append(
                database_object(
                    target_type,
                    {
                        "__key": typed,
                        "values": fields,
                        "display_text": database_display_text(
                            draft, UUID(str(target_type)), fields, typed
                        ),
                    },
                )
            )
        return result, current.dates + target.dates, len(rows) > 100


def database_neighborhood(db, workspace_id, draft, body, settings):
    center = query_instances(
        db,
        workspace_id,
        draft,
        body.type_id,
        settings,
        key=body.key,
        limit=2,
        snapshot_date=body.snapshot_date,
    )
    if not center["items"]:
        raise NotFoundError("实例不存在")
    obj = database_object(body.type_id, center["items"][0])
    nodes, edges, warnings, dates = {obj["id"]: obj}, {}, set(), center["snapshot_dates"]
    frontier, queries, started, truncated = [obj], 0, monotonic(), False
    index = draft_index(draft)
    for _ in range(body.depth):
        following = []
        for current in frontier:
            type_id = UUID(current["type_id"])
            for link in index.effective_links(type_id):
                for forward in (True, False):
                    owner = link.source_type_id if forward else link.target_type_id
                    if not index.is_a(type_id, owner):
                        continue
                    declared = link.target_type_id if forward else link.source_type_id
                    targets = resolve_binding(draft, declared).virtual_types or (declared,)
                    for target_type in targets:
                        if (
                            len(nodes) >= 100
                            or len(edges) >= 300
                            or queries >= 50
                            or monotonic() - started > 15
                        ):
                            truncated = True
                            break
                        binding = resolve_binding(draft, type_id)
                        target_binding = resolve_binding(draft, target_type)
                        join = binding.link_bindings.get(
                            link.id,
                            target_binding.link_bindings.get(link.id, link.data_join),
                        )
                        queries += 1
                        try:
                            rows, selected, more = related_rows(
                                db,
                                workspace_id,
                                draft,
                                settings,
                                type_id,
                                target_type,
                                join,
                                current["key"],
                                forward,
                                body.snapshot_date,
                            )
                        except ServiceError as exc:
                            warnings.add(
                                (link.display_name or link.name) + "：" + exc.message
                            )
                            continue
                        dates += selected
                        truncated |= more
                        for node in rows:
                            if node["id"] not in nodes:
                                if len(nodes) >= 100:
                                    truncated = True
                                    break
                                nodes[node["id"]] = node
                                following.append(node)
                            a, b = (
                                (current["id"], node["id"])
                                if forward
                                else (node["id"], current["id"])
                            )
                            eid = f"{link.id}:{a}:{b}"
                            edges[eid] = {
                                "id": eid,
                                "type_id": str(link.id),
                                "source_id": a,
                                "target_id": b,
                                "evidence": [],
                            }
        frontier = following
        if not frontier or truncated:
            break
    return {
        "center_id": obj["id"],
        "objects": list(nodes.values()),
        "links": list(edges.values()),
        "warnings": sorted(warnings),
        "truncated": truncated,
        "source": "database",
        "depth": body.depth,
        "snapshot_dates": dates,
    }
