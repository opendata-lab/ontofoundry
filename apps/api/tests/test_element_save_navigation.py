"""Element synchronization preserves executable cross-object membership paths."""

from copy import deepcopy
from uuid import uuid4

import pytest
from core1_query_fixtures import source_database
from test_element_save import preflight_confirmations, save_body
from test_modeling import ONTOLOGY, ROOT, create_session, publish, save

from ontofoundry_api.domain.bindings import binding_readiness, resolve_binding
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import strict_equal
from ontofoundry_api.domain.models import COLLECTIONS
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.element_save import calculate_element_save, element_scope
from ontofoundry_api.services.instance_plan import query_instances


@pytest.mark.parametrize("branch_kind", ["simple", "expression"])
@pytest.mark.parametrize("hops", [1, 2])
@pytest.mark.parametrize("existing_mapping", [False, True])
def test_navigation_imports_effective_mappings_and_datasets(
    client, tmp_path, monkeypatch, branch_kind, hops, existing_mapping
):
    graph, engine = source_database(tmp_path, monkeypatch, "06-inheritance")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO suppliers (supplier_id, supplier_name) VALUES ('P2', '命中')"
            )
            conn.exec_driver_sql(
                "INSERT INTO channel_partners (partner_id, partner_name) VALUES ('P2', '命中')"
            )
        latest = graph.model_dump(mode="json")
        for collection in COLLECTIONS.values():
            for element in latest[collection]:
                if "evidence" in element:
                    element["evidence"] = []
        objects = {o["name"]: o for o in latest["object_types"]}
        vip, party, supplier, partner = [
            objects[name] for name in ("vip_party", "party", "supplier", "channel_partner")
        ]

        def prop(obj, name):
            return next(
                p
                for p in latest["properties"]
                if p["owner_type_id"] == obj["id"] and p["name"] == name
            )

        template = latest["link_types"][1]
        path = []
        for source, target, source_key, target_key, name in [
            (party, supplier, "contact_no", "supplier_no", "supplier"),
            (supplier, partner, "supplier_no", "partner_no", "partner"),
        ][:hops]:
            link = {
                **deepcopy(template),
                "id": str(uuid4()),
                "name": name,
                "source_type_id": source["id"],
                "target_type_id": target["id"],
                "data_join": {
                    "kind": "direct",
                    "source_property_ids": [prop(source, source_key)["id"]],
                    "target_property_ids": [prop(target, target_key)["id"]],
                },
            }
            latest["link_types"].append(link)
            path.append({"link_type_id": link["id"], "direction": "forward"})
        terminal = supplier if hops == 1 else partner
        if branch_kind == "simple":
            vip["derived_by"] = [
                {
                    "kind": "simple",
                    "conditions": [
                        {
                            "path": {
                                "links": path,
                                "property_id": prop(terminal, "name")["id"],
                            },
                            "operator": "eq",
                            "values": ["命中"],
                        }
                    ],
                }
            ]
        else:
            navigation = "party.supplier" + (".partner" if hops == 2 else "")
            vip["derived_by"] = [
                {
                    "kind": "expression",
                    "expression": navigation + ".name = '命中'",
                }
            ]
        validate_core_graph(CoreDraft.model_validate(latest))
        initial = create_session(client)
        latest["workspace_id"] = initial["workspace_id"]
        base = {**latest, **{c: [] for c in COLLECTIONS.values()}}
        base["object_types"] = [
            {
                **deepcopy(vip),
                "extends": None,
                "derived_by": [],
                "title_property_id": None,
            }
        ]
        supplier_mapping = next(
            m for m in latest["mappings"] if m["type_id"] == supplier["id"]
        )
        if existing_mapping:
            base["object_types"].append(deepcopy(supplier))
            base["properties"] = deepcopy(
                [p for p in latest["properties"] if p["owner_type_id"] == supplier["id"]]
            )
            base["mappings"] = [deepcopy(supplier_mapping)]
            base["datasets"] = deepcopy(
                [
                    d
                    for d in latest["datasets"]
                    if d["id"] == supplier_mapping["sources"][0]["dataset_id"]
                ]
            )
        response = save(client, initial, base)
        assert response.status_code == 200, response.text
        assert publish(client, response.json()).status_code == 200
        old, newer = create_session(client), create_session(client)
        base = deepcopy(old["draft"])
        response = save(client, newer, latest)
        assert response.status_code == 200, response.text
        assert publish(client, response.json()).status_code == 200
        if existing_mapping:
            old["draft"]["object_types"][1]["description"] = "保留供应商草稿"
            old["draft"]["datasets"][0]["description"] = "保留数据集草稿"
            old["draft"]["mappings"][0]["fields"]["name"] = {
                "kind": "expression",
                "expression": "main.supplier_name || ''",
            }
            response = save(client, old, old["draft"])
            assert response.status_code == 200, response.text
            old = response.json()
        candidate = deepcopy(old["draft"])
        candidate["object_types"][0]["description"] = "只修改VIP说明"
        current = client.get(ROOT + "/published-snapshot").json()
        inputs = deepcopy([base, current, old["draft"], candidate])
        calculation = calculate_element_save(
            base, current, old["draft"], candidate, "object_type", vip["id"]
        )
        assert strict_equal([base, current, old["draft"], candidate], inputs)
        body = save_body(client, old, candidate, target_id=vip["id"])
        confirmations = preflight_confirmations(client, body)
        assert {c["target_id"] for c in confirmations} == {
            c["target_id"] for c in calculation.affected_items
        }
        local = element_scope(calculation.session_draft, "object_type", vip["id"])
        imported = {
            e["id"]: (collection, e)
            for collection in COLLECTIONS.values()
            for e in calculation.session_draft[collection]
            if e["id"] not in local[collection]
            and e["id"] not in {old_e["id"] for old_e in old["draft"][collection]}
        }
        assert set(imported) == {c["target_id"] for c in confirmations}
        for entry in confirmations:
            collection, element = imported[entry["target_id"]]
            assert entry["expected_target_hash"] == element_sha256(
                element, collection=collection
            )
        navigated = [supplier] + ([partner] if hops == 2 else [])
        required_mappings = [
            m for m in latest["mappings"] if m["type_id"] in {o["id"] for o in navigated}
        ]
        for mapping in required_mappings:
            if not (existing_mapping and mapping["id"] == supplier_mapping["id"]):
                assert mapping["id"] in imported
                assert mapping["sources"][0]["dataset_id"] in imported
        before_version = client.get(ONTOLOGY + "/version").json()
        before_session = client.get(ROOT + f"/sessions/{old['id']}").json()
        for items, status, code in [
            (confirmations[:-1], 422, "ELEMENT_SCOPE_INVALID"),
            (
                [
                    {**confirmations[0], "expected_target_hash": "0" * 64},
                    *confirmations[1:],
                ],
                409,
                "VERSION_CHANGED",
            ),
        ]:
            response = client.post(
                ROOT + "/element-saves", json={**body, "affected_items": items}
            )
            assert response.status_code == status, response.text
            assert response.json()["error"]["code"] == code
            assert client.get(ONTOLOGY + "/version").json() == before_version
            assert client.get(ROOT + f"/sessions/{old['id']}").json() == before_session
        confirmed = calculate_element_save(
            base,
            current,
            old["draft"],
            candidate,
            "object_type",
            vip["id"],
            affected_items=confirmations,
        )
        assert strict_equal(confirmed.session_draft, calculation.session_draft)
        response = client.post(
            ROOT + "/element-saves", json={**body, "affected_items": confirmations}
        )
        assert response.status_code == 200, response.text
        result = response.json()
        for raw in (
            calculation.merged,
            calculation.session_draft,
            result["draft"],
            result["session"]["draft"],
        ):
            actual = validate_core_graph(CoreDraft.model_validate(raw))
            for obj in navigated:
                type_id = next(o.id for o in actual.object_types if str(o.id) == obj["id"])
                assert binding_readiness(actual, type_id).status == "bound"
                assert resolve_binding(actual, type_id).main is not None
            rows = query_instances(None, raw["workspace_id"], actual, vip["id"], None)
            assert [row["values"]["party_no"] for row in rows["items"]] == ["P1"]
        synced = result["session"]["draft"]
        # Inherited incoming links also require their source endpoint definitions.
        expected_objects = {"vip_party", "party", "supplier", "asset", "contract"}
        if hops == 2:
            expected_objects.add("channel_partner")
        assert {o["name"] for o in synced["object_types"]} == expected_objects
        if existing_mapping:
            assert (
                next(o for o in synced["object_types"] if o["id"] == supplier["id"])[
                    "description"
                ]
                == "保留供应商草稿"
            )
            assert (
                next(m for m in synced["mappings"] if m["id"] == supplier_mapping["id"])
                == old["draft"]["mappings"][0]
            )
            assert (
                next(
                    d
                    for d in synced["datasets"]
                    if d["id"] == old["draft"]["datasets"][0]["id"]
                )["description"]
                == "保留数据集草稿"
            )
    finally:
        engine.dispose()
