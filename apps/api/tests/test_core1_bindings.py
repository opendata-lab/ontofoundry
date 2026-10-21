"""Datasets resolve only through their own explicit, same-workspace connection (DS-16)."""

from uuid import uuid4

import pytest

from ontofoundry_api.db_models import ConnectionRecord, WorkspaceRecord
from ontofoundry_api.domain.core import Dataset
from ontofoundry_api.services.dataset_sources import resolve_dataset
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.workspaces import DEV_USER_ID


def connection(db, workspace_id, **config):
    record = ConnectionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        name="虚构来源" + uuid4().hex[:4],
        kind="postgresql",
        config_json={"database": "fictional_db", **config},
        secret_encrypted="",
    )
    db.add(record)
    db.commit()
    return record.id


def facts(connection_id=None, **extra):
    return Dataset(
        id=uuid4(),
        name="facts",
        dialect="postgresql",
        table_name="fictional_facts",
        connection_id=connection_id,
        **extra,
    )


def test_dataset_resolves_through_its_bound_connection_and_default_schema(client):
    wid = str(DEMO_WORKSPACE_ID)
    with client.app.state.session_factory() as db:
        with pytest.raises(ServiceError) as exc:
            resolve_dataset(db, wid, facts(), registered=False)
        assert exc.value.code == "CONNECTION_UNBOUND"
        bound = connection(db, wid, schema_name="public")
        # A second connection in the same workspace no longer makes the choice ambiguous.
        connection(db, wid)
        source = resolve_dataset(db, wid, facts(bound), registered=False)
        assert source.connection.id == bound
        assert source.database == "fictional_db" and source.schema == "public"
        explicit = resolve_dataset(db, wid, facts(bound, schema_name="dw"), registered=False)
        assert explicit.schema == "dw"


def test_connection_of_another_workspace_or_engine_is_rejected(client):
    wid = str(DEMO_WORKSPACE_ID)
    with client.app.state.session_factory() as db:
        other = WorkspaceRecord(
            id=str(uuid4()), name="另一空间", slug="other-" + uuid4().hex[:6], created_by=DEV_USER_ID
        )
        db.add(other)
        db.commit()
        foreign = connection(db, other.id)
        with pytest.raises(ServiceError) as exc:
            resolve_dataset(db, wid, facts(foreign), registered=False)
        assert exc.value.code == "CONNECTION_UNBOUND"
        local = connection(db, wid)
        mismatched = facts(local).model_copy(update={"dialect": "mysql"})
        with pytest.raises(ServiceError) as exc:
            resolve_dataset(db, wid, mismatched, registered=False)
        assert exc.value.code == "DIALECT_MISMATCH"


def test_unregistered_table_is_reported_with_its_location(client):
    wid = str(DEMO_WORKSPACE_ID)
    with client.app.state.session_factory() as db:
        bound = connection(db, wid, schema_name="public")
        with pytest.raises(ServiceError) as exc:
            resolve_dataset(db, wid, facts(bound))
        assert exc.value.code == "SOURCE_NOT_REGISTERED"
        assert exc.value.details["table_name"] == "fictional_facts"
