"""Review hints are derived on read: similar definitions and physical differences (AR-01–AR-04)."""

from types import SimpleNamespace
from uuid import uuid4

from test_modeling import create_session

from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.proposal_alignment import AlignmentContext


def proposal(kind, after, operation="create"):
    return SimpleNamespace(operation=operation, target_kind=kind, target_id=str(uuid4()), after_json=after)


def test_new_definition_lists_existing_ones_by_name_and_synonym(client):
    draft = create_session(client)["draft"]
    existing = draft["object_types"][0]
    with client.app.state.session_factory() as db:
        context = AlignmentContext(db, str(DEMO_WORKSPACE_ID), draft)
        hits = context.similar_definitions(
            proposal("object_type", {"name": "fiction_new", "display_name": "虚构新实体", "synonyms": [existing["display_name"] or existing["name"]]})
        )
        assert hits and hits[0]["id"] == existing["id"] and hits[0]["kind"] == "object_type"
        assert context.similar_definitions(proposal("object_type", {"name": "zz_unrelated", "display_name": "毫不相干"})) == []
        # Updates and other kinds carry no hint.
        assert context.similar_definitions(proposal("object_type", {"name": existing["name"]}, operation="update")) == []
        assert context.similar_definitions(proposal("rule", {"name": existing["name"]})) == []


def test_required_property_mapped_to_a_nullable_column_shows_a_physical_difference(client):
    with client.app.state.session_factory() as db:
        db.add(ConnectionRecord(id="fiction-conn", workspace_id=str(DEMO_WORKSPACE_ID), name="虚构采购库", kind="postgresql", config_json={"database": "fiction"}, secret_encrypted=""))
        db.add(MetadataSnapshotRecord(connection_id="fiction-conn", schema_name="public", changes_json=[], snapshot_json={"tables": [
            {"name": "fiction_orders", "observed_at": "2026-10-21T00:00:00", "columns": [
                {"name": "supplier_id", "nullable": True}, {"name": "order_no", "nullable": False},
            ]},
        ]}))
        db.commit()
        type_id, dataset_id = str(uuid4()), str(uuid4())
        elements = {
            dataset_id: ("dataset", {"id": dataset_id, "connection_id": "fiction-conn", "schema_name": "public", "table_name": "fiction_orders"}),
            "m": ("mapping", {"id": "m", "type_id": type_id, "sources": [{"id": "main", "dataset_id": dataset_id}], "fields": {
                "supplier": {"kind": "column", "source_id": "main", "column": "supplier_id"},
                "order_no": {"kind": "column", "source_id": "main", "column": "order_no"},
            }}),
        }
        context = AlignmentContext(db, str(DEMO_WORKSPACE_ID), {})
        required = proposal("property", {"name": "supplier", "owner_type_id": type_id, "required": True})
        (difference,) = context.physical_differences(required, elements)
        assert difference["declared"] == "required" and difference["observed"] == "nullable"
        assert (difference["column"], difference["table"], difference["connection_name"]) == ("supplier_id", "fiction_orders", "虚构采购库")
        # A non-null column or an optional property shows nothing.
        assert context.physical_differences(proposal("property", {"name": "order_no", "owner_type_id": type_id, "required": True}), elements) == []
        assert context.physical_differences(proposal("property", {"name": "supplier", "owner_type_id": type_id, "required": False}), elements) == []
