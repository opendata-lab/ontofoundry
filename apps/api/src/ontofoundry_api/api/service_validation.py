"""Render validation errors for gateway management APIs as ServiceError bodies."""

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from ontofoundry_api.services.errors import ServiceError


class ServiceValidationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise ServiceError("请求参数无效，请核对输入", code="INVALID_ARGUMENTS", status_code=422) from None

        return validated
