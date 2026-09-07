import hashlib
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ServiceTokenRecord, UserRecord, WorkspaceMemberRecord
from ontofoundry_api.services.workspaces import get_workspace, workspace_summary

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["settings"])


class SpaceUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=1200)


@router.patch("")
def update_space(
    workspace_id: str,
    body: SpaceUpdate,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    space = get_workspace(db, workspace_id)
    space.name, space.description = body.name, body.description
    db.commit()
    return workspace_summary(db, space, user.id)


@router.get("/members")
def members(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    rows = db.execute(
        select(WorkspaceMemberRecord, UserRecord)
        .join(UserRecord, UserRecord.id == WorkspaceMemberRecord.user_id)
        .where(WorkspaceMemberRecord.workspace_id == workspace_id)
    ).all()
    return {
        "items": [
            {
                "id": m.id,
                "user_id": u.id,
                "name": u.display_name,
                "subject": u.subject,
                "role": m.role,
            }
            for m, u in rows
        ]
    }


class MemberCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    role: str = Field(default="member", pattern="^(member|admin)$")


@router.post("/members")
def add_member(
    workspace_id: str,
    body: MemberCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    target = db.scalar(select(UserRecord).where(UserRecord.subject == body.subject))
    if not target:
        raise HTTPException(404, "用户尚未登录过平台，请让对方先完成一次登录")
    existing = db.scalar(
        select(WorkspaceMemberRecord).where(
            WorkspaceMemberRecord.workspace_id == workspace_id,
            WorkspaceMemberRecord.user_id == target.id,
        )
    )
    if existing:
        raise HTTPException(409, "该用户已是空间成员")
    db.add(
        WorkspaceMemberRecord(workspace_id=workspace_id, user_id=target.id, role=body.role)
    )
    db.commit()
    return {"ok": True}


@router.delete("/members/{member_id}")
def remove_member(
    workspace_id: str,
    member_id: int,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    target = db.get(WorkspaceMemberRecord, member_id)
    if not target or target.workspace_id != workspace_id:
        raise HTTPException(404, "成员不存在")
    if target.user_id == user.id:
        raise HTTPException(422, "不能移除自己，请由另一名管理员操作")
    db.delete(target)
    db.commit()
    return {"ok": True}


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/service-tokens")
def tokens(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    return {
        "items": [
            {"id": t.id, "name": t.name, "created_at": t.created_at}
            for t in db.scalars(
                select(ServiceTokenRecord).where(
                    ServiceTokenRecord.workspace_id == workspace_id
                )
            ).all()
        ]
    }


@router.post("/service-tokens")
def create_token(
    workspace_id: str,
    body: TokenCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    token = "of_" + secrets.token_urlsafe(32)
    item = ServiceTokenRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by=user.id,
        name=body.name,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
    )
    db.add(item)
    db.commit()
    return {"id": item.id, "name": item.name, "token": token}


@router.delete("/service-tokens/{token_id}")
def revoke(
    workspace_id: str,
    token_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id, admin=True)
    item = db.get(ServiceTokenRecord, token_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(404, "令牌不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}
