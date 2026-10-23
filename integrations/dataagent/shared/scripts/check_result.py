"""Check the supplied schema, operation shapes, references and pinned context."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

# Also loaded by file path (tests, the platform's offline checks).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runpaths import command

COLLECTIONS = {
    "object_type": "object_types",
    "property": "properties",
    "link_type": "link_types",
    "rule": "rules",
    "metric": "metrics",
    "dataset": "datasets",
    "mapping": "mappings",
    "value_type": "value_types",
}
INSTANCE_KINDS = frozenset({"material_object", "material_link"})
TARGET_KINDS = COLLECTIONS.keys() | INSTANCE_KINDS


def same_json(left, right):
    """Keep boolean and numeric instance values distinct when checking a copy."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json(v, right[k]) for k, v in left.items())
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    return left == right


def pinned_targets(context):
    """Index definitions and revision-bound instances from their pinned sources."""
    targets = {
        (kind, e["id"]): (e, context.get("element_hashes", {}).get(e["id"]))
        for kind, collection in COLLECTIONS.items()
        for e in context.get("draft", {}).get(collection, [])
    }
    for entry in context.get("instance_baseline", {}).get("items", []):
        if entry["state"] == "active" or (
            entry["state"] == "staged"
            and entry["session_id"] == context.get("run", {}).get("session_id")
        ):
            targets[(entry["target_kind"], entry["target_id"])] = (entry["element"], entry["hash"])
    return targets


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


def preview(value):
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        text
        if len(text.encode()) <= 160
        else text.encode()[:150].decode("utf-8", "ignore") + "…"
    )


def example_command(kind="object_type", operation="create", after=None, pointer=""):
    kind = kind if kind in TARGET_KINDS else "object_type"
    operation = operation if operation in {"create", "update", "delete"} else "create"
    after = after if isinstance(after, dict) else {}
    fields = set(pointer.split("/"))
    bindings = after.get("fields")
    bindings = bindings if isinstance(bindings, dict) else {}
    variant, part = None, None
    # Route only on contract paths and discriminants, never business text.
    if operation == "create":
        if kind == "metric":
            if after.get("kind") in {"ratio", "expression"}:
                variant = after["kind"]
            elif fields & {"numerator_id", "denominator_id"}:
                variant = "ratio"
            elif "expression" in fields:
                variant = "expression"
            elif (
                fields & {"filters", "time_field", "aggregation", "measure"}
                or "filters" in after or "time_field" in after
                or after.get("aggregation") == "count"
            ):
                part = "04"
        elif kind == "dataset" and (
            after.get("source_kind") == "query" or "query_sql" in after
            or "query_sql" in fields
        ):
            part = "03"
        elif kind == "link_type" and ("data_join" in after or "data_join" in fields):
            join = after.get("data_join")
            if isinstance(join, dict) and join.get("kind") == "mapping_table":
                variant = "mapping_table"
            else:
                part = "02"
        elif kind == "mapping" and (
            "expression" in fields or any(
                isinstance(binding, dict) and binding.get("kind") == "expression"
                for binding in bindings.values()
            )
        ):
            variant = "expression"
        elif kind == "rule" and after.get("rule_kind") == "constraint":
            part = "01" if after.get("owner_kind") == "value_type" else "04"
        elif kind == "property" and (
            fields & {"identifier", "required", "unique", "value_type_id"}
            or "value_type_id" in after
        ):
            part = "01"
    if part:
        return command("show_example.py", "--part", part)
    return command("show_example.py", kind, "--operation", operation, *(["--variant", variant] if variant else []))


def next_step(code, item, pointer):
    """What to do about one diagnostic; a written example only helps writing errors."""
    if code.startswith("CONTEXT_MISMATCH"):
        return "结果头由合并脚本填写，不要手改；改片段后重新合并：" + command("prepare_result.py", "--work-pack", "<工作包>")
    if code in {"TARGET_NOT_FOUND", "BEFORE_MISMATCH", "TARGET_HASH_MISMATCH"}:
        target = item.get("target_id") or "<名称或id>"
        return "读取固定的现值后按它改：" + command("show_element.py", "--work-pack", "<工作包>", str(target))
    if code == "REPAIR_BUDGET_EXHAUSTED":
        return "停止修正，本轮不再发布结果；在回答里列出未通过的检查。同参重试无效。"
    if code.startswith("INPUT_"):
        return "按原因改正文件或路径后重新执行原命令。"
    return "查正确写法：" + example_command(item.get("target_kind"), item.get("operation"), item.get("after"), pointer)


