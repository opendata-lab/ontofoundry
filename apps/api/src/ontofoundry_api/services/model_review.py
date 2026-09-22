"""Check an agent's modeling result and say what is wrong in words it can use.

Two kinds of problem show up in practice, and they deserve different endings:

*Blocking* — the document cannot become a draft at all (invalid Ossie, or a
draft the model layer rejects). Accepting it is not an option.

*Advisory* — the draft is usable but breaks a convention the prompt asked for.
Observed for real: an agent that returned `Customer`, `Order`, `Product` and
`order_item` in one document, ignoring the snake_case instruction, and no
Chinese display names at all. Losing a working model over that would be worse
than the naming.

Either way the useful move is the same one a reviewer would make: hand back the
specific complaints and let the author fix them. So these messages are written
to be pasted into a prompt — each one names the offending concept and says what
to do, rather than reporting that validation failed.
"""

from __future__ import annotations

import re
from typing import Any

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")

DISPLAY_NAMES_PATH = ("ai_context", "ontofoundry", "display_names")


def _display_names(ontology: dict[str, Any]) -> dict[str, Any]:
    node: Any = ontology
    for key in DISPLAY_NAMES_PATH:
        if not isinstance(node, dict):
            return {}
        node = node.get(key)
    return node if isinstance(node, dict) else {}


def _concept_names(ontology: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in ontology.get("ontology") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("concept") or item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def review_conventions(ontology: dict[str, Any]) -> list[str]:
    """Advisory complaints about a document that already imports cleanly."""
    problems: list[str] = []

    offenders = [name for name in _concept_names(ontology) if not SNAKE_CASE.match(name)]
    if offenders:
        problems.append(
            "以下概念的技术名不是 snake_case，请改为全小写下划线形式（例如 "
            f"Customer → customer）：{'、'.join(sorted(offenders))}"
        )

    display_names = _display_names(ontology)
    if not display_names:
        problems.append(
            "ai_context.ontofoundry.display_names 为空。请为每个概念补中文显示名，"
            '格式为 {"version":"1","display_names":{"customer":"客户"}}；'
            "中文名只放在这里，不要再新建一个中文概念。"
        )
    else:
        missing = [
            name
            for name in _concept_names(ontology)
            if not str(display_names.get(name) or "").strip()
        ]
        if missing:
            problems.append(
                "以下概念缺少中文显示名，请补进 ai_context.ontofoundry.display_names："
                f"{'、'.join(sorted(missing))}"
            )

    return problems


def build_repair_request(problems: list[str], run_token: str, result_path: str) -> str:
    """The follow-up turn that asks the agent to correct its own result.

    It restates the envelope contract because the corrected result goes to a new
    path: reusing the previous round's filename would let the platform read a
    stale file and believe the problems were fixed.
    """
    numbered = "\n".join(f"{index}. {text}" for index, text in enumerate(problems, 1))
    return (
        "[OntoFoundry 结果校验未通过]\n"
        "上一轮的建模结果有以下问题，请逐条修正后重新输出**完整**的本体快照，"
        "不要只输出改动部分：\n\n"
        f"{numbered}\n\n"
        "修正后的结果仍需放入同样的信封：\n"
        "{\n"
        '  "schema_version": "ontofoundry.model-result/v1",\n'
        f'  "run_token": "{run_token}",\n'
        '  "ontology": {"...": "完整 Ossie 文档"}\n'
        "}\n"
        f"并写到 {result_path}。不要修改或覆盖其他轮次的结果文件。"
    )
