"""Repair messages for rejected core-1 proposal batches."""

from __future__ import annotations


def build_proposal_repair_request(
    problems: list[str], header: dict, result_path: str
) -> str:
    """Repair turn for an ontofoundry.proposals/v1 result that was rejected."""
    import json

    numbered = "\n".join(f"{index}. {text}" for index, text in enumerate(problems, 1))
    return (
        "[OntoFoundry 提案结果校验未通过]\n"
        "上一轮的提案结果整份被拒收，原因如下。请修正后重新输出**全部**提案：\n\n"
        f"{numbered}\n\n"
        "结果头部必须逐字使用以下值（run_token 已更换）：\n"
        + json.dumps(header, ensure_ascii=False, indent=2)
        + f"\n并写到 {result_path}。不要修改或覆盖其他轮次的结果文件。"
    )
