"""Unchanged real bottom-up proposals, owner-oriented joins and pre-write checks."""

import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select, text
from test_instance_queries import mapped_session as sql_session
from test_m8_binary_facts_replay import FIXTURES, USER, mcp, seed_evidence
from test_p3_semantic_integration import persistent_client as storage_client
from test_p3_semantic_integration import publish, source
from test_t4_proposal_decisions import decide, seed_batch, update

from ontofoundry_api.contracts.proposals import RunContext, parse_result
from ontofoundry_api.db_models import (
    ConnectionRecord,
    MetadataSnapshotRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    ProposalItemRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.runtime_views import apply_mapping_form
from ontofoundry_api.domain.semantic_views import join_columns, join_view
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposals import store_batch

mapped_session = sql_session
persistent_client = storage_client


def seed_bottomup(client):
    raw_bytes = (FIXTURES / "bottomup-raw-result.json").read_bytes()
    raw = json.loads(raw_bytes)
    replay = json.loads((FIXTURES / "bottomup-replay.json").read_text())
    # Supplied snapshots are AFTER acceptance. Restore every original before
    # and remove only the structures authored by the four mapping creates.
    pinned = deepcopy(replay["session_draft"])
    for item in raw["items"]:
        if item["before"]:
            collection = "properties" if item["target_kind"] == "property" else "link_types"
            pinned[collection] = [
                item["before"] if p["id"] == item["target_id"] else p
                for p in pinned[collection]
            ]
    for key in (
        "semantic_models",
        "datasets",
        "dataset_fields",
        "dataset_relationships",
        "metrics",
        "concept_mappings",
        "mapping_nodes",
    ):
        pinned[key] = []
    pinned["extension_v4"]["legacy_mapping_ids"] = {}
    assert (
        snapshot_sha256(pinned) == raw["source_draft_sha256"] == raw["base_version_sha256"]
    )
    model = OntologyDraft.model_validate(pinned)
    with client.app.state.session_factory() as db:
        db.add(
            WorkspaceRecord(
                id=raw["workspace_id"],
                slug="bottomup-owner-replay",
                name="真实自下而上回放",
                created_by=USER,
            )
        )
        db.flush()
        db.add(
            WorkspaceMemberRecord(
                workspace_id=raw["workspace_id"], user_id=USER, role="owner"
            )
        )
        db.add(
            OntologyVersionRecord(
                id=raw["base_version_id"],
                workspace_id=raw["workspace_id"],
                version_number=1,
                snapshot_json=pinned,
                ossie_json=compile_ossie(
                    model, ontology_name="coffee_sales", ontology_description=""
                ),
                validation_json={},
                sha256=raw["base_version_sha256"],
                published_by=USER,
            )
        )
        db.add(
            ModelingSessionRecord(
                id=raw["session_id"],
                workspace_id=raw["workspace_id"],
                created_by=USER,
                title="自下而上备用回放",
                base_version_id=raw["base_version_id"],
                base_version_sha256=raw["base_version_sha256"],
                revision=raw["source_session_revision"],
                draft_json=pinned,
                draft_sha256=raw["source_draft_sha256"],
            )
        )
        db.flush()
        db.get(WorkspaceRecord, raw["workspace_id"]).current_version_id = raw[
            "base_version_id"
        ]
        seed_evidence(db, client.app.state.settings, raw["workspace_id"], raw)
        db.commit()
    context = RunContext(
        **{
            key: raw[key]
            for key in (
                "workspace_id",
                "session_id",
                "run_token",
                "base_version_id",
                "base_version_sha256",
                "source_session_revision",
                "source_draft_sha256",
            )
        },
        draft=pinned,
    )
    return raw_bytes, raw, context


def coffee_source(client, monkeypatch, workspace):
    engine = source(client, monkeypatch, "销售业务库", workspace_id=workspace)
    with engine.begin() as sql:
        sql.execute(text("ATTACH DATABASE ':memory:' AS demo_analytics"))
        for ddl in (
            "customers(id INTEGER PRIMARY KEY, customer_name TEXT, city TEXT, signup_date TEXT)",
            "orders(id INTEGER PRIMARY KEY, customer_id INTEGER, total_amount NUMERIC, order_status TEXT, order_date TEXT)",
            "order_items(id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, unit_price NUMERIC, line_amount NUMERIC, quantity INTEGER)",
            "products(id INTEGER PRIMARY KEY, product_name TEXT, category TEXT, unit_price NUMERIC)",
        ):
            sql.execute(text("CREATE TABLE demo_analytics." + ddl))
        sql.execute(
            text(
                "INSERT INTO demo_analytics.customers VALUES (1,'星海贸易','上海','2026-01-01'),(2,'远山咖啡','北京','2026-01-01')"
            )
        )
        sql.execute(
            text("INSERT INTO demo_analytics.products VALUES (1,'经典手冲壶','咖啡',345)")
        )
        sql.execute(
            text(
                "INSERT INTO demo_analytics.orders VALUES (:id,:customer,:amount,'completed','2026-01-01')"
            ),
            [
                {
                    "id": i,
                    "customer": 2 if i <= 98 else 1,
                    "amount": 345 if i < 780 else 761,
                }
                for i in range(1, 781)
            ],
        )
        sql.execute(text("INSERT INTO demo_analytics.order_items VALUES (1,1,1,345,345,1)"))
        metadata = inspect(sql)
        tables = [
            {
                "name": t,
                "columns": [
                    {"name": c["name"]}
                    for c in metadata.get_columns(t, schema="demo_analytics")
                ],
            }
            for t in ("customers", "orders", "order_items", "products")
        ]
    with client.app.state.session_factory() as db:
        connection = db.scalar(
            select(ConnectionRecord).where(
                ConnectionRecord.workspace_id == workspace,
                ConnectionRecord.name == "销售业务库",
            )
        )
        db.add(
            MetadataSnapshotRecord(
                connection_id=connection.id,
                schema_name="demo_analytics",
                snapshot_json={"tables": tables},
                observed_at=utc_now(),
            )
        )
        db.commit()
    return engine


@pytest.mark.parametrize("shape", ["legacy_owner", "explicit_owner"])
def test_unchanged_real_bottomup_accept_publish_and_every_neighbor(
    persistent_client, monkeypatch, shape
):
    client = persistent_client
    raw_bytes, raw, context = seed_bottomup(client)
    workspace = context.workspace_id
    root = "/api/v1/workspaces/" + workspace
    engine = coffee_source(client, monkeypatch, workspace)
    try:
        result = deepcopy(raw)
        if shape == "explicit_owner":
            for item in result["items"]:
                if item["target_kind"] == "link_type":
                    join = item["after"]["data_join"]
                    item["after"]["data_join"] = {
                        "owner_columns": [join["source_column"]],
                        "role_columns": [join["target_column"]],
                    }
        with client.app.state.session_factory() as db:
            parsed = parse_result(
                raw_bytes if shape == "legacy_owner" else result,
                context,
                material_lookup=material_lookup(db, client.app.state.settings, workspace),
            )
            if shape == "explicit_owner":
                original = parse_result(
                    raw_bytes,
                    context,
                    material_lookup=material_lookup(
                        db, client.app.state.settings, workspace
                    ),
                )
                assert [i.after for i in parsed.items] == [i.after for i in original.items]
                assert [i.fingerprint for i in parsed.items] == [
                    i.fingerprint for i in original.items
                ]
                assert [i.depends_on for i in parsed.items] == [
                    i.depends_on for i in original.items
                ]
                assert [i.expected_target_hash for i in parsed.items] == [
                    i.expected_target_hash for i in original.items
                ]
            assert len(parsed.items) == 11
            if shape == "legacy_owner":
                assert parsed.result_sha256 == hashlib.sha256(raw_bytes).hexdigest()
            store_batch(
                db,
                workspace_id=workspace,
                session_id=context.session_id,
                task_id="bottomup-replay",
                manifest={
                    **{k: v for k, v in raw.items() if k != "items"},
                    "pinned_draft": context.draft,
                },
                parsed=parsed,
            )
            db.commit()
        accepted = client.post(
            root + f"/sessions/{context.session_id}/proposal-decisions",
            json={
                "idempotency_key": uuid4().hex,
                "expected_session_revision": context.source_session_revision,
                "decisions": [
                    {"proposal_id": i.id, "decision": "accept"} for i in parsed.items
                ],
            },
        )
        assert accepted.status_code == 200, accepted.text
        session = accepted.json()["session"]
        assert len(accepted.json()["results"]) == 11
        version = publish(client, session, root=root)
        exported = client.get(
            f"/api/v1/ontology/workspaces/{workspace}/versions/{version}/export"
        ).json()
        assert validate_ossie(exported)["publishable"]
        draft = OntologyDraft.model_validate(session["draft"])
        joins = {
            link.technical_name: join_columns(join_view(draft, link.id))
            for link in draft.link_types
        }
        assert joins == {
            "customer_places_order": (("id",), ("customer_id",)),
            "order_contains_item": (("id",), ("order_id",)),
            "item_refers_product": (("product_id",), ("id",)),
        }
        types = {t.technical_name: str(t.id) for t in draft.object_types}

        def find(kind, key):
            return next(
                o
                for o in mcp(
                    client,
                    workspace,
                    "search_objects",
                    type_id=types[kind],
                    source="database",
                )["items"]
                if str(o["key"]) == str(key)
            )

        def neighbors(obj):
            graph = mcp(client, workspace, "expand_object_graph", ref=obj["ref"], depth=1)
            assert not graph["warnings"] and not graph["truncated"], graph
            return graph

        order = find("order", 1)
        graph = neighbors(order)
        customer = next(o for o in graph["objects"] if o["type_id"] == types["customer"])
        assert customer["values"]["customer_name"] == "远山咖啡"
        customers = neighbors(customer)
        assert len(customers["links"]) == 98
        assert (
            len([o for o in customers["objects"] if o["type_id"] == types["order"]]) == 98
        )
        item = next(o for o in graph["objects"] if o["type_id"] == types["order_item"])
        items = neighbors(item)
        assert {o["type_id"] for o in items["objects"]} == {
            types["order"],
            types["order_item"],
            types["product"],
        }
        product = next(o for o in items["objects"] if o["type_id"] == types["product"])
        assert {o["type_id"] for o in neighbors(product)["objects"]} == {
            types["product"],
            types["order_item"],
        }
    finally:
        engine.dispose()


@pytest.mark.parametrize("direction", ["forward", "reverse"])
@pytest.mark.parametrize("shape", ["legacy_owner", "explicit_owner"])
def test_owner_column_handwritten_forward_reverse(client, mapped_session, direction, shape):
    session, supplier, material = mapped_session
    raw = deepcopy(session["draft"])
    raw["link_types"] = [r for r in raw["link_types"] if r["technical_name"] == "supplies"]
    link = raw["link_types"][0]
    if direction == "reverse":
        link["owner_ref"]["ref"] = material["id"]
        link["roles"][0]["concept"]["ref"] = supplier["id"]
        link["endpoint_direction"] = "reverse"
    owner, role = (
        ("supplier_code", "code") if direction == "reverse" else ("code", "supplier_code")
    )
    join = (
        {"source_column": owner, "target_column": role}
        if shape == "legacy_owner"
        else {"owner_columns": [owner], "role_columns": [role]}
    )
    edited = apply_mapping_form(raw, joins={link["id"]: join})
    assert join_columns(join_view(OntologyDraft.model_validate(edited), link["id"])) == (
        ("code",),
        ("supplier_code",),
    )
    response = client.put(
        f"/api/v1/workspaces/{session['workspace_id']}/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": edited},
    )
    assert response.status_code == 200, response.text
    for type_id, key, expected in (
        (supplier["id"], "S1", {"S1", "M1", "M2"}),
        (material["id"], "M1", {"S1", "M1"}),
    ):
        graph = client.post(
            f"/api/v1/workspaces/{session['workspace_id']}/instance-neighborhood",
            json={"session_id": session["id"], "type_id": type_id, "key": key},
        ).json()
        assert not graph["warnings"] and {o["key"] for o in graph["objects"]} == expected


