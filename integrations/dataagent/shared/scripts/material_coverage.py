"""Material lines that read like a metric definition or business rule but no
proposal cites, and planned metrics or rules with no matching item (design
2026-11-15 MS-04). A reminder only: the agent covers them or says why not.
"""

import json
import re
from pathlib import Path

from runpaths import PARTS

ENTITIES = Path("modeling/entities.json")
SEMANTIC = re.compile(r"口径|只有|只对|才算|才计|不计|计入|统计|合计|数量|定义|比例|除以|减去|不足|只能|称为|[=＝]")
SHOWN = 10
NAMED = {"metric": "metric", "rule": "rule", "指标": "metric", "规则": "rule"}


def cited_lines(parts):
    cited = {}
    def walk(value):
        if isinstance(value, dict):
            if value.get("kind") == "material" and isinstance(value.get("locator"), dict):
                loc = value["locator"]
                start, end = loc.get("line_start"), loc.get("line_end", loc.get("line_start"))
                if isinstance(start, int) and isinstance(end, int):
                    cited.setdefault(value.get("material_id"), set()).update(range(start, end + 1))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for items in parts:
        walk(items)
    return cited


def semantic_lines(pack):
    for material in pack.get("materials") or []:
        if material.get("from_request") or not material.get("path"):
            continue
        try:
            text = Path(material["path"]).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for number, line in enumerate(text, 1):
            stripped = line.strip()
            if len(stripped) >= 6 and not stripped.startswith("#") and SEMANTIC.search(stripped):
                yield material["id"], number, stripped


def read_parts():
    parts = []
    for path in sorted(PARTS.glob("*.json")):
        try:
            value = json.loads(path.read_bytes())
        except (OSError, ValueError):
            continue
        if isinstance(value, list):
            parts.append(value)
    return parts


def coverage_hints(pack):
    parts = read_parts()
    cited = cited_lines(parts)
    lines = []
    missing = [(m, n, t) for m, n, t in semantic_lines(pack) if n not in cited.get(m, set())]
    if missing:
        lines.append(f"材料里像指标口径或业务规则、但没有提案引作证据的行 {len(missing)} 条（补提案，或在回答里说明为何不建）：")
        lines += [f"  {m[:8]} L{n}：{t[:80]}" for m, n, t in missing[:SHOWN]]
        if len(missing) > SHOWN:
            lines.append(f"  …其余 {len(missing) - SHOWN} 条省略")
    try:
        spec = json.loads(ENTITIES.read_bytes())
    except (OSError, ValueError):
        spec = {}
    names = {(i.get("target_kind"), (i.get("after") or {}).get("name")) for p in parts for i in p if isinstance(i, dict)}
    unmet = []
    for key in ("planned_metrics", "planned_rules"):
        for plan in spec.get(key) or []:
            kind = NAMED.get(plan.get("as"))
            if kind and (kind, plan.get("name")) not in names:
                unmet.append(f"  {plan.get('display_name') or plan.get('name')}（计划为 {kind} {plan.get('name')}）")
    if unmet:
        lines.append(f"entities.json 计划了、片段里还没有的指标或规则 {len(unmet)} 个：")
        lines += unmet[:SHOWN]
    return lines
