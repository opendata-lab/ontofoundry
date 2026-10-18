"""Read-only exports and independently authorized content-addressed downloads."""

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, ontology_principal
from ontofoundry_api.contracts.exports import ExportPreview
from ontofoundry_api.database import get_db
from ontofoundry_api.services.access import require_instances, require_mappings
from ontofoundry_api.services.exports import download_export, export_snapshot

router = APIRouter(
    prefix="/api/v1/modeling/workspaces/{workspace_id}/exports/{adapter_id}",
    tags=["exports"],
)


def permissions(db, workspace_id, user):
    require_instances(db, workspace_id, user)
    require_mappings(db, workspace_id, user)


@router.get("", response_model=ExportPreview)
def preview(
    workspace_id: UUID,
    adapter_id: str,
    version_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(ontology_principal),
):
    permissions(db, str(workspace_id), user)
    return export_snapshot(
        db, request.app.state.settings, str(workspace_id), adapter_id, str(version_id)
    )


@router.get("/artifacts/{content_sha256}")
def download(
    workspace_id: UUID,
    adapter_id: str,
    content_sha256: str,
    version_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(ontology_principal),
):
    permissions(db, str(workspace_id), user)
    data, description = download_export(
        db,
        request.app.state.settings,
        str(workspace_id),
        adapter_id,
        str(version_id),
        content_sha256,
    )
    return Response(
        data,
        media_type=description["media_type"],
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(description["filename"]),
            "ETag": '"' + content_sha256 + '"',
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": content_sha256,
        },
    )
