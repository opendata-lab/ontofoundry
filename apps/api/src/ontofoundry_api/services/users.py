"""Pre-created users, directory queries and serialized membership mutations."""

from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from ontofoundry_api.db_models import UserRecord, WorkspaceMemberRecord, WorkspaceRecord
from ontofoundry_api.services.auth_config import is_local_account, is_platform_admin
from ontofoundry_api.services.errors import ConflictError, NotFoundError
from ontofoundry_api.services.workspaces import get_workspace, workspace_summary


def get_user(db, user_id):
    user = db.get(UserRecord, user_id)
    if user is None:
        raise NotFoundError(
            "用户不存在，请联系平台管理员在用户管理中创建", code="USER_NOT_FOUND"
        )
    return user


def member_item(member, user):
    return {
        "id": member.id,
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": member.role,
        "last_login_at": user.last_login_at,
    }


def membership(db, workspace_id, user_id, role, *, create_only=False):
    """Add, change or remove a membership under the workspace's row lock.

    Config-derived platform administrators never count toward LAST_ADMIN.
    """
    space = db.scalar(
        select(WorkspaceRecord)
        .where(WorkspaceRecord.id == workspace_id)
        .with_for_update()
    )
    if space is None:
        get_workspace(db, workspace_id)
    user = get_user(db, user_id)
    target = db.scalar(
        select(WorkspaceMemberRecord)
        .where(
            WorkspaceMemberRecord.workspace_id == workspace_id,
            WorkspaceMemberRecord.user_id == user_id,
        )
        .execution_options(populate_existing=True)
    )
    if target and create_only:
        raise ConflictError("该用户已是空间成员", code="ALREADY_MEMBER")
    if target and target.role == "admin" and role != "admin":
        admins = db.scalar(
            select(func.count())
            .select_from(WorkspaceMemberRecord)
            .where(
                WorkspaceMemberRecord.workspace_id == workspace_id,
                WorkspaceMemberRecord.role == "admin",
            )
        )
        if admins <= 1:
            raise ConflictError("该空间至少需要一名管理员", code="LAST_ADMIN")
    if role is None:
        if target:
            db.delete(target)
    elif target:
        target.role = role
    else:
        target = WorkspaceMemberRecord(
            workspace_id=workspace_id, user_id=user_id, role=role
        )
        db.add(target)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("该用户已是空间成员", code="ALREADY_MEMBER") from None
    return member_item(target, user) if role is not None else None


def member_by_id(db, workspace_id, member_id):
    target = db.get(WorkspaceMemberRecord, member_id)
    if target is None or target.workspace_id != workspace_id:
        raise NotFoundError("成员不存在", code="MEMBER_NOT_FOUND")
    return target


def list_members(db, workspace_id):
    rows = db.execute(
        select(WorkspaceMemberRecord, UserRecord)
        .join(UserRecord, UserRecord.id == WorkspaceMemberRecord.user_id)
        .where(WorkspaceMemberRecord.workspace_id == workspace_id)
        .order_by(WorkspaceMemberRecord.id)
    )
    return [member_item(member, user) for member, user in rows]


def user_workspaces(db, user_id, *, visibility=False):
    rows = db.execute(
        select(WorkspaceRecord, WorkspaceMemberRecord.role)
        .join(WorkspaceMemberRecord, WorkspaceMemberRecord.workspace_id == WorkspaceRecord.id)
        .where(WorkspaceMemberRecord.user_id == user_id)
        .order_by(WorkspaceRecord.name)
    )
    return [
        {
            "id": space.id,
            "name": space.name,
            "role": role,
            **({"is_public": space.is_public} if visibility else {}),
        }
        for space, role in rows
    ]


def user_item(db, user, config, *, dev_mode=False):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "local_account": is_local_account(user.username, config),
        "platform_admin": is_platform_admin(user.username, config, dev_mode=dev_mode),
        "last_login_at": user.last_login_at,
        "workspaces": user_workspaces(db, user.id),
    }


def _search(query, q):
    if not q:
        return query
    # autoescape treats user-supplied SQL wildcard characters as literal text.
    return query.where(
        or_(
            func.lower(UserRecord.username).contains(q.lower(), autoescape=True),
            func.lower(UserRecord.display_name).contains(q.lower(), autoescape=True),
        )
    )


def list_users(db, config, q="", *, dev_mode=False):
    users = db.scalars(
        _search(select(UserRecord), q).order_by(func.lower(UserRecord.username))
    )
    return [user_item(db, user, config, dev_mode=dev_mode) for user in users]


def search_users(db, workspace_id, q):
    current = select(WorkspaceMemberRecord.user_id).where(
        WorkspaceMemberRecord.workspace_id == workspace_id
    )
    users = db.scalars(
        _search(select(UserRecord).where(UserRecord.id.not_in(current)), q)
        .order_by(func.lower(UserRecord.username))
        .limit(20)
    )
    return [
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "last_login_at": user.last_login_at,
        }
        for user in users
    ]


def create_user(db, body, config, *, dev_mode=False):
    if db.scalar(
        select(UserRecord.id).where(func.lower(UserRecord.username) == body.username.lower())
    ):
        raise ConflictError("用户名已存在", code="USERNAME_EXISTS")
    user = UserRecord(id=str(uuid4()), **body.model_dump())
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("用户名已存在", code="USERNAME_EXISTS") from None
    return user_item(db, user, config, dev_mode=dev_mode)


def all_workspaces(db):
    return [
        {"id": space.id, "name": space.name, "is_public": space.is_public}
        for space in db.scalars(select(WorkspaceRecord).order_by(WorkspaceRecord.name))
    ]


def update_workspace(db, workspace_id, body, user_id):
    space = get_workspace(db, workspace_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(space, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("工作空间名称已存在，请使用其他名称") from None
    return workspace_summary(db, space, user_id)
