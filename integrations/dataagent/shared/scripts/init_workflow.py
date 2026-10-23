"""Create the modeling/ workspace skeleton; existing files are never overwritten.

With --prior-plan, the plan confirmed in the previous run (uploaded by the
platform as one JSON bundle) is restored into modeling/ first.
"""

import json
from pathlib import Path

from read_input import table_batches
from runpaths import HintParser, command, relative, usage

ROOT = Path("modeling")
PLAN_TEMPLATE = """场景：全量｜增量｜优化｜小改动（选一个，删去其余）
工作包：{work_pack}
本体为空：{draft_empty}
新增材料：{new_materials}
新增关联表：{new_tables}

## 范围

## 实体或变化清单（全量／增量）或问题清单（优化）
见 modeling/entities.json 或 modeling/issues.json。

## 来源表

## 阶段
- [ ] ①计划 - [ ] ②确认 - [ ] ③抽取 - [ ] ④合并 - [ ] ⑤修正 - [ ] ⑥输出

## 待决定问题
"""


def write_new(path, text):
    if path.exists():
        return False
    path.write_text(text)
    return True


def main():
    parser = HintParser(description="建立 modeling/ 骨架与计划模板；幂等，不覆盖已有文件")
    parser.add_argument("--work-pack", required=True)
    parser.add_argument("--prior-plan", help="平台上传的上一轮已确认计划包")
    args = parser.parse_args()
    try:
        pack = json.loads(Path(args.work_pack).read_bytes())
        # Output filenames are supplied by the platform; never infer them.
        for field in ("result_file", "needs_input_file"):
            if pack.get(field):
                Path(pack[field]).parent.mkdir(parents=True, exist_ok=True)
        for folder in (ROOT, ROOT / "parts", ROOT / "checks", ROOT / "tmp"):
            folder.mkdir(parents=True, exist_ok=True)
        created = []
        if args.prior_plan:
            prior = json.loads(Path(args.prior_plan).read_bytes())
            if prior.get("plan_md") and write_new(ROOT / "plan.md", prior["plan_md"]):
                created.append("plan.md（上一轮计划）")
            for name in ("entities", "issues"):
                if prior.get(name) is not None and write_new(
                    ROOT / f"{name}.json", json.dumps(prior[name], ensure_ascii=False, indent=1)
                ):
                    created.append(f"{name}.json（上一轮计划）")
        facts = pack.get("scenario_facts", {})
        plan = PLAN_TEMPLATE.format(
            work_pack=args.work_pack,
            draft_empty="是" if facts.get("draft_empty") else "否" if "draft_empty" in facts else "未知",
            new_materials="、".join(facts.get("new_material_ids", [])) or "无",
            new_tables="、".join(facts.get("new_table_keys", [])) or "无",
        )
        if write_new(ROOT / "plan.md", plan):
            created.append("plan.md（模板）")
        if write_new(ROOT / "notes.md", "# 证据对照与判断（≤2 KB，上下文压缩后先读）\n"):
            created.append("notes.md")
    except (OSError, ValueError) as exc:
        print(f"初始化失败：{type(exc).__name__}；检查工作包与计划包路径")
        return 1
    print("modeling/ 已就绪" + ("；新建：" + "、".join(created) if created else "；文件均已存在，未覆盖"))
    print(run_paths(args.work_pack, pack, args.prior_plan))
    return 0


def table_commands(tables_file):
    """Ready batches for the linked tables' columns: read each once, nothing re-read."""
    try:
        batches = table_batches(Path(tables_file).read_text()) if tables_file else []
    except (OSError, ValueError, KeyError, TypeError):
        return []
    if not batches:
        return []
    lines = [f"  读表结构（共 {len(batches)} 批，每批读一次，写 03 时不重读）："]
    lines += ["    " + command("read_input.py", tables_file, "--tables", ",".join(b)) for b in batches]
    return lines


def run_paths(work_pack, pack, prior_plan):
    """This run's files and commands; copy them rather than composing paths."""
    lines = ["本轮路径（相对工作区，直接复制）：", f"- 工作包：{work_pack}"]
    for material in pack.get("materials") or []:
        if material.get("path"):
            lines.append(f"- 材料：{material['path']}")
    for label, key in (("表结构", "tables_file"), ("结果", "result_file"), ("待确认", "needs_input_file")):
        if pack.get(key):
            lines.append(f"- {label}：{pack[key]}")
    if prior_plan or pack.get("prior_plan_file"):
        lines.append(f"- 前轮计划：{prior_plan or pack['prior_plan_file']}")
    references = relative(Path(__file__).resolve().parents[1] / "references")
    protocol = f"{references}/examples/protocol"
    lines.append(f"- 技能参考：{references}/")
    lines.append(f"- 模板：概念清单 {protocol}/entities.json；待确认 {protocol}/needs-input-entities.json")
    lines.append(f"- 优化模板：问题清单 {protocol}/issues.json；待选择 {protocol}/needs-input-issues.json")
    lines.append("- 概念清单写 modeling/entities.json，问题清单写 modeling/issues.json（与 plan.md 同级，不放 parts/）")
    lines.append("- 片段写 modeling/parts/，临时文件写 modeling/tmp/；不用 /tmp、绝对路径或 ../，DataAgent 会拦截")
    lines.append("常用命令：")
    lines += ["  " + line for line in usage(work_pack)]
    lines += table_commands(pack.get("tables_file"))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
