"""Share proposal diagnostics between preflight and result ingestion."""


from ontofoundry_api.contracts.proposal_checks import (
    ProposalCheckError,
    ProposalCheckResponse,
    UnacceptableGroup,
)
from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    RunContext,
    parse_result,
)
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.materials_lookup import material_lookup


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
        parsed = parse_result(
            raw, context, material_lookup(db, settings, context.workspace_id)
        )
    except ProposalContractError as exc:
        return ProposalCheckResponse(
            passed=False,
            contract_errors=[
                ProposalCheckError(
                    code=exc.code, message=f"错误 [{exc.code}]：{exc}。本次仅检查，未入库。"
                )
            ],
            unacceptable_groups=[],
            reviewable_count=0,
            unacceptable_count=0,
        )
    groups = {}
    for item in parsed.items:
        if item.status == "unacceptable":
            groups.setdefault(item.atomic_group_id or item.id, []).append(item)
    diagnostics = [
        UnacceptableGroup(
            client_refs=[i.client_ref for i in members],
            item_count=len(members),
            reason=f"错误 [PROPOSAL_GROUP_UNACCEPTABLE]：提案组 {', '.join(i.client_ref or str(i.ordinal) for i in members)}：{members[0].status_reason}。本次仅检查，未入库。下一步：修正该组片段后重新执行合并命令。",
        )
        for members in groups.values()
    ]
    count = sum(g.item_count for g in diagnostics)
    return ProposalCheckResponse(
        passed=not diagnostics,
        contract_errors=[],
        unacceptable_groups=diagnostics,
        reviewable_count=len(parsed.items) - count,
        unacceptable_count=count,
    )
