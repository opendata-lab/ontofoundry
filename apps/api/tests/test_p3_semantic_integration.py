"""Native mapping writes and published REST/MCP reads on actual SQLite source SQL.

The persistent store also runs on a disposable PostgreSQL database. SQL source
rows are deterministic equivalents, not the external demonstration database.
"""

import json
from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from test_m8_binary_facts_replay import FIXTURES as RUNS
from test_m8_binary_facts_replay import mcp
from test_modeling import ROOT, create_session
from test_p3_semantic_views import imported
from test_t4_proposal_decisions import create, decide, seed_batch, update

from ontofoundry_api.api import connections, instances
from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.domain.runtime_views import legacy_mapping_form
from ontofoundry_api.domain.semantic_views import SemanticViews
from ontofoundry_api.ossie.compiler import validate_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID


@pytest.fixture(params=["client", "pg_client"])
def persistent_client(request):
    return request.getfixturevalue(request.param)


def source(client, monkeypatch, alias, workspace_id=DEMO_WORKSPACE_ID):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @contextmanager
    def readonly(item, settings):
        with engine.connect() as sql:
            yield sql

    monkeypatch.setattr(connections, "connect_readonly", readonly)
    monkeypatch.setattr(instances, "connect_readonly", readonly)
    with client.app.state.session_factory() as db:
        db.add(
            ConnectionRecord(
                id=str(uuid4()),
                workspace_id=str(workspace_id),
                name=alias,
                kind="postgresql",
                config_json={},
                secret_encrypted="not-used",
            )
        )
        db.commit()
    return engine


