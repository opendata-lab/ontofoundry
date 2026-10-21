"""Bind test datasets to a registered fictional connection.

Saving or accepting a dataset now requires its connection and registered
tables (dataset sources DS-02/DS-07). Tests that only care about other
behaviour call ``bind_datasets`` so their drafts satisfy that rule.
"""

from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

KINDS = {"postgresql": "postgresql", "postgres": "postgresql", "mysql": "mysql", "doris": "mysql"}


def _connection(db, workspace_id, kind):
    identity = f"test-{kind}-{str(workspace_id)[:8]}"
    record = db.get(ConnectionRecord, identity)
    if record is None:
        record = ConnectionRecord(
            id=identity,
            workspace_id=str(workspace_id),
            name=f"虚构{kind}库",
            kind=kind,
            config_json={"host": "fiction.invalid", "database": "fiction"},
            secret_encrypted="",
        )
        db.add(record)
        db.flush()
    return record


def _register(db, connection, schema, table, columns):
    snapshot = db.get(MetadataSnapshotRecord, (connection.id, schema))
    if snapshot is None:
        snapshot = MetadataSnapshotRecord(
            connection_id=connection.id, schema_name=schema, snapshot_json={"tables": []}, changes_json=[]
        )
        db.add(snapshot)
        db.flush()
    tables = [t for t in snapshot.snapshot_json.get("tables", []) if t["name"] != table]
    tables.append(
        {
            "name": table,
            "schema": schema,
            "kind": "table",
            "columns": [
                {"name": c["name"], "type": c.get("physical_type"), "comment": c.get("comment") or ""}
                for c in columns or []
            ],
        }
    )
    # Reassign so SQLAlchemy notices the JSON change.
    snapshot.snapshot_json = {**snapshot.snapshot_json, "tables": tables}


def bind_datasets(client, draft, workspace_id=DEMO_WORKSPACE_ID):
    """Register every table dataset in ``draft`` and set its connection_id in place."""
    with client.app.state.session_factory() as db:
        for dataset in draft.get("datasets", []):
            if dataset.get("source_kind", "table") != "table" or not dataset.get("table_name"):
                continue
            bound = dataset.get("connection_id")
            if bound and not bound.startswith("test-"):
                continue  # A real or demo binding is left to the test.
            kind = KINDS.get(dataset.get("dialect") or "postgresql", "postgresql")
            connection = _connection(db, workspace_id, kind)
            dataset["connection_id"] = connection.id
            schema = dataset.get("schema_name") or ("public" if kind == "postgresql" else "fiction")
            _register(db, connection, schema, dataset["table_name"], dataset.get("columns"))
        db.commit()
    return draft
