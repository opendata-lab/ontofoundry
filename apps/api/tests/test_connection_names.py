"""Connections are shown by name, so one workspace cannot hold two with the same name."""

from contextlib import contextmanager

import sqlalchemy as sa

from ontofoundry_api.api import connections
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"


def test_connection_names_are_unique_ignoring_case_and_spaces(client, monkeypatch):
    engine = sa.create_engine("sqlite://")

    @contextmanager
    def connect(item, settings, *, timeout_ms=None):
        with engine.connect() as conn:
            yield conn

    monkeypatch.setattr(connections, "connect_readonly", connect)
    body = {"kind": "mysql", "host": "fiction.invalid", "port": 3306, "database": "fiction_sales", "username": "reader", "password": ""}
    created = client.post(ROOT + "/connections", json={**body, "name": " 虚构Sales库 "})
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "虚构Sales库"
    for name in ["虚构Sales库", "虚构sales库", "  虚构SALES库"]:
        assert client.post(ROOT + "/connections", json={**body, "name": name}).status_code == 409
