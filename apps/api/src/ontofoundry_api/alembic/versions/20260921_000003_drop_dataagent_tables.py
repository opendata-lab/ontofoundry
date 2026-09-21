"""Remove the DataAgent tables that came with the in-process copy.

OntoFoundry now talks to an external DataAgent over HTTP, so the 15 ``da_*``
tables hold runtime state for a service this database no longer runs.

This is the irreversible step in the migration. ``downgrade`` refuses rather
than pretending: recreating empty tables would leave the old runtime pointed at
a store with no topics, tasks or events, which is worse than a clean failure.
Roll back by restoring the backup taken before deploying.

Revision ID: 20260921_000003
Revises: 20260921_000002
"""

from __future__ import annotations

from alembic import op

revision = "20260921_000003"
down_revision = "20260921_000002"
branch_labels = None
depends_on = None

# Reverse creation order, copied from the baseline's own downgrade rather than
# reconstructed — dropping in creation order would trip over foreign keys.
DATAAGENT_TABLES = (
    "da_mcp_server",
    "da_model_provider",
    "da_agent_widget_event",
    "da_agent_message_schedule_log",
    "da_agent_message_schedule",
    "da_agent_message_queue",
    "da_agent_event_record",
    "da_agent_chunk",
    "da_agent_message",
    "da_agent_task",
    "da_agent_topic",
    "da_agent_profile",
    "da_skill_document_version",
    "da_skill_document",
    "da_agent_settings",
)


def upgrade() -> None:
    for table in DATAAGENT_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "Dropping the da_* tables is irreversible. Restore the database backup "
        "taken before this deployment."
    )
