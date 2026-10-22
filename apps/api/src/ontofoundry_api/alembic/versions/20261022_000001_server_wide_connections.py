"""MySQL and Doris connections reach the whole server; re-collect synced tables.

Historical snapshots may contain tables recorded under the wrong library,
so every recorded structure is discarded and synced again. The
source databases are untouched; datasets keep their bindings and show
"表未同步" until their tables are synced again.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "20261022_000001"
down_revision = "20261020_000002"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM metadata_sync_batches"))
    bind.execute(sa.text("DELETE FROM metadata_sync_jobs"))
    bind.execute(sa.text("DELETE FROM metadata_snapshots"))
    rows = bind.execute(sa.text("SELECT id, config_json FROM data_connections WHERE kind IN ('mysql', 'doris')")).all()
    for identity, config in rows:
        value = json.loads(config) if isinstance(config, str) else dict(config or {})
        value["database"] = ""
        # PostgreSQL needs an explicit JSON cast; SQLite stores the text as is.
        target = "CAST(:config AS json)" if bind.dialect.name == "postgresql" else ":config"
        bind.execute(
            sa.text(f"UPDATE data_connections SET config_json = {target} WHERE id = :id"),
            {"config": json.dumps(value, ensure_ascii=False), "id": identity},
        )


def downgrade():
    # Discarded structures are re-collected by syncing; nothing to restore.
    pass
