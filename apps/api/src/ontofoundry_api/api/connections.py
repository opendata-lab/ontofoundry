from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import (
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.domain.models import DataMapping
from ontofoundry_api.services.readonly import connect_readonly

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["data"])


def public_connection(item):
    return {"id": item.id, "name": item.name, "kind": item.kind, **item.config_json}


def get_connection(db, wid, cid):
    item = db.get(ConnectionRecord, cid)
    if not item or item.workspace_id != wid:
        raise HTTPException(404, "数据连接不存在")
    return item


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
        secret_encrypted=body.password,
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
    schema_name: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    with connect_readonly(
        get_connection(db, workspace_id, connection_id), request.app.state.settings
    ) as conn:
        inspector = inspect(conn)
        names = sorted(
            set(
                inspector.get_table_names(schema=schema_name)
                + inspector.get_view_names(schema=schema_name)
            )
        )
        if table:
            if table not in names:
                raise HTTPException(404, "数据表不存在")
            pks = inspector.get_pk_constraint(table, schema=schema_name).get(
                "constrained_columns", []
            )
            return {
                "items": [
                    {
                        "name": table,
                        "schema": schema_name,
                        "columns": [
                            {
                                "name": c["name"],
                                "type": str(c["type"]),
                                "primary_key": c["name"] in pks,
                                "nullable": c.get("nullable"),
                                "comment": c.get("comment"),
                            }
                            for c in inspector.get_columns(table, schema=schema_name)
                        ],
                    }
                ]
            }
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
