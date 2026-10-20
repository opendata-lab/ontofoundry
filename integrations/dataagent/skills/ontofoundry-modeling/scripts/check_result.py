"""Check the supplied schema, operation shapes, references and pinned context."""

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

COLLECTIONS = {
    "object_type": "object_types",
    "property": "properties",
    "link_type": "link_types",
    "rule": "rules",
    "metric": "metrics",
    "dataset": "datasets",
    "mapping": "mappings",
    "material_object": "material_objects",
    "material_link": "material_links",
}
HEADER_FIELDS = (
    "schema_version",
    "workspace_id",
    "session_id",
    "run_token",
    "base_version_id",
    "base_version_sha256",
    "source_session_revision",
    "source_draft_sha256",
)


def check_result(result, schema, context=None):
    errors = [
        f"{list(e.path)}: {e.message}"
        for e in Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(result)
    ]
    if errors:
        return errors
    if not isinstance(result, dict) or not isinstance(result.get("items", []), list):
        return ["结果必须为对象，items 必须为数组"]
    items = result.get("items", [])
    if any(not isinstance(item, dict) for item in items):
        return ["提案必须为对象"]
    refs = [i.get("client_ref") for i in items if i.get("client_ref")]
    if len(refs) != len(set(refs)):
        errors.append("client_ref 重复")
    creates = {
        i["client_ref"]
        for i in items
        if i.get("operation") == "create" and i.get("client_ref")
    }

    def walk(value):
        if isinstance(value, dict):
            if set(value) == {"client_ref"} and value["client_ref"] not in creates:
                errors.append("client_ref 引用未闭合：" + str(value["client_ref"]))
            for key, entry in value.items():
                if key not in {"values", "evidence"}:
                    walk(entry)
        elif isinstance(value, list):
            for entry in value:
                walk(entry)

    targets = []
    for item in items:
        operation = item.get("operation")
        before, after = item.get("before"), item.get("after")
        if operation == "create":
            if not item.get("client_ref"):
                errors.append("create 缺少 client_ref")
            if (
                item.get("target_id") is not None
                or before is not None
                or not isinstance(after, dict)
            ):
                errors.append("create 必须无 target_id/before，且有 after 对象")
        elif operation in {"update", "delete"}:
            if (
                not item.get("target_id")
                or not isinstance(before, dict)
                or not item.get("expected_target_hash")
            ):
                errors.append(
                    "update/delete 需 target_id、before 与 expected_target_hash"
                )
            if operation == "update" and not isinstance(after, dict):
                errors.append("update 需 after 对象")
            if operation == "delete" and after is not None:
                errors.append("delete 的 after 必须为空")
            if isinstance(before, dict) and before.get("id") != item.get("target_id"):
                errors.append("before.id 与 target_id 不一致")
            targets.append(item.get("target_id"))
        if isinstance(after, dict) and "id" in after:
            errors.append("after 不得带自身 id")
        walk(after)
        for ref in item.get("depends_on", []):
            if ref not in refs:
                errors.append("depends_on 引用未闭合：" + str(ref))
    if len(targets) != len(set(targets)):
        errors.append("同一批次不能重复更新或删除同一目标")
    if context is not None:
        run = context.get("run", context)
        for key in HEADER_FIELDS:
            if key in run and result.get(key) != run[key]:
                errors.append("固定上下文不一致：" + key)
        draft = context.get("draft")
        existing = {
            element["id"]: (kind, element)
            for kind, collection in COLLECTIONS.items()
            for element in (draft or {}).get(collection, [])
        }
        for item in items:
            if item.get("operation") not in {"update", "delete"}:
                continue
            target = item.get("target_id")
            if draft is not None:
                found = existing.get(target)
                if found is None:
                    errors.append("目标不在固定草稿中：" + str(target))
                else:
                    if found[0] != item.get("target_kind"):
                        errors.append("目标类型与固定草稿不一致：" + str(target))
                    if json.dumps(found[1], sort_keys=True) != json.dumps(
                        item.get("before"), sort_keys=True
                    ):
                        errors.append("before 与固定草稿不一致：" + str(target))
            hashes = context.get("element_hashes")
            if hashes is not None and (
                target not in hashes
                or hashes[target] != item.get("expected_target_hash")
            ):
                errors.append("目标哈希与固定上下文不一致：" + str(target))
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--context")
    parser.add_argument("result")
    args = parser.parse_args()

    def read(path):
        return json.loads(Path(path).read_text())

    errors = check_result(
        read(args.result),
        read(args.schema),
        read(args.context) if args.context else None,
    )
    print(
        "\n".join(errors)
        if errors
        else "提案格式、操作形态、引用及已提供上下文检查通过"
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
