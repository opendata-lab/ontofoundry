"""Delete one workspace and everything under it from the platform database.

Demo preparation only: the product has no workspace deletion. Children are
removed before parents, following the ORM's foreign keys, in one transaction.

    cd apps/api && uv run --python 3.13 python \
        ../../docs/demo/coffee-channel-sales/scripts/purge_workspace.py <slug>
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, delete, select

from ontofoundry_api.db_models import Base, WorkspaceRecord


def purge(url: str, slug: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        workspace_id = conn.scalar(select(WorkspaceRecord.id).where(WorkspaceRecord.slug == slug))
        if workspace_id is None:
            print("没有这个空间:", slug)
            return
        tables = Base.metadata.sorted_tables
        owned = {t.name for t in tables if "workspace_id" in t.c}
        for table in reversed(tables):
            if table.name == "workspaces":
                continue
            if "workspace_id" in table.c:
                result = conn.execute(delete(table).where(table.c.workspace_id == workspace_id))
            else:
                # Rows reachable only through a workspace-owned parent.
                links = [
                    (fk.parent, fk.column.table)
                    for fk in table.foreign_keys
                    if fk.column.table.name in owned
                ]
                if not links:
                    continue
                column, parent = links[0]
                result = conn.execute(delete(table).where(column.in_(
                    select(parent.c.id).where(parent.c.workspace_id == workspace_id))))
            if result.rowcount:
                print(f"  {table.name}: {result.rowcount}")
        conn.execute(delete(WorkspaceRecord.__table__).where(WorkspaceRecord.id == workspace_id))
        print("已删除空间", slug)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    purge(os.environ["ONTOFOUNDRY_DATABASE_URL"], sys.argv[1])
