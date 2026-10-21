"""Bounded proposal diagnostics; no runtime skill filesystem dependency."""

import json


def short(value):
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return (
        text
        if len(text.encode()) <= 180
        else text.encode()[:170].decode("utf-8", "ignore") + "…"
    )


def diagnostic(pointer, message, expected, actual, item=None):
    item = item if isinstance(item, dict) else {}
    kind = item.get("target_kind", "object_type")
    if kind not in {
        "object_type",
        "property",
        "link_type",
        "dataset",
        "mapping",
        "metric",
        "rule",
        "material_object",
        "material_link",
    }:
        kind = "object_type"
    operation = item.get("operation", "create")
    if operation not in {"create", "update", "delete"}:
        operation = "create"
    after = item.get("after")
    variant = after.get("kind") if isinstance(after, dict) else None
    suffix = (
        f" --variant {variant}"
        if operation == "create" and kind == "metric" and variant in {"ratio", "expression"}
        else ""
    )
    return (
        f"{pointer} [{short(item.get('client_ref', item.get('target_id', '-')))}] {message}；"
        f"期望 {short(expected)}；实际 {short(actual)}；"
        f"查写法（技能目录内执行）：python scripts/show_example.py {kind} --operation {operation}{suffix}"
    )


def schema_diagnostic(error, schema, data):
    while error.context:
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
            children = [
                e
                for e in children
                if not (e.validator == "type" and e.schema.get("type") == "null")
            ]
        error = (children or list(error.context))[0]
    path = list(error.absolute_path)
    pointer = "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in path)
    item = (
        data["items"][path[1]]
        if len(path) > 1 and path[0] == "items" and isinstance(path[1], int)
        else None
    )
    expected, actual = {error.validator: error.validator_value}, error.instance
    if error.validator == "required":
        expected = {
            "必填字段": [k for k in error.validator_value if k not in error.instance]
        }
        actual = {"已提供字段": list(error.instance)}
    elif error.validator == "additionalProperties" and isinstance(actual, dict):
        expected = "仅允许该类型定义的字段"
        actual = {"多余字段": sorted(set(actual) - set(error.schema.get("properties", {})))}
    return diagnostic(pointer, "建模结果不符合契约", expected, actual, item)
