"""Paths and ready-to-copy commands for this run, so the agent never composes them.

Most failed tool calls in real runs were paths: /tmp or absolute paths that the
DataAgent sandbox rejects, references read from the wrong directory, fragments
checked before they were written, and arguments mixed up between scripts. The
scripts print the exact commands for the current workspace instead.
"""

import argparse
import os
import shlex
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PARTS = Path("modeling/parts")
PY = '"$DATAAGENT_PYTHON_BIN"'


def relative(path):
    """A path as written from the workspace (the process working directory)."""
    return os.path.relpath(Path(path).resolve(), Path.cwd().resolve())


def script_path(script):
    """Where this skill's script actually is, as a command can name it.

    Inside the workspace the relative path; otherwise the skill's own
    directory, never a "../" climb, which sandboxes refuse. Nothing here
    depends on a particular agent runtime.
    """
    target = (SKILL_DIR / "scripts" / script).resolve()
    shown = relative(target)
    return shlex.quote(str(target) if shown.startswith("..") else shown)


def command(script, *args):
    """A ready-to-copy command; placeholders such as <工作包> stay readable."""
    quoted = [a if a.startswith("<") and a.endswith(">") else shlex.quote(str(a)) for a in args]
    return " ".join([PY, script_path(script), *quoted])


def error(code, reason, state, next_step=None, retry=True):
    """错误 [CODE]：原因。状态。下一步：命令 — the one shape every script uses."""
    parts = [f"错误 [{code}]：{reason.rstrip('。')}。", f"{state.rstrip('。')}。"]
    if next_step:
        parts.append(f"下一步：{next_step}")
    elif not retry:
        parts.append("同参重试无效。")
    return "".join(parts)


def notice(code, what, next_step=None):
    """提示 [CODE]: the call succeeded, with something the agent should know."""
    return f"提示 [{code}]：{what.rstrip('。')}。" + (f"下一步：{next_step}" if next_step else "")


def usage(work_pack="<工作包>"):
    """The commands every step uses, filled with this run's work pack when known."""
    return [
        f"检查片段：{command('check_part.py', '--work-pack', work_pack, '01')}",
        f"合并：{command('prepare_result.py', '--work-pack', work_pack, 'modeling/parts/')}",
        f"读材料：{command('read_input.py', '<材料路径>')}",
        f"读已有元素：{command('show_element.py', '--work-pack', work_pack, '<名称或id>')}",
    ]


def existing(folder, pattern="*"):
    folder = Path(folder)
    found = sorted(p.name for p in folder.glob(pattern) if p.is_file()) if folder.is_dir() else []
    if len(found) > 20:
        return "、".join(found[:20]) + f" 等 {len(found)} 个（另有 {len(found) - 20} 个未列出）"
    return "、".join(found) or "无"


class HintParser(argparse.ArgumentParser):
    """On a wrong argument, print the correct commands instead of only argparse usage."""

    def error(self, message):
        work_pack = next(
            (sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--work-pack"),
            "<工作包>",
        )
        script = Path(sys.argv[0]).name
        print(error("INVALID_ARGUMENT", f"{script} 参数错误：{message}", "脚本未执行",
                    f"按本脚本用法改正参数：{self.format_usage().strip()}"))
        print("本轮常用命令（路径已填好，可直接复制）：")
        for line in usage(work_pack):
            print("  " + line)
        raise SystemExit(2)


def fragment_paths(raw):
    """A file or directory path, or a short name: "01" → modeling/parts/01-*.json, "01-types" → its .json."""
    path = Path(raw)
    if path.exists():
        return [path]
    if raw.isdigit():
        return sorted(PARTS.glob(f"{raw}-*.json")) or [path]
    named = PARTS / f"{raw.removesuffix('.json')}.json"
    return [named] if named.is_file() else [path]
