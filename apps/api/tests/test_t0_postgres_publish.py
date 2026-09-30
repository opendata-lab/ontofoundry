"""T0: concurrent publish on real PostgreSQL, not SQLite.

Opt-in. ONTOFOUNDRY_TEST_POSTGRES_URL must point at a disposable server whose
user may CREATE DATABASE, e.g.

    podman run -d --rm --name of-pg-t0 -e POSTGRES_USER=of -e POSTGRES_PASSWORD=of \
        -e POSTGRES_DB=of_test -p 127.0.0.1:55432:5432 postgres:17-alpine
    ONTOFOUNDRY_TEST_POSTGRES_URL=postgresql+psycopg://of:of@127.0.0.1:55432/of_test

Each test gets its own throwaway database, so row locks and the publish
pointer compare-and-set are exercised by real concurrent transactions.
"""

import os
import threading

import pytest
import sqlalchemy as sa
from test_modeling import ROOT, create_session, publish, save

from ontofoundry_api.db_models import OntologyVersionRecord, WorkspaceRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ADMIN_URL = os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="Disposable PostgreSQL not supplied"
)


def publish_together(client, sessions):
    """Release every publish at the same instant and collect the responses."""
    barrier = threading.Barrier(len(sessions))
    results: list = [None] * len(sessions)

    def run(index, session):
        barrier.wait()
        results[index] = publish(client, session)

    threads = [
        threading.Thread(target=run, args=(i, s)) for i, s in enumerate(sessions)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def published_state(client):
    with client.app.state.session_factory() as db:
        numbers = sorted(
            db.scalars(
                sa.select(OntologyVersionRecord.version_number).where(
                    OntologyVersionRecord.workspace_id == str(DEMO_WORKSPACE_ID)
                )
            ).all()
        )
        current = db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID)).current_version_id
        current_number = db.get(OntologyVersionRecord, current).version_number
    return numbers, current_number


def test_concurrent_publishes_of_independent_changes_both_land_in_order(pg_client):
    a, b = create_session(pg_client), create_session(pg_client)
    a["draft"]["object_types"][0]["description"] = "A 并发修改"
    b["draft"]["object_types"][1]["description"] = "B 并发修改"
    a = save(pg_client, a, a["draft"]).json()
    b = save(pg_client, b, b["draft"]).json()

    results = publish_together(pg_client, [a, b])

    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    numbers, current = published_state(pg_client)
    # No duplicate version numbers, no gap, pointer on the newest version.
    assert numbers == [1, 2, 3]
    assert current == 3
    assert sorted(r.json()["version"]["version"] for r in results) == [2, 3]
    snapshot = pg_client.get(ROOT + "/published-snapshot").json()
    assert {"A 并发修改", "B 并发修改"} <= {
        t["description"] for t in snapshot["object_types"]
    }


def test_concurrent_publishes_of_the_same_field_let_exactly_one_win(pg_client):
    a, b = create_session(pg_client), create_session(pg_client)
    a["draft"]["object_types"][0]["description"] = "A 的值"
    b["draft"]["object_types"][0]["description"] = "B 的值"
    a = save(pg_client, a, a["draft"]).json()
    b = save(pg_client, b, b["draft"]).json()

    results = publish_together(pg_client, [a, b])

    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409], [r.text for r in results]
    winner = next(r for r in results if r.status_code == 200).json()
    numbers, current = published_state(pg_client)
    # The loser leaves no orphan version and the pointer is the winner's.
    assert numbers == [1, 2]
    assert current == 2 == winner["version"]["version"]
    snapshot = pg_client.get(ROOT + "/published-snapshot").json()
    winner_value = next(
        t["description"]
        for t in winner["session"]["draft"]["object_types"]
        if t["id"] == a["draft"]["object_types"][0]["id"]
    )
    assert winner_value in {t["description"] for t in snapshot["object_types"]}
