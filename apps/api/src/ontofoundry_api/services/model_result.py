"""Consume proposal-only DataAgent results with leases and idempotent storage."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from contextlib import suppress
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update

from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    RunContext,
    parse_result,
)
from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.model_review import (
    build_proposal_repair_request,
)
from ontofoundry_api.services.modeling_input import (
    build_work_pack,
    encode,
    execution_input,
    upload_work_pack,
)
from ontofoundry_api.services.proposals import (
    proposal_context,
    store_batch,
    store_failed_batch,
)
from ontofoundry_api.services.run_credentials import RunGrant, access_file
from ontofoundry_api.services.run_credentials import issue as issue_run_credential

logger = logging.getLogger(__name__)

RESULT_LEASE = timedelta(minutes=5)


def _client(app: Any, workspace_id: str, session_id: str) -> DataAgentClient:
    settings = app.state.settings
    return DataAgentClient(
        settings.dataagent_base_url,
        prefix=settings.dataagent_api_prefix,
        website_id=settings.dataagent_website_id,
        access_key=settings.dataagent_access_key,
        session_ref=f"ontofoundry:{workspace_id}:{session_id}",
        timeout_seconds=settings.dataagent_request_timeout_seconds,
    )


def _guarded_result_values(
    app: Any,
    session_id: str,
    task_id: str,
    claimed_at,
    **values: Any,
) -> bool:
    """Write only while this worker still owns the exact result lease."""
    with app.state.session_factory() as db:
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.last_result_task_id == task_id,
                ModelingSessionRecord.result_state == "processing",
                ModelingSessionRecord.result_claimed_at == claimed_at,
            )
            .values(**values, updated_at=utc_now())
        )
        db.commit()
        return changed.rowcount == 1


def _current_result_state(app: Any, session_id: str) -> str:
    with app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        return str(item.result_state or "") if item is not None else ""


def _finish_failure(
    app: Any,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    state: str,
    detail: str,
) -> str:
    values: dict[str, Any] = {"result_state": state, "task_detail": detail}
    if state == "failed_permanent":
        values["task_status"] = "failed"
    if _guarded_result_values(app, session_id, task_id, claimed_at, **values):
        return state
    return _current_result_state(app, session_id)


# Stepwise modeling keeps intermediate files in the agent workspace under
# modeling/ (harness design §11 items 14/15).
WORKFLOW_DIR = "modeling/"
PLAN_FILES = ("plan.md", "entities.json", "issues.json")
PART_FILES = tuple(
    "parts/" + name
    for name in (
        "01-types.json",
        "02-links.json",
        "03-datasets.json",
        "04-metrics-rules.json",
        "05-facts.json",
    )
)
PLAN_LIMIT = 16 * 1024
EXCERPT_LIMIT = 4 * 1024


def parse_questions(content: bytes, run_token: str) -> list[str] | None:
    """This run's questions as plain text; None unless the marker is for this run."""
    marker = None
    with suppress(UnicodeDecodeError, json.JSONDecodeError, TypeError):
        marker = json.loads(content)
    if not (
        isinstance(marker, dict)
        and marker.get("run_token") == run_token
        and isinstance(marker.get("questions"), list)
        and marker["questions"]
        and all(isinstance(q, str) and q.strip() for q in marker["questions"])
    ):
        return None
    return [q.strip() for q in marker["questions"]]


async def _optional_download(client: DataAgentClient, topic_id: str, path: str) -> bytes | None:
    """A workflow file, or None when it is absent or cannot be read now."""
    try:
        content, _ = await client.download(topic_id, path)
    except DataAgentError as exc:
        if exc.status_code != 404:
            logger.info("Workflow file %s unavailable: %s", path, exc)
        return None
    return content


def _text(content: bytes, limit: int) -> str:
    return content[:limit].decode("utf-8", "ignore")


