from sqlalchemy import select

from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemRecord,
)
from ontofoundry_api.services.errors import ConflictError, NotFoundError
from ontofoundry_api.services.instance_store import lock_workspace, require_open_session
from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES


def lock_session(db, workspace_id, session_id):
    lock_workspace(db, workspace_id)
    session = db.scalar(select(ModelingSessionRecord).where(
        ModelingSessionRecord.id == session_id,
        ModelingSessionRecord.workspace_id == workspace_id,
    ).with_for_update().execution_options(populate_existing=True))
    if session is None:
        raise NotFoundError("会话不存在")
    require_open_session(session)
    return session


# Starting a run clears result_state, so a settled value always belongs to
# the session's current run.
SETTLED_RESULTS = frozenset({"done", "failed_permanent"})


def result_pending(session):
    """A finished modeling run whose result has not been turned into proposals yet."""
    return (
        session.task_status == "finished"
        and session.dataagent_task_mode == "model"
        and bool(session.dataagent_task_id)
        and session.result_state not in SETTLED_RESULTS
    )


def occupied(session):
    return session.task_status in ACTIVE_RUN_STATUSES or result_pending(session)


def has_pending(db, session):
    return db.scalar(select(ProposalItemRecord.id).where(
        ProposalItemRecord.workspace_id == session.workspace_id,
        ProposalItemRecord.session_id == session.id,
        ProposalItemRecord.status == "pending",
    ).limit(1)) is not None


def require_idle(session):
    require_open_session(session)
    if result_pending(session):
        raise ConflictError("上一轮结果还在处理，请稍候", code="RESULT_PROCESSING")
    if session.task_status in ACTIVE_RUN_STATUSES:
        raise ConflictError("当前会话正在运行，请等待完成或取消后重试", code="SESSION_RUNNING")


def require_draft_edit(db, session):
    require_idle(session)
    if has_pending(db, session):
        raise ConflictError("请先处理完待审提案，或在提案上修订", code="PENDING_PROPOSALS")


def require_current_batch(db, session, batch_id):
    batch = db.get(ProposalBatchRecord, batch_id)
    revision = (session.run_manifest_json or {}).get("source_session_revision", -1)
    if batch is None or revision > batch.source_session_revision:
        raise ConflictError("新一轮已开始，旧批次只读", code="PROPOSAL_BATCH_READ_ONLY")


def batch_read_only(session, batch):
    return (session.run_manifest_json or {}).get("source_session_revision", -1) > batch.source_session_revision
