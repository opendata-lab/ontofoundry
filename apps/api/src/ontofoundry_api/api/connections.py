from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import (
    func,
    select,
    text,
)
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.domain.models import DataMapping
from ontofoundry_api.services.connections import delete_connection
from ontofoundry_api.services.readonly import connect_readonly

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["data"])


def public_connection(item):
    return {"id": item.id, "name": item.name, "kind": item.kind, **item.config_json}


def get_connection(db, wid, cid):
    item = db.get(ConnectionRecord, cid)
    if not item or item.workspace_id != wid:
        raise HTTPException(404, "数据连接不存在")
    return item


ConnectionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ConnectionCreate(BaseModel):
    name: ConnectionName
    kind: str = Field(pattern="^(postgresql|mysql|doris)$")
    host: str = Field(min_length=1, max_length=240)
    port: int = Field(ge=1, le=65535)
    # PostgreSQL only: MySQL and Doris connections reach every database on the server.
    database: str = Field(default="", max_length=120)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=4096)

    @model_validator(mode="after")
    def database_only_for_postgres(self):
        if self.kind == "postgresql" and not self.database.strip():
            raise ValueError("PostgreSQL 连接需要填写数据库")
        if self.kind != "postgresql":
            # Libraries are chosen when syncing; a fixed one hid every other library.
            self.database = ""
        return self


class ConnectionUpdate(BaseModel):
    """Every field optional; an omitted password keeps the stored one. The engine cannot change."""

    model_config = {"extra": "forbid"}
    name: ConnectionName | None = None
    host: str | None = Field(default=None, min_length=1, max_length=240)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, max_length=4096)


def _name_taken(db, workspace_id, name, except_id=None):
    query = select(ConnectionRecord).where(
        ConnectionRecord.workspace_id == workspace_id,
        # The name is shown instead of the id, so it must not differ only by case or spaces.
        func.lower(func.trim(ConnectionRecord.name)) == name.lower(),
    )
    if except_id:
        query = query.where(ConnectionRecord.id != except_id)
    return db.scalar(query) is not None


