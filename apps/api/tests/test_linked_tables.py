"""Sessions link registered tables; the agent sees a catalog and reads columns on demand."""

import json
from uuid import uuid4

from dataset_binding import bind_datasets
from test_modeling import ROOT, create_session

from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.services.dataset_sources import linked_table_details
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.modeling_input import linked_tables_payload


def register(client, tables, *, workspace_id=DEMO_WORKSPACE_ID, missing=()):
    connection_id = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(
            ConnectionRecord(
                id=connection_id,
                workspace_id=str(workspace_id),
                name="虚构零售库" + connection_id[:4],
                kind="mysql",
                config_json={"database": "retail"},
                secret_encrypted="",
            )
        )
        db.flush()
        db.add(
            MetadataSnapshotRecord(
                connection_id=connection_id,
                schema_name="retail",
                snapshot_json={
                    "tables": [
                        {
                            "name": name,
                            "kind": "table",
                            "comment": "虚构" + name,
                            "primary_key": ["id"],
                            "foreign_keys": [],
                            "missing": name in missing,
                            "columns": [
                                {"name": "id", "type": "VARCHAR(16)", "nullable": False, "comment": "编号"},
                                {"name": "amount", "type": "DECIMAL(12,2)", "nullable": True, "comment": "金额"},
                            ],
                        }
                        for name in tables
                    ]
                },
                changes_json=[],
            )
        )
        db.commit()
    return connection_id


def link(connection_id, table):
    return {"connection_id": connection_id, "schema_name": "retail", "table_name": table}


def save_links(client, session, tables):
    return client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": session["draft"], "linked_tables": tables},
    )


def test_registered_tables_list_only_present_tables_with_dataset_usage(client):
    connection_id = register(client, ["orders", "stores", "gone"], missing={"gone"})
    session = create_session(client)
    draft = session["draft"]
    draft["datasets"].append(
        {"id": str(uuid4()), "name": "orders", "display_name": "订单", "connection_id": connection_id,
         "schema_name": "retail", "table_name": "orders", "columns": None}
    )
    bind_datasets(client, draft)
    saved = client.put(ROOT + f"/sessions/{session['id']}", json={"revision": session["revision"], "draft": draft})
    assert saved.status_code == 200, saved.text
    response = client.get(ROOT + f"/registered-tables?session_id={session['id']}")
    assert response.status_code == 200, response.text
    items = {i["table_name"]: i for i in response.json()["items"] if i["connection_id"] == connection_id}
    assert set(items) == {"orders", "stores"}
    assert items["orders"]["datasets"][0]["display_name"] == "订单"
    assert items["stores"]["datasets"] == [] and items["stores"]["column_count"] == 2


def test_session_links_registered_tables_and_rejects_unsynced_or_foreign_ones(client):
    connection_id = register(client, ["orders", "refunds"], missing={"refunds"})
    session = create_session(client)
    saved = save_links(client, session, [link(connection_id, "orders")])
    assert saved.status_code == 200, saved.text
    session = saved.json()
    assert session["linked_tables"] == [link(connection_id, "orders")]
    unsynced = save_links(client, session, [link(connection_id, "refunds")])
    assert unsynced.status_code == 422 and unsynced.json()["error"]["code"] == "SOURCE_NOT_REGISTERED"
    never = save_links(client, session, [link(connection_id, "payments")])
    assert never.status_code == 422 and never.json()["error"]["code"] == "SOURCE_NOT_REGISTERED"
    foreign = save_links(client, session, [link(str(uuid4()), "orders")])
    assert foreign.status_code == 422 and foreign.json()["error"]["code"] == "CONNECTION_UNBOUND"


def test_work_pack_catalog_is_compact_and_full_columns_go_to_the_tables_file(client):
    connection_id = register(client, ["orders", "stores"])
    with client.app.state.session_factory() as db:
        details = linked_table_details(
            db,
            str(DEMO_WORKSPACE_ID),
            [link(connection_id, "stores"), link(connection_id, "orders"), link(connection_id, "orders")],
        )
    catalog, body = linked_tables_payload(details)
    # Stable table order makes the same selection produce the same receipt.
    assert [(c["key"], c["table"]) for c in catalog] == [("t1", "retail.orders"), ("t2", "retail.stores")]
    assert all("columns" not in c and c["column_count"] == 2 for c in catalog)
    full = json.loads(body)["tables"]
    assert full[1]["connection_id"] == connection_id and full[1]["dialect"] == "mysql"
    assert full[1]["primary_key"] == ["id"]
    assert full[1]["columns"][1] == {"name": "amount", "type": "DECIMAL(12,2)", "nullable": True, "comment": "金额"}


def test_publish_rechecks_datasets_saved_directly_into_the_session(client):
    connection_id = register(client, ["orders"])
    session = create_session(client)
    draft = session["draft"]
    draft["datasets"].append(
        {
            "id": str(uuid4()),
            "name": "sneaky",
            "display_name": "未登记来源",
            "source_kind": "query",
            "connection_id": connection_id,
            "query_sql": "SELECT id FROM retail.payments",
        }
    )
    saved = client.put(ROOT + f"/sessions/{session['id']}", json={"revision": session["revision"], "draft": draft})
    assert saved.status_code == 200, saved.text
    session = saved.json()
    preview = client.post(ROOT + f"/sessions/{session['id']}/preview", json={"expected_session_revision": session["revision"]})
    assert preview.status_code == 200, preview.text
    checks = preview.json()["dataset_checks"]
    assert [c["valid"] for c in checks] == [False]
    assert checks[0]["diagnostics"][0]["code"] == "SOURCE_NOT_REGISTERED"
    published = client.post(
        ROOT + f"/sessions/{session['id']}/publish",
        json={
            "expected_session_revision": session["revision"],
            "expected_current_version_id": preview.json()["current_version_id"],
            "expected_merged_snapshot_sha256": preview.json()["merged_snapshot_sha256"],
        },
    )
    assert published.status_code == 422, published.text
    assert published.json()["error"]["code"] == "DATASET_SOURCE_INVALID"


def test_a_large_linked_table_catalog_is_paged_not_rejected():
    from ontofoundry_api.services.modeling_input import (
        PACK_LIMIT,
        build_work_pack,
        encode,
        execution_input,
    )

    context = {
        "run": {"run_token": "fiction", "workspace_id": str(uuid4())},
        "execution": execution_input("fiction"),
        "draft": {"object_types": []},
    }
    tables = [
        {"table": f"retail.table_{i:03d}", "connection": "虚构零售库", "kind": "table", "comment": "虚构说明" * 20, "column_count": 5}
        for i in range(200)
    ]
    pack, pages = build_work_pack(context, [], context_file="c.json", schema_file="s.json", tables=tables, tables_file="t.json")
    assert len(encode(pack)) <= PACK_LIMIT
    assert pack["tables_file"] == "t.json" and "tables" not in pack
    paged = [row["table"]["table"] for page in pages for row in json.loads(page) if "table" in row]
    assert paged == [t["table"] for t in tables]
