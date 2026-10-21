"""Repair messages for rejected core-1 proposal batches."""

from __future__ import annotations


def build_proposal_repair_request(
    problems: list[str], *, run_token: str, work_pack_file: str, repair_used: int
) -> str:
    """Attach actual server diagnostics to the fresh dynamic entry points."""
    from ontofoundry_api.services.dataagent import proposal_instructions

    entry = proposal_instructions(
        run_token=run_token,
        work_pack_file=work_pack_file,
        header={},
        materials=[],
        schema_file="",
        mcp=None,
    )
    return (
        f"模式：建模修复\n{entry}\n累计修正：{repair_used}/2\n"
        "在 modeling/parts/ 已有片段上修改，只改报错指向的片段，再重新合并。\n\n"
        "[服务端实际错误]\n" + "\n".join(problems)
    )
