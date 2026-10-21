"""A small fictional core-1 demonstration, with no adapter dependency."""

from uuid import UUID, uuid5

from ontofoundry_api.domain.models import OntologyDraft

DEMO_WORKSPACE_ID = UUID("10000000-0000-4000-8000-000000000001")
# The demo dataset is bound to a registered fictional table so it is a valid source.
DEMO_CONNECTION_ID = "10000000-0000-4000-8000-0000000000c1"
DEMO_TABLE = {"name": "fictional_sales", "schema": "public", "kind": "table", "columns": [{"name": "amount", "type": "numeric", "comment": "金额"}]}


def build_demo_draft():
    def identity(name):
        return str(uuid5(DEMO_WORKSPACE_ID, name))

    return OntologyDraft.model_validate(
        {
            "schema_version": "core-1",
            "workspace_id": str(DEMO_WORKSPACE_ID),
            "object_types": [
                {
                    "id": identity("customer"),
                    "display_name": "客户",
                    "name": "customer",
                    "title_property_id": identity("customer_label"),
                },
                {"id": identity("order"), "display_name": "订单", "name": "order"},
            ],
            "link_types": [
                {
                    "id": identity("buyer"),
                    "name": "buyer",
                    "target_role_name": "购买客户",
                    "verbalizes": ["{source}由{target}购买", "{target}购买{source}"],
                    "source_type_id": identity("order"),
                    "target_type_id": identity("customer"),
                    "multiplicity": "many_to_one",
                }
            ],
            "properties": [
                {
                    "id": identity("customer_label"),
                    "owner_type_id": identity("customer"),
                    "display_name": "名称",
                    "name": "label",
                    "value_kind": "string",
                },
                {
                    "id": identity("order_label"),
                    "owner_type_id": identity("order"),
                    "display_name": "订单号",
                    "name": "order_no",
                    "value_kind": "string",
                },
            ],
            "datasets": [
                {
                    "id": identity("sales"),
                    "name": "sales",
                    "display_name": "销售",
                    "connection_id": DEMO_CONNECTION_ID,
                    "table_name": "fictional_sales",
                    "dialect": "postgresql",
                    "columns": [{"name": "amount", "physical_type": "numeric"}],
                }
            ],
            "metrics": [
                {
                    "id": identity("revenue"),
                    "kind": "simple",
                    "display_name": "销售额",
                    "name": "revenue",
                    "dataset_id": identity("sales"),
                    "aggregation": "sum",
                    "measure": {"dataset_id": identity("sales"), "column": "amount"},
                }
            ],

        }
    )


def build_demo_instance():
    return {"id": str(uuid5(DEMO_WORKSPACE_ID, "customer_fact")),
            "type_id": str(uuid5(DEMO_WORKSPACE_ID, "customer")),
            "values": {"label": "星港商店"}, "evidence": []}
