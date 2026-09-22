"""Translate DataAgent task states into Agent Conversation SDK run states."""

from __future__ import annotations

ACTIVE_RUN_STATUSES = {
    "submitting",
    "queued",
    "running",
    "waiting_input",
    "waiting_permission",
}
TERMINAL_RUN_STATUSES = {"finished", "failed", "cancelled"}

_TASK_TO_RUN_STATUS = {
    "waiting": "queued",
    "running": "running",
    "waiting_input": "waiting_input",
    "waiting_permission": "waiting_permission",
    "finished": "finished",
    "error": "failed",
    "suspended": "cancelled",
}


def to_run_status(task_status: str | None) -> str:
    """Return the SDK run state, treating missing and unknown tasks as failed."""
    return _TASK_TO_RUN_STATUS.get(str(task_status or "").strip().lower(), "failed")