@router.get("/connections")
def connections(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    return {
        "items": [
            public_connection(c)
            for c in db.scalars(
                select(ConnectionRecord).where(
                    ConnectionRecord.workspace_id == workspace_id
                )
            ).all()
        ]
    }


@router.post("/connections", status_code=201)
def create_connection(
    workspace_id: str,
    body: ConnectionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    # Mappings name their data source, so the name has to identify one connection.
    if _name_taken(db, workspace_id, body.name):
        raise HTTPException(409, "本空间已有同名数据连接，请换一个名称")
    item = ConnectionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        name=body.name,
        kind=body.kind,
        config_json=body.model_dump(exclude={"name", "kind", "password"}),
        secret_encrypted=body.password,
    )
    with connect_readonly(item, request.app.state.settings) as conn:
        conn.execute(text("SELECT 1"))
    db.add(item)
    db.commit()
    return public_connection(item)


@router.patch("/connections/{connection_id}")
def update_connection(
    workspace_id: str,
    connection_id: str,
    body: ConnectionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    item = get_connection(db, workspace_id, connection_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and _name_taken(db, workspace_id, changes["name"], except_id=item.id):
        raise HTTPException(409, "本空间已有同名数据连接，请换一个名称")
    config = {**item.config_json, **{k: v for k, v in changes.items() if k in {"host", "port", "database", "username"}}}
    if item.kind != "postgresql":
        config["database"] = ""
    if item.kind == "postgresql" and not (config.get("database") or "").strip():
        raise HTTPException(422, "PostgreSQL 连接需要填写数据库")
    candidate = ConnectionRecord(
        id=item.id, workspace_id=item.workspace_id, name=changes.get("name", item.name), kind=item.kind,
        config_json=config,
        secret_encrypted=changes["password"] if changes.get("password") is not None else item.secret_encrypted,
    )
    # Save only settings that actually connect.
    with connect_readonly(candidate, request.app.state.settings) as conn:
        conn.execute(text("SELECT 1"))
    item.name, item.config_json, item.secret_encrypted = candidate.name, config, candidate.secret_encrypted
    db.commit()
    return public_connection(item)


@router.delete("/connections/{connection_id}", status_code=204)
def remove_connection(
    workspace_id: str,
    connection_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    delete_connection(db, workspace_id, connection_id)
    return Response(status_code=204)


@router.post("/connections/{connection_id}/test")
def test_connection(
    workspace_id: str,
    connection_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    with connect_readonly(
        get_connection(db, workspace_id, connection_id), request.app.state.settings
    ) as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True}


@router.get("/connections/{connection_id}/tables")
def tables(
    workspace_id: str,
    connection_id: str,
    request: Request,
    table: str | None = None,
    schema_name: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    from ontofoundry_api.services.metadata_catalog import list_tables, require_schema
    from ontofoundry_api.services.metadata_sync import normalize_schema, read_table

    connection = get_connection(db, workspace_id, connection_id)
    # Only PostgreSQL has a default schema; MySQL and Doris require a library.
    schema_name = normalize_schema(connection, schema_name)
    require_schema(connection, schema_name)
    with connect_readonly(connection, request.app.state.settings) as conn:
        names = list_tables(conn, schema_name)
        if table:
            if table not in names:
                raise HTTPException(404, "数据表不存在")
            # One reader for every engine, the same one sync uses.
            observed = read_table(conn, schema_name, table)
            return {"items": [{"name": table, "schema": schema_name, "columns": observed.get("columns", [])}]}
        return {"items": [{"name": n, "schema": schema_name, "columns": []} for n in names]}


class TableMaterialRequest(BaseModel):
    schema_name: str | None = Field(default=None, max_length=120)
    tables: list[str] = Field(min_length=1, max_length=20)


@router.post("/connections/{connection_id}/table-material", status_code=201)
def table_material(
    workspace_id: str,
    connection_id: str,
    body: TableMaterialRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    get_connection(db, workspace_id, connection_id)
    from ontofoundry_api.services.errors import DatasetSourceError
    raise DatasetSourceError("请在本体目录创建数据集，并在构建页直接关联到会话；不再生成重复表结构材料", code="DATASET_ASSOCIATION_REQUIRED")


class PreviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    mapping: DataMapping
    session_id: str | None = None
    q: str = Field(default="", max_length=240)
    key: list[dict] | None = None
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)
    snapshot_date: str | None = None


def query_mapping(db, workspace_id, body, settings, draft=None):
    from ontofoundry_api.api.modeling import get_modeling_session, version_snapshot
    from ontofoundry_api.domain.models import OntologyDraft
    from ontofoundry_api.services.instance_plan import query_instances
    from ontofoundry_api.services.workspaces import get_workspace

    if draft is None:
        raw = (
            get_modeling_session(db, workspace_id, body.session_id).draft_json
            if body.session_id
            else version_snapshot(
                db, workspace_id, get_workspace(db, workspace_id).current_version_id
            )
        )
        raw = {
            **raw,
            "mappings": [
                m for m in raw["mappings"] if m["type_id"] != str(body.mapping.type_id)
            ]
            + [body.mapping.model_dump(mode="json")],
        }
        draft = OntologyDraft.model_validate(raw)
    return query_instances(
        db,
        workspace_id,
        draft,
        body.mapping.type_id,
        settings,
        key=body.key,
        q=body.q,
        offset=body.offset,
        limit=body.limit,
        snapshot_date=body.snapshot_date,
    )


@router.post("/mapping-preview")
def preview(
    workspace_id: str,
    body: PreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.services.access import require_instances, require_mappings

    require_instances(db, workspace_id, user)
    require_mappings(db, workspace_id, user)
    return query_mapping(db, workspace_id, body, request.app.state.settings)
