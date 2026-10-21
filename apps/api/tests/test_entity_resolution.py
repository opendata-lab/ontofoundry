"""Entity resolution grades candidates in the service, never in the prompt (ER-01–ER-13)."""

from core1_fixtures import example_draft
from test_instance_store import accept_all, call, create_instance
from test_modeling import ROOT, create_session

from ontofoundry_api.services import entity_resolution

ONTOLOGY = ROOT.replace("/api/v1/workspaces/", "/api/v1/ontology/workspaces/")


def customer_type(session):
    return next(o for o in session["draft"]["object_types"] if o["name"] == "customer")


def resolve(client, mention, type_id, **extra):
    response = client.post(ONTOLOGY + "/entities/resolve", json={"mention": mention, "object_type_id": type_id, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_document_instances_resolve_by_level_and_status(client):
    session = create_session(client)
    type_id = customer_type(session)["id"]
    session, _ = accept_all(client, session, [create_instance(session, name) for name in ("月湾客户", "月湾客户二部", "鹭汀商行")])

    exact = resolve(client, " 月湾客户 ", type_id)
    assert exact["status"] == "MATCHED" and exact["coverage"] in {"complete", "partial"}
    (only,) = exact["candidates"]
    assert only["source"] == "document" and only["entity_ref"].startswith("doc.")
    assert only["match"]["level"] == "name_exact" and only["display"] == "月湾客户"

    ambiguous = resolve(client, "月湾", type_id)
    assert ambiguous["status"] == "AMBIGUOUS"
    assert {c["display"] for c in ambiguous["candidates"]} == {"月湾客户", "月湾客户二部"}
    assert all(c["match"]["level"] == "name_contains" for c in ambiguous["candidates"])

    # A single contains hit counts as matched (ER-03).
    assert resolve(client, "鹭汀", type_id)["status"] == "MATCHED"
    assert resolve(client, "虚构不存在", type_id)["status"] == "NOT_FOUND"
    # Full-width input is normalized before grading (ER-05).
    assert resolve(client, "月湾客户　", type_id)["status"] == "MATCHED"

    via_mcp = call(client, "resolve_entity", {"mention": "月湾", "object_type_id": type_id})["structuredContent"]
    assert via_mcp["status"] == "AMBIGUOUS" and len(via_mcp["candidates"]) == 2


def test_database_identifier_match_and_truncation(client, monkeypatch):
    draft = example_draft("01-basic-sales")
    customer = next(o for o in draft.object_types if o.name == "customer")
    rows = [
        {"__ref": "db.c001", "display_text": "C001", "values": {"customer_no": "C001", "name": "虚构商行"}},
        {"__ref": "db.c0011", "display_text": "C0011", "values": {"customer_no": "C0011", "name": "虚构商行二部"}},
    ]
    more = {"value": False}
    monkeypatch.setattr(
        "ontofoundry_api.services.instance_plan.query_instances",
        lambda *a, q, **k: {"items": rows, "has_more": more["value"]},
    )
    monkeypatch.setattr("ontofoundry_api.services.instance_store.visible", lambda *a, **k: {"objects": []})

    def run():
        with client.app.state.session_factory() as db:
            return entity_resolution.resolve_entity(
                db, str(draft.workspace_id), draft, mention="ｃ001", object_type_id=customer.id,
                limit=10, settings=client.app.state.settings, mappings_readable=True,
            )

    result = run()
    assert result["status"] == "MATCHED" and result["coverage"] == "complete"
    (hit,) = result["candidates"]
    assert hit["source"] == "database" and hit["match"]["level"] == "identifier_exact"
    assert hit["identifiers"] == {"customer_no": "C001"}
    # Rows beyond what was read may also match, so one hit is not proven unique (ER-10).
    more["value"] = True
    truncated = run()
    assert truncated["status"] == "AMBIGUOUS" and truncated["coverage"] == "partial"


def test_unknown_type_and_missing_title_are_refused(client):
    response = client.post(ONTOLOGY + "/entities/resolve", json={"mention": "x", "object_type_id": "00000000-0000-4000-8000-000000000000"})
    assert response.status_code == 404
