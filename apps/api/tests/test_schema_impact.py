"""Structure changes list the published definitions they touch (SC-01)."""

from types import SimpleNamespace

from core1_fixtures import example_draft

from ontofoundry_api.services.schema_impact import schema_impact


def bound_example():
    draft = example_draft("01-basic-sales")
    connection = SimpleNamespace(id="fiction-conn", kind="postgresql", config_json={})
    datasets = [d.model_copy(update={"connection_id": "fiction-conn"}) for d in draft.datasets]
    return draft.model_copy(update={"datasets": datasets}), connection


def test_removed_key_column_hits_its_property_and_type_by_column():
    draft, connection = bound_example()
    customers = next(d for d in draft.datasets if d.table_name == "customers")
    change = {"table": "customers", "column": "customer_id", "kind": "removed", "before": {"name": "customer_id"}, "after": None}
    (item,) = schema_impact(draft, connection, customers.schema_name, [change])
    assert item["datasets"] == [{"id": str(customers.id), "name": customers.name}]
    by_column = {(a["kind"], a["name"]) for a in item["affected"] if a["via"] == "column"}
    assert ("property", "customer_no") in by_column and ("object_type", "customer") in by_column
    # Column-level hits come first.
    assert item["affected"][0]["via"] == "column"


def test_unbound_table_and_no_changes_are_empty():
    draft, connection = bound_example()
    assert schema_impact(draft, connection, "dw", []) == []
    (item,) = schema_impact(draft, connection, "dw", [{"table": "fiction_unbound", "column": None, "kind": "added"}])
    assert item["datasets"] == [] and item["affected"] == []


def test_impact_endpoint_reads_recorded_changes(client):
    from test_modeling import ROOT

    from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
    from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

    with client.app.state.session_factory() as db:
        db.add(ConnectionRecord(id="fiction-impact", workspace_id=str(DEMO_WORKSPACE_ID), name="虚构影响库", kind="postgresql", config_json={"database": "fiction"}, secret_encrypted=""))
        db.add(MetadataSnapshotRecord(connection_id="fiction-impact", schema_name="public", snapshot_json={"tables": []}, changes_json=[
            {"table": "fiction_orders", "column": "supplier_code", "kind": "removed", "before": {"name": "supplier_code"}, "after": None},
        ]))
        db.commit()
    body = client.get(ROOT + "/connections/fiction-impact/assets/impact").json()
    assert body["schema_name"] == "public"
    (item,) = body["items"]
    assert (item["table"], item["column"], item["kind"]) == ("fiction_orders", "supplier_code", "removed")
    assert item["datasets"] == [] and item["affected"] == []
