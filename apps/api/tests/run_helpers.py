"""Shared helpers for driving a finished DataAgent run through reconcile_run."""

from __future__ import annotations

import asyncio
import json
import sys

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
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


_SUBMISSIONS: list = []


def install_download(monkeypatch, values) -> list[str]:
    """Queue what the agent hands in. Since SC-05 the merge script submits the
    result during the run; `reconcile` replays that submission first. An
    exception stands for a run that submitted nothing."""
    queue = list(values)
    # Through monkeypatch, so a queue never leaks into the next test.
    monkeypatch.setattr(sys.modules[__name__], "_SUBMISSIONS", list(values))
    paths: list[str] = []

    async def download(self, topic_id: str, rel_path: str):
        paths.append(rel_path)
        # Legacy cases have no intermediate artifacts in the agent workspace.
        if rel_path.startswith("modeling/"):
            raise DataAgentError("missing workflow file", status_code=404)
        value = queue.pop(0)
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, bytes):
            return value, "application/json"
        return json.dumps(value, ensure_ascii=False).encode(), "application/json"

    monkeypatch.setattr(DataAgentClient, "download", download)
    return paths


def submit(client, session_id: str, value):
    """Submit `value` as the running agent would, keeping the task status."""
    from ontofoundry_api.services.proposal_submit import submit_result

    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        status, workspace_id, run_token = item.task_status, item.workspace_id, item.dataagent_run_token
        item.task_status = "running"
        db.commit()
        report = submit_result(db, client.app.state.settings, workspace_id, session_id, run_token, raw)
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session_id).task_status = status
        db.commit()
    return report


def reconcile(client, session_id: str, task_id: str = TASK_ID) -> str:
    pending = sys.modules[__name__]._SUBMISSIONS
    while pending:
        value = pending.pop(0)
        if not isinstance(value, BaseException):
            submit(client, session_id, value)
            break
    return asyncio.run(
        reconcile_run(client.app, str(DEMO_WORKSPACE_ID), session_id, task_id)
    )
