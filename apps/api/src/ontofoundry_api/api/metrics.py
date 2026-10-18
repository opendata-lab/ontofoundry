"""Read-only preview of a complete, unsaved metric form."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.core import Metric, SimpleMetric, Strict
from ontofoundry_api.services.metric_preview import preview_metric

router = APIRouter(
    prefix="/api/v1/modeling/workspaces/{workspace_id}/metrics", tags=["metrics"]
)


class TimeRange(Strict):
    start: str
    end: str


class MetricPreviewRequest(Strict):
    session_id: str | None = None
    expected_session_revision: int | None = None
    expected_current_version_id: str | None = None
    metric: Metric
    components: list[SimpleMetric] | None = None
    time_range: TimeRange | None = None
    trend_grain: Literal["month"] | None = None


@router.post("/preview")
def preview(
    workspace_id: str,
    body: MetricPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    return preview_metric(db, workspace_id, user, body, request.app.state.settings)