@pytest.mark.parametrize("operation", ["proposal", "draft", "element"])
@pytest.mark.parametrize("schema_source", ["asset", "metadata"])
def test_known_columns_rejected_before_write_and_decisions_atomic(
    client, mapped_session, operation, schema_source
):
    session, _, _ = mapped_session
    wid = session["workspace_id"]
    root = "/api/v1/workspaces/" + wid
    if operation == "element":
        publish(client, session, root=root)
        session = client.get(root + "/sessions/" + session["id"]).json()
    link = next(
        r for r in session["draft"]["link_types"] if r["technical_name"] == "supplies"
    )
    if schema_source == "asset":
        with client.app.state.session_factory() as db:
            connection = db.scalar(
                select(ConnectionRecord).where(
                    ConnectionRecord.workspace_id == wid,
                    ConnectionRecord.name == "测试连接",
                )
            )
            db.add(
                MetadataSnapshotRecord(
                    connection_id=connection.id,
                    schema_name="",
                    observed_at=utc_now(),
                    snapshot_json={
                        "tables": [
                            {
                                "name": "suppliers",
                                "columns": [{"name": "code"}, {"name": "name"}],
                            },
                            {
                                "name": "materials",
                                "columns": [
                                    {"name": "code"},
                                    {"name": "name"},
                                    {"name": "supplier_code"},
                                ],
                            },
                        ]
                    },
                )
            )
            db.commit()
    bad = {"owner_columns": ["nonexistent_owner_key"], "role_columns": ["supplier_code"]}
    if operation == "proposal":
        batch = seed_batch(client, session, [update("link_type", link, data_join=bad)])
        result = decide(client, session, [(i["id"], "accept") for i in batch["items"]])
    else:
        body = {"draft": session["draft"], "legacy_joins": {link["id"]: bad}}
        if operation == "draft":
            result = client.put(
                root + "/sessions/" + session["id"],
                json={**body, "revision": session["revision"]},
            )
        else:
            result = client.post(
                root + "/element-saves",
                json={
                    **body,
                    "target_kind": "link_type",
                    "target_id": link["id"],
                    "session_id": session["id"],
                    "expected_session_revision": session["revision"],
                    "expected_current_version_id": session["base_version_id"],
                },
            )
    assert result.status_code == 422, result.text
    assert result.json()["error"]["code"] == "JOIN_COLUMN_NOT_FOUND"
    assert result.json()["error"]["side"] == "owner"
    assert result.json()["error"]["table"] == "suppliers"
    assert result.json()["error"]["columns"] == ["nonexistent_owner_key"]
    with client.app.state.session_factory() as db:
        stored = db.get(ModelingSessionRecord, session["id"])
        assert (
            stored.revision == session["revision"] and stored.draft_json == session["draft"]
        )
        if operation == "proposal":
            assert db.get(ProposalItemRecord, batch["items"][0]["id"]).status == "pending"


