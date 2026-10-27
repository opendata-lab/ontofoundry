"""Share proposal diagnostics between preflight and result ingestion."""


from ontofoundry_api.contracts.proposal_checks import (
    ProposalCheckError,
    ProposalCheckResponse,
)
from ontofoundry_api.contracts.proposals import RunContext
from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposal_apply import parse_agent


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


def check_result(db, settings, manifest, raw):
    context = context_from_manifest(manifest)
    try:
        session = db.get(ModelingSessionRecord, context.session_id)
        parsed = parse_agent(db, settings, session, raw, context)
    except ServiceError as exc:
        return ProposalCheckResponse(passed=False, contract_errors=[ProposalCheckError(
            code=exc.code, message=f"错误 [{exc.code}]：{exc}。本次整批检查未通过，未入库。")], reviewable_count=0)
    return ProposalCheckResponse(passed=True, contract_errors=[], reviewable_count=len(parsed.items))
