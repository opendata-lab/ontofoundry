"""Element synchronization preserves executable cross-object membership paths."""

from copy import deepcopy
from uuid import uuid4

import pytest
from core1_query_fixtures import source_database
from test_element_save import preflight_confirmations, save_body
from test_modeling import ROOT, create_session, publish, published_snapshot, save

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import strict_equal
from ontofoundry_api.domain.models import COLLECTIONS
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.element_save import calculate_element_save


@pytest.mark.parametrize("branch_kind", ["simple", "expression"])
@pytest.mark.parametrize("hops", [1, 2])
@pytest.mark.parametrize("existing_mapping", [False, True])
def test_save_does_not_import_published_navigation_dependencies(
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
        from pr23_fixtures import clear_instances
        clear_instances(client, initial["workspace_id"])
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
        current = published_snapshot(client, ROOT)
        inputs = deepcopy([base, current, old["draft"], candidate])
        calculation = calculate_element_save(old["draft"], candidate, "object_type", vip["id"])
        assert strict_equal([base, current, old["draft"], candidate], inputs)
        body = save_body(client, old, candidate, target_id=vip["id"])
        assert preflight_confirmations(client, old, body) == []
        response = client.post(ROOT + f"/sessions/{old['id']}/element-saves", json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["draft"] == calculation.session_draft
        assert {o["id"] for o in result["draft"]["object_types"]} == {
            o["id"] for o in old["draft"]["object_types"]
        }
        assert result["draft"]["datasets"] == old["draft"]["datasets"]
        assert result["draft"]["mappings"] == old["draft"]["mappings"]
        assert published_snapshot(client, ROOT) == current
    finally:
        engine.dispose()
