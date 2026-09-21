from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ontofoundry_api.config import Settings
from ontofoundry_api.main import create_app


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