async def saved_plan(client: DataAgentClient, topic_id: str) -> dict[str, Any] | None:
    """The plan the user is asked to confirm, kept for the next run."""
    plan: dict[str, Any] = {}
    for name in PLAN_FILES:
        content = await _optional_download(client, topic_id, WORKFLOW_DIR + name)
        if content is None:
            continue
        if name == "plan.md":
            plan["plan_md"] = _text(content, PLAN_LIMIT)
            continue
        with suppress(UnicodeDecodeError, json.JSONDecodeError):
            plan[name.removesuffix(".json")] = json.loads(content)
    if not plan:
        return None
    for name in ("issues", "entities"):
        if len(encode(plan)) > PLAN_LIMIT and name in plan:
            plan.pop(name)
            plan["truncated"] = True
    return plan


async def workflow_diagnostics(client: DataAgentClient, topic_id: str) -> list[dict[str, Any]]:
    """Which workflow files exist; plan and notes keep a short excerpt."""
    found = []
    for name in ("plan.md", "notes.md", *PART_FILES):
        content = await _optional_download(client, topic_id, WORKFLOW_DIR + name)
        if content is None:
            continue
        entry: dict[str, Any] = {"path": WORKFLOW_DIR + name, "bytes": len(content)}
        if name.endswith(".md"):
            entry["excerpt"] = _text(content, EXCERPT_LIMIT)
        found.append(entry)
    return found


async def _fail_with_workflow(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    topic_id: str,
    manifest: dict[str, Any],
    detail: str,
) -> str:
    """A permanent failure that also keeps the workflow files as diagnostics."""
    found = await workflow_diagnostics(_client(app, workspace_id, session_id), topic_id)
    values: dict[str, Any] = {
        "result_state": "failed_permanent",
        "task_status": "failed",
        "task_detail": detail
        + ("；已取回中间文件：" + "、".join(f["path"] for f in found) if found else ""),
    }
    if found:
        values["run_manifest_json"] = {**manifest, "workflow_diagnostics": found}
    if _guarded_result_values(app, session_id, task_id, claimed_at, **values):
        return "failed_permanent"
    return _current_result_state(app, session_id)


async def _request_repair(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    topic_id: str,
    problems: list[str],
    manifest: dict[str, Any] | None = None,
) -> str | None:
    """Hand the complaints back to the agent and let it produce a fix.

    Returns the new result-state on success, or None when the caller should fall
    through to its own ending — no topic, or DataAgent refused the turn. Failing
    to ask must never be worse than not trying: the original outcome still
    applies.

    The claim is released only after DataAgent accepts the follow-up, so a
    refusal leaves the lease exactly as it was.
    """
    if not topic_id or not problems or (manifest or {}).get("repair_used", 0) >= 2:
        return None

    next_token = secrets.token_hex(16)
    next_manifest = (
        {
            **manifest,
            "run_token": next_token,
            "repair_used": manifest.get("repair_used", 0) + 1,
        }
        if manifest
        else None
    )
    if next_manifest is None:
        return None
    try:
        client = _client(app, workspace_id, session_id)
        files = next_manifest.get("input_files", {})
        if not files.get("schema") or "materials" not in files:
            return None
        if files.get("mcp") or files.get("run_access"):
            metadata = files.get("mcp_access")
            if not metadata:
                return None
            credential = issue_run_credential(
                app.state.settings.session_secret,
                RunGrant(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_token=next_token,
                    version_id=next_manifest.get("base_version_id"),
                    user_id=metadata["user_id"],
                ),
            )
            uploaded_mcp = await client.upload(
                topic_id,
                f"ontofoundry-mcp-{next_token}.json",
                encode(
                    access_file(
                        {
                            "url": metadata["url"],
                            "version_id": next_manifest.get("base_version_id"),
                            "credential": credential,
                        }
                    )
                ),
                "application/json",
            )
            files = {
                **files,
                "run_access": uploaded_mcp["rel_path"],
                **({"mcp": uploaded_mcp["rel_path"]} if files.get("mcp") else {}),
            }
        context = proposal_context(next_manifest, next_manifest["pinned_draft"])
        context["execution"] = execution_input(next_token, next_manifest["repair_used"])
        uploaded = await client.upload(
            topic_id,
            f"ontofoundry-context-{next_token}.json",
            encode(context),
            "application/json",
        )
        pack, pages = build_work_pack(
            context,
            files["materials"],
            context_file=uploaded["rel_path"],
            schema_file=files["schema"],
            mcp_config_file=files.get("mcp"),
            platform_check_file=files.get("run_access"),
            tables=files.get("tables"),
            tables_file=files.get("tables_file"),
            scenario_facts=files.get("scenario_facts"),
        )
        work_pack_file = await upload_work_pack(client, topic_id, next_token, pack, pages)
        next_manifest["input_files"] = {
            **files,
            "context": uploaded["rel_path"],
            "work_pack": work_pack_file,
        }
        content = build_proposal_repair_request(
            problems,
            run_token=next_token,
            work_pack_file=work_pack_file,
            repair_used=next_manifest["repair_used"],
        )
        submitted = await client.deliver(
            topic_id=topic_id,
            content=content,
            agent_id=app.state.settings.dataagent_agent_id,
            execution_mode=app.state.settings.dataagent_execution_mode,
        )
    except DataAgentError:
        return None

    next_task_id = str(submitted.get("task_id") or "")
    if not next_task_id:
        return None

    # The new task becomes the session's run. `last_result_task_id` stays on the
    # task being abandoned so this result is never consumed again, and
    # result_state clears so the next reconcile can claim the new one.
    if not _guarded_result_values(
        app,
        session_id,
        task_id,
        claimed_at,
        dataagent_task_id=next_task_id,
        dataagent_run_token=next_token,
        **({"run_manifest_json": next_manifest} if next_manifest else {}),
        result_state="",
        result_claimed_at=None,
        task_status="running",
        task_detail="结果未通过校验，已把问题交回 DataAgent 修正",
    ):
        return _current_result_state(app, session_id)
    return ""


