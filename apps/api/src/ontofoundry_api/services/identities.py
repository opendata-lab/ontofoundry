"""The element identity registry (design §4.2).

An element id is minted once as one kind and never reused as another, even
after the element is deleted. Publishing records every id in the new head,
retires ids that left it and revives ids that came back.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.db_models import OntologyElementIdentityRecord
from ontofoundry_api.domain.models import COLLECTIONS

from .errors import ConflictError


def element_kinds(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        str(element["id"]): kind.value
        for kind, collection in COLLECTIONS.items()
        for element in snapshot.get(collection) or []
    }


def check_identities(db: Session, workspace_id: str, kinds: dict[str, str]) -> None:
    """Refuse an id already registered as a different kind."""
    if not kinds:
        return
    clashes = db.scalars(
        select(OntologyElementIdentityRecord).where(
            OntologyElementIdentityRecord.workspace_id == workspace_id,
            OntologyElementIdentityRecord.element_id.in_(list(kinds)),
        )
    ).all()
    wrong = [row for row in clashes if row.kind != kinds[row.element_id]]
    if wrong:
        row = wrong[0]
        raise ConflictError(
            f"元素 {row.element_id} 已登记为 {row.kind}，不能作为 {kinds[row.element_id]} 使用",
            code="ELEMENT_KIND_CONFLICT",
            details={"element_ids": [r.element_id for r in wrong]},
        )


def sync_identities(
    db: Session,
    workspace_id: str,
    snapshot: dict[str, Any],
    *,
    user_id: str | None,
    now: datetime,
) -> None:
    kinds = element_kinds(snapshot)
    check_identities(db, workspace_id, kinds)
    rows = {
        row.element_id: row
        for row in db.scalars(
            select(OntologyElementIdentityRecord).where(
                OntologyElementIdentityRecord.workspace_id == workspace_id
            )
        )
    }
    for element_id, kind in kinds.items():
        row = rows.get(element_id)
        if row is None:
            db.add(
                OntologyElementIdentityRecord(
                    workspace_id=workspace_id,
                    element_id=element_id,
                    kind=kind,
                    created_at=now,
                    created_by=user_id,
                )
            )
        elif row.retired_at is not None:
            row.retired_at = None
    for element_id, row in rows.items():
        if element_id not in kinds and row.retired_at is None:
            row.retired_at = now
