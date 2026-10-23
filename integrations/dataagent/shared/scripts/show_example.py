"""Look up a bounded, executable positive example without loading the schema."""

import argparse
import json
from pathlib import Path

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


def example(target_kind, operation="create", variant=None):
    catalog = json.loads((EXAMPLES / "catalog.json").read_bytes())
    choices = catalog["lookup"]
    if target_kind not in choices:
        hint = FIELDS.get(target_kind)
        raise ValueError((f"{target_kind} 不是提案类型，是字段；{hint}。" if hint else "未知类型；") + "可选值：" + "、".join(sorted(choices)))
    if operation not in choices[target_kind]:
        raise ValueError("未知操作；可选值：create、update、delete")
    if variant:
        variants = VARIANTS.get(target_kind, {}) if operation == "create" else {}
        if variant not in variants:
            raise ValueError(
                "未知分支；本类型 create 可选值："
                + "、".join(VARIANTS.get(target_kind, {}))
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
    parser = argparse.ArgumentParser(
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
            if len((content + "\n").encode()) > LIMIT:
                raise ValueError("固定包输出超过8 KiB，请维护更小的片段")
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
        content = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len((content + "\n").encode()) > LIMIT:
            raise ValueError("正例超过8 KiB，请分批查询或维护更小的完整正例")
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc))
        return 1
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
