"""File import previews, confirmation and explicit human completion."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.contracts.imports import (
    ImportCompletionRequest,
    ImportConfirm,
    ImportConfirmed,
    ImportPreview,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.import_completion import complete_import
from ontofoundry_api.services.imports import (
    confirm_import,
    get_import,
    import_view,
    preview_import,
)

router = APIRouter(
    prefix="/api/v1/modeling/workspaces/{workspace_id}/imports/{adapter_id}",
    tags=["imports"],
)


@router.post("", response_model=ImportPreview, status_code=201)
async def preview(
    workspace_id: UUID,
    adapter_id: str,
    request: Request,
    name: str = Query(min_length=1, max_length=240),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, str(workspace_id), user.id)
    if set(request.query_params) - {"name"}:
        raise ServiceError(
            "预览不接受替换或直接发布等附加选项",
            code="IMPORT_OPTIONS_UNSUPPORTED",
            status_code=422,
        )
    data = bytearray()
    async for block in request.stream():
        data.extend(block)
        if len(data) > request.app.state.settings.max_file_mb * 1024 * 1024:
            raise ServiceError(
                "文件超过上传限制", code="IMPORT_FILE_TOO_LARGE", status_code=413
            )
    return preview_import(
        db,
        request.app.state.settings,
        str(workspace_id),
        user.id,
        adapter_id,
        name,
        bytes(data),
    )


@router.get("/{import_id}", response_model=ImportPreview)
def read(
    workspace_id: UUID,
    adapter_id: str,
    import_id: UUID,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, str(workspace_id), user.id)
    return import_view(db, get_import(db, str(workspace_id), adapter_id, str(import_id)))


@router.post("/{import_id}/confirm", response_model=ImportConfirmed)
def confirm(
    workspace_id: UUID,
    adapter_id: str,
    import_id: UUID,
    body: ImportConfirm,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, str(workspace_id), user.id)
    return confirm_import(
        db,
        request.app.state.settings,
        str(workspace_id),
        user.id,
        adapter_id,
        str(import_id),
        body,
    )


@router.post("/{import_id}/completions", response_model=ImportConfirmed)
def complete(
    workspace_id: UUID,
    adapter_id: str,
    import_id: UUID,
    body: ImportCompletionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, str(workspace_id), user.id)
    return complete_import(
        db,
        request.app.state.settings,
        str(workspace_id),
        user.id,
        adapter_id,
        str(import_id),
        body,
    )
