import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

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


ADMIN_URL = os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL")


@pytest.fixture
def pg_client(tmp_path) -> Iterator[TestClient]:
    """A client on a throwaway PostgreSQL database (needs ONTOFOUNDRY_TEST_POSTGRES_URL)."""
    if not ADMIN_URL:
        pytest.skip("Disposable PostgreSQL not supplied")
    name = "of_t0_" + uuid4().hex[:12]
    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    settings = Settings(
        environment="test",
        database_url=make_url(ADMIN_URL).set(database=name).render_as_string(
            hide_password=False
        ),
        data_dir=tmp_path / "files",
        auto_create_schema=True,
        seed_demo=True,
        auth_mode="dev",
        session_secret="test-session-secret-with-more-than-32-chars",
    )
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.state.engine.dispose()
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


