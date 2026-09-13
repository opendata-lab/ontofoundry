"""Producer identity survives persistence.

The writer declared it stored NeutralAgentEvents but kept only the payload.
Without event_id, run_id, sequence and the engine timestamp a stored record
cannot be deduplicated, ordered against its producer, or attributed to an engine
— all of which history replay needs once the second projection is removed.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.agent_event_writer import AgentEventWriter  # noqa: E402


class _CapturingStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append_agent_record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _event(**overrides: Any) -> dict[str, Any]:
    base = {
        "event_id": "evt-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "task_attempt_id": "attempt-1",
        "sequence": 1,
        "timestamp": "2026-09-10T12:00:00Z",
        "type": "turn.started",
        "payload": {"turn_id": "turn-1"},
    }
    base.update(overrides)
    return base


def test_the_envelope_is_persisted_not_discarded():
    store = _CapturingStore()
    AgentEventWriter(store, "task-1", "topic-1").ingest(_event())

    env = store.records[0]["envelope"]
    assert env["contract_version"] == 1
    assert env["engine_kind"] == "pi_agent_core"
    assert env["event_id"] == "evt-1"
    assert env["run_id"] == "run-1"
    assert env["task_attempt_id"] == "attempt-1"
    assert env["engine_sequence"] == 1
    assert isinstance(env["occurred_at"], datetime)


def test_records_are_written_as_agent_event():
    store = _CapturingStore()
    AgentEventWriter(store, "task-1", "topic-1").ingest(_event())
    assert store.records[0]["record_type"] == "agent_event"


def test_a_malformed_timestamp_does_not_cost_the_record():
    """Ordering can fall back to created_at; losing the event cannot be undone."""
    store = _CapturingStore()
    AgentEventWriter(store, "task-1", "topic-1").ingest(_event(timestamp="not-a-time"))

    assert len(store.records) == 1
    assert store.records[0]["envelope"]["occurred_at"] is None


def test_a_missing_envelope_field_is_stored_as_null_not_empty_string():
    """NULL is what marks a field absent; '' would look like a real value."""
    store = _CapturingStore()
    AgentEventWriter(store, "task-1", "topic-1").ingest(_event(event_id="", run_id=""))

    env = store.records[0]["envelope"]
    assert env["event_id"] is None
    assert env["run_id"] is None
