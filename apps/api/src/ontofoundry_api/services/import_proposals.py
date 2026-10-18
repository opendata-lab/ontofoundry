"""Build trusted import batches without relaxing the agent result contract."""

from uuid import UUID, uuid5

from ontofoundry_api.contracts.proposals import (
    ParsedBatch,
    ParsedItem,
    group_items,
    item_fingerprint,
)
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.evidence import check_material_evidence
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.services.element_diff import field_changes
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.import_integrity import payload_sha256


def _build_import_batch(base, changes, *, batch_id, lookup, evidence_by_target=None):
    base = CoreDraft.model_validate(base).model_dump(mode="json")
    items = []
    for index, change in enumerate(changes):
        collection = COLLECTIONS[ElementKind(change["target_kind"])]
        after, before = change["after"], change["before"]
        for evidence in after.get("evidence", []):
            if evidence["kind"] == "material":
                check_material_evidence(evidence, lookup, "导入证据")
        evidence = (evidence_by_target or {}).get(change["target_id"], [])
        for entry in evidence:
            check_material_evidence(entry, lookup, "文件来源")
        items.append(
            ParsedItem(
                id=str(uuid5(UUID(batch_id), change["target_id"])),
                ordinal=index,
                client_ref=None,
                operation=change["operation"],
                target_kind=change["target_kind"],
                target_id=change["target_id"],
                expected_target_hash=element_sha256(before, collection=collection)
                if before
                else None,
                before=before,
                after=after,
                field_changes=field_changes(before, after) if before else [],
                evidence=evidence,
                reason="从文件导入，等待成员审阅",
                fingerprint=item_fingerprint(
                    change["operation"], change["target_kind"], change["target_id"], after
                ),
            )
        )
    group_items(base, items, references_resolved=True)
    return ParsedBatch(batch_id, payload_sha256([i.fingerprint for i in items]), items)


def build_import_batch(base, changes, *, batch_id, lookup, evidence_by_target=None):
    try:
        return _build_import_batch(
            base,
            changes,
            batch_id=batch_id,
            lookup=lookup,
            evidence_by_target=evidence_by_target,
        )
    except ValueError as error:
        raise ServiceError(
            "导入提案校验失败：" + str(error),
            code="IMPORT_PROPOSAL_INVALID",
            status_code=422,
        ) from error
