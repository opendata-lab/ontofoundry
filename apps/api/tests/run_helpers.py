"""Shared helpers for driving a finished DataAgent run through reconcile_run."""

from __future__ import annotations

import asyncio
import json

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.dataagent import DataAgentClient
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.model_result import reconcile_run

RUN_TOKEN = "0123456789abcdef0123456789abcdef"
TASK_ID = "task-model-1"


def row(client, session_id: str) -> ModelingSessionRecord:
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        assert item is not None
        db.expunge(item)
        return item


def install_download(monkeypatch, values) -> list[str]:
    queue = list(values)
    paths: list[str] = []

    async def download(self, topic_id: str, rel_path: str):
        paths.append(rel_path)
        value = queue.pop(0)
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, bytes):
            return value, "application/json"
        return json.dumps(value, ensure_ascii=False).encode(), "application/json"

    monkeypatch.setattr(DataAgentClient, "download", download)
    return paths


def reconcile(client, session_id: str, task_id: str = TASK_ID) -> str:
    return asyncio.run(reconcile_run(client.app, str(DEMO_WORKSPACE_ID), session_id, task_id))
