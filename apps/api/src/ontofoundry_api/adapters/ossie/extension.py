"""Only the documented core-1 presentation metadata is read."""

from dataclasses import dataclass, field


@dataclass
class Extension:
    data: dict = field(default_factory=dict)

    def name(self, path, fallback):
        return self.data.get("display_names", {}).get(path, fallback)

    def labels(self, kind, path):
        return self.data.get(kind, {}).get(path, [])

    def required(self, path):
        return path in self.data.get("required", [])


def read_extension(translation):
    context = translation.source.value.get("ai_context")
    if not isinstance(context, dict):
        if context:
            translation.issue(
                "/ai_context",
                "dropped",
                "AIContext",
                "RT-02",
                "文档上下文没有可确定的对象归属，保留原文",
            )
        return Extension()
    data = context.get("ontofoundry")
    if data is None:
        return Extension()
    if not isinstance(data, dict) or data.get("version") != "core-1":
        translation.issue(
            "/ai_context/ontofoundry",
            "dropped",
            "Extension",
            "RT-03",
            "仅读取 core-1 显示扩展；旧版本整块不读取",
        )
        return Extension()
    allowed = {
        "version",
        "display_names",
        "inverse_names",
        "synonyms",
        "tags",
        "title_properties",
        "required",
        "unsupported",
    }
    for key in data.keys() - allowed:
        translation.issue(
            "/ai_context/ontofoundry/" + key.replace("~", "~0").replace("/", "~1"),
            "dropped",
            "Extension",
            "RT-03",
            "本期未承载的扩展字段",
        )
    clean = {}
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
    clean["required"] = (
        data.get("required", []) if isinstance(data.get("required", []), list) else []
    )
    return Extension(clean)
