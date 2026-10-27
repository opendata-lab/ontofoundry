"""Session reads converge a run that no conversation view is watching."""

from __future__ import annotations

from functools import partial

import httpx
import pytest
from run_helpers import TASK_ID, install_download, row
from sqlalchemy import update
from test_modeling import ROOT
from test_t3_proposal_results import proposals_run, result, some_items, stored

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services import modeling_runs


@pytest.fixture(autouse=True)
def _fresh_throttle():
    modeling_runs._last_sync.clear()
    yield
    modeling_runs._last_sync.clear()


def _configure(client) -> None:
    client.app.state.settings.dataagent_base_url = "https://dataagent.example"
    client.app.state.settings.dataagent_access_key = "server-secret"


def _set(client, session_id: str, **values) -> None:
    with client.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session_id)
            .values(**values)
        )
        db.commit()


def _upstream(monkeypatch, statuses: list[str]) -> list[str]:
    """DataAgent reports each status in turn; returns the task paths asked."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tasks/" + TASK_ID):
            asked.append(request.url.path)
            status = statuses[min(len(asked), len(statuses)) - 1]
            return httpx.Response(200, json={"task_id": TASK_ID, "task_status": status})
        raise AssertionError(request.url.path)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )
    return asked


def _queued_run(client):
    session, manifest = proposals_run(client)
    _set(client, session["id"], task_status="queued", task_detail="等待 DataAgent 调度")
    return session, manifest


def test_detail_read_projects_a_finished_run_and_claims_its_batch(client, monkeypatch):
    _configure(client)
    session, manifest = _queued_run(client)
    asked = _upstream(monkeypatch, ["finished"])
    paths = install_download(monkeypatch, [result(manifest, some_items(session["draft"]))])

    # A detail read settles the finished run first, so the page that reads it
    # when the conversation ends sees the new proposals.
    first = client.get(ROOT + "/sessions/" + session["id"])
    assert first.status_code == 200, first.text
    assert first.json()["task_status"] == "finished"
    assert first.json()["pending_proposal_count"] == 3
    assert len(asked) == 1 and len(paths) == 1

    current = row(client, session["id"])
    assert current.task_status == "finished"
    assert current.result_state == "done"
    batches, items, _ = stored(client, session["id"])
    assert len(batches) == 1 and len(items) == 3

    # Idempotent: a claimed run is neither asked about nor downloaded again.
    modeling_runs._last_sync.clear()
    second = client.get(ROOT + "/sessions/" + session["id"]).json()
    assert second["task_status"] == "finished"
    assert second["pending_proposal_count"] == 3
    assert len(asked) == 1 and len(paths) == 1
    assert len(stored(client, session["id"])[0]) == 1


def test_list_read_syncs_a_live_run_without_claiming_anything(client, monkeypatch):
    _configure(client)
    session, _ = _queued_run(client)
    asked = _upstream(monkeypatch, ["running"])
    paths = install_download(monkeypatch, [])

    response = client.get(ROOT + "/sessions")
    assert response.status_code == 200, response.text
    assert len(asked) == 1 and paths == []
    current = row(client, session["id"])
    assert current.task_status == "running"
    assert current.task_detail == "DataAgent 正在处理"


def test_list_reads_are_throttled_per_session(client, monkeypatch):
    _configure(client)
    _queued_run(client)
    asked = _upstream(monkeypatch, ["running"])

    for _ in range(3):
        assert client.get(ROOT + "/sessions").status_code == 200
    assert len(asked) == 1


def test_a_finished_but_unclaimed_run_is_claimed_without_asking_dataagent(
    client, monkeypatch
):
    _configure(client)
    session, manifest = proposals_run(client)  # finished, result never claimed
    asked = _upstream(monkeypatch, [])
    paths = install_download(monkeypatch, [result(manifest, some_items(session["draft"]))])

    client.get(ROOT + "/sessions/" + session["id"])
    assert asked == [] and len(paths) == 1
    assert row(client, session["id"]).result_state == "done"


def test_idle_or_unconfigured_sessions_never_call_dataagent(client, monkeypatch):
    session, _ = _queued_run(client)
    asked = _upstream(monkeypatch, ["finished"])

    # DataAgent not configured: nothing to sync against.
    client.get(ROOT + "/sessions/" + session["id"])
    client.get(ROOT + "/sessions")
    assert asked == []

    # A cancelled run is terminal and has no result to claim.
    _configure(client)
    _set(client, session["id"], task_status="cancelled")
    client.get(ROOT + "/sessions/" + session["id"])
    assert asked == []
    assert row(client, session["id"]).task_status == "cancelled"


def test_a_newer_run_is_never_overwritten_by_a_slow_sync(client, monkeypatch):
    _configure(client)
    session, _ = _queued_run(client)

    def handler(request: httpx.Request) -> httpx.Response:
        # A new turn takes the session while DataAgent answers for the old task.
        _set(
            client,
            session["id"],
            dataagent_task_id="task-new",
            task_status="running",
            task_detail="new",
        )
        return httpx.Response(200, json={"task_id": TASK_ID, "task_status": "finished"})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )
    paths = install_download(monkeypatch, [])
    client.get(ROOT + "/sessions/" + session["id"])
    current = row(client, session["id"])
    assert (current.dataagent_task_id, current.task_status, current.task_detail) == (
        "task-new",
        "running",
        "new",
    )
    assert paths == []
