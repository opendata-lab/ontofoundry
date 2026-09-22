import pytest

from ontofoundry_api.services.run_status import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    to_run_status,
)


@pytest.mark.parametrize(
    ("task_status", "expected"),
    [
        ("waiting", "queued"),
        ("running", "running"),
        ("waiting_input", "waiting_input"),
        ("waiting_permission", "waiting_permission"),
        ("finished", "finished"),
        ("error", "failed"),
        ("suspended", "cancelled"),
        ("unknown", "failed"),
        (None, "failed"),
    ],
)
def test_to_run_status(task_status, expected):
    assert to_run_status(task_status) == expected


def test_run_status_sets_cover_all_local_lifecycle_states():
    assert {
        "submitting",
        "queued",
        "running",
        "waiting_input",
        "waiting_permission",
    } == ACTIVE_RUN_STATUSES
    assert {"finished", "failed", "cancelled"} == TERMINAL_RUN_STATUSES
    assert ACTIVE_RUN_STATUSES.isdisjoint(TERMINAL_RUN_STATUSES)
