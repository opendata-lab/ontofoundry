"""Derive history-wide source usage without persisting counters."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.contracts.materials import MaterialUsage
from ontofoundry_api.db_models import (
    ImportRecord,
    InstanceEvidenceRecord,
    InstanceHistoryRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    ProposalBatchRecord,
    ProposalItemRecord,
)
from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES

# A run that is still being produced may yet cite its uploaded materials; once
# it settles, its generated batch carries the manifest that matters.
UNSETTLED_RESULT_STATES = {"processing", "failed_retriable"}

COLLECTIONS = {
    "object_types": "object_type", "link_types": "link_type",
    "properties": "property", "rules": "rule", "metrics": "metric",
    "material_objects": "material_object", "material_links": "material_link",
}


def material_usage(db: Session, workspace_id: str, material_ids: set[str]) -> dict[str, MaterialUsage]:
    if not material_ids:
        return {}
    references: dict[str, set[str]] = defaultdict(set)
    elements: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def mentioned(value) -> set[str]:
        if isinstance(value, str):
            # Preserve the conservative deletion check for legacy embedded JSON.
            return {key for key in material_ids if key in value}
        if isinstance(value, list):
            return set().union(*(mentioned(item) for item in value)) if value else set()
        if isinstance(value, dict):
            return mentioned(list(value.values()))
        return set()

    def element(kind: str, target_id: str, value):
        if kind not in COLLECTIONS.values():
            return
        # Only explicit evidence contributes element counts.
        def evidence_ids(node) -> set[str]:
            if isinstance(node, list):
                return set().union(*(evidence_ids(item) for item in node)) if node else set()
            if not isinstance(node, dict):
                return set()
            own = {node["material_id"]} if node.get("material_id") in material_ids else set()
            return own | evidence_ids(list(node.values()))

        for material_id in evidence_ids(value):
            elements[material_id][kind].add(target_id)

    def snapshot(value):
        if not isinstance(value, dict):
            return
        for collection, kind in COLLECTIONS.items():
            for item in value.get(collection, []) or []:
                if isinstance(item, dict) and item.get("id"):
                    element(kind, item["id"], item.get("evidence", []))

    def mark(label, value):
        for material_id in mentioned(value):
            references[material_id].add(label)

    for row in db.scalars(select(InstanceEvidenceRecord).where(
        InstanceEvidenceRecord.workspace_id == workspace_id,
        InstanceEvidenceRecord.material_id.in_(material_ids))):
        references[row.material_id].add("实例证据")
        elements[row.material_id]["material_object" if row.owner_kind == "instance" else "material_link"].add(row.owner_id)
    for row in db.scalars(select(InstanceHistoryRecord).where(InstanceHistoryRecord.workspace_id == workspace_id)):
        mark("实例历史", [row.before, row.after])
        element("material_object" if row.owner_kind == "instance" else "material_link", row.owner_id, [row.before, row.after])
    for row in db.scalars(select(ImportRecord).where(ImportRecord.workspace_id == workspace_id)):
        mark("导入报告", row.material_id)
    for row in db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.workspace_id == workspace_id)):
        values = [row.evidence_json, row.before_json, row.after_json]
        mark("提案", values)
        element(row.target_kind, row.target_id, [row.evidence_json,
            (row.before_json or {}).get("evidence", []), (row.after_json or {}).get("evidence", [])])
    for row in db.scalars(select(ProposalBatchRecord).where(ProposalBatchRecord.workspace_id == workspace_id)):
        mark("运行清单", row.material_manifest_json)
    for row in db.scalars(select(ModelingSessionRecord).where(ModelingSessionRecord.workspace_id == workspace_id)):
        mark("会话草稿", [row.draft_json, row.material_ids, row.candidates_json])
        if (
            row.task_status in ACTIVE_RUN_STATUSES
            or row.result_state in UNSETTLED_RESULT_STATES
        ):
            mark("运行清单", [row.run_manifest_json, row.uploaded_material_ids])
        snapshot(row.draft_json)
    for row in db.scalars(select(OntologyVersionRecord).where(OntologyVersionRecord.workspace_id == workspace_id)):
        mark("已发布版本", row.snapshot_json)
        snapshot(row.snapshot_json)

    order = ["实例证据", "实例历史", "导入报告", "提案", "运行清单", "会话草稿", "已发布版本"]
    return {material_id: MaterialUsage(
        **{collection: len(elements[material_id][kind]) for collection, kind in COLLECTIONS.items()},
        references=[label for label in order if label in references[material_id]],
        can_delete=not references[material_id],
    ) for material_id in material_ids}


def material_references(db: Session, workspace_id: str, material_id: str) -> list[str]:
    return material_usage(db, workspace_id, {material_id})[material_id].references
