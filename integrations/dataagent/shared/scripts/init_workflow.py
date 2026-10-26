"""Create the modeling/ workspace skeleton; existing files are never overwritten.

The user approves the concept or issue list inside the run (the plan card),
so there is no earlier plan to restore.
"""

import json
from pathlib import Path

from read_input import table_batches
from runpaths import HintParser, command, error, notice, relative, usage

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


RUN_MARK = ROOT / ".run_token"
PREVIOUS = ROOT / "previous"


def run_token(pack):
    return str((pack.get("run") or {}).get("run_token") or "")


def archive_previous_parts(pack):
    """Move another run's fragments out of modeling/parts/ before this run starts.

    The DataAgent topic keeps its workspace across turns, so a new request
    (e.g. an incremental change) found the last run's 01–05 fragments and the
    default merge would have resubmitted them. A repair round is the same run
    under a new token and keeps its fragments, so only a fresh run (no repair
    used yet) moves them.
    """
    token = run_token(pack)
    previous = RUN_MARK.read_text().strip() if RUN_MARK.exists() else ""
    repair_used = int((pack.get("execution") or {}).get("repair_used") or 0)
    fragments = sorted((ROOT / "parts").glob("*.json")) if (ROOT / "parts").is_dir() else []
    if not fragments or previous == token or repair_used:
        return None
    target = PREVIOUS / (previous or "unknown")
    for folder in ("parts", "checks"):
        source = ROOT / folder
        if source.is_dir() and any(source.iterdir()):
            (target / folder).mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                item.replace(target / folder / item.name)
    return target


def done(created):
    return ("已新建：" + "、".join(created) + "；其余未完成") if created else "未新建任何文件"


def main():
    parser = HintParser(description="建立 modeling/ 骨架与计划模板；幂等，不覆盖已有文件")
    parser.add_argument("--work-pack", required=True)
    args = parser.parse_args()
    created, step = [], f"读取工作包 {args.work_pack}"
    try:
        pack = json.loads(Path(args.work_pack).read_bytes())
        step = "创建 modeling/ 与输出目录"
        # Output filenames are supplied by the platform; never infer them.
        if pack.get("result_file"):
            Path(pack["result_file"]).parent.mkdir(parents=True, exist_ok=True)
        step = "整理上一轮的片段"
        archived = archive_previous_parts(pack)
        step = "创建 modeling/ 与输出目录"
        for folder in (ROOT, ROOT / "parts", ROOT / "checks", ROOT / "tmp"):
            folder.mkdir(parents=True, exist_ok=True)
        RUN_MARK.write_text(run_token(pack))
        facts = pack.get("scenario_facts", {})
        plan = PLAN_TEMPLATE.format(
            work_pack=args.work_pack,
            draft_empty="是" if facts.get("draft_empty") else "否" if "draft_empty" in facts else "未知",
            new_materials="、".join(facts.get("new_material_ids", [])) or "无",
            new_tables="、".join(facts.get("new_table_keys", [])) or "无",
        )
        step = "写入 modeling/plan.md 与 notes.md"
        if write_new(ROOT / "plan.md", plan):
            created.append("modeling/plan.md（模板）")
        if write_new(ROOT / "notes.md", "# 证据对照与判断（≤2 KB，上下文压缩后先读）\n"):
            created.append("modeling/notes.md")
    except json.JSONDecodeError as exc:
        print(error("JSON_INVALID", f"{step}失败：第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}", done(created),
                    "路径照平台本轮提示复制；文件本身损坏时重新发起本轮", retry=False))
        return 1
    except FileNotFoundError:
        print(error("FILE_NOT_FOUND", f"{step}失败：文件不存在", done(created),
                    "路径照平台本轮提示里的工作包复制"))
        return 1
    except (OSError, ValueError) as exc:
        print(error("INIT_FAILED", f"{step}失败：{type(exc).__name__}", done(created), retry=False))
        return 1
    print("modeling/ 已就绪" + ("；新建：" + "、".join(created) if created else "；文件均已存在，未覆盖"))
    if archived:
        print(notice("PREVIOUS_PARTS_MOVED", f"上一轮的片段与检查报告已移到 {archived}/，本轮从空的 modeling/parts/ 开始",
                     "只写本轮的变化；已入库的定义用 show_element.py 查，不必读该目录"))
    print(run_paths(args.work_pack, pack))
    return 0


def table_commands(tables_file):
    """Ready batches for the linked tables' columns: read each once, nothing re-read."""
    try:
        batches = table_batches(Path(tables_file).read_text()) if tables_file else []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ["  " + notice("TABLES_UNREADABLE", f"表结构 {tables_file} 无法读取（{type(exc).__name__}），未生成读表命令",
                              command("read_input.py", tables_file, "--start", "1", "--end", "40"))]
    if not batches:
        return []
    lines = [f"  读表结构（共 {len(batches)} 批，每批读一次，写 03 时不重读）："]
    lines += ["    " + command("read_input.py", tables_file, "--tables", ",".join(b)) for b in batches]
    return lines


def run_paths(work_pack, pack):
    """This run's files and commands; copy them rather than composing paths."""
    lines = ["本轮路径（相对工作区，直接复制）：", f"- 工作包：{work_pack}"]
    for material in pack.get("materials") or []:
        if material.get("path"):
            lines.append(f"- 材料：{material['path']}")
    for label, key in (("表结构", "tables_file"), ("结果", "result_file")):
        if pack.get(key):
            lines.append(f"- {label}：{pack[key]}")
    references = relative(Path(__file__).resolve().parents[1] / "references")
    protocol = f"{references}/examples/protocol"
    lines.append(f"- 技能参考：{references}/")
    lines.append(f"- 模板：概念清单 {protocol}/entities.json；问题清单 {protocol}/issues.json（计划获批准后再写）")
    lines.append("- 概念清单写 modeling/entities.json，问题清单写 modeling/issues.json（与 plan.md 同级，不放 parts/）")
    lines.append("- 片段写 modeling/parts/，临时文件写 modeling/tmp/；业务文件用工作区相对路径，不用 /tmp 或 ../（DataAgent 会拦截），技能脚本照下面的命令写")
    lines.append("常用命令：")
    lines += ["  " + line for line in usage(work_pack)]
    lines += table_commands(pack.get("tables_file"))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
