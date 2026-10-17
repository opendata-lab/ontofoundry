"""Authorization is applied before datasets, expressions, evidence and caches."""

from ontofoundry_api.api.auth import Principal
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.mcp_ontology import invoke
from ontofoundry_api.services.workspaces import DEV_USER_ID


def test_low_scope_never_receives_physical_or_fact_content(client):
    wid = str(DEMO_WORKSPACE_ID)
    low = Principal(
        id=DEV_USER_ID,
        subject="test",
        display_name="test",
        email=None,
        service_token_id="fictional-token",
        scopes=frozenset({"ontology:read"}),
    )
    high = Principal(id=DEV_USER_ID, subject="test", display_name="test", email=None)
    with client.app.state.session_factory() as db:
        args = {"include": ["semantic", "physical", "rules", "adjacency"]}
        directory = invoke(db, wid, high, "get_ontology", {}, client.app.state.settings)
        ids = [e["id"] for e in directory["elements"]]
        invoke(
            db, wid, high, "get_ontology", {**args, "ids": ids}, client.app.state.settings
        )
        result = invoke(
            db, wid, low, "get_ontology", {**args, "ids": ids}, client.app.state.settings
        )
        text = str(result)
        assert "fictional_sales" not in text
        assert (
            "evidence" not in text and "quote" not in text and "sql_reference" not in text
        )
        metric = next(e for e in result["elements"] if e["kind"] == "metric")
        assert metric["binding_status"] == "forbidden"
        first = invoke(
            db, wid, high, "get_ontology", {"limit": 1}, client.app.state.settings
        )
        import pytest

        with pytest.raises(ServiceError):
            invoke(
                db,
                wid,
                low,
                "get_ontology",
                {"limit": 1, "cursor": first["next_cursor"]},
                client.app.state.settings,
            )


def test_mapping_only_token_ratio_recursively_crops_component_evidence(client):
    import hashlib
    import json
    from uuid import uuid4

    from pr23_fixtures import example_session
    from test_modeling import ONTOLOGY, publish, save

    from ontofoundry_api.db_models import ServiceTokenRecord, ServiceTokenScopeRecord

    session = example_session(client, "13-dataset-metrics")
    ratio = next(m for m in session["draft"]["metrics"] if m["kind"] == "ratio")
    component_ids = {ratio["numerator_id"], ratio["denominator_id"]}
    uploaded = client.post(
        f"/api/v1/workspaces/{session['workspace_id']}/materials",
        params={"name": "虚构指标说明.md"},
        content="私密材料引文".encode(),
    )
    assert uploaded.status_code == 201, uploaded.text
    material = uploaded.json()
    for metric in session["draft"]["metrics"]:
        if metric["id"] in component_ids:
            metric["evidence"] = [
                {
                    "id": str(uuid4()),
                    "kind": "manual",
                    "note": "私密口径说明",
                    "created_by": DEV_USER_ID,
                    "created_at": "2026-10-17T00:00:00Z",
                },
                {
                    "id": str(uuid4()),
                    "kind": "material",
                    "material_id": material["id"],
                    "material_sha256": material["sha256"],
                    "locator": {"line_start": 1, "line_end": 1},
                    "quote": "私密材料引文",
                },
            ]
    session = save(client, session, session["draft"]).json()
    assert publish(client, session).status_code == 200
    token, token_id = "fictional-mapping-token", str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(
            ServiceTokenRecord(
                id=token_id,
                workspace_id=session["workspace_id"],
                created_by=DEV_USER_ID,
                name="仅映射读取",
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
            )
        )
        db.flush()
        db.add(ServiceTokenScopeRecord(token_id=token_id, scope="mappings:read"))
        db.commit()
    high = client.get(ONTOLOGY + f"/types/{ratio['id']}")
    assert high.status_code == 200
    assert "私密口径说明" in high.text
    low = client.get(
        ONTOLOGY + f"/types/{ratio['id']}", headers={"Authorization": "Bearer " + token}
    )
    assert low.status_code == 200, low.text
    definition = low.json()["item"]["definition"]
    assert definition["components"]["numerator"]["id"] == ratio["numerator_id"]
    assert definition["components"]["denominator"]["id"] == ratio["denominator_id"]
    assert "evidence" not in json.dumps(definition)
    assert "私密口径说明" not in low.text and "私密材料引文" not in low.text
    from test_modeling import mcp_request

    mcp = mcp_request(
        client,
        "tools/call",
        {
            "name": "get_ontology",
            "arguments": {"ids": [ratio["id"]], "include": ["physical"]},
        },
        headers={"Authorization": "Bearer " + token},
    )
    assert mcp.status_code == 200, mcp.text
    projected = mcp.json()["result"]["structuredContent"]["elements"][0]
    assert projected["components"]["numerator"]["id"] == ratio["numerator_id"]
    assert "evidence" not in json.dumps(projected) and "私密材料引文" not in mcp.text
