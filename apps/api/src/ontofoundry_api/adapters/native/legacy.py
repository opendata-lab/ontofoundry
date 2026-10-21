"""Convert previous core-1 files only at the external import boundary."""


def convert_names(data, report):
    for collection in ("object_types", "properties", "link_types", "rules", "metrics"):
        for position, element in enumerate(data.get(collection, [])):
            if "technical_name" not in element:
                continue
            previous = element.pop("name", None)
            element["name"] = element.pop("technical_name")
            if collection == "link_types":
                inverse = element.pop("inverse_name", None)
                if "verbalizes" not in element:
                    element["verbalizes"] = (
                        ["{source}" + previous + "{target}"] if previous else []
                    ) + (["{target}" + inverse + "{source}"] if inverse else [])
                element.setdefault("display_name", None)
            else:
                element["display_name"] = previous
            report.add(
                outcome="converted",
                construct="LegacyNames",
                source_path=f"/draft/{collection}/{position}",
                message="旧版原生文件字段已转换：technical_name → name，原名称 → display_name；仅兼容外部文件",
            )
    return data
