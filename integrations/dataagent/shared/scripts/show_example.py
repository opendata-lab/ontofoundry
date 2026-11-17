"""The fixed extract kit and the rare patterns, each bounded; no per-kind examples."""

import json
from pathlib import Path

from runpaths import HintParser, command, error, without_material_hashes

REFERENCES = Path(__file__).resolve().parents[1] / "references"
LIMIT = 8 * 1024
KIT = REFERENCES / "extract-kit"
# The full extract reads principles, guide, values and parts 01–05. One output
# above DataAgent's 16 KB inline limit is folded to a file, so it comes in two
# pages that each stay well below it (four calls before).
EXTRACT_PAGES = {
    "1": [("原则", "principles.md"), ("固定包说明", "extract-kit/guide.md"), ("取值速查", "extract-kit/values.json"),
          ("片段 01", "extract-kit/01.json"), ("片段 02", "extract-kit/02.json")],
    "2": [("片段 03", "extract-kit/03.json"), ("片段 04", "extract-kit/04.json"), ("片段 05", "extract-kit/05.json")],
}
PAGE_LIMIT = 14 * 1024


def extract_page(page):
    """Concatenate one page of the extract reading with plain section headers."""
    sections = []
    for title, name in EXTRACT_PAGES[page]:
        content = (REFERENCES / name).read_text().rstrip("\n")
        if name.endswith(".json"):
            content = json.dumps(without_material_hashes(json.loads(content)), ensure_ascii=False, separators=(",", ":"))
        sections.append(f"===== {title}（{name.rsplit('/', 1)[-1]}）=====\n{content}")
    if page == "1":
        sections.append("下一页：" + command("show_example.py", "--extract", "2"))
    return "\n".join(sections)
# Where each kind is shown in the fixed kit (create), for lookups by kind.
PARTS_BY_KIND = {
    "object_type": "01", "property": "01", "value_type": "01", "link_type": "02",
    "dataset": "03", "mapping": "03", "metric": "04", "rule": "04",
    "material_object": "05", "material_link": "05",
}


def variants():
    return json.loads((KIT / "variants.json").read_bytes())


def by_kind(kinds):
    """Per-kind examples are gone (design §6): name the kit part that shows each kind."""
    unknown = [k for k in kinds if k not in PARTS_BY_KIND]
    if unknown:
        return f"未知类型 {'、'.join(unknown)}；类型可选：" + "、".join(PARTS_BY_KIND)
    parts = dict.fromkeys(PARTS_BY_KIND[k] for k in kinds)
    return ("按类型的正例已并入固定包：" + "；".join(command("show_example.py", "--part", n) for n in parts)
            + "；修改用 --part update，改名称或删除用 --part edit，少见写法用 --variant <名称>")


def main():
    parser = HintParser(description="固定抽取包与少见写法；UUID／材料证据须替换为本轮真实值")
    parser.add_argument("target_kinds", nargs="*", metavar="target_kind", help="已取消；会告诉你该读哪个 --part")
    fixed = parser.add_mutually_exclusive_group()
    fixed.add_argument("--part", choices=["01", "02", "03", "04", "05", "01b", "02b", "03b", "update", "edit"], help="裸 items 数组；01–05 全量（01b–03b 同 01–03），update 增量补齐，edit 修改删除")
    fixed.add_argument("--incremental-guide", action="store_true", help="增量查询与写法说明")
    fixed.add_argument("--values", action="store_true", help="契约取值速查")
    fixed.add_argument("--guide", action="store_true", help="固定包说明与确定的读取参数")
    fixed.add_argument("--extract", choices=sorted(EXTRACT_PAGES), help="全量抽取要读的全部内容，分两页：1 原则、说明、取值、01–02；2 为 03–05")
    fixed.add_argument("--variant", help="少见写法，如 inheritance、metric-ratio；写错时列出全部")
    args, extra = parser.parse_known_args()
    try:
        if extra or (args.target_kinds and any([args.part, args.values, args.guide, args.incremental_guide, args.extract, args.variant])):
            raise ValueError("参数只写一个入口：--part、--extract、--variant、--guide、--values 或 --incremental-guide")
        if args.target_kinds:
            raise ValueError(by_kind(list(dict.fromkeys(args.target_kinds))))
        if args.extract:
            content = extract_page(args.extract)
            limit, what = PAGE_LIMIT, f"抽取第 {args.extract} 页"
        elif args.variant:
            found = variants()
            if args.variant not in found:
                raise ValueError(f"没有写法 {args.variant}；可选：" + "、".join(found))
            content = json.dumps(without_material_hashes(found[args.variant]), ensure_ascii=False, separators=(",", ":"))
            limit, what = LIMIT, f"写法 {args.variant}"
        elif args.part or args.values or args.guide or args.incremental_guide:
            filename = f"{args.part.rstrip('b')}.json" if args.part else "values.json" if args.values else "incremental.md" if args.incremental_guide else "guide.md"
            content = (KIT / filename).read_text().rstrip("\n")
            if filename.endswith(".json"):
                content = json.dumps(without_material_hashes(json.loads(content)), ensure_ascii=False, separators=(",", ":"))
            if args.incremental_guide:
                # The incremental step always needs the update example next; one call, not two.
                update = json.dumps(without_material_hashes(json.loads((KIT / "update.json").read_text())), ensure_ascii=False, separators=(",", ":"))
                content += "\n===== 增量补齐正例（update.json，同 --part update）=====\n" + update
            limit, what = LIMIT, f"固定包 {filename}"
        else:
            raise ValueError("请用 --extract 1、--part 01 至 --part 05、--variant <名称>、--values 或 --guide")
    except ValueError as exc:
        print(error("INVALID_ARGUMENT", str(exc), "未返回示例"))
        return 1
    except (OSError, KeyError) as exc:
        print(error("SKILL_ASSET_MISSING", f"技能示例文件缺失或损坏（{type(exc).__name__}）", "未返回示例；需要重新安装技能", retry=False))
        return 1
    size = len((content + "\n").encode())
    if size > limit:
        print(error("EXAMPLE_TOO_LARGE", f"{what}有 {size} 字节，超过 {limit} 字节", "未回显内容；这是技能自身的问题，需要维护者拆小", retry=False))
        return 1
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
