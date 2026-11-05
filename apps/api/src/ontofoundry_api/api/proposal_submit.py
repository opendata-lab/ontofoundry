"""Run-scoped proposal submission from the modeling skill's merge script."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ontofoundry_api.contracts.proposal_submit import ProposalSubmitResponse
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposal_submit import submit_result
from ontofoundry_api.services.run_credentials import verify
from ontofoundry_api.services.workspaces import membership_role

router = APIRouter(
    prefix="/api/v1/ontology/workspaces/{workspace_id}/runs", tags=["proposals"]
)

MAX_RESULT_BYTES = 8 * 1024 * 1024


def _invalid():
    return ServiceError(
        "错误 [RUN_CREDENTIAL_INVALID]：需要本轮运行凭据。未提交。同参重试无效，请重新发起建模。",
        code="RUN_CREDENTIAL_INVALID",
        status_code=401,
    )


@router.post("/{run_token}/proposals", response_model=ProposalSubmitResponse)
async def submit_proposals(
    workspace_id: str,
    run_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    # Not mcp_principal: that one ends with the run, but a submitter whose
    # response was lost must still be able to fetch its receipt.
    token = request.headers.get("authorization", "").partition(" ")[2]
    grant = verify(request.app.state.settings.session_secret, token)
    if grant is None or grant.run_token != run_token or grant.workspace_id != workspace_id:
        raise _invalid()
    session = db.get(ModelingSessionRecord, grant.session_id)
    if (
        session is None
        or session.workspace_id != workspace_id
        or not membership_role(db, workspace_id, grant.user_id)
    ):
        raise _invalid()
    raw = await request.body()
    if len(raw) > MAX_RESULT_BYTES:
        raise ServiceError("建模结果超过 8 MB", code="RESULT_TOO_LARGE", status_code=413)
    return submit_result(
        db, request.app.state.settings, workspace_id, grant.session_id, run_token, raw
    )
