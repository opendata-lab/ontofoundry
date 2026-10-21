"""Session reads reuse derived parts until the session's revision or draft moves."""

from __future__ import annotations

from sqlalchemy import update
from test_modeling import ROOT, create_session, save

from ontofoundry_api.api import modeling
from ontofoundry_api.db_models import ProposalItemRecord
from ontofoundry_api.services.read_cache import ReadCache, session_reads


def _count(monkeypatch, name: str) -> list[int]:
    calls = [0]
    original = getattr(modeling, name)

    def counted(*args, **kwargs):
        calls[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(modeling, name, counted)
    return calls


def _read(client, session_id: str) -> dict:
    response = client.get(ROOT + "/sessions/" + session_id)
    assert response.status_code == 200, response.text
    return response.json()


def test_repeated_reads_reuse_derived_parts(client, monkeypatch):
    session = create_session(client)
    session_reads.clear()
    views = _count(monkeypatch, "_derived_views")
    diffs = _count(monkeypatch, "element_changes")
    summaries = _count(monkeypatch, "pending_summary")

    first = _read(client, session["id"])
    second = _read(client, session["id"])
    assert second == first
    assert (views[0], diffs[0], summaries[0]) == (1, 1, 1)


def test_a_new_revision_recomputes_every_derived_part(client, monkeypatch):
    session = create_session(client)
    before = _read(client, session["id"])
    views = _count(monkeypatch, "_derived_views")
    diffs = _count(monkeypatch, "element_changes")

    draft = before["draft"]
    target = draft["object_types"][0]
    target["display_name"] = "改名后的实体"
    saved = save(client, before, draft)
    assert saved.status_code == 200, saved.text
    after = _read(client, session["id"])

    assert after["revision"] == before["revision"] + 1
    assert views[0] >= 1 and diffs[0] >= 1
    labels = {node["id"]: node["label"] for node in after["graph"]["nodes"]}
    assert labels[target["id"]] == "改名后的实体"
    assert [change["element_id"] for change in after["base_diff"]] == [target["id"]]
    assert before["base_diff"] == []

    # Unchanged again: served from the cache.
    views[0] = diffs[0] = 0
    assert _read(client, session["id"]) == after
    assert (views[0], diffs[0]) == (0, 0)


def test_a_decision_without_a_draft_change_recomputes_the_summary(client, monkeypatch):
    from run_helpers import install_download, reconcile
    from test_t3_proposal_results import proposals_run, result, some_items

    session, manifest = proposals_run(client)
    install_download(monkeypatch, [result(manifest, some_items(session["draft"]))])
    assert reconcile(client, session["id"]) == "done"
    assert _read(client, session["id"])["pending_proposal_count"] == 3

    # A rejection changes no draft and no revision, only an item's status.
    with client.app.state.session_factory() as db:
        db.execute(
            update(ProposalItemRecord)
            .where(
                ProposalItemRecord.session_id == session["id"],
                ProposalItemRecord.ordinal == 0,
            )
            .values(status="rejected")
        )
        db.commit()
    assert _read(client, session["id"])["pending_proposal_count"] < 3


def test_read_cache_evicts_least_recently_used():
    cache = ReadCache(max_entries=2)
    computed: list[str] = []

    def value(key):
        def compute():
            computed.append(key)
            return key.upper()

        return compute

    assert cache.get("a", value("a")) == "A"
    assert cache.get("b", value("b")) == "B"
    assert cache.get("a", value("a")) == "A"  # a is now the most recent
    assert cache.get("c", value("c")) == "C"  # evicts b
    assert cache.get("a", value("a")) == "A"
    assert cache.get("b", value("b")) == "B"
    assert computed == ["a", "b", "c", "b"]
