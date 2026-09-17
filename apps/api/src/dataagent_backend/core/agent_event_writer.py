"""Persist platform AgentEvents emitted by the Pi execution engine.

Pi is an implementation detail. The durable and streamed protocol is the
engine-neutral ``record_type="agent_event"`` envelope.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _parse_occurred_at(value: Any) -> Any:
    """Producer timestamp as a datetime, or None if it is not usable.

    A malformed timestamp must not cost us the record: ordering falls back to
    the row's own created_at, which is close enough for display.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

class AgentEventWriter:
    """Writes neutral platform AgentEvents into the durable event store."""

    def __init__(self, store: Any, task_id: str, topic_id: str) -> None:
        self._store = store
        self._task_id = task_id
        self._topic_id = topic_id
        self._turn_index = 0
        self._highest_sequence = 0

    @property
    def turn_index(self) -> int:
        return self._turn_index

    def ingest(self, event: dict[str, Any]) -> None:
        """Persist one neutral AgentEvent.

        Never raises: a malformed event from the child must not abort the run.
        Out-of-order and replayed events are dropped by sequence, mirroring the
        monotonic guarantee the Cell's run state machine provides.
        """
        try:
            self._ingest_safe(event)
        except Exception:
            logger.exception(
                "agent_event.ingest_failed task_id=%s event_type=%s",
                self._task_id,
                (event or {}).get("type"),
            )

    def _ingest_safe(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        event_type = str(event.get("type") or "").strip()
        if not event_type:
            return

        sequence = event.get("sequence")
        if isinstance(sequence, int):
            if sequence <= self._highest_sequence:
                logger.warning(
                    "agent_event.out_of_order task_id=%s sequence=%s highest=%s",
                    self._task_id,
                    sequence,
                    self._highest_sequence,
                )
                return
            self._highest_sequence = sequence

        # A new turn starts a fresh block group for history projection.
        if event_type == "turn.started":
            self._turn_index += 1

        # A malformed payload must not cost us the event itself: the type and
        # sequence still carry information the projection and the terminal
        # handling need, so coerce rather than drop.
        raw_payload = event.get("payload")
        payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
        # Preserve producer identity so stored records can be deduplicated and
        # ordered independently of database insertion time.
        self._store.append_agent_record(
            task_id=self._task_id,
            topic_id=self._topic_id,
            turn_index=self._turn_index,
            record_type="agent_event",
            event_type=event_type,
            data=payload,
            envelope={
                "contract_version": 1,
                "engine_kind": "pi_agent_core",
                "event_id": str(event.get("event_id") or "") or None,
                "run_id": str(event.get("run_id") or "") or None,
                "task_attempt_id": str(event.get("task_attempt_id") or "") or None,
                "engine_sequence": sequence if isinstance(sequence, int) else None,
                "occurred_at": _parse_occurred_at(event.get("timestamp")),
            },
        )

        if event_type == "run.failed":
            self.append_error(
                code=str(payload.get("error_code") or "pi_runtime_error"),
                message=str(payload.get("message") or "Pi 运行时执行失败"),
                detail=str(payload.get("detail") or ""),
            )

    def append_error(self, *, code: str = "pi_runtime_error", message: str = "请求失败", detail: str = "") -> None:
        """Emit a terminal error record."""
        payload: dict[str, Any] = {
            "code": str(code or "pi_runtime_error"),
            "message": str(message or "请求失败"),
        }
        if detail:
            payload["detail"] = str(detail)
        self._store.append_agent_record(
            task_id=self._task_id,
            topic_id=self._topic_id,
            turn_index=self._turn_index,
            record_type="error",
            event_type=None,
            data=payload,
        )