def _permanent_detail(exc: DataAgentError) -> str:
    return f"建模结果下载失败：{exc}"


# Transient by status code. 429 matters most: a rate-limited file service is the
# one case where the result exists and is correct, and calling that permanent
# throws away a model the agent already produced. 408 and 425 are the same
# shape. Everything else — 404, a malformed body, a contract violation — is a
# statement about the result itself and will not improve by asking again.
_RETRIABLE_DOWNLOAD_STATUSES = frozenset({408, 425, 429})


def _is_retriable_download(status_code: int) -> bool:
    return status_code >= 500 or status_code in _RETRIABLE_DOWNLOAD_STATUSES


async def reconcile_run(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str | None = None,
) -> str:
    """Consume one successful model task, returning its result-state projection."""
    with app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        if item is None or item.workspace_id != workspace_id:
            return ""
        current_task_id = str(item.dataagent_task_id or "")
        if task_id is not None and current_task_id != task_id:
            return str(item.result_state or "")
        task_id = current_task_id
        if item.task_status != "finished" or not task_id:
            return str(item.result_state or "")
        if item.dataagent_task_mode != "model":
            return str(item.result_state or "")

        claimed_at = utc_now()
        claimed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                or_(
                    ModelingSessionRecord.last_result_task_id.is_distinct_from(task_id),
                    ModelingSessionRecord.result_state == "failed_retriable",
                    and_(
                        ModelingSessionRecord.result_state == "processing",
                        ModelingSessionRecord.result_claimed_at < claimed_at - RESULT_LEASE,
                    ),
                ),
            )
            .values(
                result_state="processing",
                last_result_task_id=task_id,
                result_claimed_at=claimed_at,
                updated_at=claimed_at,
            )
        )
        db.commit()
        if claimed.rowcount != 1:
            db.refresh(item)
            return str(item.result_state or "")

        topic_id = str(item.dataagent_topic_id or "")
        run_token = str(item.dataagent_run_token or "")
        manifest = dict(item.run_manifest_json or {})

    result_path = f"output/ontofoundry-result-{run_token}.json"
    try:
        content, _content_type = await _client(app, workspace_id, session_id).download(
            topic_id, result_path
        )
    except DataAgentError as exc:
        if exc.status_code == 404:
            # Only an explicit marker for this run means the agent is waiting.
            needs_input_path = f"output/ontofoundry-needs-input-{run_token}.json"
            marker = None
            try:
                marker_content, _ = await _client(app, workspace_id, session_id).download(
                    topic_id, needs_input_path
                )
            except DataAgentError as marker_exc:
                if _is_retriable_download(marker_exc.status_code):
                    return _finish_failure(
                        app,
                        session_id,
                        task_id,
                        claimed_at,
                        state="failed_retriable",
                        detail=f"建模结果下载暂时失败，等待重试：{marker_exc}",
                    )
                if marker_exc.status_code != 404:
                    return _finish_failure(
                        app,
                        session_id,
                        task_id,
                        claimed_at,
                        state="failed_permanent",
                        detail=_permanent_detail(marker_exc),
                    )
            else:
                marker = parse_questions(marker_content, run_token)

            what = "提案"
            if marker is None:
                return await _fail_with_workflow(
                    app,
                    workspace_id,
                    session_id,
                    task_id,
                    claimed_at,
                    topic_id=topic_id,
                    manifest=manifest,
                    detail=f"建模没有产出{what}：智能体结束时没有写入结果文件，请重试或换个说法描述需求",
                )
            # The entity list or issue list the user confirms is reused next run.
            plan = await saved_plan(_client(app, workspace_id, session_id), topic_id)
            if _guarded_result_values(
                app,
                session_id,
                task_id,
                claimed_at,
                result_state="awaiting_reply",
                task_detail=f"智能体需要你确认后才能生成{what}，请在对话中回复",
                **({"run_manifest_json": {**manifest, "prior_plan": plan}} if plan else {}),
            ):
                return "awaiting_reply"
            return _current_result_state(app, session_id)
        if _is_retriable_download(exc.status_code):
            return _finish_failure(
                app,
                session_id,
                task_id,
                claimed_at,
                state="failed_retriable",
                detail=f"建模结果下载暂时失败，等待重试：{exc}",
            )
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail=_permanent_detail(exc),
        )

    return await _consume_proposals(
        app,
        workspace_id,
        session_id,
        task_id,
        claimed_at,
        topic_id=topic_id,
        manifest=manifest,
        content=content,
    )


