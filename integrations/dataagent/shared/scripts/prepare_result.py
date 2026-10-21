"""Assemble a pinned proposal batch without inferring business content."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from check_result import COLLECTIONS, atomic_write, diagnostic, encode, validate_file


class PrepareInputError(ValueError):
    """A precise fragment diagnostic, before any output is replaced."""


def assemble(context, fragments):
    items, refs = [], set()
    existing = {
        e["id"]: (kind, e)
        for kind, collection in COLLECTIONS.items()
        for e in context["draft"].get(collection, [])
    }
    for fragment_index, fragment in enumerate(fragments):
        if not isinstance(fragment, list):
            raise PrepareInputError(
                diagnostic(
                    f"/fragments/{fragment_index}",
                    "PREPARE_INPUT",
                    "items 数组片段",
                    fragment,
                )
            )
        for raw in fragment:
            index = len(items)
            item = deepcopy(raw)

            def fail(field, expected, actual, index=index, item=item):
                raise PrepareInputError(
                    diagnostic(
                        f"/items/{index}/{field}",
                        "PREPARE_INPUT",
                        expected,
                        actual,
                        item,
                    )
                )

            if not isinstance(item, dict):
                fail("", "提案对象", item)
            for field in ("operation", "target_kind"):
                if field not in item:
                    fail(field, "必填字段", "缺失")
            if item["operation"] in {"update", "delete"}:
                target = item.get("target_id")
                if not isinstance(target, str) or target not in existing:
                    fail("target_id", "固定草稿中存在的目标 UUID", target)
                kind, before = existing[target]
                if item["target_kind"] != kind:
                    fail("target_kind", kind, item["target_kind"])
                for field, value in (
                    ("before", before),
                    ("expected_target_hash", context["element_hashes"][target]),
                ):
                    if field in item and item[field] != value:
                        fail(field, value, item[field])
                    item[field] = deepcopy(value)
                if item["operation"] == "delete":
                    item.setdefault("after", None)
            else:
                item.setdefault("before", None)
                item.setdefault("client_ref", f"{item['target_kind']}-{index + 1}")
            ref = item.get("client_ref")
            if isinstance(ref, str):
                if ref in refs:
                    fail("client_ref", "不重复的 client_ref", ref)
                refs.add(ref)
            items.append(item)
    return {**context["run"], "items": items}


def workspace_path(raw):
    path = Path(raw).resolve()
    if not path.is_relative_to(Path.cwd().resolve()):
        raise ValueError("片段、候选与输出路径必须位于当前工作区")
    return path


def fragment_files(raw_paths):
    """Files in order; a directory such as modeling/parts/ expands to its *.json by name."""
    files = []
    for raw in raw_paths:
        path = workspace_path(raw)
        if path.is_dir():
            found = sorted(p for p in path.glob("*.json") if p.is_file())
            if not found:
                raise ValueError(f"片段目录中没有 JSON 片段：{raw}")
            files.extend(found)
        else:
            files.append(path)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("fragments", nargs="+", help="items 数组片段文件，或片段目录（按文件名排序合并）")
    args = parser.parse_args()
    try:
        output = workspace_path(args.output)
        fragments = [json.loads(p.read_bytes()) for p in fragment_files(args.fragments)]
        context = json.loads(Path(args.context).read_bytes())
        candidate = output.with_suffix(".pending.json")
        batch = assemble(context, fragments)
        atomic_write(candidate, encode(batch))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        message = (
            str(exc)
            if isinstance(exc, PrepareInputError)
            else diagnostic(
                "/fragments",
                "PREPARE_INPUT",
                "工作区内可读 JSON 片段、固定上下文和输出路径",
                type(exc).__name__,
            )
        )
        report = Path(args.output + ".errors.json")
        try:
            atomic_write(
                workspace_path(str(report)), encode({"total": 1, "errors": [message]})
            )
        except (OSError, ValueError):
            pass
        print(message + "；未替换最终文件")
        return 1
    return validate_file(
        candidate, args.schema, args.context, repair=args.repair, publish=output
    )


if __name__ == "__main__":
    raise SystemExit(main())
