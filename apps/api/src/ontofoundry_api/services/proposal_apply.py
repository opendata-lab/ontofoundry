from copy import deepcopy
from dataclasses import dataclass

from pydantic import TypeAdapter
from sqlalchemy import delete, or_

from ontofoundry_api.contracts.proposals import (
    ParsedBatch,
    ParsedItem,
    ProposalContractError,
    apply_items,
    group_items,
    parse_result,
)
from ontofoundry_api.db_models import (
    InstanceEvidenceRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import canonical, element_sha256
from ontofoundry_api.domain.evidence import EvidenceError, check_material_evidence
from ontofoundry_api.domain.instances import (
    INSTANCE_KINDS,
    combined_snapshot,
    definitions,
    instance_hash,
    validate_instances,
)
from ontofoundry_api.domain.models import (
    COLLECTIONS,
    ELEMENT_MODELS,
    PROPOSAL_COLLECTIONS,
    ElementKind,
    OntologyDraft,
)
from ontofoundry_api.services import instance_store
from ontofoundry_api.services.errors import ConflictError, ServiceError
from ontofoundry_api.services.identities import check_identities, element_kinds
from ontofoundry_api.services.join_validation import validate_join_columns
from ontofoundry_api.services.materials_lookup import material_lookup


@dataclass
class Trial:
    items: list[ParsedItem]
    candidate: dict
    instance_states: dict[str, str | None]


def stored_items(rows, dependencies):
    ids = {row.id for row in rows}
    return [ParsedItem(
        id=row.id, ordinal=row.ordinal, client_ref=row.client_ref,
        operation=row.operation, target_kind=row.target_kind, target_id=row.target_id,
        expected_target_hash=row.expected_target_hash,
        expected_instance_revision=row.expected_instance_revision,
        before=deepcopy(row.before_json), after=deepcopy(row.after_json),
        field_changes=deepcopy(row.field_changes_json or []),
        evidence=deepcopy(row.evidence_json or []), reason=row.reason or "",
        fingerprint=row.fingerprint,
        depends_on=[dep for dep in dependencies.get(row.id, []) if dep in ids],
        atomic_group_id=row.atomic_group_id,
    ) for row in rows]


def _unfold_groups(items):
    """Put back the mutual edges parsing folded into atomic_group_id, so a
    batch tried again (stored, revised, accepted) finds the same groups."""
    groups: dict[str, set[str]] = {}
    for item in items:
        if item.atomic_group_id:
            groups.setdefault(item.atomic_group_id, set()).add(item.id)
    for item in items:
        peers = groups.get(item.atomic_group_id, set()) - {item.id}
        if peers:
            item.depends_on = sorted({*item.depends_on, *peers})


def _evidence(db, workspace_id, before, candidate, items, lookup):
    owners = {}
    for snapshot in (before, candidate):
        seen = {}
        for collection in PROPOSAL_COLLECTIONS.values():
            for element in snapshot.get(collection, []):
                owner = element["id"]
                for evidence in element.get("evidence", []):
                    identity = evidence["id"]
                    if identity in seen or (identity in owners and owners[identity] != owner):
                        raise EvidenceError("EVIDENCE_ID_DUPLICATE", "证据 UUID 不能重复或转移归属")
                    seen[identity] = owner
                    owners[identity] = owner
    for item in items:
        for evidence in [*item.evidence, *((item.after or {}).get("evidence", []))]:
            identity = evidence["id"]
            if identity in owners and owners[identity] != item.target_id:
                raise EvidenceError("EVIDENCE_ID_DUPLICATE", "同一批内的证据 UUID 不能复用于其他目标")
            owners[identity] = item.target_id
            collision = db.get(InstanceEvidenceRecord, identity)
            if collision and (
                collision.workspace_id != workspace_id
                or collision.owner_id != item.target_id
                or item.target_kind not in INSTANCE_KINDS
                or collision.owner_kind != instance_store.OWNERS[item.target_kind]
            ):
                raise EvidenceError("EVIDENCE_ID_DUPLICATE", "证据 UUID 不能转移到其他实例")
            if evidence["kind"] == "material":
                check_material_evidence(evidence, lookup, "证据")


def _instances(model, candidate, items):
    """Check changed instances together with the relations that touch them.

    An instance whose type changes can break a relation the batch does not
    edit; acceptance checks those relations, so the trial does too."""
    changed = {i.target_id for i in items if i.target_kind in INSTANCE_KINDS}
    if not changed:
        return
    objects = {o["id"]: o for o in candidate.get("material_objects", [])}
    # Deleting an instance cascades to its relations.
    deleted = {i.target_id for i in items if i.operation == "delete"}
    links = [
        link for link in candidate.get("material_links", [])
        if (link["id"] in changed or {link["source_id"], link["target_id"]} & changed)
        and not {link["source_id"], link["target_id"]} & deleted
    ]
    ids = (changed & set(objects)) | {end for link in links for end in (link["source_id"], link["target_id"])}
    validate_instances(model, [objects[key] for key in ids if key in objects], links)


def trial_apply(db, workspace_id, session, items, settings, *, baseline=None, draft=None, accepting=False):
    """Apply ``items`` to the draft in memory under every rule acceptance uses.

    Building or revising a batch may leave a dataset unbound (an imported file
    or an unsynced table); ``accepting`` requires every dataset to be bound."""
    items = deepcopy(items)
    _unfold_groups(items)
    baseline = baseline if baseline is not None else instance_store.baseline(db, workspace_id, session.id)
    draft = draft if draft is not None else session.draft_json
    before = combined_snapshot(draft, baseline)
    existing = {e["id"]: (kind.value, e) for kind, c in PROPOSAL_COLLECTIONS.items() for e in before.get(c, [])}
    entries = {e["target_id"]: e for e in baseline.get("items", [])}
    lookup = material_lookup(db, settings, workspace_id)
    try:
        if len({i.target_id for i in items}) != len(items):
            raise ValueError("同一批次不能重复作用于同一目标")
        for item in items:
            found = existing.get(item.target_id)
            kind = ElementKind(item.target_kind)
            if item.operation == "create":
                if found or item.before is not None or item.after is None:
                    raise ValueError("新增目标已存在或内容形态无效")
            else:
                if not found or found[0] != item.target_kind:
                    raise ConflictError("目标不存在或类型已变化", code="PROPOSAL_TARGET_CHANGED")
                current_hash = (instance_hash(found[1], entries[item.target_id]["revision"])
                                if item.target_kind in INSTANCE_KINDS else element_sha256(found[1], collection=PROPOSAL_COLLECTIONS[kind]))
                if canonical(found[1]) != canonical(item.before) or current_hash != item.expected_target_hash:
                    raise ConflictError("目标内容已变化，请重新生成或审阅", code="PROPOSAL_TARGET_CHANGED")
                if (item.operation == "update") != (item.after is not None):
                    raise ValueError("更新或删除的内容形态无效")
            if item.after is not None:
                item.after = TypeAdapter(ELEMENT_MODELS[kind]).validate_python(item.after).model_dump(mode="json")
                if item.after["id"] != item.target_id:
                    raise ValueError("元素 id 与提案目标不一致")
            if item.target_kind in INSTANCE_KINDS:
                row = db.get(instance_store.RECORDS[item.target_kind], item.target_id)
                if (row is None and item.expected_instance_revision is not None) or (row is not None and (
                    row.workspace_id != workspace_id or row.state == "deleted"
                    or (row.state == "staged" and row.session_id != session.id)
                    or row.revision != item.expected_instance_revision
                )):
                    raise ConflictError("实例已变化或不属于当前会话", code="INSTANCE_REVISION_CHANGED")
                if item.after is not None:
                    item.after = instance_store.reconcile_evidence(
                        found[1] if found else None, item.after, item.target_kind,
                        lookup=lookup, actor=session.created_by, now=utc_now(),
                    )
        candidate = apply_items(before, items)
        checked = definitions(candidate)
        validate_join_columns(db, workspace_id, definitions(before), checked, settings,
                              probe=False, allow_unbound=not accepting)
        normalized = {e["id"]: e for c in COLLECTIONS.values() for e in checked.get(c, [])}
        for item in items:
            if item.after is not None and item.target_kind not in INSTANCE_KINDS:
                item.after = normalized[item.target_id]
        group_items(before, items, references_resolved=True)
        candidate = apply_items(before, items)
        model = OntologyDraft.model_validate(definitions(candidate))
        _instances(model, candidate, items)
        _evidence(db, workspace_id, before, candidate, items, lookup)
        check_identities(db, workspace_id, element_kinds(candidate))
        published = instance_store.published_model(db, workspace_id)
        objects = {o["id"]: o for o in candidate.get("material_objects", [])}
        active = {e["target_id"] for e in baseline.get("items", []) if e["state"] == "active"}
        states = {}
        for item in sorted(items, key=lambda i: i.target_kind == "material_link"):
            if item.target_kind not in INSTANCE_KINDS:
                continue
            state = instance_store.state_for(model, published, item.target_kind, item.after, objects, active) if item.after else None
            states[item.id] = state
            if state == "active":
                active.add(item.target_id)
            else:
                active.discard(item.target_id)
        return Trial(items, candidate, states)
    except EvidenceError as exc:
        raise ServiceError(str(exc), code=exc.code, status_code=422) from exc
    except ValueError as exc:
        raise ServiceError("候选图校验未通过：" + str(exc), code="VALIDATION_FAILED", status_code=422) from exc


def parse_agent(db, settings, session, raw, context):
    try:
        parsed = parse_result(raw, context, material_lookup(db, settings, context.workspace_id))
    except ProposalContractError as exc:
        raise ServiceError(str(exc), code=exc.code, status_code=422) from exc
    trial = trial_apply(db, context.workspace_id, session, parsed.items, settings)
    return ParsedBatch(parsed.id, parsed.result_sha256, trial.items)


def save_pending(db, session, batch_id, trial):
    from ontofoundry_api.services.proposals import batch_items
    rows = {r.id: r for r in batch_items(db, [batch_id], session.workspace_id, session.id)}
    pending_ids = [i.id for i in trial.items]
    decided = {r.fingerprint for r in rows.values() if r.status != "pending" and r.id not in pending_ids}
    if any(item.id not in rows and item.fingerprint in decided for item in trial.items):
        raise ConflictError("相同内容的提案已在本批次中决定过，可在“已拒绝”中恢复", code="PROPOSAL_DUPLICATE")
    removed = [row.id for row in rows.values() if row.status == "pending" and row.id not in pending_ids]
    db.execute(delete(ProposalItemDependencyRecord).where(
        ProposalItemDependencyRecord.batch_id == batch_id,
        or_(ProposalItemDependencyRecord.item_id.in_(pending_ids + removed),
            ProposalItemDependencyRecord.depends_on_item_id.in_(removed)),
    ))
    for identity in removed:
        rows[identity].status = "rejected"
    ordinal = max((row.ordinal for row in rows.values()), default=-1) + 1
    for item in trial.items:
        row = rows.get(item.id)
        if row is None:
            row = ProposalItemRecord(id=item.id, workspace_id=session.workspace_id,
                session_id=session.id, batch_id=batch_id, ordinal=ordinal,
                client_ref=item.client_ref, target_kind=item.target_kind, status="pending")
            db.add(row)
            ordinal += 1
        for attr in ("operation", "target_id", "expected_target_hash", "expected_instance_revision", "atomic_group_id", "fingerprint", "reason"):
            setattr(row, attr, getattr(item, attr))
        row.after_json, row.before_json = item.after, item.before
        row.field_changes_json, row.evidence_json = [], item.evidence
    db.flush()
    for item in trial.items:
        for dep in item.depends_on:
            db.add(ProposalItemDependencyRecord(workspace_id=session.workspace_id, session_id=session.id,
                batch_id=batch_id, item_id=item.id, depends_on_item_id=dep))


def trial_pending(db, session, batch_id, settings, changes=None):
    from ontofoundry_api.services.proposals import batch_items, dependency_map
    rows = batch_items(db, [batch_id], session.workspace_id, session.id)
    deps = dependency_map(db, [batch_id], session.workspace_id, session.id)
    items = stored_items([r for r in rows if r.status == "pending"], deps)
    for item in items:
        if changes and item.id in changes:
            item.after = changes[item.id]
    return trial_apply(db, session.workspace_id, session, items, settings)


def apply_trial(db, workspace_id, session_id, trial, accepted, actor, lookup):
    from ontofoundry_api.services.instance_proposals import apply_changes
    ordered = sorted(accepted, key=lambda item: 2 if item.target_kind == "material_object" and item.operation == "delete" else 1 if item.target_kind == "material_link" else 0)
    return apply_changes(db, workspace_id, session_id, trial.candidate, ordered, [], actor, lookup,
                         instance_states=trial.instance_states)
