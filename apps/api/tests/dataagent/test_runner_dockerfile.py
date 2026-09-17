from __future__ import annotations

from pathlib import Path

from conftest import PACKAGE_ROOT, REPO_ROOT, REPO_DATAAGENT_DIR  # noqa: E402


DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile"


def _stage(name: str) -> str:
    """返回某个 build target 独有的那段内容。

    backend 与 runner 现在是同一个多阶段文件的两个 target，所以按整份文件断言
    会互相串味——backend 的 alembic CMD 会让「runner 不跑迁移」这条永远失败。
    这里按 `FROM ... AS <name>` 切出各自的段落。
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    start = text.index(f"AS {name}\n")
    rest = text[start:]
    nxt = rest.find("\nFROM ")
    return rest if nxt == -1 else rest[:nxt]


def _shared_base() -> str:
    return _stage("base")
OLD_SANDBOX_ROOT_ENV = "DATAAGENT_" "SANDBOX_ROOT"
OLD_WORKSPACES_ROOT = "/" "workspaces"


def test_runner_stage_uses_runner_entrypoint():
    base = _shared_base()
    runner = _stage("runner")
    whole = DOCKERFILE.read_text(encoding="utf-8")

    # 共享基座提供运行时布局
    assert "ENV HOME=/dataagent_runtime" in base
    assert "mkdir -p /dataagent_runtime /app/.claude/skills" in base
    assert "WORKDIR /opt/ontofoundry-api" in base
    # 装的是整个发行包，而不是拷一个后端目录进去
    assert "RUN pip install --no-cache-dir /opt/ontofoundry-api" in base

    # runner 段只负责 docker CLI 与入口
    assert "dataagent_backend.sandbox_runner_main:app" in runner
    assert "EXPOSE 8910" in runner
    assert "docker:27-cli" in runner
    # 迁移是 backend 的职责，runner 段不该碰
    assert "alembic" not in runner

    assert OLD_SANDBOX_ROOT_ENV not in whole
    assert OLD_WORKSPACES_ROOT not in whole
    assert "COPY dataagent/.claude" not in whole
    assert '"main:app"' not in whole


def test_backend_stage_runs_migrations_then_the_merged_app():
    content = _shared_base() + _stage("backend")

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
