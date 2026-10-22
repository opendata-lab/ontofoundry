"""A deployment-fixed MCP bearer token reads one workspace, read-only."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_modeling import ONTOLOGY, mcp_request

from ontofoundry_api.config import Settings
from ontofoundry_api.main import create_app

TOKEN = "fiction-static-mcp-token-0123456789"


def settings(tmp_path, **extra):
    return Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "files",
        auto_create_schema=True,
        seed_demo=True,
        auth_mode="dev",
        session_secret="test-session-secret-with-more-than-32-chars",
        **extra,
    )


@pytest.fixture
def static_client(tmp_path) -> Iterator[TestClient]:
    with TestClient(create_app(settings(tmp_path, mcp_token=TOKEN))) as client:
        yield client


def bearer(token):
    return {"Authorization": "Bearer " + token}


def test_fixed_token_reads_the_workspace_with_mappings_and_instances(static_client):
    listed = mcp_request(static_client, "tools/list", headers=bearer(TOKEN))
    assert listed.status_code == 200, listed.text
    assert listed.json()["result"]["tools"]
    # Instance reads need instances:read; the fixed token carries it.
    objects = static_client.get(ONTOLOGY + "/objects", headers=bearer(TOKEN))
    assert objects.status_code == 200, objects.text


def test_wrong_token_and_directory_reads_are_refused(static_client):
    assert mcp_request(static_client, "tools/list", headers=bearer(TOKEN + "x")).status_code == 401
    assert static_client.get("/api/v1/ontology/workspaces", headers=bearer(TOKEN)).status_code == 401


def test_default_fixed_token_works_out_of_the_box(client):
    default = Settings.model_fields["mcp_token"].default
    assert default == "ontofoundry-mcp-default-token"
    assert mcp_request(client, "tools/list", headers=bearer(default)).status_code == 200
    assert mcp_request(client, "tools/list", headers=bearer(TOKEN)).status_code == 401


def test_empty_fixed_token_disables_external_access(tmp_path):
    with TestClient(create_app(settings(tmp_path, mcp_token=""))) as client:
        assert mcp_request(client, "tools/list", headers=bearer("")).status_code == 401
        default = Settings.model_fields["mcp_token"].default
        assert mcp_request(client, "tools/list", headers=bearer(default)).status_code == 401


def test_short_fixed_token_is_rejected_at_startup(tmp_path):
    with pytest.raises(ValueError, match="at least 24"):
        settings(tmp_path, mcp_token="short")