def publish(client, session, root=ROOT):
    preview = client.post(
        root + "/sessions/" + session["id"] + "/preview",
        json={"revision": session["revision"]},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["validation"]["publishable"] and not body["validation"]["errors"], body
    response = client.post(
        root + "/sessions/" + session["id"] + "/publish",
        json={
            "expected_session_revision": session["revision"],
            "expected_current_version_id": body["current_version_id"],
            "expected_merged_snapshot_sha256": body["merged_snapshot_sha256"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["version"]["version_id"]


def test_b_simple_native_mappings_query_all_ten_complex_readonly_and_clean_catalog(
    persistent_client, monkeypatch
):
    client = persistent_client
    _, draft = imported()
    views = SemanticViews(draft)
    simple = [a.mapping for t in draft.object_types if (a := views.analyze(t.id)).mapping]
    engine = source(client, monkeypatch, simple[0].connection_alias)
    try:
        tables = {}
        for mapping in simple:
            tables.setdefault((mapping.schema_name, mapping.table_name), set()).update(
                [mapping.key_column, *mapping.fields.values()]
            )
        with engine.begin() as sql:
            for schema in {schema for schema, _ in tables if schema}:
                sql.execute(text("ATTACH DATABASE ':memory:' AS " + schema))
            for (schema, table), cols in tables.items():
                names = sorted(cols)
                sql.execute(
                    text(
                        "CREATE TABLE "
                        + (schema + "." if schema else "")
                        + '"'
                        + table
                        + '" ('
                        + ",".join('"' + c + '" TEXT' for c in names)
                        + ")"
                    )
                )
                sql.execute(
                    text(
                        "INSERT INTO "
                        + (schema + "." if schema else "")
                        + '"'
                        + table
                        + '" VALUES ('
                        + ",".join(":c" + str(i) for i in range(len(names)))
                        + ")"
                    ),
                    {"c" + str(i): "sample_" + c for i, c in enumerate(names)},
                )
        session = create_session(client)
        saved = client.put(
            ROOT + "/sessions/" + session["id"],
            json={"revision": session["revision"], "draft": draft.model_dump(mode="json")},
        )
        assert saved.status_code == 200, saved.text
        version = publish(client, saved.json())
        for mapping in simple:
            found = mcp(
                client,
                str(DEMO_WORKSPACE_ID),
                "search_objects",
                version_id=version,
                type_id=str(mapping.type_id),
                source="database",
            )
            assert len(found["items"]) == 1, found
            obj = found["items"][0]
            assert (
                mcp(client, str(DEMO_WORKSPACE_ID), "get_object", ref=obj["ref"])["item"][
                    "values"
                ]
                == obj["values"]
            )
        component = next(t for t in draft.object_types if t.concept == "component")
        response = client.get(
            f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}/objects",
            params={"type_id": str(component.id), "source": "database"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "COMPLEX_MAPPING_READ_ONLY"
        catalog = client.get(ROOT + "/semantic-models").json()
        model = catalog["items"][0]
        assert (
            len(model["datasets"]) == 41
            and sum(len(d["fields"]) for d in model["datasets"]) == 371
        )
        assert len(model["metrics"]) == 27
        assert any(
            m["name"] == "core_service_count" and m["concepts"] for m in model["metrics"]
        )
        assert all(
            key not in json.dumps(catalog)
            for key in ("native_presence", "position", "origin")
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize("proposal_shape", ["native_update", "endpoint_create"])
def test_coffee_four_mapping_three_join_proposals_publish_query_and_edit(
    persistent_client, monkeypatch, proposal_shape
):
    client = persistent_client
    original = json.loads((RUNS / "topdown-replay.json").read_text())["published_snapshot"]
    old_form = legacy_mapping_form(original)
    draft = json.loads(json.dumps(original))
    draft["workspace_id"] = str(DEMO_WORKSPACE_ID)
    # Fresh modeling run using the real concepts; do not silently repair fixture native joins.
    for collection in (
        "semantic_models",
        "datasets",
        "dataset_fields",
        "dataset_relationships",
        "metrics",
        "concept_mappings",
        "mapping_nodes",
    ):
        draft[collection] = []
    draft["extension_v4"]["legacy_mapping_ids"] = {}
    links = draft["link_types"]
    if proposal_shape == "endpoint_create":
        draft["link_types"] = []
    session = create_session(client)
    saved = client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": draft},
    )
    assert saved.status_code == 200, saved.text
    session = saved.json()
    items = [
        create("map_" + str(i), "mapping", {k: v for k, v in m.items() if k != "id"})
        for i, m in enumerate(old_form["mappings"])
    ]
    pairs = {
        "customer_places_order": ("id", "customer_id"),
        "order_contains_item": ("id", "order_id"),
        "item_refers_product": ("product_id", "id"),
    }
    from ontofoundry_api.domain.models import OntologyDraft

    templates = OntologyDraft.model_validate(original).link_types
    for link, template in zip(links, templates, strict=True):
        a, b = pairs[link["technical_name"]]
        owner, role = (b, a) if template.endpoint_direction == "reverse" else (a, b)
        join = {"owner_columns": [owner], "role_columns": [role]}
        if proposal_shape == "native_update":
            items.append(update("link_type", link, data_join=join))
        else:
            items.append(
                dict(
                    client_ref=link["technical_name"],
                    operation="create",
                    target_kind="link_type",
                    target_id=None,
                    expected_target_hash=None,
                    before=None,
                    after=dict(
                        name=link["name"],
                        technical_name=link["technical_name"],
                        source_type_id=str(template.source_type_id),
                        target_type_id=str(template.target_type_id),
                        multiplicity="one_to_many"
                        if template.endpoint_direction == "reverse"
                        else "many_to_one",
                        data_join=join,
                    ),
                )
            )
    batch = seed_batch(client, session, items)
    assert len(batch["items"]) == 7
    accepted = decide(client, session, [(i["id"], "accept") for i in batch["items"]])
    assert accepted.status_code == 200, accepted.text
    session = accepted.json()["session"]
    assert session["draft"]["mappings"] == []
    fields = {}
    for field in session["draft"]["dataset_fields"]:
        fields.setdefault(field["dataset_id"], set()).add(field["name"])
    datasets = {d["name"]: d for d in session["draft"]["datasets"]}
    for relationship in session["draft"]["dataset_relationships"]:
        assert (
            set(relationship["from_columns"])
            <= fields[datasets[relationship["from"]]["id"]]
        )
        assert set(relationship["to_columns"]) <= fields[datasets[relationship["to"]]["id"]]
    for name, key in (
        ("order", "customer_id"),
        ("order_item", "order_id"),
        ("order_item", "product_id"),
    ):
        assert key in fields[datasets[name]["id"]]
    assert all(
        key not in m["fields"].values()
        for m in old_form["mappings"]
        for key in ("customer_id", "order_id", "product_id")
    )
    engine = source(client, monkeypatch, "销售业务库")
    try:
        with engine.begin() as sql:
            sql.execute(text("ATTACH DATABASE ':memory:' AS demo_analytics"))
            sql.execute(
                text(
                    "CREATE TABLE demo_analytics.customers(id INTEGER PRIMARY KEY, customer_name TEXT, city TEXT, signup_date TEXT)"
                )
            )
            sql.execute(
                text(
                    "CREATE TABLE demo_analytics.orders(id INTEGER PRIMARY KEY, customer_id INTEGER, total_amount NUMERIC, order_status TEXT, order_date TEXT)"
                )
            )
            sql.execute(
                text(
                    "CREATE TABLE demo_analytics.products(id INTEGER PRIMARY KEY, product_name TEXT, category TEXT, unit_price NUMERIC)"
                )
            )
            sql.execute(
                text(
                    "CREATE TABLE demo_analytics.order_items(id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, unit_price NUMERIC, line_amount NUMERIC, quantity INTEGER)"
                )
            )
            sql.execute(
                text(
                    "INSERT INTO demo_analytics.customers VALUES (1,'星海贸易','上海','2026-01-01'),(2,'远山咖啡','北京','2026-01-01')"
                )
            )
            sql.execute(
                text(
                    "INSERT INTO demo_analytics.products VALUES (1,'经典手冲壶','咖啡',345)"
                )
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
            sql.execute(
                text("INSERT INTO demo_analytics.order_items VALUES (1,1,1,345,345,1)")
            )
        version = publish(client, session)
        wid = str(DEMO_WORKSPACE_ID)
        types = {t["technical_name"]: t["id"] for t in session["draft"]["object_types"]}
        orders, cursor = [], None
        while True:
            page = mcp(
                client,
                wid,
                "search_objects",
                type_id=types["order"],
                source="database",
                limit=100,
                **({"cursor": cursor} if cursor else {}),
            )
            orders.extend(page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
        assert len(orders) == 780
        assert sum(Decimal(str(o["values"]["order_amount"])) for o in orders) == Decimal(
            "269516"
        )
        first = orders[0]
        graph = mcp(client, wid, "expand_object_graph", ref=first["ref"], depth=1)
        assert not graph["warnings"] and {o["type_id"] for o in graph["objects"]} == {
            types["order"],
            types["customer"],
            types["order_item"],
        }
        customer = next(o for o in graph["objects"] if o["type_id"] == types["customer"])
        assert customer["values"]["customer_name"] == "远山咖啡"
        customer_graph = mcp(
            client, wid, "expand_object_graph", ref=customer["ref"], depth=1
        )
        assert not customer_graph["warnings"] and not customer_graph["truncated"]
        assert (
            len([o for o in customer_graph["objects"] if o["type_id"] == types["order"]])
            == 98
        )
        assert len(customer_graph["links"]) == 98
        item = next(o for o in graph["objects"] if o["type_id"] == types["order_item"])
        inverse = mcp(client, wid, "expand_object_graph", ref=item["ref"], depth=1)
        assert not inverse["warnings"] and {o["type_id"] for o in inverse["objects"]} == {
            types["order"],
            types["order_item"],
            types["product"],
        }
        product = next(o for o in inverse["objects"] if o["type_id"] == types["product"])
        product_graph = mcp(client, wid, "expand_object_graph", ref=product["ref"], depth=1)
        assert not product_graph["warnings"]
        assert {o["type_id"] for o in product_graph["objects"]} == {
            types["product"],
            types["order_item"],
        }
        assert len(mcp(client, wid, "list_ontology_elements", kind="mapping")["items"]) == 4
        exported = client.get(
            f"/api/v1/ontology/workspaces/{wid}/versions/{version}/export"
        ).json()
        assert validate_ossie(exported)["publishable"]
        # Form editing persists native structure, then publishing reads the updated projection.
        edit_session = create_session(client)
        form = edit_session["legacy_mapping_form"]
        next(m for m in form["mappings"] if m["type_id"] == types["customer"])["fields"][
            "customer_name"
        ] = "city"
        saved = client.put(
            ROOT + "/sessions/" + edit_session["id"],
            json={
                "revision": edit_session["revision"],
                "draft": edit_session["draft"],
                "legacy_mappings": form["mappings"],
                "legacy_joins": form["joins"],
            },
        )
        assert saved.status_code == 200, saved.text
        publish(client, saved.json())
        customer = mcp(
            client, wid, "search_objects", type_id=types["customer"], source="database"
        )["items"][0]
        assert customer["values"]["customer_name"] == "上海"
        assert mcp(client, wid, "expand_object_graph", ref=first["ref"], depth=1)["links"]
    finally:
        engine.dispose()
