"""Server connection selection is unique, independent of stored aliases."""

from uuid import uuid4

import pytest

from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.domain.core import Dataset
from ontofoundry_api.services.dataset_sources import resolve_dataset
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.errors import ServiceError


def test_dataset_source_uses_dialect_and_default_schema(client):
    wid = str(DEMO_WORKSPACE_ID)
    ds = Dataset(
        id=uuid4(), name="facts", dialect="postgresql", table_name="fictional_facts"
    )
    with client.app.state.session_factory() as db:
        with pytest.raises(ServiceError, match="尚无"):
            resolve_dataset(db, wid, ds)
        db.add(
            ConnectionRecord(
                id=str(uuid4()),
                workspace_id=wid,
                name="虚构来源",
                kind="postgresql",
                config_json={"database": "fictional_db", "schema_name": "public"},
                secret_encrypted="",
            )
        )
        db.commit()
        source = resolve_dataset(db, wid, ds)
        assert source.database == "fictional_db" and source.schema == "public"
        db.add(
            ConnectionRecord(
                id=str(uuid4()),
                workspace_id=wid,
                name="另一个虚构来源",
                kind="postgresql",
                config_json={"database": "other_db"},
                secret_encrypted="",
            )
        )
        db.commit()
        with pytest.raises(ServiceError) as exc:
            resolve_dataset(db, wid, ds)
        assert exc.value.code == "SOURCE_AMBIGUOUS"
