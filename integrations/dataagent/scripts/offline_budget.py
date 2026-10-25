"""Offline byte budgets and usage conservation. No model or network calls."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SELECTED_EXAMPLES_LIMIT = 5600
# The plan run reads every material in full (7.4 KB in the fixture), so the
# plan step now reads only the routing entry and plan.md (about 15.6 KB in total).
PLAN_ROUTE_LIMIT = 15500
EXTRACT_ROUTE_LIMIT = 36000
INCREMENTAL_ROUTE_LIMIT = 30000
INCREMENTAL_QUERIES = [
    ["object_type:refund", "dataset:refunds", "dataset:orders"],
    [f"property:refund.{name}" for name in ("refund_no", "order_no", "refund_date", "refund_amount", "reason")],
]

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE / "shared"
ROOT = BASE.parents[1]
import sys
sys.path.insert(0, str(SKILL / "scripts"))


def resource(path):
    """Locate the sole source of a runtime reference or offline fixture."""
    if path.startswith("tests/"):
        return BASE / path
    if path == "SKILL.md":
        return BASE / "skills/ontology-discovery/SKILL.md"
    shared = SKILL / path
    if shared.exists():
        return shared
    skill = "entity-extraction" if path in ("references/extract-facts.md", "references/steps/facts.md") else "ontology-discovery"
    return BASE / "skills" / skill / path
EXPECTED = {
    "task_dd4fe3ae4f894cc983abeccf": (201573, 1175808, 22794, 44),
    "task_fac43c47c66b4b2f939e08c9": (124881, 1011584, 36904, 39),
    "task_14d60faed1a541afbd4db995": (7081, 94592, 5339, 6),
    "task_3e2d92eda8334b74936adc44": (41877, 457728, 20015, 20),
}


def purpose(task, turn):
    if task not in EXPECTED:
        return "无法分类"
    suffix = task.removeprefix("task_")[:4]
    if suffix == "dd4f":
        if turn <= 3:
            return "环境探索"
        if turn in [4, 17, 18, 19, 20]:
            return "技能"
        if turn in [5, 14, 15, 16]:
            return "材料上下文"
        if turn == 13:
            return "混合规划"
        if turn == 44:
            return "零用量终止"
        return "Schema"
    if suffix == "14d6":
        return "最终说明" if turn == 6 else "材料上下文"
    if suffix == "3e2d":
        if turn <= 9:
            return "材料上下文"
        if turn <= 12:
            return "Schema"
        if turn <= 15:
            return "材料上下文"
        if turn <= 17:
            return "写结果"
        if turn <= 19:
            return "检查"
        return "最终说明"
    if suffix == "fac4":
        if turn == 3:
            return "环境探索"
        if turn in [*range(10, 20), 27, 30]:
            return "Schema"
        if turn in [20, 21, 22, 23]:
            return "MCP"
        if 31 <= turn <= 33:
            return "写结果"
        if 34 <= turn <= 38:
            return "检查"
        if turn == 39:
            return "最终说明"
        return "材料上下文"
    return "无法分类"


def trace_rows(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        event_id, turn, event, raw = line.split("\t", 3)
        if event != "usage.updated":
            continue
        # PostgreSQL COPY text doubles backslashes. Only usage is retained.
        data = json.loads(raw.replace(chr(92) * 2, chr(92)))
        usage = data["usage"]
        rows.append(
            {
                "event_id": int(event_id),
                "turn": int(turn),
                "U": usage.get("input_tokens", 0),
                "C": usage.get("cache_read_input_tokens", 0),
                "O": usage.get("output_tokens", 0),
            }
        )
    return rows


def summarize(task, rows):
    totals = {k: sum(row[k] for row in rows) for k in ("U", "C", "O")}
    totals["I"] = totals["U"] + totals["C"]
    categories = defaultdict(lambda: {k: 0 for k in ("U", "C", "O", "I", "turns")})
    fallbacks = []
    previous = None
    for row in rows:
        category = categories[purpose(task, row["turn"])]
        for key in ("U", "C", "O"):
            category[key] += row[key]
        category["I"] += row["U"] + row["C"]
        category["turns"] += 1
        if previous and row["C"] < previous["C"] * 0.8 and row["U"] >= 5000:
            fallbacks.append(row["turn"])
        previous = row
    expected = EXPECTED.get(task)
    return {
        "task": task,
        **totals,
        "runtime_turns": max((r["turn"] for r in rows), default=0),
        "usage_turns": sum(bool(r["U"] + r["C"] + r["O"]) for r in rows),
        "categories": dict(categories),
        "cache_fallback_candidates": fallbacks,
        "conserved": expected is None
        or (totals["U"], totals["C"], totals["O"]) == expected[:3],
        "uncertainty": "按整轮主用途归因，含历史重放；回退不证明压缩或过期。阶段收益与其子集不能相加；新生成和校验成本未模拟。",
    }


def measure(data):
    if isinstance(data, str):
        data = data.encode()
    return {
        "bytes": len(data),
        "characters": len(data.decode("utf-8")),
        "bytes/3": round(len(data) / 3, 1),
        "range_bytes/4_to_bytes/2": [round(len(data) / 4, 1), round(len(data) / 2, 1)],
        "sha256": hashlib.sha256(data).hexdigest(),
        "lines": len(data.splitlines()),
    }


def byte_report():
    from ontofoundry_api.services.dataagent import (
        build_turn_prompt,
        proposal_instructions,
    )
    from ontofoundry_api.services.modeling_input import (
        build_work_pack,
        encode,
        execution_input,
        material_index,
    )
    from read_input import render_lines, render_tables

    context = json.loads(resource("tests/fixtures/budget-context.json").read_bytes())
    context["execution"] = execution_input(context["run"]["run_token"])
    materials = []
    for index in (1, 2):
        content = resource(f"tests/fixtures/budget-material-{index}.md").read_bytes()
        materials.append(
            material_index(
                {
                    "id": f"55555555-5555-4555-8555-{index:012d}",
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
                content,
                f"inputs/material-{index}.md",
            )
        )
    pack, pages = build_work_pack(
        context,
        materials,
        context_file="inputs/context.json",
        schema_file="inputs/schema.json",
    )
    if pages:
        raise ValueError("同规模预算样本不应分页")
    prompt = build_turn_prompt(
        "基于六份数据集和两份材料生成合法范围的完整提案。",
        mode="model",
        workspace_id=context["run"]["workspace_id"],
        session_id=context["run"]["session_id"],
        context_file="inputs/context.json",
        context_bytes=len(encode(context)),
        material_files=[],
        run_token=context["run"]["run_token"],
        proposal_prompt=proposal_instructions(
            run_token=context["run"]["run_token"],
            header=context["run"],
            materials=materials,
            schema_file="inputs/schema.json",
            mcp=None,
            work_pack_file="inputs/work-pack.json",
        ),
    )
    examples = ["facts", "mapping", "metrics", "rules"]
    selected = b"".join(
        resource(f"references/examples/{name}.json").read_bytes() for name in examples
    )
    agent_file = (
        ROOT / "integrations/dataagent/agents/agent_ontofoundry.md"
    ).read_text()
    system_body = agent_file.split("系统提示词：", 1)[1].strip() + "\n"
    common = {
        "技能入口": "SKILL.md",
        "速查": "references/quick-reference.md",
        "原则": "references/principles.md",
        "计划步骤": "references/steps/plan.md",
    }
    method_paths = [
        "extract-types",
        "extract-mappings",
        "extract-metrics-rules",
        "extract-facts",
    ]
    decisions = {}
    for name in method_paths:
        body = resource(f"references/{name}.md").read_text()
        lines = body.splitlines()
        start = lines.index("## 决策") + 1
        end = next(
            (i for i in range(start, len(lines)) if lines[i].startswith("## ")),
            len(lines),
        )
        decisions[name] = render_lines(body, start, end).encode()
    method_bytes = b"".join(decisions.values())
    components = {
        "平台提示": measure(prompt),
        "已知Agent提示": measure(system_body),
        **{
            label: measure(resource(path).read_bytes())
            for label, path in common.items()
        },
        "工作包": measure(encode(pack)),
        "选中示例": measure(selected),
        "方法决策段": measure(method_bytes),
        "带原行号材料": measure(
            b"".join(
                render_lines(
                    resource(f"tests/fixtures/budget-material-{i}.md").read_text()
                ).encode()
                for i in (1, 2)
            )
        ),
    }
    # The plan step is read only in the plan run, not by extraction or edits.
    common_bytes = sum(components[k]["bytes"] for k in common if k != "计划步骤")
    steps = {
        name: len(resource(f"references/steps/{file}").read_bytes())
        for name, file in (("抽取步骤", "extract.md"), ("增量步骤", "incremental.md"), ("收尾步骤", "finish.md"), ("实例步骤", "facts.md"))
    }
    limits = {
        "系统正文": (len(system_body.encode()), 450),
        "每轮提示": (len(prompt.encode()), 600),
        # Entries only route; each run reads the one step file it needs.
        "技能入口": (components["技能入口"]["bytes"], 1100),
        "速查": (components["速查"]["bytes"], 1800),
        "原则": (components["原则"]["bytes"], 2400),
        "计划步骤": (components["计划步骤"]["bytes"], 1500),
        "优化步骤": (len(resource("references/steps/optimize.md").read_bytes()), 900),
        "抽取步骤": (steps["抽取步骤"], 1700),
        "增量步骤": (steps["增量步骤"], 1400),
        "收尾步骤": (steps["收尾步骤"], 900),
        "实例步骤": (steps["实例步骤"], 2800),
        "共同必读": (common_bytes, 9600),
        "工作包": (len(encode(pack)), 6500),
        # Examples carry display_name so the agent learns to fill Chinese names.
        "选中示例": (len(selected), SELECTED_EXAMPLES_LIMIT),
        "方法决策段": (len(method_bytes), 6000),
        "核心语义": (len(resource("references/core-model.md").read_bytes()), 4500),
    }
    for name, limit in zip(method_paths, [3000, 3000, 3200, 2500]):
        limits[name] = (len(resource(f"references/{name}.md").read_bytes()), limit)
    for name in ("entity-extraction", "semantic-grounding"):
        limits[name + "入口"] = (len((BASE / "skills" / name / "SKILL.md").read_bytes()), 1100)
    routes = {}
    for task, method, sample in [
        ("名称修改", None, "operations"),
        ("单主题映射", "extract-mappings", "mapping"),
        ("单主题实例", "extract-facts", "facts"),
        ("单主题指标规则", "extract-metrics-rules", "metrics"),
    ]:
        extra = len(decisions[method]) if method else 0
        example_bytes = len(resource(f"references/examples/{sample}.json").read_bytes())
        # Reuse the same six-table fixture as a conservative, comparable route.
        route_total = (
            len(system_body.encode())
            + len(prompt.encode())
            + common_bytes
            + len(encode(pack))
            + components["带原行号材料"]["bytes"]
            + extra
            + example_bytes
            + steps["增量步骤"]
            + steps["收尾步骤"]
        )
        routes[task] = {
            "bytes": route_total,
            "pass": route_total <= 36000,
            "scope": "同一完整工作包和材料，不裁剪；实际完整目标回读量按任务另计",
        }
    # The plan route is retained for comparison. Extraction now has its own
    # complete input fixture, including prior plan, material and physical columns.
    fixed = len(system_body.encode()) + len(prompt.encode()) + len(encode(pack))
    stepwise = {
        "第一步（计划）": (
            fixed
            + components["技能入口"]["bytes"]
            + components["计划步骤"]["bytes"]
            + components["带原行号材料"]["bytes"],
            PLAN_ROUTE_LIMIT,
        ),
    }
    for task, (size, limit) in stepwise.items():
        routes[task] = {
            "bytes": size,
            "limit": limit,
            "pass": size <= limit,
            "scope": "计划轮首阶段完整材料与协议入口，表目录由工作包给出",
        }
    fixture = resource("tests/fixtures/extract-retail")
    extract_context = json.loads((fixture / "context.json").read_bytes())
    extract_material = (fixture / "material.md").read_bytes()
    extract_materials = [material_index(
        {"id": "0b2f2b9b-938b-4452-8a7a-45587024538d", "sha256": hashlib.sha256(extract_material).hexdigest()},
        extract_material, "inputs/retail-material.md",
    )]
    extract_tables = json.loads((fixture / "tables.json").read_bytes())["tables"]
    extract_pack, extract_pages = build_work_pack(
        extract_context, extract_materials,
        context_file="inputs/context.json", schema_file="inputs/schema.json",
        tables=extract_tables, tables_file="inputs/tables.json",
        prior_plan_file="inputs/prior-plan.json",
        scenario_facts={"draft_empty": True},
    )
    if extract_pages:
        raise ValueError("抽取预算样本不应分页")
    extract_prompt = build_turn_prompt(
        "可以，商品改名为‘商品 SKU’，其余照旧。", mode="model",
        workspace_id=extract_context["run"]["workspace_id"],
        session_id=extract_context["run"]["session_id"], context_file="inputs/context.json",
        context_bytes=len(encode(extract_context)), material_files=[],
        run_token=extract_context["run"]["run_token"],
        proposal_prompt=proposal_instructions(
            run_token=extract_context["run"]["run_token"], header=extract_context["run"],
            materials=extract_materials, schema_file="inputs/schema.json", mcp=None,
            work_pack_file="inputs/work-pack.json",
        ),
    )
    kit = SKILL / "references/extract-kit"
    extract_inputs = {
        "已知Agent提示": system_body.encode(), "平台提示": extract_prompt.encode(),
        "技能入口": resource("SKILL.md").read_bytes(),
        "抽取步骤": resource("references/steps/extract.md").read_bytes(),
        "收尾步骤": resource("references/steps/finish.md").read_bytes(),
        "工作包": encode(extract_pack),
        "带原行号材料": (render_lines(extract_material.decode()) + "\n").encode(),
        "前轮计划": (fixture / "prior-plan.json").read_bytes(),
        "表结构": (render_tables(json.dumps({"tables": extract_tables}), ",".join(t["key"] for t in extract_tables)) + "\n").encode(),
        "原则": resource("references/principles.md").read_bytes(),
        **{f"写法包/{name}": (kit / name).read_bytes() for name in ["guide.md", "values.json", "01.json", "02.json", "03.json", "04.json", "05.json"]},
    }
    extract_components = {name: measure(data) for name, data in extract_inputs.items()}
    extract_bytes = sum(c["bytes"] for c in extract_components.values())
    for name, data in extract_inputs.items():
        limits[f"抽取单次/{name}"] = (len(data), 8192)
    routes["第二步（抽取）"] = {
        "bytes": extract_bytes, "limit": EXTRACT_ROUTE_LIMIT,
        "pass": extract_bytes <= EXTRACT_ROUTE_LIMIT,
        "components": extract_components,
        "scope": "虚构星河零售：工作包＋全部带行号材料＋前轮计划＋五表结构＋原则＋完整图书馆写法包（与验收业务分离）；refunds 无列",
        "estimated_rounds": {
            "normal": [9, 11], "two_repairs": [13, 15],
            "first_part_by": [3, 4],
            "stages": {"输入与包": [2, 3], "写片段与即检": [4, 5], "合并与说明": [2, 3], "每次修正增加": [2, 2]},
            "basis": "可执行路径估计，没有模型行为或概率分布实测",
        },
    }
    from show_element import ElementIndex, bounded

    incremental_context = json.loads((fixture / "v1-context.json").read_bytes())
    incremental_tables = json.loads((fixture / "tables-supplemented.json").read_bytes())["tables"]
    incremental_pack, incremental_pages = build_work_pack(
        incremental_context, extract_materials,
        context_file="inputs/context.json", schema_file="inputs/schema.json",
        tables=incremental_tables, tables_file="inputs/tables.json",
        scenario_facts={"draft_empty": False},
    )
    incremental_pack["index_pages"] = [f"inputs/incremental-index-{i}.json" for i in range(len(incremental_pages))]
    incremental_prompt = build_turn_prompt(
        "refunds 表已经同步，请补齐退款：退款的映射、退款金额和退款率指标。", mode="model",
        workspace_id=incremental_context["run"]["workspace_id"],
        session_id=incremental_context["run"]["session_id"], context_file="inputs/context.json",
        context_bytes=len(encode(incremental_context)), material_files=[],
        run_token=incremental_context["run"]["run_token"],
        proposal_prompt=proposal_instructions(
            run_token=incremental_context["run"]["run_token"], header=incremental_context["run"],
            materials=extract_materials, schema_file="inputs/schema.json", mcp=None,
            work_pack_file="inputs/work-pack.json",
        ),
    )
    incremental_inputs = {
        "已知Agent提示": system_body.encode(), "平台提示": incremental_prompt.encode(),
        "技能入口": resource("SKILL.md").read_bytes(),
        "增量步骤": resource("references/steps/incremental.md").read_bytes(),
        "收尾步骤": resource("references/steps/finish.md").read_bytes(),
        "工作包": encode(incremental_pack),
        "带原行号材料": extract_inputs["带原行号材料"],
        "表结构": (render_tables(json.dumps({"tables": incremental_tables}), ",".join(t["key"] for t in incremental_tables)) + "\n").encode(),
        # The incremental step reads only the guide and the update example.
        **{f"写法包/{name}": (kit / name).read_bytes() for name in ("incremental.md", "update.json")},
        # Targets are looked up by name with show_element, so index pages stay unread.
    }
    index = ElementIndex(incremental_context)
    for i, selectors in enumerate(INCREMENTAL_QUERIES):
        value, status = index.query(selectors)
        if status:
            raise ValueError("增量预算查询必须精确命中")
        output = bounded(value)
        if "elements" not in json.loads(output):
            raise ValueError("预算查询须拆为有界的完整元素输出")
        incremental_inputs[f"已有元素/{i}"] = (output + "\n").encode()
    incremental_components = {name: measure(data) for name, data in incremental_inputs.items()}
    incremental_bytes = sum(c["bytes"] for c in incremental_components.values())
    for name, data in incremental_inputs.items():
        limits[f"增量单次/{name}"] = (len(data), 8192)
    routes["增量（退款补齐）"] = {
        "bytes": incremental_bytes, "limit": INCREMENTAL_ROUTE_LIMIT,
        "pass": incremental_bytes <= INCREMENTAL_ROUTE_LIMIT,
        "components": incremental_components,
        "scope": "离线零售 v1＋独立图书馆写法：完整工作包（索引页不读，按名称精确查询）、全部材料、六表结构、提示、增量指南、update 和两组精确查询；不读 context／源码／Schema，无前轮计划；名称删除另加 edit",
        "optional_edit_bytes": (kit / "edit.json").stat().st_size,
        "estimated_rounds": {
            "normal": [6, 8], "two_repairs": [10, 12], "first_part_by": [3, 4],
            "stages": {"输入与查询及包": [2, 3], "写片段与即检": [2, 2], "合并与说明": [2, 3]},
            "basis": "可执行路径估计，没有模型行为实测；分页、歧义重查增加轮数",
        },
    }
    # The retail fixtures contain definitions, not concrete instances. Dynamic
    # selection does not load entity-extraction for those routes. This separate
    # document fixture counts both complete skill entries and all shared inputs.
    from ontofoundry_api.domain.snapshot import empty_snapshot
    from ontofoundry_api.domain.canonical import snapshot_sha256
    combined_context = json.loads(resource("tests/fixtures/context.json").read_bytes())
    combined_context["draft"] = empty_snapshot(combined_context["run"]["workspace_id"])
    combined_context["element_hashes"] = {}
    combined_context["run"]["source_draft_sha256"] = snapshot_sha256(combined_context["draft"])
    combined_context["execution"] = execution_input(combined_context["run"]["run_token"])
    combined_material = resource("tests/fixtures/material.md").read_bytes()
    combined_materials = [material_index(
        {"id": "11111111-1111-4111-8111-111111111111", "sha256": hashlib.sha256(combined_material).hexdigest()},
        combined_material, "inputs/material.md",
    )]
    combined_pack, combined_pages = build_work_pack(
        combined_context, combined_materials,
        context_file="inputs/context.json", schema_file="inputs/schema.json",
        prior_plan_file="inputs/combined-plan.json",
    )
    if combined_pages:
        raise ValueError("组合预算样本不应分页")
    combined_prompt = build_turn_prompt(
        "确认员工类型与汇报关系，并抽取材料中的实例。", mode="model",
        workspace_id=combined_context["run"]["workspace_id"],
        session_id=combined_context["run"]["session_id"], context_file="inputs/context.json",
        context_bytes=len(encode(combined_context)), material_files=[],
        run_token=combined_context["run"]["run_token"],
        proposal_prompt=proposal_instructions(
            run_token=combined_context["run"]["run_token"], header=combined_context["run"],
            materials=combined_materials, schema_file="inputs/schema.json", mcp=None,
            work_pack_file="inputs/work-pack.json",
        ),
    )
    combined_reads = {
        "已知Agent提示": system_body.encode(), "平台提示": combined_prompt.encode(),
        "技能入口": resource("SKILL.md").read_bytes(),
        "实例技能入口": (BASE / "skills/entity-extraction/SKILL.md").read_bytes(),
        "抽取步骤": resource("references/steps/extract.md").read_bytes(),
        "实例步骤": resource("references/steps/facts.md").read_bytes(),
        "收尾步骤": resource("references/steps/finish.md").read_bytes(),
        "工作包": encode(combined_pack), "带原行号材料": render_lines(combined_material.decode()).encode(),
        "前轮计划": resource("tests/fixtures/combined-plan.json").read_bytes(),
        "原则": resource("references/principles.md").read_bytes(),
        "实例方法": resource("references/extract-facts.md").read_bytes(),
        "实例正例": resource("references/examples/facts.json").read_bytes(),
        **{f"写法包/{name}": (kit / name).read_bytes() for name in
           ("guide.md", "values.json", "01.json", "02.json", "03.json", "04.json", "05.json")},
    }
    combined_bytes = sum(len(value) for value in combined_reads.values())
    routes["定义与实例组合"] = {
        "bytes": combined_bytes, "limit": EXTRACT_ROUTE_LIMIT,
        "pass": combined_bytes <= EXTRACT_ROUTE_LIMIT and all(len(value) <= 8192 for value in combined_reads.values()),
        "components": {key: measure(value) for key, value in combined_reads.items()},
        "scope": "具体文档陈述：两技能入口、完整工作包／材料／前轮计划、原则、固定包全量及实例方法和正例；不裁剪既有路线样本",
    }
    total = sum(v["bytes"] for v in components.values())
    from ontofoundry_api.contracts.proposals import result_schema

    schema = json.dumps(result_schema(), ensure_ascii=False).encode()
    return {
        "components": components,
        "agent_configuration_file": measure(agent_file),
        "system_body_lines": len(system_body.splitlines()),
        "common_required_bytes": common_bytes,
        "limits": {
            k: {"bytes": size, "limit": limit, "pass": size <= limit}
            for k, (size, limit) in limits.items()
        },
        "all_limits_pass": all(size <= limit for size, limit in limits.values())
        and all(route["pass"] for route in routes.values()),
        "routes": routes,
        "first_read_bytes": total,
        "first_read_bytes/3": round(total / 3, 1),
        "first_read_target": 12000,
        "first_read_pass": total <= 36000,
        "work_pack_pass": len(encode(pack)) <= 8192,
        "skill_and_reference_pass": common_bytes <= 9600,
        "selected_examples_pass": len(selected) <= SELECTED_EXAMPLES_LIMIT,
        "subsequent_new_read_budget": {
            "bytes": 24000,
            "bytes/3": 8000,
            "status": "上限策略；实际读取依任务与真实运行核对，非实测",
        },
        "upload": {
            "context": measure(encode(context)),
            "schema": measure(schema),
            "work_pack": measure(encode(pack)),
            "materials": measure(
                b"".join(
                    resource(f"tests/fixtures/budget-material-{i}.md").read_bytes()
                    for i in (1, 2)
                )
            ),
            "mcp": "N/A：虚构空发布版本；实际凭据不计入模型默认读取",
        },
        "unknown_system_and_tool_definitions": "未知：DataAgent 注入的系统包装、工具定义与压缩历史，未假装计入；需真实运行补采。",
        "method": "UTF-8 bytes/3 中心估计，bytes/4–bytes/2 区间，非模型 tokenizer；虚构六 Dataset、两份共7351 B材料，不重放真实业务名。",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    traces = []
    for task in EXPECTED:
        path = args.trace_dir / f"trace-{task}.tsv" if args.trace_dir else None
        if path and path.exists():
            rows = trace_rows(path)
            if task.startswith("task_dd4f") and max(r["turn"] for r in rows) == 43:
                rows.append({"turn": 44, "U": 0, "C": 0, "O": 0})
            traces.append(summarize(task, rows))
        else:
            traces.append(
                {"task": task, "trace": "N/A：未提供 trace，不能分类或推算收益"}
            )
    report = {
        "budget": byte_report(),
        "traces": traces,
        "runtime_governance": "未调用相邻运行时或模型压缩器；折叠、分页、sticky generation 仍待真实运行验证。",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)
    return int(
        not report["budget"]["first_read_pass"]
        or not report["budget"]["all_limits_pass"]
        or any(not route["pass"] for route in report["budget"]["routes"].values())
        or any(t.get("conserved") is False for t in traces)
    )


if __name__ == "__main__":
    raise SystemExit(main())
