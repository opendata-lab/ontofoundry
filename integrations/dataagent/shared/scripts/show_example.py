"""Look up a bounded, executable positive example without loading the schema."""

import json
from pathlib import Path

from runpaths import HintParser, command, error

EXAMPLES = Path(__file__).resolve().parents[1] / "references/examples"
LIMIT = 8 * 1024
KIT = EXAMPLES.parent / "extract-kit"
VARIANTS = {
    "metric": {
        "ratio": ("metrics.json", [0, 1, 2, 3]),
        "expression": ("metrics.json", [0, 5]),
    },
    "mapping": {
        "expression": ("expression-binding.json", None),
        "shared_parent": ("inheritance.json", None),
    },
    "link_type": {
        "direct": ("link-joins.json", None),
        "mapping_table": ("link-joins.json", None),
    },
    "rule": {"derivation": ("derivation.json", None)},
    # Cross-table measures: an expression dataset plus single-dataset metrics.
    "dataset": {"query": ("cross-dataset-events.json", None)},
}


# Field names agents look up as if they were kinds.
FIELDS = {
    "data_join": "属于 link_type，外键查 link_type --variant direct，关联表查 link_type --variant mapping_table",
    "sources": "属于 mapping，查 mapping",
    "fields": "属于 mapping，列绑定查 mapping，表达式绑定查 mapping --variant expression",
    "filters": "属于 metric，查 metric",
    "evidence": "每个元素都有，查对应类型的正例",
}


def without_material_hashes(value):
    """Examples show evidence as id, locator and quote: the merge fills
    material_sha256 by id, so the agent never copies a 64-digit hash."""
    if isinstance(value, dict):
        return {k: without_material_hashes(v) for k, v in value.items()
                if not (k == "material_sha256" and value.get("kind") == "material")}
    if isinstance(value, list):
        return [without_material_hashes(v) for v in value]
    return value


def example(target_kind, operation="create", variant=None):
    catalog = json.loads((EXAMPLES / "catalog.json").read_bytes())
    choices = catalog["lookup"]
    if target_kind not in choices:
        hint = FIELDS.get(target_kind)
        raise ValueError((f"{target_kind} 不是提案类型，是字段，{hint}" if hint else f"未知类型 {target_kind}") + "；类型可选：" + "、".join(sorted(choices)))
    if operation not in choices[target_kind]:
        raise ValueError(f"未知操作 {operation}；可选：create、update、delete")
    if variant:
        if operation != "create":
            raise ValueError(f"--variant 只用于 create，本次是 --operation {operation}；去掉 --variant："
                             + command("show_example.py", target_kind, "--operation", operation))
        variants = VARIANTS.get(target_kind, {})
        if variant not in variants:
            raise ValueError(
                f"{target_kind} 没有分支 {variant}；可选："
                + ("、".join(variants) or "无（直接查 " + command("show_example.py", target_kind) + "）")
            )
        filename, indices = variants[variant]
        items = json.loads((EXAMPLES / filename).read_bytes())
        for item in items:
            item.setdefault("before", None)
        return [items[i] for i in indices] if indices else items
    return json.loads((EXAMPLES / choices[target_kind][operation]).read_bytes())


def without_dependencies(target_kind, items):
    """Only the requested kind; dependencies are named so the agent can look them up."""
    def owned(item):
        # A value type's constraints are rules it owns; they belong to its example.
        after = item.get("after") or {}
        return item["target_kind"] == target_kind or (
            item["target_kind"] == "rule" and after.get("owner_kind") == target_kind
        )

    own = [i for i in items if owned(i)]
    skipped = [f"{i['target_kind']}:{i.get('client_ref') or i.get('target_id')}" for i in items if not owned(i)]
    return {"items": own, "依赖已省略": skipped} if skipped else {"items": own}


def main():
    parser = HintParser(
        description="返回一个或多个类型的最小正例；默认不附依赖，--with-deps 附带；UUID／材料证据须替换为本轮真实值"
    )
    parser.add_argument("target_kinds", nargs="*", metavar="target_kind")
    fixed = parser.add_mutually_exclusive_group()
    fixed.add_argument("--part", choices=["01", "02", "03", "04", "05", "update", "edit"], help="裸 items 数组；01–05 全量，update 增量补齐，edit 修改删除")
    fixed.add_argument("--incremental-guide", action="store_true", help="增量查询与写法说明")
    fixed.add_argument("--values", action="store_true", help="契约取值速查")
    fixed.add_argument("--guide", action="store_true", help="固定包说明与确定的读取参数")
    parser.add_argument("--operation", default="create")
    parser.add_argument("--variant", help="可选分支，如 metric 的 ratio／expression、dataset 的 query")
    parser.add_argument("--with-deps", action="store_true", help="附带依赖元素，输出可直接整批检查的完整正例")
    args = parser.parse_args()
    try:
        if args.part or args.values or args.guide or args.incremental_guide:
            if args.target_kinds or args.variant or args.with_deps or args.operation != "create":
                raise ValueError("固定包入口不能与类型、操作或分支查询混用")
            filename = f"{args.part}.json" if args.part else "values.json" if args.values else "incremental.md" if args.incremental_guide else "guide.md"
            content = (KIT / filename).read_text().rstrip("\n")
            if filename.endswith(".json"):
                content = json.dumps(without_material_hashes(json.loads(content)), ensure_ascii=False, separators=(",", ":"))
            size = len((content + "\n").encode())
            if size > LIMIT:
                print(error("EXAMPLE_TOO_LARGE", f"固定包 {filename} 有 {size} 字节，超过单次 {LIMIT} 字节上限",
                            "未回显内容；这是技能自身的问题，需要维护者拆小", retry=False))
                return 1
            print(content)
            return 0
        if not args.target_kinds:
            raise ValueError("请用 --part 01 至 --part 05、--values、--guide 或 target_kind")
        if args.with_deps:
            if len(args.target_kinds) != 1:
                raise ValueError("--with-deps 一次只查一个类型")
            value = example(args.target_kinds[0], args.operation, args.variant)
        else:
            value = {
                kind: without_dependencies(kind, example(kind, args.operation, args.variant))
                for kind in dict.fromkeys(args.target_kinds)
            }
        content = json.dumps(without_material_hashes(value), ensure_ascii=False, separators=(",", ":"))
        size = len((content + "\n").encode())
        if size > LIMIT:
            kinds = list(dict.fromkeys(args.target_kinds))
            step = ("每次查一个类型：" + "；".join(command("show_example.py", k, "--operation", args.operation) for k in kinds)
                    if len(kinds) > 1 else None)
            print(error("EXAMPLE_TOO_LARGE", f"正例 {size} 字节，超过单次 {LIMIT} 字节上限", "未回显内容",
                        step, retry=len(kinds) > 1))
            return 1
    except ValueError as exc:
        print(error("INVALID_ARGUMENT", str(exc), "未返回示例"))
        return 1
    except (OSError, KeyError) as exc:
        print(error("SKILL_ASSET_MISSING", f"技能示例文件缺失或损坏（{type(exc).__name__}）", "未返回示例；需要重新安装技能", retry=False))
        return 1
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
