from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.contracts.instances import AbandonSessionRead
from ontofoundry_api.contracts.session_writes import SessionMode, SessionPatch, SessionRead
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.models import Strict
from ontofoundry_api.services import sessions as session_service
from ontofoundry_api.services.access import require_edit, require_read

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = Field(default="新的建模会话", min_length=1, max_length=240)
    mode: SessionMode = "model"


class SessionPublish(Strict):
    expected_session_revision: int
    expected_current_version_id: str | None = None
    expected_merged_snapshot_sha256: str | None = None
    expected_instance_change_sequence: int | None = None
    message: str = Field(default="", max_length=240)

    @property
    def session_revision(self):
        return self.expected_session_revision

    @property
    def strict(self):
        return True


class MergeResolution(Strict):
    expected_session_revision: int
    expected_current_version_id: str | None
    resolutions: dict[str, dict[str, Any]]


def schedule_run_sync(request: Request, background: BackgroundTasks, items) -> None:
    """Let reads converge a run nobody is watching: after the response, sync
    each session whose stored run state may lag DataAgent."""
    from ontofoundry_api.services.modeling_runs import needs_run_sync, sync_session_run

    for item in items:
        if needs_run_sync(request.app, item):
            background.add_task(sync_session_run, request.app, item.workspace_id, item.id)


@router.post("/sessions/{session_id}/resolve-merge")
def resolve_merge(
    workspace_id: str,
    session_id: str,
    body: MergeResolution,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    return session_service.resolve_merge(
        workspace_id=workspace_id,
        session_id=session_id,
        body=body,
        db=db,
        user_id=user.id,
    )


@router.get("/sessions")
def sessions(
    workspace_id: str,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    rows, result = session_service.sessions(workspace_id=workspace_id, db=db)
    schedule_run_sync(request, background, rows)
    return result


@router.post("/sessions", status_code=201)
def create_session(
    workspace_id: str,
    body: SessionCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    return session_service.create_session(
        workspace_id=workspace_id, body=body, db=db, user=user
    )


@router.get("/sessions/personal", response_model=SessionRead)
def personal_session(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    return session_service.personal_session(workspace_id, db, user)


@router.get("/sessions/{session_id}")
async def read_session(
    workspace_id: str,
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """The session as it stands now: a run that has finished gets its result
    settled before the answer, so the page reading it after the conversation
    ends sees the new proposals."""
    require_read(db, str(workspace_id), user)
    from ontofoundry_api.services.modeling_runs import needs_run_sync, settle_session_run

    item = session_service.get_modeling_session(db, workspace_id, session_id)
    if needs_run_sync(request.app, item):
        await settle_session_run(request.app, workspace_id, session_id)
        db.expire(item)
        item = session_service.get_modeling_session(db, workspace_id, session_id)
    return session_service.session_response(db, item)


@router.patch("/sessions/{session_id}", response_model=SessionRead)
def save_session(
    workspace_id: str,
    session_id: str,
    body: SessionPatch,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    return session_service.save_session(
        workspace_id=workspace_id,
        session_id=session_id,
        body=body,
        settings=request.app.state.settings,
        db=db,
        user=user,
    )


@router.post("/sessions/{session_id}/validate")
def validate_session(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    return session_service.validate_session(
        workspace_id=workspace_id, session_id=session_id, db=db
    )


@router.post("/sessions/{session_id}/publish")
def publish_session(
    workspace_id: str,
    session_id: str,
    body: SessionPublish,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    return session_service.publish_session(
        workspace_id=workspace_id,
        session_id=session_id,
        body=body,
        settings=request.app.state.settings,
        db=db,
        user=user,
    )


@router.post("/sessions/{session_id}/publish-preview")
def preview_definition(
    workspace_id: str,
    session_id: str,
    body: SessionPublish,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    return session_service.preview_definition(
        workspace_id=workspace_id,
        session_id=session_id,
        body=body,
        settings=request.app.state.settings,
        db=db,
    )


@router.post("/sessions/{session_id}/abandon", response_model=AbandonSessionRead)
def abandon_session(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_edit(db, str(workspace_id), user)
    from ontofoundry_api.services.instance_store import abandon

    result = abandon(db, workspace_id, session_id, user.id)
    db.commit()
    return result
