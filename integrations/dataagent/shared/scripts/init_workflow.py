"""Create the modeling/ workspace skeleton; existing files are never overwritten.

Earlier work in modeling/ is kept only while it can still be valid: within the
same run, or when the platform marks this run as a continuation (work pack
run.resume: same baseline, nothing stored). Everything else is archived so the
default merge never resubmits another run's fragments. How to continue is the
agent's decision (references/steps/resume.md), not this script's.
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

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
LATEST_CHECK = ROOT / "checks" / "latest-content-check.json"
# Everything one run's modeling depends on; kept or archived together so a
# plan or scope file never outlives the fragments it describes.
WORK_FILES = ("parts", "checks", "plan.md", "notes.md", "entities.json", "issues.json")


def run_token(pack):
    return str((pack.get("run") or {}).get("run_token") or "")


def resume_tokens(pack):
    """Every earlier run of the unbroken chain whose work may be continued."""
    resume = (pack.get("run") or {}).get("resume") or {}
    if not isinstance(resume, dict):
        return []
    tokens = [str(t) for t in resume.get("previous_run_tokens") or [] if t]
    single = str(resume.get("previous_run_token") or "")
    return tokens or ([single] if single else [])


def has_work():
    for name in WORK_FILES:
        path = ROOT / name
        if path.is_file() or (path.is_dir() and any(path.iterdir())):
            return True
    return False


def archive_work(previous):
    """Move every work file of an earlier run to a new modeling/previous/<token>/."""
    target, number = PREVIOUS / (previous or "unknown"), 1
    while target.exists():  # never mix two runs' files in one folder
        number += 1
        target = PREVIOUS / f"{previous or 'unknown'}-{number}"
    for name in WORK_FILES:
        source = ROOT / name
        if source.is_dir() and any(source.iterdir()):
            (target / name).mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                item.replace(target / name / item.name)
        elif source.is_file():
            target.mkdir(parents=True, exist_ok=True)
            source.replace(target / name)
    return target


def settle_previous_work(pack, restart=False):
    """Return ("same" | "resume" | "archived" | "fresh", archive dir or None)."""
    token = run_token(pack)
    previous = RUN_MARK.read_text().strip() if RUN_MARK.exists() else ""
    if not has_work():
        return "fresh", None
    if restart:
        # By now this run has usually claimed the files; they are the earlier run's work.
        earlier = (resume_tokens(pack) or [previous])[-1] if previous == token else previous
        return "archived", archive_work(earlier or token)
    if previous == token:
        return "same", None
    if previous and previous in resume_tokens(pack):
        return "resume", None
    return "archived", archive_work(previous)


def point_plan_at(work_pack):
    """A kept plan names the earlier run's work pack, whose submit credential
    is no longer current; this run's commands must use its own."""
    plan = ROOT / "plan.md"
    if plan.is_file():
        text = plan.read_text()
        plan.write_text(re.sub(r"(?m)^工作包：.*$", lambda _: f"工作包：{work_pack}", text, count=1))


def resume_summary():
    """What the earlier run left, so the agent can decide without opening files."""
    lines = ["上一轮未入库，基线未变，已保留其成果："]
    parts = sorted((ROOT / "parts").glob("*.json")) if (ROOT / "parts").is_dir() else []
    newest = 0.0
    for part in parts:
        newest = max(newest, part.stat().st_mtime)
        try:
            items = json.loads(part.read_bytes())
            kinds = Counter(i.get("target_kind", "?") for i in items if isinstance(i, dict))
            detail = "、".join(f"{k} {n}" for k, n in kinds.most_common())
            lines.append(f"- {relative(part)}：{len(items)} 条" + (f"（{detail}）" if detail else ""))
        except (OSError, ValueError, TypeError):
            lines.append(f"- {relative(part)}：无法读取（按缺失处理）")
    if not parts:
        lines.append("- 片段：无")
    for name in ("entities.json", "issues.json", "plan.md", "notes.md"):
        if (ROOT / name).is_file():
            extra = ""
            if name == "entities.json":
                try:
                    extra = f"（范围 {len(json.loads((ROOT / name).read_bytes()).get('items') or [])} 项）"
                except (OSError, ValueError, AttributeError):
                    extra = "（无法读取）"
            lines.append(f"- modeling/{name}：有{extra}")
    if LATEST_CHECK.is_file():
        try:
            report = json.loads(LATEST_CHECK.read_bytes())
            errors = report.get("errors") or []
            stale = "；之后片段又改过，报告可能过时，先重新检查" if newest > LATEST_CHECK.stat().st_mtime else ""
            lines.append(f"- 最近一次内容检查（{report.get('source', '?')}）：{len(errors)} 个错误{stale}；全文 {relative(LATEST_CHECK)}")
            for error_item in errors[:3]:
                text = error_item.get("message") if isinstance(error_item, dict) else str(error_item)
                lines.append("  · " + " ".join(str(text).split())[:200])
        except (OSError, ValueError):
            lines.append(f"- 最近一次内容检查：{relative(LATEST_CHECK)}（无法读取）")
    else:
        lines.append("- 最近一次内容检查：无")
    return "\n".join(lines)


def done(created):
    return ("已新建：" + "、".join(created) + "；其余未完成") if created else "未新建任何文件"


