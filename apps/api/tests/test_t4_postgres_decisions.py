"""T4: decision idempotency and races on real PostgreSQL (opt-in)."""

import threading

import sqlalchemy as sa
from test_modeling import ROOT, create_session
from test_t0_postgres_publish import pytestmark  # noqa: F401 - opt-in marker
from test_t4_proposal_decisions import decide, seed_batch, update

from ontofoundry_api.db_models import ProposalDecisionRequestRecord


def race(calls):
    barrier = threading.Barrier(len(calls))
    results = [None] * len(calls)

    def run(i, fn):
        barrier.wait()
        results[i] = fn()

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def test_concurrent_replays_of_one_request_apply_once(pg_client):
    session = create_session(pg_client)
    target = session["draft"]["object_types"][0]
    (item,) = seed_batch(pg_client, session, [update("object_type", target, description="并发")])["items"]

    results = race([lambda: decide(pg_client, session, [(item["id"], "accept")], key="same-key-0001")] * 3)

    assert [r.status_code for r in results] == [200, 200, 200], [r.text for r in results]
    assert results[0].json() == results[1].json() == results[2].json()
    after = pg_client.get(ROOT + f"/sessions/{session['id']}").json()
    assert after["revision"] == session["revision"] + 1
    with pg_client.app.state.session_factory() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(ProposalDecisionRequestRecord)) == 1


def test_a_serial_replay_after_success_returns_the_first_response(pg_client):
    session = create_session(pg_client)
    target = session["draft"]["object_types"][0]
    (item,) = seed_batch(pg_client, session, [update("object_type", target, description="串行")])["items"]
    first = decide(pg_client, session, [(item["id"], "accept")], key="serial-key-01")
    again = decide(pg_client, session, [(item["id"], "accept")], key="serial-key-01")
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()


def test_two_different_requests_on_one_item_let_one_win(pg_client):
    session = create_session(pg_client)
    target = session["draft"]["object_types"][0]
    (item,) = seed_batch(pg_client, session, [update("object_type", target, description="竞争")])["items"]

    results = race(
        [
            lambda: decide(pg_client, session, [(item["id"], "accept")], key="racer-key-a1"),
            lambda: decide(pg_client, session, [(item["id"], "accept")], key="racer-key-b2"),
        ]
    )

    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    after = pg_client.get(ROOT + f"/sessions/{session['id']}").json()
    assert after["revision"] == session["revision"] + 1


def test_a_three_level_group_is_accepted_atomically_under_a_race(pg_client):
    from test_t4_proposal_decisions import chain

    session = create_session(pg_client)
    po, prop, link = seed_batch(pg_client, session, chain(session))["items"]
    group = [(po["id"], "accept"), (prop["id"], "accept"), (link["id"], "accept")]

    results = race(
        [
            lambda: decide(pg_client, session, group, key="group-key-a1"),
            lambda: decide(pg_client, session, group, key="group-key-b2"),
        ]
    )

    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    draft = pg_client.get(ROOT + f"/sessions/{session['id']}").json()["draft"]
    assert sum(t["technical_name"] == "purchase_order" for t in draft["object_types"]) == 1
    assert sum(p["technical_name"] == "order_no" for p in draft["properties"]) == 1
    assert sum(link["technical_name"] == "supplied_by" for link in draft["link_types"]) == 1
