"""Existing document instances that share a proposed instance's business identity."""

from __future__ import annotations

from uuid import UUID

from ontofoundry_api.domain.core import CoreDraft, MaterialObject
from ontofoundry_api.domain.graph import read_only_index
from ontofoundry_api.domain.instance_display import business_identity, document_display_text
from ontofoundry_api.services import instance_store


class DuplicateCandidates:
    """Index of existing instances by type and business identity, shared by one batch read.

    Matching each proposal on its own re-validated the draft and re-read every instance,
    so a batch of P new instances against I existing ones cost O(P×I) reads
    (400×400 ≈ 16 s on SQLite). The index is built on first use only.
    """

    def __init__(self, db, workspace_id, session):
        self.db, self.workspace_id, self.session = db, workspace_id, session
        self._index = None

    def _build(self):
        draft = read_only_index(CoreDraft.model_validate(self.session.draft_json))
        by_type: dict[str, list] = {}
        for entry in instance_store.baseline(self.db, self.workspace_id, self.session.id)["items"]:
            if entry["target_kind"] != "material_object":
                continue
            fact = MaterialObject.model_validate(entry["element"])
            identity = business_identity(draft, fact.type_id, fact.values)
            if identity is None:
                continue
            by_type.setdefault(str(fact.type_id), []).append(
                (
                    identity,
                    {
                        "id": str(fact.id),
                        "type_id": str(fact.type_id),
                        "display_text": document_display_text(draft, fact),
                        "expected_target_hash": entry["hash"],
                        "revision": entry["revision"],
                    },
                )
            )
        return draft, by_type

    def __call__(self, item) -> list[dict]:
        if (
            item.target_kind != "material_object"
            or item.operation != "create"
            or item.after_json is None
        ):
            return []
        if self._index is None:
            self._index = self._build()
        draft, by_type = self._index
        fact = item.after_json
        identity = business_identity(draft, UUID(fact["type_id"]), fact["values"])
        if identity is None:
            return []
        return [view for other, view in by_type.get(fact["type_id"], []) if other == identity]
