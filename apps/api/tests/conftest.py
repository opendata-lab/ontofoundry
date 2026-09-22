from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ontofoundry_api.config import Settings
from ontofoundry_api.main import create_app

# Several tests assert on declared defaults, which means they must not inherit a
# developer's local `.env`. Without this the suite passes in CI and fails on any
# machine configured to run the DataAgent end-to-end flow — the local file
# supplies a base URL and access key the tests expect to be empty.
Settings.model_config["env_file"] = None


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "files",
        auto_create_schema=True,
        seed_demo=True,
        auth_mode="dev",
        session_secret="test-session-secret-with-more-than-32-chars",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
