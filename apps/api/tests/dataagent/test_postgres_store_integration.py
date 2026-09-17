"""Opt-in unified persistence check against a disposable PostgreSQL schema.

Set DATAAGENT_TEST_POSTGRES_URL to a throwaway database. The test only drops a
schema whose name starts with dataagent_test_; it never controls containers.

    podman run -d --name pgtest -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test \
        -e POSTGRES_DB=dataagent_itest -p 55433:5432 postgres:16-alpine
    DATAAGENT_TEST_POSTGRES_URL=postgresql://test:test@127.0.0.1:55433/dataagent_itest \
        pytest tests/test_postgres_store_integration.py

Without the variable every test here skips, which reads like the file is broken
rather than opt-in — so the command is written down.

These stores are the only place the real SQL dialect, transaction boundaries and
search_path are exercised. Everywhere else they are replaced by in-memory
doubles, and a double cannot fail when the connection layer changes.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


import psycopg
import pytest
from alembic import command
from alembic.config import Config
from dataagent_backend.config import get_settings, update_settings
from dataagent_backend.core.runtime_registry_store import RuntimeRegistryStore
from dataagent_backend.core.topic_task_store import TopicTaskStore

import dataagent_backend

# 包安装后的真实位置，不再依赖测试文件与源码的相对层级
BACKEND_ROOT = Path(dataagent_backend.__file__).resolve().parent


POSTGRES_URL = os.environ.get("DATAAGENT_TEST_POSTGRES_URL", "")
TEST_SCHEMA = os.environ.get("DATAAGENT_TEST_POSTGRES_SCHEMA", "dataagent_test_store")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Disposable PostgreSQL URL not supplied",
)


@pytest.fixture
def migrated_postgres():
    if not re.fullmatch(r"dataagent_test_[a-z0-9_]+", TEST_SCHEMA):
        pytest.fail("DATAAGENT_TEST_POSTGRES_SCHEMA must start with dataagent_test_")

    previous = get_settings().model_dump()
    with psycopg.connect(POSTGRES_URL, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE')
        connection.execute(f'CREATE SCHEMA "{TEST_SCHEMA}"')

    update_settings(
        {
            "dataagent_database_url": POSTGRES_URL,
            "dataagent_database_schema": TEST_SCHEMA,
        }
    )
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(alembic_config, "head")

    try:
        yield
    finally:
        update_settings(previous)
        with psycopg.connect(POSTGRES_URL, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE')


def test_postgres_baseline_and_store_round_trip(migrated_postgres):
    registry = RuntimeRegistryStore()
    provider = registry.save_provider(
        {
            "provider_id": "integration",
            "provider_type": "anthropic_compatible",
            "display_name": "Integration Provider",
            "provider_group": "test",
            "base_url": "https://example.invalid",
            "auth_token": "secret",
            "provider_enabled": True,
            "supports_partial_messages": False,
            "enabled_models": ["integration-model"],
            "models": [{"id": "integration-model"}],
            "validation_status": "verified",
        }
    )
    assert provider["provider_id"] == "integration"
    assert provider["enabled_models"] == ["integration-model"]

    store = TopicTaskStore()
    topic = store.create_topic(title="PostgreSQL integration")
    task = store.create_task(
        topic_id=topic["topic_id"],
        prompt="hello",
        provider_id="integration",
        model="integration-model",
        database_hint=None,
        debug=False,
        timeout_seconds=30,
        sql_read_timeout_seconds=30,
        sql_write_timeout_seconds=30,
    )
    store.append_user_message(
        topic_id=topic["topic_id"],
        task_id=task["task_id"],
        content="hello",
    )
    assistant = store.ensure_assistant_message(
        topic_id=topic["topic_id"],
        task_id=task["task_id"],
        status="streaming",
    )
    updated_assistant = store.ensure_assistant_message(
        topic_id=topic["topic_id"],
        task_id=task["task_id"],
        status="running",
    )
    assert updated_assistant["message_id"] == assistant["message_id"]
    assert updated_assistant["status"] == "running"
    assert store.mark_task_running(task["task_id"])["task_status"] == "running"

    for sequence, event_type in enumerate(
        ("run.started", "turn.started", "run.completed"), start=1
    ):
        store.append_agent_record(
            task_id=task["task_id"],
            topic_id=topic["topic_id"],
            turn_index=1,
            record_type="agent_event",
            event_type=event_type,
            data={"sequence": sequence},
            envelope={
                "contract_version": 1,
                "engine_kind": "pi_agent_core",
                "event_id": f"event-{sequence}",
                "engine_sequence": sequence,
            },
        )

    finished = store.finish_task(task_id=task["task_id"], task_status="finished")
    records = store.list_agent_records(task_id=task["task_id"])

    assert finished["task_status"] == "finished"
    assert [record["record_type"] for record in records] == ["agent_event"] * 3
    assert [record["event_type"] for record in records] == [
        "run.started",
        "turn.started",
        "run.completed",
    ]
    assert store.get_topic(topic["topic_id"])["current_task_status"] == "finished"

    with psycopg.connect(POSTGRES_URL) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = %s",
                (TEST_SCHEMA,),
            )
        }
        persisted = connection.execute(
            f'SELECT task_status FROM "{TEST_SCHEMA}".da_agent_task WHERE task_id = %s',
            (task["task_id"],),
        ).fetchone()

    platform_tables = {
        "users",
        "workspaces",
        "workspace_members",
        "ontology_versions",
        "modeling_sessions",
        "materials",
        "material_chunks",
        "data_connections",
        "service_tokens",
        "service_token_scopes",
        "metadata_snapshots",
    }
    dataagent_tables = {
        "da_agent_settings",
        "da_skill_document",
        "da_skill_document_version",
        "da_agent_profile",
        "da_agent_topic",
        "da_agent_task",
        "da_agent_message",
        "da_agent_chunk",
        "da_agent_event_record",
        "da_agent_message_queue",
        "da_agent_message_schedule",
        "da_agent_message_schedule_log",
        "da_agent_widget_event",
        "da_model_provider",
        "da_mcp_server",
    }
    assert tables == platform_tables | dataagent_tables | {"alembic_version"}
    assert not {name for name in tables if name.startswith("eval_")}
    assert (
        not {
            "agent_runs",
            "run_events",
            "run_calls",
            "run_results",
            "runtime_workers",
            "runtime_claims",
        }
        & tables
    )
    assert persisted == ("finished",)


def test_skill_admin_store_round_trip(migrated_postgres):
    """SkillAdminStore 对真实 PostgreSQL 的往返。

    单元测试用的是 FakeSkillStore 这类内存替身，它们不碰数据库，所以连接层一旦
    出问题——方言差异、事务边界、search_path——替身一个都不会失败。这里走真库。
    """
    from dataagent_backend.core.skill_admin_store import SkillAdminStore

    store = SkillAdminStore()
    store.init_schema()

    store.save_settings_record(
        {
            "provider_id": "integration",
            "model": "integration-model",
            "anthropic_auth_token": "secret",
            "anthropic_base_url": "https://example.invalid",
            "skills_output_dir": "../.claude/skills/md2ossie",
            "skill_runtime": {"md2ossie": {"enabled": True}},
        }
    )
    reloaded = store.load_settings_record()
    assert reloaded is not None
    assert reloaded["provider_id"] == "integration"
    assert reloaded["model"] == "integration-model"
    # skill_runtime 不是列，只存在于序列化后的 raw_json 里；往返必须保住它
    assert (reloaded.get("skill_runtime") or {}).get("md2ossie", {}).get("enabled") is True

    document = store.save_document(
        relative_path="md2ossie/SKILL.md",
        content="---\nname: md2ossie\ndescription: 本体建模\n---\n初版\n",
        change_source="import",
        change_summary="发现磁盘文件",
        actor="system",
    )
    assert document["id"] > 0
    assert store.get_document_by_path("md2ossie/SKILL.md")["id"] == document["id"]

    # 二次保存必须产生新版本，而不是覆盖历史
    store.save_document(
        relative_path="md2ossie/SKILL.md",
        content="---\nname: md2ossie\ndescription: 本体建模\n---\n改过\n",
        change_source="edit",
        change_summary="手工编辑",
        actor="tester",
    )
    versions = store.list_versions(document["id"])
    assert len(versions) >= 2, "同一路径的第二次保存应当留下历史版本"

    listed = store.list_documents()
    assert [item["relative_path"] for item in listed] == ["md2ossie/SKILL.md"]

    store.rename_document_path("md2ossie/SKILL.md", "renamed/SKILL.md")
    assert store.get_document_by_path("md2ossie/SKILL.md") is None
    assert store.get_document_by_path("renamed/SKILL.md") is not None

    store.delete_document_by_path("renamed/SKILL.md")
    assert store.list_documents() == []


def test_agent_profile_store_round_trip(migrated_postgres):
    """AgentProfileStore 对真实 PostgreSQL 的往返，含全表 backfill。

    backfill_default_bindings() 对 da_agent_topic 与 da_agent_task 各执行一条全表
    UPDATE。这类语句最容易在换连接层时因为事务或自动提交行为变化而静默失效，
    内存替身完全测不到。
    """
    from dataagent_backend.core.agent_profile_service import AgentProfileStore, default_agent_payload

    store = AgentProfileStore()
    store.init_schema()

    # 内置 agent 受删除保护（save_profile 之后 delete 会抛 ValueError），
    # 所以往返用一个自定义 profile，内置的那条单独断言它删不掉。
    builtin = store.save_profile(default_agent_payload())
    payload = {
        **default_agent_payload(),
        "agent_id": "agent_integration",
        "name": "Integration",
        "is_builtin": False,
    }
    saved = store.save_profile(payload)
    agent_id = saved["agent_id"]
    assert agent_id

    assert store.get_profile(agent_id)["agent_id"] == agent_id
    listed = {item["agent_id"] for item in store.list_profiles()}
    assert listed == {builtin["agent_id"], agent_id}

    # 没有任何 topic 引用它
    assert store.count_topic_references(agent_id) == 0

    # 全表 backfill 在空表上也必须正常收口，不抛异常、不留开着的事务
    store.backfill_default_bindings(saved)
    assert store.get_profile(agent_id) is not None

    assert store.delete_profile(agent_id) is True
    assert store.get_profile(agent_id) is None
    assert store.delete_profile(agent_id) is False, "重复删除应返回 False 而不是报错"

    # 内置 agent 不可删，这条保护必须在真库上也成立
    with pytest.raises(ValueError, match="built-in agent"):
        store.delete_profile(builtin["agent_id"])
