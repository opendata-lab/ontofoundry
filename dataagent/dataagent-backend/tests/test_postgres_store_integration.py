"""Opt-in unified persistence check against a disposable PostgreSQL schema.

Set DATAAGENT_TEST_POSTGRES_URL to a throwaway database. The test only drops a
schema whose name starts with dataagent_test_; it never controls containers.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from config import get_settings, update_settings
from core.runtime_registry_store import RuntimeRegistryStore
from core.topic_task_store import TopicTaskStore

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