@pytest.mark.parametrize(
    "relation,table,column",
    [
        ("customer_places_order", "demo_analytics.customers", "customer_id"),
        ("order_contains_item", "demo_analytics.orders", "order_id"),
    ],
)
def test_wrong_endpoint_spelling_real_batch_rejected_instead_of_published(
    client, monkeypatch, relation, table, column
):
    _, raw, context = seed_bottomup(client)
    engine = coffee_source(client, monkeypatch, context.workspace_id)
    try:
        item = next(
            i for i in raw["items"] if (i["after"] or {}).get("technical_name") == relation
        )
        item["after"]["data_join"] = {"source_column": "id", "target_column": column}
        with client.app.state.session_factory() as db:
            parsed = parse_result(
                raw,
                context,
                material_lookup=material_lookup(
                    db, client.app.state.settings, context.workspace_id
                ),
            )
            store_batch(
                db,
                workspace_id=context.workspace_id,
                session_id=context.session_id,
                task_id="invalid-owner-replay",
                manifest={
                    **{k: v for k, v in raw.items() if k != "items"},
                    "pinned_draft": context.draft,
                },
                parsed=parsed,
            )
            db.commit()
        root = "/api/v1/workspaces/" + context.workspace_id
        response = client.post(
            root + f"/sessions/{context.session_id}/proposal-decisions",
            json={
                "idempotency_key": uuid4().hex,
                "expected_session_revision": context.source_session_revision,
                "decisions": [
                    {"proposal_id": i.id, "decision": "accept"} for i in parsed.items
                ],
            },
        )
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "JOIN_COLUMN_NOT_FOUND" and error["side"] == "role"
        assert error["table"] == table and error["columns"] == [column]
        with client.app.state.session_factory() as db:
            session = db.get(ModelingSessionRecord, context.session_id)
            assert (
                session.revision == context.source_session_revision
                and session.draft_json == context.draft
            )
            assert all(
                db.get(ProposalItemRecord, i.id).status == "pending" for i in parsed.items
            )
    finally:
        engine.dispose()
