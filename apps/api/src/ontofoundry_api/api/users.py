"""Session-only platform administration and personal membership routes."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.contracts.users import (
    AdminUser,
    AdminUsers,
    AdminWorkspaces,
    Assignment,
    MyWorkspaces,
    RoleUpdate,
    UserCreate,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.services import users
from ontofoundry_api.services.errors import ForbiddenError


def platform_admin(user: Principal = Depends(current_principal)):
    if not user.is_platform_admin:
        raise ForbiddenError("需要平台管理员权限", code="PLATFORM_ADMIN_REQUIRED")
    return user


router = APIRouter(prefix="/api/v1/admin", tags=["users"], dependencies=[Depends(platform_admin)])
me_router = APIRouter(prefix="/api/v1/me", tags=["users"])


@me_router.get("/workspaces", response_model=MyWorkspaces)
def my_workspaces(db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    return {"items": users.user_workspaces(db, user.id, visibility=True)}


@router.get("/users", response_model=AdminUsers)
def list_users(request: Request, q: str = "", db: Session = Depends(get_db)):
    return {"items": users.list_users(db, request.app.state.auth_config, q, dev_mode=request.app.state.settings.auth_mode == "dev")}


@router.post("/users", status_code=201, response_model=AdminUser)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db)):
    return users.create_user(db, body, request.app.state.auth_config, dev_mode=request.app.state.settings.auth_mode == "dev")


@router.get("/workspaces", response_model=AdminWorkspaces)
def workspaces(db: Session = Depends(get_db)):
    return {"items": users.all_workspaces(db)}


@router.put("/users/{user_id}/workspaces/{workspace_id}", response_model=Assignment)
def assign(user_id: str, workspace_id: str, body: RoleUpdate, db: Session = Depends(get_db)):
    users.membership(db, workspace_id, user_id, body.role)
    return {"workspace_id": workspace_id, "role": body.role}


@router.delete("/users/{user_id}/workspaces/{workspace_id}", status_code=204)
def remove(user_id: str, workspace_id: str, db: Session = Depends(get_db)):
    users.membership(db, workspace_id, user_id, None)
    return Response(status_code=204)
