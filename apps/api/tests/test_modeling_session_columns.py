from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import JSON, DateTime, String, create_engine, inspect, text, update

from ontofoundry_api.api.modeling import revise, session_data
from ontofoundry_api.database import Base, build_session_factory
from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

MIGRATION = (
    Path(__file__).parents[1]
    / "src"
    / "ontofoundry_api"
    / "alembic"
    / "versions"
    / "20260921_000001_modeling_session_dataagent_columns.py"
)
ACTIVE_STATUSES = (
    "submitting",
    "queued",
    "running",
    "waiting_input",
    "waiting_permission",
)


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'model.db'}")
    Base.metadata.create_all(engine)
    yield build_session_factory(engine)
    engine.dispose()


def _new_record(*, status: str = "idle") -> ModelingSessionRecord:
    workspace_id = str(DEMO_WORKSPACE_ID)
    return ModelingSessionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by="test-user",
        title="显式字段测试",
        draft_json=OntologyDraft(workspace_id=workspace_id).model_dump(mode="json"),
        candidates_json=[],
        messages_json=[],
        material_ids=[],
        task_status=status,
        task_detail="",
    )


def _load_migration():
    spec = importlib.util.spec_from_file_location("modeling_session_columns", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_session_has_explicit_dataagent_fields_and_defaults(session_factory):
    expected = {
        "dataagent_topic_id": None,
        "dataagent_task_id": None,
        "dataagent_task_mode": "",
        "dataagent_run_token": None,
        "uploaded_material_ids": [],
        "last_result_task_id": None,
        "result_state": "",
        "result_warnings": [],
        "result_claimed_at": None,
    }

    with session_factory() as db:
        item = _new_record()
        db.add(item)
        db.commit()
        db.refresh(item)
        assert {key: getattr(item, key) for key in expected} == expected
        projected = session_data(item)
        assert {key: projected[key] for key in expected} == expected


def test_explicit_dataagent_model_columns_match_the_contract():
    expected = {
        "dataagent_topic_id": (String, 64, True, None),
        "dataagent_task_id": (String, 64, True, None),
        "dataagent_task_mode": (String, 8, False, ""),
        "dataagent_run_token": (String, 32, True, None),
        "uploaded_material_ids": (JSON, None, False, "[]"),
        "last_result_task_id": (String, 64, True, None),
        "result_state": (String, 20, False, ""),
        "result_warnings": (JSON, None, False, "[]"),
        "result_claimed_at": (DateTime, None, True, None),
    }

    for name, (type_class, length, nullable, server_default) in expected.items():
        column = ModelingSessionRecord.__table__.c[name]
        assert isinstance(column.type, type_class)
        assert getattr(column.type, "length", None) == length
        assert column.nullable is nullable
        actual_default = (
            str(column.server_default.arg) if column.server_default is not None else None
        )
        assert actual_default == server_default

    assert ModelingSessionRecord.__table__.c.result_claimed_at.type.timezone is True


@pytest.mark.parametrize("status", ACTIVE_STATUSES)
def test_revise_rejects_every_active_status(session_factory, status):
    with session_factory() as db:
        item = _new_record(status=status)
        db.add(item)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            revise(db, item, item.revision, draft_json=item.draft_json)

    assert exc_info.value.status_code == 409


def test_revise_cas_rejects_status_changed_by_another_transaction(session_factory):
    with session_factory() as setup_db:
        item = _new_record()
        setup_db.add(item)
        setup_db.commit()
        item_id = item.id

    with session_factory() as stale_db:
        stale_item = stale_db.get(ModelingSessionRecord, item_id)
        assert stale_item is not None
        assert stale_item.task_status == "idle"

        with session_factory() as concurrent_db:
            concurrent_db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == item_id)
                .values(task_status="waiting_permission")
            )
            concurrent_db.commit()

        with pytest.raises(HTTPException) as exc_info:
            revise(
                stale_db,
                stale_item,
                stale_item.revision,
                draft_json=stale_item.draft_json,
            )

    assert exc_info.value.status_code == 409


def test_migration_backfills_existing_rows_and_can_downgrade(tmp_path):
    migration = _load_migration()
    assert migration.revision == "20260921_000001"
    assert migration.down_revision == "20260916_000001"

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE modeling_sessions (id VARCHAR(36) PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO modeling_sessions (id) VALUES (:id)"),
            {"id": "existing-session"},
        )

        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()

        row = connection.execute(
            text(
                """
                SELECT dataagent_topic_id, dataagent_task_id, dataagent_task_mode,
                       dataagent_run_token, uploaded_material_ids,
                       last_result_task_id, result_state, result_warnings,
                       result_claimed_at
                FROM modeling_sessions
                WHERE id = :id
                """
            ),
            {"id": "existing-session"},
        ).mappings().one()
        assert row["dataagent_topic_id"] is None
        assert row["dataagent_task_id"] is None
        assert row["dataagent_task_mode"] == ""
        assert row["dataagent_run_token"] is None
        assert json.loads(row["uploaded_material_ids"]) == []
        assert row["last_result_task_id"] is None
        assert row["result_state"] == ""
        assert json.loads(row["result_warnings"]) == []
        assert row["result_claimed_at"] is None
        assert all(
            row[name] is not None
            for name in (
                "dataagent_task_mode",
                "uploaded_material_ids",
                "result_state",
                "result_warnings",
            )
        )

        columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("modeling_sessions")
        }
        assert columns["dataagent_topic_id"]["type"].length == 64
        assert columns["dataagent_task_id"]["type"].length == 64
        assert columns["dataagent_task_mode"]["type"].length == 8
        assert columns["dataagent_run_token"]["type"].length == 32
        assert isinstance(columns["uploaded_material_ids"]["type"], JSON)
        assert columns["last_result_task_id"]["type"].length == 64
        assert columns["result_state"]["type"].length == 20
        assert isinstance(columns["result_warnings"]["type"], JSON)
        assert isinstance(columns["result_claimed_at"]["type"], DateTime)
        assert {
            name: columns[name]["nullable"]
            for name in columns
            if name != "id"
        } == {
            "dataagent_topic_id": True,
            "dataagent_task_id": True,
            "dataagent_task_mode": False,
            "dataagent_run_token": True,
            "uploaded_material_ids": False,
            "last_result_task_id": True,
            "result_state": False,
            "result_warnings": False,
            "result_claimed_at": True,
        }

        migration.downgrade()
        assert {column["name"] for column in inspect(connection).get_columns("modeling_sessions")} == {
            "id"
        }
