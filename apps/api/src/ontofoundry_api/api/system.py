"""Deployment-level diagnostics, for platform administrators only."""

from fastapi import APIRouter, Depends, Request

from ontofoundry_api.api.auth import Principal
from ontofoundry_api.api.users import platform_admin
from ontofoundry_api.services.dataagent_health import dataagent_health

# The DataAgent check reports internal addresses and agent ids and calls
# DataAgent as the calling admin, so only platform admins may run it.
router = APIRouter(prefix="/api/v1/system", tags=["system"], dependencies=[Depends(platform_admin)])


@router.get("/dataagent-health")
async def system_dataagent_health(request: Request, user: Principal = Depends(platform_admin)) -> dict:
    return await dataagent_health(request.app.state.settings, user.username)