def diagnostic(pointer, code, expected, actual, item=None):
    """错误 [CODE]：位置 [项]，期望…；实际…。下一步：…"""
    item = item if isinstance(item, dict) else {}
    label = preview(item.get("client_ref", item.get("target_id", "-")))
    where = pointer if pointer not in {"", "/"} else "文档根"
    short, _, detail = code.partition(" ")
    detail = f"（{detail}）" if detail else ""
    return (
        f"错误 [{short}]：{where} [{label}]{detail}，期望 {preview(expected)}；实际 {preview(actual)}。"
        f"下一步：{next_step(short, item, pointer)}"
    )


def escape(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def mapping_local_errors(item):
    """Source ids a mapping declares and uses; scoped to the item, so exact."""
    after = item.get("after")
    if not isinstance(after, dict) or item["target_kind"] != "mapping":
        return []
    problems = []
    sources = [source["id"] for source in after.get("sources", [])]
    if len(sources) != len(set(sources)):
        problems.append(("/after/sources", "LOCAL_SOURCE_DUPLICATE", "来源 id 不重复", sources))
    for name, binding in after.get("fields", {}).items():
        if (
            after.get("binding_mode") == "independent"
            and binding.get("kind") == "column"
            and binding["source_id"] not in sources
        ):
            problems.append(
                (
                    f"/after/fields/{escape(name)}/source_id",
                    "LOCAL_SOURCE_UNKNOWN",
                    {"已声明来源": sources},
                    binding["source_id"],
                )
            )
    return problems


def check_result(result, schema, context=None):
    errors = schema_errors(result, schema)
    if errors:
        return errors
    items = result["items"]
    refs = [i["client_ref"] for i in items if i.get("client_ref")]
    creates = {
        i["client_ref"]
        for i in items
        if i["operation"] == "create" and i.get("client_ref")
    }
    seen_refs, targets = set(), set()
    for index, item in enumerate(items):
        base = f"/items/{index}"

        def add(path, code, expected, actual, base=base, item=item):
            errors.append(diagnostic(base + path, code, expected, actual, item))

        operation = item["operation"]
        before, after = item.get("before"), item.get("after")
        ref = item.get("client_ref")
        if ref and ref in seen_refs:
            add("/client_ref", "CHECK", "client_ref 不重复", ref)
        if ref:
            seen_refs.add(ref)
        if operation == "create":
            if not ref:
                add("/client_ref", "CHECK", "create 需非空 client_ref", ref)
            for key in ("target_id", "before"):
                if item.get(key) is not None:
                    add("/" + key, "CHECK", "create 必须为空", item[key])
            if not isinstance(after, dict):
                add("/after", "CHECK", "create 需对象", after)
        elif operation in {"update", "delete"}:
            for key in ("target_id", "before", "expected_target_hash"):
                if not item.get(key) or (
                    key == "before" and not isinstance(before, dict)
                ):
                    add(
                        "/" + key,
                        "CHECK",
                        "update/delete 需 target_id、before 与 expected_target_hash",
                        item.get(key),
                    )
            if operation == "update" and not isinstance(after, dict):
                add("/after", "CHECK", "update 需对象", after)
            if operation == "delete" and after is not None:
                add("/after", "CHECK", "delete 必须为空", after)
            if isinstance(before, dict) and before.get("id") != item.get("target_id"):
                add("/before/id", "CHECK", item.get("target_id"), before.get("id"))
            if item.get("target_id") in targets:
                add(
                    "/target_id",
                    "CHECK",
                    "同一批次不能重复更新或删除同一目标",
                    item.get("target_id"),
                )
            targets.add(item.get("target_id"))
        if isinstance(after, dict) and "id" in after:
            add("/after/id", "CHECK", "after 不带自身 id", after["id"])
        for problem in mapping_local_errors(item):
            add(*problem)

        def walk(value, path):
            if isinstance(value, dict):
                if set(value) == {"client_ref"} and value["client_ref"] not in creates:
                    add(
                        path + "/client_ref",
                        "CHECK",
                        {"client_ref 引用未闭合，可用": sorted(creates)},
                        value["client_ref"],
                    )
                for key, entry in value.items():
                    if key not in {"values", "evidence"}:
                        walk(entry, path + "/" + escape(key))
            elif isinstance(value, list):
                for offset, entry in enumerate(value):
                    walk(entry, path + f"/{offset}")

        walk(after, "/after")
        for offset, dependency in enumerate(item.get("depends_on", [])):
            if dependency not in refs:
                add(
                    f"/depends_on/{offset}",
                    "CHECK",
                    {"depends_on 引用未闭合，可用": refs},
                    dependency,
                )
    if context is not None:
        run = context.get("run", context)
        for key in HEADER_FIELDS:
            if key in run and result.get(key) != run[key]:
                errors.append(
                    diagnostic(
                        "/" + key,
                        "CONTEXT_MISMATCH 固定上下文不一致",
                        run[key],
                        result.get(key),
                    )
                )
        existing = pinned_targets(context)
        for index, item in enumerate(items):
            if item["operation"] not in {"update", "delete"}:
                continue
            base = f"/items/{index}"
            target = item.get("target_id")
            found = existing.get((item["target_kind"], target))
            if found is None:
                errors.append(diagnostic(
                    base + "/target_id", "TARGET_NOT_FOUND",
                    "固定草稿中的定义或实例基线中的实例", target, item,
                ))
                continue
            for field, code, expected in (
                ("before", "BEFORE_MISMATCH", found[0]),
                ("expected_target_hash", "TARGET_HASH_MISMATCH", found[1]),
            ):
                if not same_json(expected, item.get(field)):
                    errors.append(diagnostic(
                        base + "/" + field, code, expected, item.get(field), item,
                    ))
    return errors


def schema_errors(result, schema):
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def relevant(error):
        if not error.context:
            yield error
            return
        choices = error.schema.get(error.validator, [])
        selected = None
        if isinstance(error.instance, dict) and isinstance(choices, list):
            for index, choice in enumerate(choices):
                if "$ref" in choice:
                    choice = schema["$defs"].get(choice["$ref"].split("/")[-1], {})
                constants = {
                    k: v["const"]
                    for k, v in choice.get("properties", {}).items()
                    if "const" in v
                }
                if constants and all(
                    error.instance.get(k) == v for k, v in constants.items()
                ):
                    selected = index
                    break
        children = [
            e for e in error.context if selected is None or e.schema_path[0] == selected
        ]
        if selected is None and error.validator == "anyOf":
            # Prefer the structured value branch to the null alternative.
            children = [
                e
                for e in children
                if not (e.validator == "type" and e.schema.get("type") == "null")
            ]
        for child in children or [error]:
            if child is error:
                yield error
            else:
                yield from relevant(child)

    output = []
    for top in validator.iter_errors(result):
        for error in relevant(top):
            pointer = "/" + "/".join(escape(p) for p in error.absolute_path)
            code = "SCHEMA_" + str(error.validator).upper()
            expected = {error.validator: error.validator_value}
            actual = error.instance
            if error.validator == "required":
                expected = {
                    "必填字段": [
                        k for k in error.validator_value if k not in error.instance
                    ]
                }
                actual = {"已提供字段": list(error.instance)}
            elif error.validator == "additionalProperties" and isinstance(
                error.instance, dict
            ):
                expected = {"允许字段": list(error.schema.get("properties", {}))}
                actual = {
                    "不允许字段": sorted(
                        set(error.instance) - set(error.schema.get("properties", {}))
                    )
                }
            path = list(error.absolute_path)
            item = (
                result["items"][path[1]]
                if len(path) > 1 and path[0] == "items" and isinstance(path[1], int)
                else None
            )
            label = diagnostic(pointer, code, expected, actual, item)
            if label not in output:
                output.append(label)
    return output


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(handle, "wb") as target:
            target.write(data)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode()


def validate_file(
    result_path, schema_path, context_path=None, *, repair=False, publish=None, origins=None
):
    """origins: (fragment file, index) per merged item, so errors point at the part to fix."""
    errors, result, context = [], None, None
    report_path = Path(str(result_path) + ".errors.json")
    try:
        result_bytes = Path(result_path).read_bytes()
        schema = json.loads(Path(schema_path).read_bytes())
        context = json.loads(Path(context_path).read_bytes()) if context_path else None
        execution = (context or {}).get("execution")
        if execution:
            budget_path = Path(execution["budget_file"])
            minimum = execution["repair_used"]
            ledger = (
                json.loads(budget_path.read_bytes()) if budget_path.exists() else None
            )
            if ledger is not None and (
                ledger["run_token"] != context["run"]["run_token"]
                or type(ledger["used"]) is not int
                or ledger["used"] < minimum
            ):
                raise ValueError("修正计数不属于本轮或小于平台已用次数")
            used = ledger["used"] if ledger is not None else minimum
            changed = (
                ledger is not None
                and ledger.get("result_sha256")
                != hashlib.sha256(result_bytes).hexdigest()
            )
            # A changed candidate after a previous check is a correction even
            # when the caller forgets --repair. Rechecking identical bytes is free.
            used += int(bool(repair or changed))
            if used > 2:
                errors.append(
                    diagnostic(
                        "/execution/repair_used",
                        "REPAIR_BUDGET_EXHAUSTED",
                        "修正预算最多 2 轮，停止生成",
                        used,
                    )
                )
            atomic_write(
                budget_path,
                encode(
                    {
                        "run_token": context["run"]["run_token"],
                        "used": used,
                        "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
                    }
                ),
            )
        result = json.loads(result_bytes)
        errors.extend(check_result(result, schema, context))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        where = getattr(exc, "filename", None) or "候选结果、Schema、固定上下文或修正计数"
        reason = f"第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}" if isinstance(exc, json.JSONDecodeError) else str(exc)[:200] or type(exc).__name__
        errors.append(
            diagnostic(
                "/",
                f"INPUT_{type(exc).__name__.upper()}",
                f"可读的 {where}",
                reason,
            )
        )
    if origins:
        from prepare_result import located

        errors = [located(e, origins) for e in errors]
    # Full validator errors remain on disk, never on stdout.
    raw_errors = []
    if result is not None and "schema" in locals():
        raw_errors = [
            e.message
            for e in Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(result)
        ]
    atomic_write(
        report_path,
        encode({"total": len(errors), "errors": errors, "schema_details": raw_errors}),
    )
    shown = []
    for error in errors:
        line = error
        if len(("\n".join([*shown, line])).encode()) > 2700:
            break
        shown.append(line)
    if errors:
        omitted = len(errors) - len(shown)
        summary = (
            f"检查未通过：共 {len(errors)} 条，显示 {len(shown)} 条" + (f"、省略 {omitted} 条" if omitted else "")
            + f"。{'最终文件未替换。' if publish else ''}完整报告：{report_path}"
            + (f"。读后续：{command('read_input.py', str(report_path), '--pointer', f'/errors/{len(shown)}')}" if omitted else "")
        )
    else:
        summary = f"检查通过：{len(result['items'])} 条提案。完整报告：{report_path}"
        if publish:
            atomic_write(publish, result_bytes)
            summary += f"。已发布：{publish}"
    print((summary + "\n" + "\n".join(shown)).strip())
    return int(bool(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--context")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--publish", help="检查通过后原子替换最终文件")
    parser.add_argument("result")
    args = parser.parse_args()
    return validate_file(
        args.result, args.schema, args.context, repair=args.repair, publish=args.publish
    )


if __name__ == "__main__":
    raise SystemExit(main())
