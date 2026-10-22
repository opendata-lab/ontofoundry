"""Delete unused connections and their local metadata without opening the source."""

from sqlalchemy import delete, select

from ontofoundry_api.contracts.connections import ConnectionReference
from ontofoundry_api.db_models import (
    ConnectionRecord,
    MetadataSnapshotRecord,
    MetadataSyncBatchRecord,
    MetadataSyncJobRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    ProposalItemRecord,
    WorkspaceRecord,
)
from ontofoundry_api.services.errors import (
    ConnectionInUseError,
    NotFoundError,
    SyncRunningError,
)
from ontofoundry_api.services.metadata_sync import ACTIVE


def connection_references(db, workspace_id, connection_id):
    references = []

    published = set()

    def datasets(raw, location, skip=frozenset()):
        for dataset in raw.get("datasets", []):
            if dataset.get("connection_id") == connection_id and dataset.get("id") not in skip:
                references.append(ConnectionReference(
                    type="dataset", name=dataset.get("display_name") or dataset["name"],
                    location=location,
                ))

    workspace = db.get(WorkspaceRecord, workspace_id)
    if workspace.current_version_id:
        version = db.scalar(select(OntologyVersionRecord).where(
            OntologyVersionRecord.workspace_id == workspace_id,
            OntologyVersionRecord.id == workspace.current_version_id,
        ))
        if version:
            datasets(version.snapshot_json, "已发布版本")
            published = {d.get("id") for d in version.snapshot_json.get("datasets", [])}

    # All persisted sessions are active: this schema has no abandonment lifecycle.
    sessions = db.scalars(select(ModelingSessionRecord).where(
        ModelingSessionRecord.workspace_id == workspace_id,
    ).order_by(ModelingSessionRecord.id)).all()
    titles = {session.id: session.title for session in sessions}
    for session in sessions:
        # Drafts carry the whole model; published datasets are reported once above,
        # so a session only adds what it introduced and has not published.
        datasets(session.draft_json, session.title, published)
        for table in session.linked_tables or []:
            if table.get("connection_id") == connection_id:
                name = ".".join(filter(None, [table.get("schema_name"), table["table_name"]]))
                references.append(ConnectionReference(type="linked_table", name=name, location=session.title))

    for proposal in db.scalars(select(ProposalItemRecord).where(
        ProposalItemRecord.workspace_id == workspace_id,
        ProposalItemRecord.session_id.in_(titles),
        ProposalItemRecord.target_kind == "dataset",
        ProposalItemRecord.status == "pending",
    ).order_by(ProposalItemRecord.id)):
        dataset = proposal.after_json or proposal.before_json or {}
        if dataset.get("connection_id") == connection_id:
            references.append(ConnectionReference(
                type="dataset_proposal", name=dataset.get("display_name") or dataset["name"],
                location=titles[proposal.session_id],
            ))
    return references


def delete_connection(db, workspace_id, connection_id):
    connection = db.scalar(select(ConnectionRecord).where(
        ConnectionRecord.workspace_id == workspace_id,
        ConnectionRecord.id == connection_id,
    ))
    if not connection:
        raise NotFoundError("数据连接不存在")
    references = connection_references(db, workspace_id, connection_id)
    if references:
        raise ConnectionInUseError(
            "该连接仍被引用，请先改用其他连接或删除这些数据集",
            details={"references": [reference.model_dump() for reference in references]},
        )
    jobs = select(MetadataSyncJobRecord.id).where(MetadataSyncJobRecord.connection_id == connection_id)
    if db.scalar(jobs.where(MetadataSyncJobRecord.state.in_(ACTIVE))) is not None:
        raise SyncRunningError("该连接正在同步，请等同步结束后再删除")
    # Delete children first, including every schema, within the same transaction.
    db.execute(delete(MetadataSyncBatchRecord).where(MetadataSyncBatchRecord.job_id.in_(jobs)))
    db.execute(delete(MetadataSyncJobRecord).where(MetadataSyncJobRecord.connection_id == connection_id))
    db.execute(delete(MetadataSnapshotRecord).where(MetadataSnapshotRecord.connection_id == connection_id))
    db.delete(connection)
    db.commit()
