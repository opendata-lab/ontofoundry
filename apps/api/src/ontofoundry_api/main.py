from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from ontofoundry_api.api import (
    agent,
    auth,
    connections,
    instances,
    materials,
    mcp,
    modeling,
    ontology,
    workspaces,
)
from ontofoundry_api.api import settings as settings_api
from ontofoundry_api.config import Settings, get_settings
from ontofoundry_api.database import Base, build_engine, build_session_factory
from ontofoundry_api.db_models import WorkspaceRecord
from ontofoundry_api.domain.models import WorkspaceCreate
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID, build_demo_draft
from ontofoundry_api.services.errors import PublishValidationError, ServiceError
from ontofoundry_api.services.workspaces import (
    DEV_USER_ID,
    create_workspace,
    ensure_dev_user,
    publish_draft,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = build_engine(app_settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if app_settings.auto_create_schema:
            Base.metadata.create_all(engine)
        from sqlalchemy import update

        from ontofoundry_api.db_models import ModelingSessionRecord

        with session_factory() as session:
            session.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.task_status.in_(["queued", "running"]))
                .values(
                    task_status="failed",
                    task_detail="服务已重启，请手动重试。此前生成的候选仍然保留。",
                )
            )
            session.commit()
        app_settings.data_dir.mkdir(parents=True, exist_ok=True)
        if app_settings.auth_mode == "dev" or app_settings.seed_demo:
            with session_factory() as session:
                ensure_dev_user(session)
                if app_settings.seed_demo:
                    workspace = session.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID))
                    if workspace is None:
                        workspace = create_workspace(
                            session,
                            payload=WorkspaceCreate(
                                name="制造供应链",
                                slug="manufacturing-supply-chain",
                                description="采购、物料、生产与设备的发布本体样例。",
                            ),
                            user_id=DEV_USER_ID,
                            workspace_id=DEMO_WORKSPACE_ID,
                        )
                    if workspace.current_version_id is None:
                        publish_draft(
                            session,
                            workspace_id=workspace.id,
                            draft=build_demo_draft(),
                            user_id=DEV_USER_ID,
                            message="初始化可查询的发布基线",
                        )
        yield
        engine.dispose()

    app = FastAPI(
        title="OntoFoundry API",
        version="0.1.0",
        description="企业本体建模、发布与只读查询服务。",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.agent_slots = asyncio.Semaphore(10)

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = app_settings.cors_origin_list + [str(request.base_url).rstrip("/")]
        if (
            origin
            and origin not in allowed
            and (
                request.method not in ("GET", "HEAD", "OPTIONS")
                or request.url.path.endswith("/mcp")
            )
        ):
            return JSONResponse({"detail": "请求来源不被允许"}, status_code=403)
        return await call_next(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=app_settings.session_secret,
        session_cookie=app_settings.session_cookie_name,
        https_only=app_settings.cookie_secure,
        same_site="lax",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "MCP-Protocol-Version",
            "Mcp-Method",
            "Mcp-Name",
        ],
    )

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        body = {"error": {"code": exc.code, "message": exc.message}}
        if isinstance(exc, PublishValidationError):
            body["error"]["validation"] = exc.report
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.get("/healthz", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "service": "ontofoundry-api"}

    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(ontology.router)
    app.include_router(modeling.router)
    app.include_router(materials.router)
    app.include_router(agent.router)
    app.include_router(connections.router)
    app.include_router(instances.router)
    app.include_router(settings_api.router)
    app.include_router(mcp.router)
    if app_settings.web_dist:
        from ontofoundry_api.web import FrontendFiles

        app.mount(
            "/", FrontendFiles(directory=app_settings.web_dist, html=True), name="frontend"
        )
    return app


app = create_app()
