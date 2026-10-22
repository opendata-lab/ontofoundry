"""Paths and ready-to-copy commands for this run, so the agent never composes them.

Most failed tool calls in real runs were paths: /tmp or absolute paths that the
DataAgent sandbox rejects, references read from the wrong directory, fragments
checked before they were written, and arguments mixed up between scripts. The
scripts print the exact commands for the current workspace instead.
"""

import argparse
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PARTS = Path("modeling/parts")
PY = '"$DATAAGENT_PYTHON_BIN"'


def relative(path):
    """A path as written from the workspace (the process working directory)."""
    return os.path.relpath(Path(path).resolve(), Path.cwd().resolve())


def command(script, *args):
    return " ".join([PY, relative(SKILL_DIR / "scripts" / script), *args])


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
    return "、".join(found[:20]) or "无"


class HintParser(argparse.ArgumentParser):
    """On a wrong argument, print the correct commands instead of only argparse usage."""

    def error(self, message):
        work_pack = next(
            (sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--work-pack"),
            "<工作包>",
        )
        print(f"参数错误：{message}")
        print("本轮正确写法（路径相对工作区）：")
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
