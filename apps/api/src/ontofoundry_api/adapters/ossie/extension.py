"""Only the documented core-1 presentation metadata is read."""

from dataclasses import dataclass, field


@dataclass
class Extension:
    data: dict = field(default_factory=dict)
    source_path: str = "/ontofoundry-extension.json"

    def name(self, path, fallback=None):
        return self.data.get("display_names", {}).get(path, fallback)

    def labels(self, kind, path):
        return self.data.get(kind, {}).get(path, [])

    def required(self, path):
        return path in self.data.get("required", [])


def read_extension(translation):
    data = getattr(translation, "extension", None)
    source_path = "/ontofoundry-extension.json"
    if data is None:
        return Extension()
    if not isinstance(data, dict) or data.get("version") != "core-1":
        translation.issue(
            source_path,
            "dropped",
            "Extension",
            "RT-03",
            "仅读取 core-1 显示扩展；旧版本整块不读取",
        )
        return Extension()
    allowed = {
        "version",
        "action_ref_names",
        "dataset_metadata",
        "metric_metadata",
        "display_names",
        "inverse_names",
        "link_role_names",
        "generated_link_readings",
        "synonyms",
        "tags",
        "title_properties",
        "required",
        "unsupported",
        "rules",
        "actions",
    }
    for key in data.keys() - allowed:
        translation.issue(
            source_path + "/" + key.replace("~", "~0").replace("/", "~1"),
            "dropped",
            "Extension",
            "RT-03",
            "本期未承载的扩展字段",
        )
    clean = {}
    for key in ("dataset_metadata", "metric_metadata"):
        clean[key] = {k: v for k, v in data.get(key, {}).items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(data.get(key), dict) else {}
    for key in ("display_names", "inverse_names", "title_properties"):
        clean[key] = (
            {
                k: v
                for k, v in data.get(key, {}).items()
                if isinstance(k, str) and isinstance(v, str) and v.strip()
            }
            if isinstance(data.get(key, {}), dict)
            else {}
        )
    rules = data.get("rules", {})
    clean["rules"] = (
        {
            key: value
            for key, value in rules.items()
            if isinstance(key, str)
            and "." in key
            and isinstance(value, dict)
            and isinstance(value.get("owner"), str)
            and key.startswith(value["owner"] + ".")
            and value.get("kind") in {"constraint", "derivation"}
            and type(value.get("position")) is int
            and value["position"] >= 0
            and isinstance(value.get("description", ""), str)
        }
        if isinstance(rules, dict)
        else {}
    )
    clean["link_role_names"] = {}
    roles = data.get("link_role_names", {})
    if isinstance(roles, dict):
        for path, names in roles.items():
            if not isinstance(path, str) or not isinstance(names, dict):
                continue
            clean["link_role_names"][path] = {
                key: value
                for key, value in names.items()
                if key in {"source_role_name", "target_role_name"}
                and (
                    value is None
                    or isinstance(value, str)
                    and 0 < len(value.strip()) <= 240
                )
            }
    for key in ("synonyms", "tags"):
        clean[key] = (
            {
                k: v
                for k, v in data.get(key, {}).items()
                if isinstance(v, list)
                and all(isinstance(s, str) and 0 < len(s) <= 120 for s in v)
                and len(v) <= 50
            }
            if isinstance(data.get(key, {}), dict)
            else {}
        )
    clean["generated_link_readings"] = (
        [path for path in data.get("generated_link_readings", []) if isinstance(path, str)]
        if isinstance(data.get("generated_link_readings", []), list)
        else []
    )
    clean["required"] = (
        data.get("required", []) if isinstance(data.get("required", []), list) else []
    )
    if "action_ref_names" in data and data["action_ref_names"] is not None:
        if source_path == "/ontofoundry-extension.json" and data["action_ref_names"] == "core":
            clean["action_ref_names"] = "core"
        else:
            translation.issue(
                source_path + "/action_ref_names",
                "dropped",
                "Extension",
                "RT-03",
                "扩展字段 action_ref_names 仅在 ZIP 的 ontofoundry-extension.json 中支持 core",
            )
    if "actions" in data and not isinstance(data["actions"], dict):
        translation.issue(
            source_path + "/actions",
            "dropped",
            "Action",
            "RT-03",
            "扩展字段 actions 必须是按英文标识为键的对象",
            completion=True,
        )
        clean["actions"] = {}
    else:
        clean["actions"] = data.get("actions", {}) if isinstance(data.get("actions"), dict) else {}
    return Extension(clean, source_path)


def metadata_key(scope, name):
    import json
    return json.dumps([scope, name], ensure_ascii=False, separators=(",", ":"))
