"""Evidence integrity, shared by proposal parsing and draft saves.

Material evidence must point at a stored material of the same workspace, carry
its content hash, and quote text that is really on the cited lines. Manual
evidence is a member vouching for a fact: its author and time are written by
the server, entries are immutable once saved, and only their author may remove
them from an element that still exists.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ontofoundry_api.domain.canonical import canonical
from ontofoundry_api.domain.models import COLLECTIONS

MaterialLookup = Callable[[str], tuple[str, list[str]] | None]
"""material_id -> (sha256, text lines) within one workspace, or None."""


class EvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def check_material_evidence(evidence: dict, lookup: MaterialLookup, where: str) -> None:
    found = lookup(str(evidence["material_id"]))
    if found is None:
        raise EvidenceError("EVIDENCE_INVALID", f"{where}：材料 {evidence['material_id']} 不属于当前空间")
    sha, lines = found
    if evidence.get("material_sha256") != sha:
        raise EvidenceError("EVIDENCE_INVALID", f"{where}：材料哈希缺失或与已保存的材料不一致")
    start, end = evidence["locator"]["line_start"], evidence["locator"]["line_end"]
    if end > len(lines):
        raise EvidenceError("EVIDENCE_INVALID", f"{where}：证据行号超出材料范围")
    quote = " ".join((evidence.get("quote") or "").split())
    window = " ".join(" ".join(lines[start - 1 : end]).split())
    if quote and quote not in window:
        raise EvidenceError("EVIDENCE_INVALID", f"{where}：引用原文与材料第 {start}–{end} 行不符")


def _evidence_by_element(draft: dict[str, Any]) -> dict[str, dict[str, dict]]:
    return {
        str(element["id"]): {str(e["id"]): e for e in element.get("evidence") or []}
        for collection in COLLECTIONS.values()
        for element in draft.get(collection) or []
    }


def reconcile_draft_evidence(
    previous: dict[str, Any],
    draft: dict[str, Any],
    *,
    lookup: MaterialLookup,
    actor_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Check a draft about to be saved against the stored one; stamp new
    manual evidence with the author and time. Returns the draft to store."""
    before = _evidence_by_element(previous)
    for collection in COLLECTIONS.values():
        for element in draft.get(collection) or []:
            element_id = str(element["id"])
            old = before.get(element_id, {})
            kept_ids = set()
            for position, evidence in enumerate(element.get("evidence") or []):
                evidence_id = str(evidence["id"])
                kept_ids.add(evidence_id)
                where = f"{collection}[{element_id}].evidence[{position}]"
                unchanged = evidence_id in old and canonical(old[evidence_id]) == canonical(evidence)
                if evidence.get("kind") == "manual":
                    if evidence_id in old:
                        if not unchanged:
                            raise EvidenceError("MANUAL_EVIDENCE_IMMUTABLE", f"{where}：人工证据保存后不能修改")
                        continue
                    evidence["created_by"] = actor_id
                    evidence["created_at"] = now.isoformat()
                    continue
                if not unchanged:
                    check_material_evidence(evidence, lookup, where)
            for evidence_id, evidence in old.items():
                if (
                    evidence_id not in kept_ids
                    and evidence.get("kind") == "manual"
                    and evidence.get("created_by") != actor_id
                ):
                    raise EvidenceError(
                        "MANUAL_EVIDENCE_IMMUTABLE",
                        f"{collection}[{element_id}]：不能删除他人录入的人工证据",
                    )
    return draft
