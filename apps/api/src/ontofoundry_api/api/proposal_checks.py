"""Run-scoped, read-only proposal validation."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, mcp_principal
from ontofoundry_api.contracts.proposal_checks import ProposalCheckResponse
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposal_checks import check_result
from ontofoundry_api.services.run_credentials import verify

router = APIRouter(
    prefix="/api/v1/ontology/workspaces/{workspace_id}/runs", tags=["proposals"]
)


@router.post("/{run_token}/proposal-check", response_model=ProposalCheckResponse)
async def proposal_check(
    workspace_id: str,
    run_token: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(mcp_principal),
):
    token = request.headers.get("authorization", "").partition(" ")[2]
    grant = verify(request.app.state.settings.session_secret, token)
    if (
        grant is None
        or grant.run_token != run_token
        or principal.service_token_id != f"run:{run_token}"
    ):
        raise ServiceError(
            "错误 [RUN_CREDENTIAL_INVALID]：需要本轮运行凭据。未执行检查。同参重试无效，请重新发起建模。",
            code="RUN_CREDENTIAL_INVALID",
            status_code=401,
        )
    session = db.get(ModelingSessionRecord, grant.session_id)
    return check_result(
        db,
        request.app.state.settings,
        session.run_manifest_json or {},
        await request.body(),
    )