async def _consume_proposals(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    topic_id: str,
    manifest: dict[str, Any],
    content: bytes,
) -> str:
    """Store an ontofoundry.proposals/v1 result as a batch. Never touches the
    draft: a session edited during the run only makes affected items stale."""
    if manifest.get("invalidated") or "pinned_draft" not in manifest:
        return _finish_failure(app, session_id, task_id, claimed_at,
            state="failed_permanent", detail="运行固定上下文已失效，请重新运行")
    context = RunContext(
        workspace_id=manifest["workspace_id"],
        session_id=manifest["session_id"],
        run_token=manifest["run_token"],
        base_version_id=manifest.get("base_version_id"),
        base_version_sha256=manifest["base_version_sha256"],
        source_session_revision=manifest["source_session_revision"],
        source_draft_sha256=manifest["source_draft_sha256"],
        draft=manifest["pinned_draft"],
        instance_baseline=manifest.get("instance_baseline", {}),
    )
    # Questions belong in the agent's reply. A needs-input file left beside a
    # result is not read: it must never cost the proposals.
    budget_failure = None
    if manifest.get("repair_budget_required"):
        try:
            ledger_bytes, _ = await _client(app, workspace_id, session_id).download(
                topic_id, execution_input(manifest["run_token"])["budget_file"]
            )
            ledger = json.loads(ledger_bytes)
            used = ledger["used"]
            if (
                ledger["run_token"] != manifest["run_token"]
                or type(used) is not int
                or not manifest.get("repair_used", 0) <= used <= 2
                or ledger["result_sha256"] != hashlib.sha256(content).hexdigest()
            ):
                raise ValueError("invalid correction ledger")
            manifest = {**manifest, "repair_used": used}
        except DataAgentError as exc:
            if _is_retriable_download(exc.status_code):
                return _finish_failure(
                    app,
                    session_id,
                    task_id,
                    claimed_at,
                    state="failed_retriable",
                    detail="修正计数下载暂时失败，等待重试",
                )
            budget_failure = ProposalContractError(
                "REPAIR_BUDGET_INVALID", "修正计数缺失，无法继续本轮"
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            budget_failure = ProposalContractError(
                "REPAIR_BUDGET_INVALID", "修正计数缺失、过期或耗尽，请结束本轮"
            )
    with app.state.session_factory() as db:
        lookup = material_lookup(db, app.state.settings, workspace_id)
        try:
            if budget_failure:
                raise budget_failure
            parsed = parse_result(content, context, material_lookup=lookup)
        except ProposalContractError as exc:
            parsed, failure = None, exc
        except Exception:
            logger.exception("Unexpected proposal result validation failure")
            parsed, failure = (
                None,
                ProposalContractError(
                    "RESULT_VALIDATION_FAILED", "建模结果校验异常，请按本轮契约重新生成"
                ),
            )
    if parsed is None:
        repaired = await _request_repair(
            app,
            workspace_id,
            session_id,
            task_id,
            claimed_at,
            topic_id=topic_id,
            problems=[f"{failure.code}：{failure}"],
            manifest={**manifest, "repair_used": 2} if budget_failure else manifest,
        )
        if repaired is not None:
            return repaired
        with app.state.session_factory() as db:
            current = db.scalar(
                select(ModelingSessionRecord)
                .where(
                    ModelingSessionRecord.id == session_id,
                    ModelingSessionRecord.dataagent_task_id == task_id,
                    ModelingSessionRecord.result_claimed_at == claimed_at,
                )
                .with_for_update()
            )
            if current is None:
                return _current_result_state(app, session_id)
            store_failed_batch(
                db,
                workspace_id=workspace_id,
                session_id=session_id,
                task_id=task_id,
                manifest=manifest,
                result_sha256=hashlib.sha256(content).hexdigest(),
                code=failure.code,
                message=str(failure),
            )
            db.commit()
        return await _fail_with_workflow(
            app,
            workspace_id,
            session_id,
            task_id,
            claimed_at,
            topic_id=topic_id,
            manifest=manifest,
            detail=f"提案结果被拒收：{failure}",
        )

    with app.state.session_factory() as db:
        current = db.scalar(
            select(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.result_claimed_at == claimed_at,
            )
            .with_for_update()
        )
        if current is None:
            return _current_result_state(app, session_id)
        store_batch(
            db,
            workspace_id=workspace_id,
            session_id=session_id,
            task_id=task_id,
            manifest=manifest,
            parsed=parsed,
        )
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.last_result_task_id == task_id,
                ModelingSessionRecord.result_state == "processing",
                ModelingSessionRecord.result_claimed_at == claimed_at,
            )
            .values(
                result_state="done",
                result_warnings=[],
                task_status="finished",
                task_detail=f"已生成 {len(parsed.items)} 条提案，请在“提案”中审阅",
                updated_at=utc_now(),
            )
        )
        if changed.rowcount != 1:
            db.rollback()
            return _current_result_state(app, session_id)
        db.commit()
    return "done"


def exhaust_retriable_result(app: Any, session_id: str, task_id: str) -> str:
    """Turn an exhausted download retry loop into a visible terminal failure."""
    with app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        if item is None:
            return ""
        detail = str(item.task_detail or "建模结果下载失败").replace(
            "等待重试", "重试三次后仍失败"
        )
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.last_result_task_id == task_id,
                ModelingSessionRecord.result_state == "failed_retriable",
            )
            .values(
                result_state="failed_permanent",
                task_status="failed",
                task_detail=detail,
                updated_at=utc_now(),
            )
        )
        db.commit()
        if changed.rowcount == 1:
            return "failed_permanent"
    return _current_result_state(app, session_id)
