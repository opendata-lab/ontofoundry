"""E2E 所需的 fixture：真实 schema、真实执行链路、被替换掉的 cell 进程。

单独成文件再由 conftest 导入，是为了让「什么被 stub 了」集中在一处可读，而不是
散落在各个测试里。
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import dataagent_backend
from dataagent_backend.config import get_settings, update_settings
from dataagent_backend.core import pi_runtime, task_coordinator
from dataagent_backend.core.pi_runtime import PiRunOutcome
from ontofoundry_api.config import Settings
from ontofoundry_api.main import create_app

PACKAGE_ROOT = __import__("pathlib").Path(dataagent_backend.__file__).resolve().parent

POSTGRES_URL = os.environ.get("DATAAGENT_TEST_POSTGRES_URL", "")
E2E_SCHEMA = os.environ.get("DATAAGENT_TEST_E2E_SCHEMA", "dataagent_test_e2e")


@pytest.fixture
def dataagent_schema() -> Iterator[None]:
    """一次性的 DataAgent schema，迁移到 head。

    没有 DATAAGENT_TEST_POSTGRES_URL 就 skip，而不是让测试偶然通过：DataAgent 的
    store 是裸 psycopg，本机碰巧跑着一个 Postgres 时测试会"通过"，换台机器就
    炸。CI 里那 20 个因 Redis 缺失而失败的用例就是这么来的。
    """
    if not POSTGRES_URL:
        pytest.skip("需要 DATAAGENT_TEST_POSTGRES_URL 才能跑完整回合")
    if not re.fullmatch(r"dataagent_test_[a-z0-9_]+", E2E_SCHEMA):
        pytest.fail("DATAAGENT_TEST_E2E_SCHEMA 必须以 dataagent_test_ 开头")

    previous = get_settings().model_dump()
    with psycopg.connect(POSTGRES_URL, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA IF EXISTS "{E2E_SCHEMA}" CASCADE')
        connection.execute(f'CREATE SCHEMA "{E2E_SCHEMA}"')

    # skills 根必须是真实目录：自举会扫它，缺了整个 skill 索引建不起来。
    # 用仓库里那份而不是造一个空目录——E2E 要跑的就是真实配置。
    repo_skills = PACKAGE_ROOT.parents[3] / "dataagent" / ".claude" / "skills"
    update_settings(
        {
            "dataagent_database_url": POSTGRES_URL,
            "dataagent_database_schema": E2E_SCHEMA,
            "skills_root_dir": str(repo_skills),
        }
    )
    config = Config(str(PACKAGE_ROOT / "alembic.ini"))
    command.upgrade(config, "head")

    # 任务提交会校验"存在一个已启用且带已启用模型的 provider"，没有就 400。
    # 这一行不是为了调模型——cell 是替身——而是因为那道校验本身属于被测链路。
    from dataagent_backend.core.runtime_registry_store import get_runtime_registry_store

    get_runtime_registry_store().save_provider(
        {
            "provider_id": "e2e-stub",
            "provider_type": "anthropic_compatible",
            "api_format": "/v1/messages",
            "display_name": "E2E Stub",
            "provider_group": "test",
            "base_url": "https://stub.invalid",
            "auth_token": "not-used-the-cell-is-a-stub",
            "provider_enabled": True,
            "supports_partial_messages": True,
            "enabled_models": ["stub-model"],
            "models": [{"id": "stub-model"}],
            "validation_status": "verified",
        }
    )
    try:
        yield
    finally:
        update_settings(previous)
        with psycopg.connect(POSTGRES_URL, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{E2E_SCHEMA}" CASCADE')


class StubCell:
    """替身 cell：产出协议事件，不调用任何模型。

    只替换 cell 进程本身。任务状态机、事件持久化、消息收口走的都是真实代码——
    被换掉的是"模型说了什么"，不是"系统怎么处理模型说的话"。
    """

    def __init__(self) -> None:
        self._answer: str | None = None
        self._failure: str | None = None

    def will_answer(self, text: str) -> None:
        self._answer = text
        self._failure = None

    def will_fail(self, reason: str) -> None:
        self._failure = reason
        self._answer = None

    def outcome(self) -> PiRunOutcome:
        if self._failure is not None:
            return PiRunOutcome(
                terminal_status="failed",
                error_code="stub_failure",
                error_message=self._failure,
            )
        return PiRunOutcome(terminal_status="success", answer=self._answer or "")

    def events(self, ctx: Any) -> list[dict[str, Any]]:
        started = {"type": "run.started", "task_id": getattr(ctx, "task_id", "")}
        if self._failure is not None:
            return [started, {"type": "run.failed", "error": {"message": self._failure}}]
        return [
            started,
            {"type": "message.delta", "text": self._answer or ""},
            {"type": "run.completed", "content": self._answer or ""},
        ]


@pytest.fixture
def stub_cell(monkeypatch: pytest.MonkeyPatch) -> StubCell:
    cell = StubCell()

    async def fake_execute_pi_run(ctx, writer, **kwargs):
        # 返回真实的 PiRunOutcome，而不是 None：调用方读 terminal_status 决定
        # 任务收口到哪个状态。替身要守住引擎的契约，否则测的就不是真实链路。
        for event in cell.events(ctx):
            writer.ingest(event)
        return cell.outcome()

    monkeypatch.setattr(pi_runtime, "execute_pi_run", fake_execute_pi_run)
    # cell 二进制不需要真的存在：替身没有进程要拉起。
    monkeypatch.setattr(pi_runtime, "resolve_cell_command", lambda cfg=None: ["/bin/true"])
    return cell


@pytest.fixture
def client(tmp_path, dataagent_schema, monkeypatch) -> Iterator[TestClient]:
    """覆盖默认 client：E2E 需要 DataAgent 自举真的跑起来。"""
    # 默认的 /dataagent_runtime 在开发机上不可写。topic 工作区是真实创建的，
    # 所以要给它一个能写的根——这一段不 stub，工作区布局本身就是被测内容。
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    update_settings({"dataagent_host_root": str(runtime_root)})
    monkeypatch.setenv("DATAAGENT_RUNTIME_ROOT", str(runtime_root))

    # 任务协调器是进程级单例。上一个 client 关闭时把它停了，下一个 client 再
    # start() 拿到的还是那个已停实例，任务就永远停在 waiting——单独跑能过、
    # 一起跑就挂。重置成 None，让每个 client 拿到自己的协调器。
    monkeypatch.setattr(task_coordinator, "_COORDINATOR", None, raising=False)
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "files",
        auto_create_schema=True,
        seed_demo=False,
        auth_mode="dev",
        session_secret="test-session-secret-with-more-than-32-chars",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
