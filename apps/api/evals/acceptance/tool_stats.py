"""Count model turns and tool calls in an archived DataAgent conversation.

Usage: python tool_stats.py <conversation.json> [...] [--calls]

Prints, per file: turns (turn.started events), tool calls by kind, tool output
bytes and token usage; with --calls also lists every call in order. Used to
compare a modeling run against the archived baselines in results/.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


def _kind(name: str, data: dict) -> str:
    """Name a call by what it did: the skill script run, or the tool and file."""
    if name in {"bash", "shell", "exec", "run_command"}:
        command = str(data.get("command") or data.get("cmd") or "")
        script = re.search(r"([\w-]+\.py)", command)
        if script:
            return f"bash:{script.group(1)}"
        return "bash:" + (command.split()[0] if command.split() else "?")
    if name in {"read", "read_file"}:
        path = str(data.get("path") or data.get("file_path") or "")
        return "read:" + Path(path).name
    if name in {"write", "write_file", "edit", "edit_file"}:
        return name
    return name


def _size(output) -> int:
    if isinstance(output, list):
        return sum(len(str(part.get("text", "")) if isinstance(part, dict) else str(part)) for part in output)
    return len(str(output or ""))


def stats(path: Path) -> dict:
    data = json.loads(path.read_text())
    calls, turns, usage = [], 0, Counter()
    for message in data.get("messages", []):
        if message.get("type") != "assistant":
            continue
        for key, value in (message.get("usage") or {}).items():
            if isinstance(value, (int, float)):
                usage[key] += value
        turns += sum(1 for r in message.get("records") or [] if r.get("event_type") == "turn.started")
        for block in message.get("blocks") or []:
            if block.get("type") != "tool_use":
                continue
            raw = block.get("input") or {}
            calls.append({
                "kind": _kind(str(block.get("tool_name") or ""), raw if isinstance(raw, dict) else {}),
                "input": json.dumps(raw, ensure_ascii=False)[:160],
                "bytes": _size(block.get("output")),
            })
    return {"turns": turns, "calls": calls, "usage": dict(usage)}


def main(argv: list[str]) -> None:
    show = "--calls" in argv
    for name in [a for a in argv if not a.startswith("--")]:
        result = stats(Path(name))
        kinds = Counter(c["kind"] for c in result["calls"])
        out_bytes = sum(c["bytes"] for c in result["calls"])
        print(f"== {name}")
        print(f"turns {result['turns']}  tool calls {len(result['calls'])}  tool output {out_bytes} B  usage {result['usage']}")
        for kind, count in kinds.most_common():
            print(f"  {count:3d}  {kind}")
        if show:
            for i, call in enumerate(result["calls"], 1):
                print(f"  {i:3d}. {call['kind']:<28} {call['bytes']:>7} B  {call['input']}")


if __name__ == "__main__":
    main(sys.argv[1:])
