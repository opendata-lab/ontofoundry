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
