from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    """Serve the compiled SPA from the same origin; unknown API routes remain JSON 404."""

    async def get_response(self, path, scope):
        if path.split("/", 1)[0] in {"api", "healthz", "docs", "openapi.json"}:
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("assets/"):
                raise
            return await super().get_response("index.html", scope)