def main():
    parser = HintParser(description="建立 modeling/ 骨架与计划模板；幂等，不覆盖已有文件")
    parser.add_argument("--work-pack", required=True)
    parser.add_argument("--restart", action="store_true", help="放弃保留的成果：整体归档后从头开始")
    args = parser.parse_args()
    created, step = [], f"读取工作包 {args.work_pack}"
    try:
        pack = json.loads(Path(args.work_pack).read_bytes())
        # The work pack lives in <workspace>/uploads/; work there even when
        # started from the read-only skill folder.
        uploads = Path(args.work_pack).resolve().parent
        if uploads.name == "uploads":
            os.chdir(uploads.parent)
        step = "创建 modeling/ 与输出目录"
        # Output filenames are supplied by the platform; never infer them.
        if pack.get("result_file"):
            Path(pack["result_file"]).parent.mkdir(parents=True, exist_ok=True)
        step = "整理上一轮的成果"
        state, archived = settle_previous_work(pack, restart=args.restart)
        if state == "resume":
            point_plan_at(args.work_pack)
        step = "创建 modeling/ 与输出目录"
        for folder in (ROOT, ROOT / "parts", ROOT / "checks", ROOT / "tmp"):
            folder.mkdir(parents=True, exist_ok=True)
        RUN_MARK.write_text(run_token(pack))
        facts = pack.get("scenario_facts", {})
        plan = PLAN_TEMPLATE.format(
            work_pack=args.work_pack,
            draft_empty="是" if facts.get("draft_empty") else "否" if "draft_empty" in facts else "未知",
            new_materials="、".join(facts.get("new_material_ids", [])) or "无",
            new_tables=str(facts.get("new_table_count", 0)) + " 张",
        )
        step = "写入 modeling/plan.md 与 notes.md"
        if write_new(ROOT / "plan.md", plan):
            created.append("modeling/plan.md（模板）")
        # No byte limit: a hard number made the agent spend calls trimming bytes.
        if write_new(ROOT / "notes.md", "# 证据对照与判断（只记要点，上下文压缩后先读）\n"):
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
    if state == "resume":
        steps = relative(Path(__file__).resolve().parents[1] / "references" / "steps")
        print(resume_summary())
        print(notice("PREVIOUS_WORK_KEPT", "本轮可在上一轮成果上继续",
                     f"先读 {steps}/resume.md，按用户这条消息决定：修正后提交、补写缺少的部分、按新要求改受影响的部分，或运行 init_workflow.py --restart 从头开始"))
    elif archived:
        print(notice("PREVIOUS_PARTS_MOVED", f"上一轮的成果已移到 {archived}/，本轮从空的 modeling/ 开始",
                     "只写本轮的变化；已入库的定义用 show_element.py 查，不必读该目录"))
    print(run_paths(args.work_pack, pack))
    return 0


def run_paths(work_pack, pack):
    """This run's files and commands; copy them rather than composing paths."""
    lines = ["本轮路径（相对工作区，直接复制）：", f"- 工作包：{work_pack}"]
    for material in pack.get("materials") or []:
        if material.get("path") and material.get("from_request"):
            lines.append(f"- 用户消息原文：{material['path']}（id {material.get('id', '?')}；内容就是本轮或之前的消息，引证时用这个 id，不必再读）")
        elif material.get("path"):
            lines.append(f"- 材料：{material['path']}（id {material.get('id', '?')}，{material.get('lines', '?')} 行）")
    for table in pack.get("tables") or []:
        if isinstance(table, dict) and table.get("key"):
            lines.append(f"- 表 {table['key']}：{table.get('table', '')} {table.get('comment') or ''}".rstrip())
    lines.append("- 本轮只用以上材料与表结构，没有业务库查询通道；MCP 访问文件只供 prepare_result 使用，不打开、不打印")
    for label, key in (("表结构", "tables_file"), ("结果", "result_file")):
        if pack.get(key):
            lines.append(f"- {label}：{pack[key]}")
    references = relative(Path(__file__).resolve().parents[1] / "references")
    protocol = f"{references}/examples/protocol"
    lines.append(f"- 技能参考：{references}/")
    lines.append(f"- 模板：概念清单 {protocol}/entities.json；问题清单 {protocol}/issues.json（计划获批准后再写）")
    lines.append("- 概念清单写 modeling/entities.json，问题清单写 modeling/issues.json（与 plan.md 同级，不放 parts/）")
    lines.append("- 片段写 modeling/parts/，临时文件写 modeling/tmp/；业务文件用工作区相对路径，不用 /tmp 或 ../（DataAgent 会拦截），技能脚本照下面的命令写")
    # Seen in a real run: piping into head cut the examples, and --help cost calls.
    lines.append("- 技能脚本的输出已控制在一次能完整显示的大小：不要接 head、tail 截断，也不必先查 --help，参数照下面的命令写")
    lines.append("常用命令：")
    lines += ["  " + line for line in usage(work_pack)]
    lines += ["  " + line for line in reading_commands(pack)]
    return "\n".join(lines)


def reading_commands(pack):
    """Exact reader commands for this run's tables and structured materials.

    Opening these files with python, cat or grep loads every table or the whole
    material into context and loses the refs and line numbers evidence needs.
    """
    lines = []
    tables = pack.get("tables_file")
    if tables:
        total = (pack.get("table_scope") or {}).get("total")
        lines.append("检索表（用需求和材料里的业务词；表超过 30 张时必须给词）：" + command("read_input.py", tables, "--search-tables", "业务词1 业务词2"))
        lines.append("看候选表的列（只看计划要用的表）：" + command("read_input.py", tables, "--describe-tables", "t1,t3"))
        if total:
            lines.append(f"本轮表范围共 {total} 张；不要全部列出或全部读列")
    for number, material in enumerate(pack.get("materials") or [], 1):
        path = material.get("path") or ""
        if path.lower().endswith((".json", ".csv")):
            lines.append(f"材料 m{number} 先看结构：" + command("read_input.py", path, "--outline", "--ref", f"m{number}"))
    if lines:
        lines.append("表结构文件和材料只用 read_input.py 读：它按需返回片段并带 ref／原行号供引证；用 python、cat、grep 直接打开会把无关内容塞进上下文，也拿不到可引证的位置")
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
