from contextlib import contextmanager
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import (
    URL,
    MetaData,
    String,
    Table,
    cast,
    create_engine,
    inspect,
    or_,
    select,
    text,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.domain.models import DataMapping

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["data"])


def public_connection(item):
    return {"id": item.id, "name": item.name, "kind": item.kind, **item.config_json}


def get_connection(db, wid, cid):
    item = db.get(ConnectionRecord, cid)
    if not item or item.workspace_id != wid:
        raise HTTPException(404, "数据连接不存在")
    return item


def resolve_alias(db, wid, alias: str):
    """Bind a mapping's data source name to a configured connection.

    The published model only names the source, so a workspace that has not
    configured that name yet gets a precise message instead of a broken query.
    """
    item = db.scalar(
        select(ConnectionRecord).where(
            ConnectionRecord.workspace_id == wid, ConnectionRecord.name == alias
        )
    )
    if not item:
        raise HTTPException(422, f"映射使用的数据源“{alias}”还没有在本空间配置连接")
    return item


@contextmanager
def connect_readonly(item, settings):
    if not settings.connection_key:
        raise HTTPException(503, "服务器尚未配置连接加密主密钥")
    try:
        password = (
            Fernet(settings.connection_key.encode())
            .decrypt(item.secret_encrypted.encode())
            .decode()
        )
        config = item.config_json
        driver = "postgresql+psycopg" if item.kind == "postgresql" else "mysql+pymysql"
        args = (
            {"connect_timeout": 5, "options": "-c statement_timeout=10000"}
            if item.kind == "postgresql"
            else {"connect_timeout": 5, "read_timeout": 10, "write_timeout": 5}
        )
        engine = create_engine(
            URL.create(
                driver,
                username=config["username"],
                password=password,
                host=config["host"],
                port=config["port"],
                database=config["database"],
            ),
            connect_args=args,
            pool_pre_ping=False,
        )
        try:
            with engine.connect() as connection:
                if item.kind == "postgresql":
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                elif item.kind == "mysql":
                    connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
                    connection.execute(text("SET SESSION MAX_EXECUTION_TIME=10000"))
                else:
                    connection.execute(text("SET query_timeout = 10"))
                yield connection
                connection.rollback()
        finally:
            engine.dispose()
    except (SQLAlchemyError, InvalidToken, ValueError) as exc:
        raise HTTPException(
            422, "连接或只读查询失败，请检查只读账号、网络、字段和服务器配置"
        ) from exc


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(pattern="^(postgresql|mysql|doris)$")
    host: str = Field(min_length=1, max_length=240)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=4096)


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
    key = request.app.state.settings.connection_key
    if not key:
        raise HTTPException(503, "请先在服务器设置 ONTOFOUNDRY_CONNECTION_KEY 加密主密钥")
    try:
        encrypted = Fernet(key.encode()).encrypt(body.password.encode()).decode()
    except ValueError as exc:
        raise HTTPException(503, "连接加密主密钥格式无效") from exc
    # Mappings name their data source, so the name has to identify one connection.
    if db.scalar(
        select(ConnectionRecord).where(
            ConnectionRecord.workspace_id == workspace_id,
            ConnectionRecord.name == body.name,
        )
    ):
        raise HTTPException(409, "本空间已有同名数据连接，请换一个名称")
    item = ConnectionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        name=body.name,
        kind=body.kind,
        config_json=body.model_dump(exclude={"name", "kind", "password"}),
        secret_encrypted=encrypted,
    )
    with connect_readonly(item, request.app.state.settings) as conn:
        conn.execute(text("SELECT 1"))
    db.add(item)
    db.commit()
    return public_connection(item)


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
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    with connect_readonly(
        get_connection(db, workspace_id, connection_id), request.app.state.settings
    ) as conn:
        inspector = inspect(conn)
        names = sorted(set(inspector.get_table_names() + inspector.get_view_names()))
        if table:
            if table not in names:
                raise HTTPException(404, "数据表不存在")
            pks = inspector.get_pk_constraint(table).get("constrained_columns", [])
            return {
                "items": [
                    {
                        "name": table,
                        "schema": None,
                        "columns": [
                            {
                                "name": c["name"],
                                "type": str(c["type"]),
                                "primary_key": c["name"] in pks,
                            }
                            for c in inspector.get_columns(table)
                        ],
                    }
                ]
            }
        return {"items": [{"name": n, "schema": None, "columns": []} for n in names]}


class PreviewRequest(BaseModel):
    mapping: DataMapping
    q: str = Field(default="", max_length=240)
    key: str | None = None
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)


def query_mapping(db, workspace_id, body, settings):
    mapping = body.mapping
    item = resolve_alias(db, workspace_id, mapping.connection_alias)
    with connect_readonly(item, settings) as conn:
        table = Table(
            mapping.table_name, MetaData(), schema=mapping.schema_name, autoload_with=conn
        )
        column_names = set(mapping.fields.values()) | {mapping.key_column}
        if not column_names <= set(table.c.keys()):
            raise HTTPException(422, "映射字段不存在，请刷新字段列表")
        columns = [table.c[mapping.key_column].label("__key")] + [
            table.c[column].label(name) for name, column in mapping.fields.items()
        ]
        query = select(*columns)
        if body.key is not None:
            query = query.where(table.c[mapping.key_column] == body.key)
        elif body.q:
            query = query.where(
                or_(
                    *(
                        cast(table.c[name], String).contains(body.q, autoescape=True)
                        for name in column_names
                    )
                )
            )
        query = (
            query.order_by(table.c[mapping.key_column])
            .offset(body.offset)
            .limit(body.limit + 1)
        )
        rows = [dict(r) for r in conn.execute(query).mappings()]
        return {
            "items": rows[: body.limit],
            "has_more": len(rows) > body.limit,
            "source": "database",
        }


@router.post("/mapping-preview")
def preview(
    workspace_id: str,
    body: PreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    return query_mapping(db, workspace_id, body, request.app.state.settings)
