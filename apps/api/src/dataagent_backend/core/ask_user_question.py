"""Durable waiting support for an interactive agent question."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from dataagent_backend.core.task_control import RunnerStoppedError, TaskCancelledError

logger = logging.getLogger(__name__)

async def wait_for_answer(
    task_id: str,
    request_id: str,
    *,
    poll_interval_seconds: float = 1.0,
    cancel_reason: Any = None,
) -> list[dict[str, Any]] | None:
    """Poll PostgreSQL for the user's answer; return the answers list."""
    from dataagent_backend.core.topic_task_store import get_topic_task_store

    store = get_topic_task_store()
    while True:
        reason = await _read_cancel_reason(cancel_reason)
        if reason == "user_cancel":
            raise TaskCancelledError("task cancelled")
        if reason == "runner_stop":
            raise RunnerStoppedError("runner stopped")
        try:
            answers = store.get_resolved_question_answer(task_id=task_id, request_id=request_id)
        except Exception:
            logger.warning(
                "ask_user wait: durable read failed; retrying task_id=%s request_id=%s",
                task_id,
                request_id,
                exc_info=True,
            )
        else:
            if answers is not None:
                return answers
        await asyncio.sleep(max(0.1, float(poll_interval_seconds)))


async def _read_cancel_reason(cancel_reason: Any) -> str | None:
    if cancel_reason is None:
        return None
    try:
        result = cancel_reason()
        if asyncio.iscoroutine(result):
            result = await result
        reason = str(result or "").strip()
        return reason if reason in {"user_cancel", "runner_stop"} else None
    except Exception:
        logger.warning("ask_user wait: cancel_reason check failed; continuing", exc_info=True)
        return None
