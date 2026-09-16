from __future__ import annotations

from pathlib import Path

from conftest import PACKAGE_ROOT, REPO_ROOT, REPO_DATAAGENT_DIR  # noqa: E402


BACKEND_DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile"
RUNNER_DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile.runner"
OLD_SANDBOX_ROOT_ENV = "DATAAGENT_" "SANDBOX_ROOT"
OLD_WORKSPACES_ROOT = "/" "workspaces"


def test_runner_dockerfile_uses_runner_entrypoint():
    content = RUNNER_DOCKERFILE.read_text(encoding="utf-8")

    assert "ENV HOME=/dataagent_runtime" in content
    assert OLD_SANDBOX_ROOT_ENV not in content
    assert "mkdir -p /dataagent_runtime /app/.claude/skills" in content
    assert OLD_WORKSPACES_ROOT not in content
    assert "WORKDIR /opt/ontofoundry-api" in content
    # 合并后镜像装的是整个发行包，而不是拷一个后端目录进去
    assert "RUN pip install --no-cache-dir /opt/ontofoundry-api" in content
    assert "COPY dataagent/.claude" not in content
    assert "dataagent_backend.sandbox_runner_main:app" in content
    assert 'EXPOSE 8910' in content
    # runner 不跑迁移，那是 backend 镜像的职责
    assert "alembic" not in content
    assert '"main:app"' not in content


def test_backend_dockerfile_uses_opt_backend_and_no_bundled_skills():
    content = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "ENV HOME=/dataagent_runtime" in content
    assert "ENV DATAAGENT_RUNTIME_ROOT=/dataagent_runtime" in content
    assert OLD_SANDBOX_ROOT_ENV not in content
    assert "mkdir -p /dataagent_runtime /app/.claude/skills" in content
    assert OLD_WORKSPACES_ROOT not in content
    assert "WORKDIR /opt/ontofoundry-api" in content
    # 合并后镜像装的是整个发行包，而不是拷一个后端目录进去
    assert "RUN pip install --no-cache-dir /opt/ontofoundry-api" in content
    assert "COPY dataagent/.claude" not in content
    # 包安装之后 alembic.ini 不在 cwd 里，必须显式指路；仍要在起服务前跑迁移
    assert "alembic -c /opt/ontofoundry-api/src/dataagent_backend/alembic.ini upgrade head" in content
    assert "uvicorn ontofoundry_api.main:app" in content
    assert 'EXPOSE 8900' in content
