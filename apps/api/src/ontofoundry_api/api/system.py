"""Deployment-level diagnostics, for platform administrators only."""

from fastapi import APIRouter, Depends, Request

from ontofoundry_api.api.users import platform_admin
from ontofoundry_api.services.dataagent_health import dataagent_health

# The DataAgent check reports internal addresses and agent ids and calls
# DataAgent with the deployment's access key, so only platform admins may run it.
router = APIRouter(prefix="/api/v1/system", tags=["system"], dependencies=[Depends(platform_admin)])


@router.get("/dataagent-health")
async def system_dataagent_health(request: Request) -> dict:
    return await dataagent_health(request.app.state.settings)
