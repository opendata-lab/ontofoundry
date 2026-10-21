"""Create the modeling/ workspace skeleton; existing files are never overwritten.

With --prior-plan, the plan confirmed in the previous run (uploaded by the
platform as one JSON bundle) is restored into modeling/ first.
"""

import argparse
import json
from pathlib import Path

ROOT = Path("modeling")
PLAN_TEMPLATE = """场景：全量｜增量｜优化｜小改动（选一个，删去其余）
工作包：{work_pack}
本体为空：{draft_empty}
新增材料：{new_materials}
新增关联表：{new_tables}

## 范围

## 实体或变化清单（全量／增量）或问题清单（优化）
见 entities.json 或 issues.json。

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
    parser = argparse.ArgumentParser(description="建立 modeling/ 骨架与计划模板；幂等，不覆盖已有文件")
    parser.add_argument("--work-pack", required=True)
    parser.add_argument("--prior-plan", help="平台上传的上一轮已确认计划包")
    args = parser.parse_args()
    try:
        pack = json.loads(Path(args.work_pack).read_bytes())
        # Output filenames are supplied by the platform; never infer them.
        for field in ("result_file", "needs_input_file"):
            if pack.get(field):
                Path(pack[field]).parent.mkdir(parents=True, exist_ok=True)
        for folder in (ROOT, ROOT / "parts", ROOT / "checks"):
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
