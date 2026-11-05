"""Check a run's result and store it as a batch in one transaction (SC-05).

The agent is still running when it submits, so every rejection reaches it as
tool output it can fix; nothing is checked again after the run ends."""

import hashlib
import logging

from ontofoundry_api.contracts.proposal_submit import (
    ProposalSubmitIssue,
    ProposalSubmitResponse,
)
from ontofoundry_api.contracts.proposals import RunContext
from ontofoundry_api.db_models import utc_now
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposal_apply import parse_agent
from ontofoundry_api.services.proposals import (
    batch_item_count,
    store_batch,
    submitted_batch,
)
from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES
from ontofoundry_api.services.session_gate import lock_session

logger = logging.getLogger(__name__)


def context_from_manifest(manifest):
    if manifest.get("invalidated") or "pinned_draft" not in manifest:
        raise ServiceError(
            "运行固定上下文已失效，请重新运行",
            code="RUN_CONTEXT_INVALIDATED",
            status_code=409,
        )
    return RunContext(
        **{
            key: manifest[key]
            for key in (
                "workspace_id",
                "session_id",
                "run_token",
                "base_version_sha256",
                "source_session_revision",
                "source_draft_sha256",
            )
        },
        base_version_id=manifest.get("base_version_id"),
        draft=manifest["pinned_draft"],
        instance_baseline=manifest.get("instance_baseline", {}),
    )


def _rejected(code, message):
    return ProposalSubmitResponse(
        passed=False,
        errors=[ProposalSubmitIssue(
            code=code, message=f"错误 [{code}]：{message}。本次整批提交未通过，未入库。"
        )],
        reviewable_count=0,
    )


def _receipt(db, batch):
    return ProposalSubmitResponse(
        passed=True, errors=[], reviewable_count=batch_item_count(db, batch), batch_id=batch.id
    )


def submit_result(db, settings, workspace_id, session_id, run_token, raw):
    """Returns the outcome; the caller has already verified the run credential."""
    session = lock_session(db, workspace_id, session_id)
    if session.dataagent_run_token != run_token:
        return _rejected("RUN_NOT_CURRENT", "本轮运行已不是会话的当前运行，请重新发起建模")
    digest = hashlib.sha256(raw).hexdigest()
    # Before the pending gate: a retry after a lost response finds its own batch.
    existing = submitted_batch(db, workspace_id, session_id, run_token)
    if existing is not None:
        if existing.result_sha256 == digest:
            return _receipt(db, existing)
        return _rejected("RUN_ALREADY_SUBMITTED", "本轮已提交过不同内容的结果，不能再次提交")
    if session.task_status not in ACTIVE_RUN_STATUSES:
        return _rejected("RUN_NOT_ACTIVE", "本轮运行已结束，不能再提交结果")
    manifest = dict(session.run_manifest_json or {})
    try:
        context = context_from_manifest(manifest)
        parsed = parse_agent(db, settings, session, raw, context)
        batch = store_batch(
            db, workspace_id=workspace_id, session_id=session_id,
            task_id=session.dataagent_task_id, manifest=manifest, parsed=parsed,
            settings=settings,
        )
    except ServiceError as exc:
        db.rollback()
        return _rejected(exc.code, str(exc))
    except Exception:
        # Reported to the agent like any rejection, so it never looks like an outage.
        logger.exception("Unexpected proposal submit failure")
        db.rollback()
        return _rejected("RESULT_CHECK_FAILED", "建模结果校验异常，请按本轮契约重新生成")
    session.result_state = "done"
    session.result_warnings = []
    session.updated_at = utc_now()
    db.commit()
    return _receipt(db, batch)
