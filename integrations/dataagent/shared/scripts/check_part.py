"""Quick check of one or more modeling/parts fragments before merging.

Shape follows the item schema, client_ref is unique within the fragment and
across the other fragments already written, and references inside the fragment
are closed. References to other fragments are
listed as "待合并检查" rather than reported as errors; the merged check in
prepare_result.py decides them. Pinned before/hash checks use definitions and the independent instance baseline.
Repair budgets are never touched.
"""

import json
from pathlib import Path

from check_result import (
    atomic_write,
    diagnostic,
    encode,
    mapping_local_errors,
    schema_errors,
)
from prepare_result import PrepareInputError, assemble, effective_ref, material_hashes
from runpaths import PARTS, HintParser, command, error, existing, fragment_paths, plan_not_approved

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
        after = item.get("after")
        if (
            item["operation"] == "create"
            and item["target_kind"] == "object_type"
            and isinstance(after, dict)
            and after.get("title_property_id") is None
        ):
            hints.append(
                f"{after.get('display_name') or after.get('name')}（{after.get('name')}）未设标题属性（可不设）："
                "若材料给出名称属性请设置，否则按标识显示，按名称解析会找不到；无需仅为此提示修正。"
            )
        errors += [diagnostic(f"/items/{n}" + path, *rest, item) for path, *rest in mapping_local_errors(item)]
    return {
        "errors": errors,
        "pending_refs": sorted(used - defined),
        "hints": hints,
    }




def duplicate_refs(path, items):
    """Refs this fragment shares with other parts, numbered as the default merge of modeling/parts/ would.

    Only a fragment inside modeling/parts/ is compared; a replacement kept
    elsewhere is merged by explicit choice, which this cannot know.
    """
    parts = sorted(PARTS.glob("*.json"))
    if path.resolve() not in {p.resolve() for p in parts}:
        return []
    owner, index, found = {}, 0, []
    for part in parts:
        mine = part.resolve() == path.resolve()
        try:
            fragment = items if mine else json.loads(part.read_bytes())
        except (OSError, ValueError):
            fragment = []
        for item in fragment if isinstance(fragment, list) else []:
            ref = effective_ref(item, index)
            index += 1
            if not isinstance(ref, str):
                continue
            other = owner.setdefault(ref, (part.name, mine))
            if other[0] != part.name and (mine or other[1]):
                found.append(error(
                    "DUPLICATE_REF", f"client_ref {ref} 与 {other[0] if mine else part.name} 重复，合并会拒收", "片段未改动",
                    f"把 {path} 里的这个名字改成别的（如 {ref}_2），再执行 " + command("check_part.py", "--work-pack", "<工作包>", str(path))))
    return found


def main():
    parser = HintParser(
        description="片段快速检查；跨片段引用留待合并检查，不计修正次数。片段可写 01、01-types 或路径"
    )
    parser.add_argument("--work-pack", help="工作包；从中取 context_file 与 schema_file")
    parser.add_argument("--context")
    parser.add_argument("--schema")
    parser.add_argument("--reports", default="modeling/checks")
    parser.add_argument("fragments", nargs="+")
    args = parser.parse_args()
    if refusal := plan_not_approved():
        print(refusal)
        return 2
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
        context["material_hashes"] = material_hashes(pack if args.work_pack else None, context)
    except (OSError, ValueError, KeyError) as exc:
        which = args.work_pack if not (args.context and args.schema) else f"{args.context} 或 {args.schema}"
        print(error("INPUT_UNREADABLE", f"读取 {which} 失败：{type(exc).__name__}", "未检查任何片段",
                    "路径照 init_workflow 打印的本轮工作包复制"))
        return 1
    failed, lines = False, []
    for raw, path in ((name, p) for name in args.fragments for p in fragment_paths(name)):
        try:
            items = json.loads(path.read_bytes())
        except FileNotFoundError:
            failed = True
            lines.append(error("FILE_NOT_FOUND", f"片段 {raw} 不存在（找的是 {path}）", f"modeling/parts/ 现有：{existing(PARTS, '*.json')}",
                               "先把片段写到 modeling/parts/<编号>-<名称>.json，再检查"))
            continue
        except json.JSONDecodeError as exc:
            failed = True
            lines.append(error("JSON_INVALID", f"{path} 第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}", "文件已存在，未检查",
                               f"修正该处后重新检查：{command('check_part.py', '--work-pack', args.work_pack or '<工作包>', str(path))}"))
            continue
        except OSError as exc:
            failed = True
            lines.append(error("READ_FAILED", f"无法读取 {path}：{type(exc).__name__}", "未检查", retry=False))
            continue
        report = check_fragment(items, context, schema)
        report["errors"] += duplicate_refs(path, items)
        report_path = Path(args.reports) / f"{path.stem}.json"
        try:
            atomic_write(report_path, encode(report))
            saved = f"完整报告：{report_path}"
        except OSError as exc:
            saved = f"报告未保存（{type(exc).__name__}）"
        failed = failed or bool(report["errors"])
        errors = report["errors"]
        if errors:
            shown = errors[:5]
            more = f"，显示 {len(shown)} 个、省略 {len(errors) - len(shown)} 个" if len(errors) > len(shown) else ""
            lines.append(f"{path}：{len(errors)} 个错误{more}。{saved}")
            if len(errors) > len(shown):
                lines.append("  读后续错误：" + command("read_input.py", str(report_path), "--pointer", f"/errors/{len(shown)}"))
        else:
            lines.append(f"{path}：通过")
        lines += ["  " + e for e in errors[:5]]
        if report["pending_refs"]:
            lines.append("  待合并检查的跨片段引用：" + "、".join(report["pending_refs"]))
        lines += ["  " + h for h in report["hints"][:5]]
    # Cut at whole lines so a path or command is never half printed.
    kept, size = [], 0
    for line in lines:
        size += len(line.encode()) + 1
        if size > SUMMARY_LIMIT:
            kept.append(f"…其余 {len(lines) - len(kept)} 行省略，各片段完整报告在 {args.reports}/<片段名>.json")
            break
        kept.append(line)
    print("\n".join(kept))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
