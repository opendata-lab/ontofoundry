"""DataAgent 在宿主 FastAPI 应用里的装配点。

这里只做两件事：把路由挂上去，以及把启动/停机步骤暴露成宿主生命周期可以 await
的一对函数。DataAgent 不再自己建 FastAPI 实例，也不再自己配 CORS 或中间件——
那些归宿主应用统一负责，否则同一个进程里会出现两套互相覆盖的策略。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from dataagent_backend.api.admin_routes import router as admin_router
from dataagent_backend.api.auth_routes import oauth_callback_router
from dataagent_backend.api.auth_routes import router as auth_router
from dataagent_backend.api.routes import router as agent_router
from dataagent_backend.config import get_settings
from dataagent_backend.core.auth import init_auth
from dataagent_backend.core.runtime_registry_store import get_runtime_registry_store
from dataagent_backend.core.skill_admin_service import reindex_documents_from_disk
from dataagent_backend.core.skill_discovery import (
    resolve_agent_project_cwd,
    resolve_skills_root_dir,
)
from dataagent_backend.core.skill_admin_store import get_skill_admin_store
from dataagent_backend.core.task_coordinator import get_task_coordinator
from dataagent_backend.core.topic_task_store import get_topic_task_store

logger = logging.getLogger(__name__)


def include_dataagent_routes(app: FastAPI) -> None:
    """挂载 DataAgent 路由。

    前缀（/api/v1/agent、/api/v1/agent/auth、/api/v1/agent-admin、
    /api/v1/dataagent）与 OntoFoundry 的（/api/v1/auth、/api/v1/workspaces、
    /api/v1/ontology）互不相交，所以前端和 TS 运行时的地址都不用动。
    """
    app.include_router(auth_router)
    app.include_router(oauth_callback_router)
    app.include_router(agent_router)
    app.include_router(admin_router)


async def start_dataagent() -> None:
    """启动期自举：认证配置、schema、skill 索引、任务协调器。

    认证是 fail-closed 的：env 已设置但配置非法时 init_auth() 抛错，整个进程起不
    来。合并之后这一点比以前更要紧——它现在会连带拦住 OntoFoundry，而这正是期望
    行为，一个认证配置错误的进程不该对外提供任何服务。

    其余几步各自 try/except：它们是自举而非契约，失败只影响 DataAgent 自己的功
    能，不该让本体建模一起下线。
    """
    auth_settings = init_auth()
    logger.info(
        "DataAgent auth ready enabled=%s mode=%s",
        auth_settings.enabled,
        getattr(auth_settings, "mode", ""),
    )

    try:
        get_skill_admin_store().init_schema()
        get_runtime_registry_store().init_schema()
        logger.info("DataAgent admin settings initialized")
    except Exception as exc:
        logger.exception("DataAgent admin settings bootstrap failed: %s", exc)

    try:
        skills_root = resolve_skills_root_dir()
        agent_cwd = resolve_agent_project_cwd()
        logger.info("DataAgent skills discovery ready root=%s agent_cwd=%s", skills_root, agent_cwd)
        changed = reindex_documents_from_disk()
        logger.info("DataAgent skill documents indexed changed=%s", len(changed))
    except Exception as exc:
        logger.exception("DataAgent skills bootstrap failed: %s", exc)

    cfg = get_settings()
    try:
        get_topic_task_store().init_schema()
        logger.info("DataAgent topic/task store ready schema=%s", cfg.dataagent_database_schema)
    except Exception as exc:
        logger.exception("DataAgent topic/task store bootstrap failed: %s", exc)
        raise

    await get_task_coordinator().start()
    logger.info(
        "DataAgent task coordinator ready redis=%s:%s",
        cfg.redis_host,
        cfg.redis_port,
    )


async def stop_dataagent() -> None:
    try:
        await get_task_coordinator().stop()
    except Exception as exc:
        logger.exception("DataAgent task coordinator shutdown failed: %s", exc)
