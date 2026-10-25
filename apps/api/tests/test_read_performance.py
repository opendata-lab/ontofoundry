"""Immutable reads coalesce work and reauthorize HTTP validators."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from test_api import ONTOLOGY
from test_modeling import ROOT

from ontofoundry_api.services.read_cache import ReadCache, published_reads


@pytest.mark.parametrize("fail", [False, True])
def test_parallel_miss_has_one_computation_and_failure_is_retryable(fail):
    cache = ReadCache(8)
    barrier, entered, finish = Barrier(10), Event(), Event()
    calls = []

    def compute():
        calls.append(1)
        entered.set()
        assert finish.wait(5)
        if fail:
            raise ValueError("failure")
        return {"value": [1, 2, 3]}

    def read():
        barrier.wait()
        return cache.get("version", compute)

    with ThreadPoolExecutor(10) as pool:
        futures = [pool.submit(read) for _ in range(10)]
        assert entered.wait(5)
        # The barrier puts every caller inside get before the owner is released.
        import time

        deadline = time.monotonic() + 5
        while cache.stats().get("coalesced", 0) < 9 and time.monotonic() < deadline:
            Event().wait(0.001)
        finish.set()
        for future in futures:
            if fail:
                with pytest.raises(ValueError):
                    future.result()
            else:
                assert future.result() == {"value": [1, 2, 3]}
    assert len(calls) == 1
    assert cache.stats()["coalesced"] == 9
    if fail:
        assert cache.get("version", lambda: 42) == 42


def test_byte_budget_and_clear_do_not_retain_late_results():
    cache = ReadCache(2, max_bytes=100)
    assert cache.get("large", lambda: "x" * 1000).startswith("x")
    assert cache.stats()["entries"] == 0

    def clear_during_compute():
        cache.clear()
        return "late"

    assert cache.get("late", clear_during_compute) == "late"
    assert cache.stats()["entries"] == 0


def test_warm_version_skips_normalization_and_building_indexes(client, monkeypatch):
    from ontofoundry_api.services import ontology_query as query

    published_reads.clear()
    response = client.get(ONTOLOGY + "/version")
    assert response.status_code == 200

    def forbidden(*args, **kwargs):
        raise AssertionError("warm read rebuilt immutable context")

    monkeypatch.setattr(query, "read_snapshot", forbidden)
    monkeypatch.setattr(query, "DraftIndex", forbidden)
    assert client.get(ONTOLOGY + "/version").json() == response.json()
    assert (
        client.get(
            ROOT + "/versions/" + response.json()["version_id"] + "/presentation"
        ).status_code
        == 200
    )


def test_etag_lists_weak_comparison_empty_body_and_version_membership(client, monkeypatch):
    from ontofoundry_api.services import public_projection

    version_id = client.get(ONTOLOGY + "/version").json()["version_id"]
    path = ROOT + "/versions/" + version_id + "/presentation"
    response = client.get(path)
    assert response.status_code == 200
    tag = response.headers["etag"]
    assert response.headers["cache-control"] == "private, no-cache"

    def forbidden(*args, **kwargs):
        raise AssertionError("304 projected the full snapshot")

    monkeypatch.setattr(public_projection, "authorized_snapshot", forbidden)
    for header in [tag, '"other", ' + tag.removeprefix("W/"), "*"]:
        hit = client.get(path, headers={"If-None-Match": header})
        assert hit.status_code == 304
        assert hit.content == b""
        assert hit.headers["etag"] == tag
    assert (
        client.get(
            ROOT + "/versions/00000000-0000-0000-0000-000000000000/presentation",
            headers={"If-None-Match": "*"},
        ).status_code
        == 404
    )


def test_validator_never_bypasses_authentication_or_permission_changes(client, monkeypatch):
    from ontofoundry_api.services import access

    version_id = client.get(ONTOLOGY + "/version").json()["version_id"]
    path = ROOT + "/versions/" + version_id + "/presentation"
    first = client.get(path)
    denied = client.get(
        path,
        headers={"If-None-Match": first.headers["etag"], "Authorization": "Bearer invalid"},
    )
    assert denied.status_code == 401
    monkeypatch.setattr(
        access, "authorization_fingerprint", lambda *args: "changed-permission"
    )
    monkeypatch.setattr(access, "can_read_mappings", lambda *args: False)
    changed = client.get(path, headers={"If-None-Match": first.headers["etag"]})
    assert changed.status_code == 200
    assert changed.headers["etag"] != first.headers["etag"]
    assert changed.json()["model"]["mappings"] == []


def test_304_reads_metadata_without_loading_snapshot_or_validation(client):
    from sqlalchemy import event

    path = ONTOLOGY + "/version"
    first = client.get(path)
    statements = []

    def capture(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(client.app.state.engine, "before_cursor_execute", capture)
    try:
        hit = client.get(path, headers={"If-None-Match": first.headers["etag"]})
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", capture)
    assert hit.status_code == 304
    assert not any("snapshot_json" in sql or "validation_json" in sql for sql in statements)


def test_warm_instance_reads_reuse_the_current_definition(client, monkeypatch):
    from ontofoundry_api.domain.models import OntologyDraft

    assert client.get(ONTOLOGY + "/version").status_code == 200

    def forbidden(*args, **kwargs):
        raise AssertionError("warm instance read revalidated immutable definitions")

    monkeypatch.setattr(OntologyDraft, "model_validate", forbidden)
    response = client.get(ONTOLOGY + "/objects", params={"source": "document"})
    assert response.status_code == 200, response.text
