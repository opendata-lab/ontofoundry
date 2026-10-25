"""Remove host-specific paths from tool display projections, never stored I/O."""

import re
from typing import Any

# URI paths and relative paths are not host filesystem paths.
_LOCAL_PATH = re.compile(
    r"(?<![\w:/\\])(?:[A-Za-z]:[\\/]|/(?:Users|home|root|tmp|private|var|opt|srv|app|mnt|workspace|workspaces|dataagent_runtime|data|Volumes|usr|etc)/)"
    r"[^\s\"'`<>|，。；（）\[\]{}]+"
)


def _display_path(match: re.Match) -> str:
    raw = match.group().replace("\\", "/")
    path = raw.rstrip(",;:)")
    suffix = raw[len(path):]
    if "/skills/" in path:
        relative = path.rsplit("/skills/", 1)[1]
        return f"技能 {relative}" + suffix
    if "/workspace/" in path:
        return path.split("/workspace/", 1)[1] + suffix
    # Older runtimes put uploads and modeling directly under the topic root.
    topic = re.search(r"/topic[_-][^/]+/(.+)", path)
    if topic:
        return topic[1] + suffix
    return path.rsplit("/", 1)[-1] + suffix


def present_tool_value(value: Any) -> Any:
    if isinstance(value, str):
        return _LOCAL_PATH.sub(_display_path, value)
    if isinstance(value, list):
        return [present_tool_value(part) for part in value]
    if isinstance(value, dict):
        return {key: present_tool_value(part) for key, part in value.items()}
    return value
