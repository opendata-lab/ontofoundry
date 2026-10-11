"""Bounded read-through neighborhoods. No copied database rows or graph store."""

from time import monotonic
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import MetaData, Table, and_, select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.connections import (
    PreviewRequest,
    connect_readonly,
    query_mapping,
    resolve_alias,
)
from ontofoundry_api.api.modeling import (
    get_modeling_session,
    published_snapshot,
    require_member,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.semantic_views import SemanticViews, join_columns
from ontofoundry_api.domain.snapshot import read_snapshot
from ontofoundry_api.services.source_rows import source_key, validate_source_rows

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["instances"])


class NeighborhoodRequest(BaseModel):
    type_id: str
    key: str = Field(max_length=2000)
    session_id: str | None = None
    depth: int = Field(default=1, ge=1, le=3)


def database_object(type_id, row):
    key = source_key(row.get("__key"))
    return {
        "id": f"db:{type_id}:{quote(key, safe='')}",
        "type_id": str(type_id),
        "key": key,
        "name": key,
        "values": {k: v for k, v in row.items() if k != "__key"},
        "evidence": [],
        "source": "database",
    }


def related_rows(
    db, wid, settings, source_mapping, target_mapping, join, key, forward, limit
):
    item = resolve_alias(db, wid, source_mapping.connection_alias)
    with connect_readonly(item, settings) as conn:
        metadata = MetaData()
        source = Table(
            source_mapping.table_name,
            metadata,
            schema=source_mapping.schema_name,
            autoload_with=conn,
        ).alias("source_object")
        target = Table(
            target_mapping.table_name,
            metadata,
            schema=target_mapping.schema_name,
            autoload_with=conn,
        ).alias("target_object")
        source_columns, target_columns = join_columns(join)
        missing = [
            f"{mapping.table_name}.{column}"
            for mapping, table, columns in (
                (source_mapping, source, source_columns),
                (target_mapping, target, target_columns),
            )
            for column in columns if column not in table.c
        ]
        if missing:
            raise HTTPException(422, "关系物理字段不存在：" + "、".join(missing))
        current, current_mapping = (
            (source, source_mapping) if forward else (target, target_mapping)
        )
        other, other_mapping = (
            (target, target_mapping) if forward else (source, source_mapping)
        )
        if (
            not (
                {other_mapping.key_column, *other_mapping.fields.values()}
                <= set(other.c.keys())
            )
            or current_mapping.key_column not in current.c
        ):
            raise HTTPException(422, "对象映射字段已不存在，请检查属性映射")
        query = (
            select(
                other.c[other_mapping.key_column].label("__key"),
                *[
                    other.c[column].label(name)
                    for name, column in other_mapping.fields.items()
                ],
            )
            .select_from(
                source.join(
                    target, and_(*(source.c[a] == target.c[b] for a, b in zip(source_columns, target_columns, strict=True)))
                )
            )
            .where(current.c[current_mapping.key_column] == key)
            .distinct()
            .order_by(other.c[other_mapping.key_column])
            .limit(limit + 1)
        )
        rows = [dict(row) for row in conn.execute(query).mappings()]
        validate_source_rows(rows)
        return rows


@router.post("/instance-neighborhood")
def neighborhood(
    workspace_id: str,
    body: NeighborhoodRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    raw = (
        get_modeling_session(db, workspace_id, body.session_id).draft_json
        if body.session_id
        else published_snapshot(workspace_id, db, user)
    )
    return database_neighborhood(
        db,
        workspace_id,
        read_snapshot(raw, workspace_id, target_version="3"),
        body,
        request.app.state.settings,
    )


def database_neighborhood(db, workspace_id, draft, body, settings):
    from ontofoundry_api.services.instance_query import mapping_for
    mapping_for(draft, body.type_id)
    views = SemanticViews(draft)
    mappings = {str(t.id): a.mapping for t in draft.object_types if (a := views.analyze(t.id)).mapping}
    center_rows = query_mapping(
        db,
        workspace_id,
        PreviewRequest(mapping=mappings[body.type_id], key=body.key, limit=2),
        settings,
    )["items"]
    if not center_rows:
        raise HTTPException(404, "实例不存在或源数据已删除")
    if len(center_rows) > 1 or center_rows[0]["__key"] is None:
        raise HTTPException(422, "实例标识不唯一或为空，请更换映射标识字段")
    center = database_object(body.type_id, center_rows[0])
    nodes, edges, warnings = {center["id"]: center}, {}, set()
    frontier, queries, started, truncated = [center], 0, monotonic(), False
    for _ in range(body.depth):
        next_frontier = []
        for current in frontier:
            for relation in draft.link_types:
                if relation.source_type_id is None:
                    continue
                endpoints = (str(relation.source_type_id), str(relation.target_type_id))
                if current["type_id"] not in endpoints:
                    continue
                source, target = (mappings.get(tid) for tid in endpoints)
                join = views.join(relation.id)
                if source and target and source.connection_alias != target.connection_alias:
                    warnings.add(f"{relation.name}：两端在不同数据源，关系不可查询")
                    continue
                if not join or not source or not target:
                    reason = views.join_errors.get(str(relation.id), "未配置完整关系映射")
                    warnings.add(f"{relation.name}：{reason}")
                    continue
                for forward in (True, False):
                    if current["type_id"] != endpoints[0 if forward else 1]:
                        continue
                    if (
                        len(nodes) >= 100
                        or len(edges) >= 300
                        or queries >= 50
                        or monotonic() - started >= 15
                    ):
                        truncated = True
                        break
                    queries += 1
                    try:
                        rows = related_rows(
                            db,
                            workspace_id,
                            settings,
                            source,
                            target,
                            join,
                            current["key"],
                            forward,
                            100,
                        )
                    except HTTPException as exc:
                        warnings.add(f"{relation.name}：{exc.detail}")
                        continue
                    truncated |= len(rows) > 100
                    for row in rows[:100]:
                        if row["__key"] is None:
                            warnings.add(f"{relation.name}：跳过标识为空的实例")
                            continue
                        node = database_object(endpoints[1 if forward else 0], row)
                        if node["id"] not in nodes:
                            if len(nodes) >= 100:
                                truncated = True
                                break
                            nodes[node["id"]] = node
                            next_frontier.append(node)
                        source_id, target_id = (
                            (current["id"], node["id"])
                            if forward
                            else (node["id"], current["id"])
                        )
                        eid = f"{relation.id}:{source_id}:{target_id}"
                        if len(edges) >= 300 and eid not in edges:
                            truncated = True
                            break
                        edges[eid] = {
                            "id": eid,
                            "type_id": str(relation.id),
                            "source_id": source_id,
                            "target_id": target_id,
                            "evidence": [],
                        }
        frontier = next_frontier
        if not frontier or truncated:
            break
    return {
        "center_id": center["id"],
        "objects": list(nodes.values()),
        "links": list(edges.values()),
        "warnings": sorted(warnings),
        "truncated": truncated,
        "source": "database",
        "depth": body.depth,
    }
