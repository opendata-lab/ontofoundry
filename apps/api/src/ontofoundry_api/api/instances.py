"""Bounded read-through neighborhoods. No copied database rows or graph store."""

from time import monotonic
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import MetaData, Table, select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.connections import (
    PreviewRequest,
    connect_readonly,
    get_connection,
    query_mapping,
)
from ontofoundry_api.api.modeling import (
    get_modeling_session,
    published_snapshot,
    require_member,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.models import OntologyDraft

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["instances"])


class NeighborhoodRequest(BaseModel):
    type_id: str
    key: str = Field(max_length=2000)
    session_id: str | None = None
    depth: int = Field(default=1, ge=1, le=3)


def database_object(type_id, row):
    key = str(row["__key"])
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
    item = get_connection(db, wid, str(source_mapping.connection_id))
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
        if join.source_column not in source.c or join.target_column not in target.c:
            raise HTTPException(422, "关系字段已不存在，请检查关系映射")
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
                    target, source.c[join.source_column] == target.c[join.target_column]
                )
            )
            .where(current.c[current_mapping.key_column] == key)
            .distinct()
            .order_by(other.c[other_mapping.key_column])
            .limit(limit + 1)
        )
        return [dict(row) for row in conn.execute(query).mappings()]


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
    draft = OntologyDraft.model_validate(raw)
    mappings = {str(m.type_id): m for m in draft.mappings}
    if body.type_id not in mappings:
        raise HTTPException(422, "此对象尚未配置数据映射")
    settings = request.app.state.settings
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
                endpoints = (str(relation.source_type_id), str(relation.target_type_id))
                if current["type_id"] not in endpoints:
                    continue
                source, target = (mappings.get(tid) for tid in endpoints)
                if not relation.data_join or not source or not target:
                    warnings.add(f"{relation.name}：未配置完整关系映射")
                    continue
                if source.connection_id != target.connection_id:
                    warnings.add(f"{relation.name}：跨连接关系不可查询")
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
                            relation.data_join,
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
