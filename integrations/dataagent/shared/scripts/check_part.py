"""Quick check of one or more modeling/parts fragments before merging.

Shape follows the item schema, client_ref is unique within the fragment and
references inside the fragment are closed. References to other fragments are
listed as "待合并检查" rather than reported as errors; the merged check in
prepare_result.py decides them. Pinned before/hash checks use definitions and the independent instance baseline.
Repair budgets are never touched.
"""

import argparse
import json
from pathlib import Path

from check_result import (
    atomic_write,
    diagnostic,
    encode,
    mapping_local_errors,
    schema_errors,
)
from prepare_result import PrepareInputError, assemble

SUMMARY_LIMIT = 4000
NAMED_KINDS = {"object_type", "property", "value_type", "link_type", "metric", "dataset", "rule"}


def references(value):
    """client_ref values an item points at, in its body or depends_on."""
    found = set()
    if isinstance(value, dict):
        if set(value) == {"client_ref"} and isinstance(value["client_ref"], str):
            found.add(value["client_ref"])
        for child in value.values():
            found |= references(child)
    elif isinstance(value, list):
        for child in value:
            found |= references(child)
    return found


def check_fragment(items, context, schema):
    try:
        batch = assemble(context, [items])
    except PrepareInputError as exc:
        return {"errors": [str(exc)], "pending_refs": [], "hints": []}
    defined = {i.get("client_ref") for i in batch["items"]}
    used = set()
    for item in batch["items"]:
        used |= references(item.get("after"))
        used |= {d for d in item.get("depends_on", []) if isinstance(d, str)}
    hints = [
        f"/items/{n}/after/display_name：建议填写中文名称"
        for n, item in enumerate(batch["items"])
        if item["target_kind"] in NAMED_KINDS
        and isinstance(item.get("after"), dict)
        and not item["after"].get("display_name")
    ]
    errors = schema_errors(batch, schema)
    for n, item in enumerate(batch["items"]):
        errors += [diagnostic(f"/items/{n}" + path, *rest, item) for path, *rest in mapping_local_errors(item)]
    return {
        "errors": errors,
        "pending_refs": sorted(used - defined),
        "hints": hints,
    }


PARTS = Path("modeling/parts")


def fragment_paths(raw):
    """A file path, or a short name: "01" → modeling/parts/01-*.json, "01-types" → its .json."""
    path = Path(raw)
    if path.is_file():
        return [path]
    if raw.isdigit():
        return sorted(PARTS.glob(f"{raw}-*.json")) or [path]
    named = PARTS / f"{raw.removesuffix('.json')}.json"
    return [named] if named.is_file() else [path]


def main():
    parser = argparse.ArgumentParser(
        description="片段快速检查；跨片段引用留待合并检查，不计修正次数。片段可写 01、01-types 或路径"
    )
    parser.add_argument("--work-pack", help="工作包；从中取 context_file 与 schema_file")
    parser.add_argument("--context")
    parser.add_argument("--schema")
    parser.add_argument("--reports", default="modeling/checks")
    parser.add_argument("fragments", nargs="+")
    args = parser.parse_args()
    try:
        if args.work_pack:
            pack = json.loads(Path(args.work_pack).read_bytes())
            args.context = args.context or pack["context_file"]
            args.schema = args.schema or pack["schema_file"]
        if not (args.context and args.schema):
            print("需要 --work-pack <工作包>，或同时给出 --context 与 --schema")
            return 2
        context = json.loads(Path(args.context).read_bytes())
        schema = json.loads(Path(args.schema).read_bytes())
    except (OSError, ValueError, KeyError) as exc:
        print(f"读取工作包、固定上下文或 Schema 失败：{type(exc).__name__}")
        return 1
    failed, lines = False, []
    for raw, path in ((name, p) for name in args.fragments for p in fragment_paths(name)):
        try:
            items = json.loads(path.read_bytes())
        except (OSError, ValueError) as exc:
            failed = True
            existing = "、".join(p.name for p in sorted(PARTS.glob("*.json"))) or "无"
            lines.append(f"{raw}：无法读取为 JSON（{type(exc).__name__}）；modeling/parts/ 现有：{existing}")
            continue
        report = check_fragment(items, context, schema)
        reports = Path(args.reports)
        reports.mkdir(parents=True, exist_ok=True)
        atomic_write(reports / f"{path.stem}.json", encode(report))
        failed = failed or bool(report["errors"])
        status = f"{len(report['errors'])} 个错误" if report["errors"] else "通过"
        lines.append(f"{path}：{status}")
        lines += ["  " + e for e in report["errors"][:5]]
        if report["pending_refs"]:
            lines.append("  待合并检查的跨片段引用：" + "、".join(report["pending_refs"]))
        lines += ["  " + h for h in report["hints"][:5]]
    summary = "\n".join(lines)
    if len(summary.encode()) > SUMMARY_LIMIT:
        summary = summary.encode()[:SUMMARY_LIMIT].decode("utf-8", "ignore") + f"\n…完整报告见 {args.reports}/"
    print(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
