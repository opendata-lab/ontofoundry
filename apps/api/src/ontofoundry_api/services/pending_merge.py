"""Merge an agent's submission with the session's pending proposals (AI-08, design §4.7).

The run was pinned to the draft with the pending proposals applied, so the agent's
items are relative to that candidate. Merged with the pending items they become one
set relative to the real draft, checked again and stored as the one pending batch;
the old pending items are superseded.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid5

from sqlalchemy import select

from ontofoundry_api.contracts.proposals import ParsedBatch, ParsedItem
from ontofoundry_api.db_models import ProposalItemRecord


def pending_items(db, session) -> list[ProposalItemRecord]:
    return list(db.scalars(select(ProposalItemRecord).where(
        ProposalItemRecord.workspace_id == session.workspace_id,
        ProposalItemRecord.session_id == session.id,
        ProposalItemRecord.status == "pending",
    ).order_by(ProposalItemRecord.created_at, ProposalItemRecord.ordinal)))


def _carried(batch_id: str, row: ProposalItemRecord) -> ParsedItem:
    """A pending item the agent did not mention, carried into the new batch as is."""
    return ParsedItem(
        id=str(uuid5(UUID(batch_id), f"carried:{row.id}")), ordinal=0, client_ref=row.client_ref,
        operation=row.operation, target_kind=row.target_kind, target_id=row.target_id,
        expected_target_hash=row.expected_target_hash, before=row.before_json, after=row.after_json,
        field_changes=row.field_changes_json or [], evidence=row.evidence_json or [],
        reason=row.reason or "", fingerprint=row.fingerprint or "",
        expected_instance_revision=row.expected_instance_revision,
    )


def _combine(pending: ProposalItemRecord, item: ParsedItem) -> ParsedItem | None:
    """The agent's change on top of a pending one, as one change to the real draft."""
    if pending.operation == "create":
        if item.operation == "delete":
            return None  # proposed and withdrawn: nothing to review
        return replace(item, operation="create", before=None, expected_target_hash=None,
                       expected_instance_revision=None)
    # The real draft still has the element as it was before the pending change.
    operation = "delete" if item.operation == "delete" else "update"
    return replace(
        item, operation=operation, before=pending.before_json,
        expected_target_hash=pending.expected_target_hash,
        expected_instance_revision=pending.expected_instance_revision,
    )


def instance_overlay(baseline: dict, pending: list[ProposalItemRecord], session_id: str) -> dict:
    """The run's instance baseline with the pending instance proposals applied, as
    the pinned draft has the pending definitions applied: the agent can revise them."""
    from copy import deepcopy

    from ontofoundry_api.domain.instances import INSTANCE_KINDS, instance_hash

    out = deepcopy(baseline)
    entries = {e["target_id"]: e for e in out.get("items", [])}
    for row in pending:
        if row.target_kind not in INSTANCE_KINDS:
            continue
        if row.after_json is None:
            entries.pop(row.target_id, None)
            continue
        element = {**row.after_json, "id": row.target_id}
        entry = entries.get(row.target_id)
        revision = entry["revision"] if entry else 1
        entries[row.target_id] = {
            "target_kind": row.target_kind, "target_id": row.target_id, "revision": revision,
            "state": entry["state"] if entry else "staged", "session_id": entry["session_id"] if entry else session_id,
            "element": element, "hash": instance_hash(element, revision),
        }
    out["items"] = list(entries.values())
    return out


def merge(
    parsed: ParsedBatch, pending: list[ProposalItemRecord], *, import_batch_id: str | None = None,
) -> tuple[ParsedBatch, dict[str, str]]:
    """The merged batch and, for each pending item, what became of it ("revised",
    "withdrawn" or "carried")."""
    by_target = {(p.target_kind, p.target_id): p for p in pending}
    fate: dict[str, str] = {}
    items: list[ParsedItem] = []
    for item in parsed.items:
        earlier = by_target.pop((item.target_kind, item.target_id), None)
        if earlier is None:
            items.append(item)
            continue
        combined = _combine(earlier, item)
        fate[earlier.id] = "withdrawn" if combined is None else "revised"
        if combined is not None:
            if earlier.batch_id == import_batch_id:
                references = [{k: v for k, v in entry.items() if k != "id"} for entry in combined.evidence]
                combined.evidence = [
                    *combined.evidence,
                    *(entry for entry in earlier.evidence_json or []
                      if {k: v for k, v in entry.items() if k != "id"} not in references),
                ]
            items.append(combined)
    for row in by_target.values():
        fate[row.id] = "carried"
        items.append(_carried(parsed.id, row))
    # Dependencies and atomic groups are recomputed by the check on the merged set.
    items = [replace(item, ordinal=index, depends_on=[], atomic_group_id=None) for index, item in enumerate(items)]
    return ParsedBatch(parsed.id, parsed.result_sha256, items), fate
