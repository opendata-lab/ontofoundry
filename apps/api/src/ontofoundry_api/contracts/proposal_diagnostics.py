"""Bounded proposal diagnostics; no runtime skill filesystem dependency."""

import json


def short(value):
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return (
        text
        if len(text.encode()) <= 180
        else text.encode()[:170].decode("utf-8", "ignore") + "…"
    )


def diagnostic(pointer, message, expected, actual, item=None, *, graph=False):
    if graph:
        # Whole-graph checks name the elements in `actual`; no single example fits.
        return (
            f"{pointer} [\"-\"] {message}；期望 {short(expected)}；实际 {actual}；"
            "下一步：按“实际”中列出的对象、关系逐个修正对应片段，全部改完后整批重提"
        )
    item = item if isinstance(item, dict) else {}
    return (
        f"{pointer} [{short(item.get('client_ref', item.get('target_id', '-')))}] {message}；"
        f"期望 {short(expected)}；实际 {short(actual)}；"
        # The platform cannot know where the skill is installed; it names the
        # skill's kit entry, and the error itself carries the expected shape.
        f"下一步：按“期望”改；完整写法见建模技能的 scripts/show_example.py {kit_entry(item)}"
    )


# Where the skill's fixed kit shows each kind (create).
KIT_PARTS = {
    "object_type": "01", "property": "01", "value_type": "01", "link_type": "02",
    "dataset": "03", "mapping": "03", "metric": "04", "rule": "04", "action": "04",
    "material_object": "05", "material_link": "05",
}
KIT_VARIANTS = {("metric", "ratio"): "metric-ratio", ("metric", "expression"): "metric-expression",
                ("dataset", "query"): "query-dataset", ("rule", "derivation"): "derivation"}


def kit_entry(item):
    operation = item.get("operation", "create")
    if operation == "delete":
        return "--part edit"
    if operation == "update":
        return "--part update"
    after = item.get("after") if isinstance(item.get("after"), dict) else {}
    kind = item.get("target_kind")
    variant = KIT_VARIANTS.get((kind, after.get("kind") or after.get("source_kind") or after.get("rule_kind")))
    return f"--variant {variant}" if variant else f"--part {KIT_PARTS.get(kind, '01')}"


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
