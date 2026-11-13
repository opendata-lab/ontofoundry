from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.contracts.users import (
    MemberCreate,
    MemberItem,
    MemberList,
    RoleUpdate,
    SpaceUpdate,
    UserSearchList,
    WorkspaceItem,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.services import users
from ontofoundry_api.services.access import require_manage
from ontofoundry_api.services.dataagent_health import dataagent_health

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["settings"])


@router.get("/settings/dataagent-health")
async def get_dataagent_health(workspace_id: str, request: Request, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return await dataagent_health(request.app.state.settings, workspace_id)


@router.patch("", response_model=WorkspaceItem)
def update_space(workspace_id: str, body: SpaceUpdate, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return users.update_workspace(db, workspace_id, body, user.id)


@router.get("/members", response_model=MemberList)
def members(workspace_id: str, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return {"items": users.list_members(db, workspace_id)}


@router.get("/users/search", response_model=UserSearchList)
def search_users(workspace_id: str, q: str = "", db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return {"items": users.search_users(db, workspace_id, q)}


@router.post("/members", status_code=201, response_model=MemberItem)
def add_member(workspace_id: str, body: MemberCreate, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return users.membership(db, workspace_id, body.user_id, body.role, create_only=True)


@router.patch("/members/{member_id}", response_model=MemberItem)
def change_member(workspace_id: str, member_id: int, body: RoleUpdate, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    target = users.member_by_id(db, workspace_id, member_id)
    return users.membership(db, workspace_id, target.user_id, body.role)


@router.delete("/members/{member_id}")
def remove_member(workspace_id: str, member_id: int, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    target = users.member_by_id(db, workspace_id, member_id)
    users.membership(db, workspace_id, target.user_id, None)
    return {"ok": True}
