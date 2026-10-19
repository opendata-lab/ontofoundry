"""Compile the approved core-1 exchange subset and gate delivery on official validation."""

import re

from ontofoundry_api.adapters.exporting import ExportBuilder, file_stem
from ontofoundry_api.domain.core import DerivedExpression, LinkType
from ontofoundry_api.domain.expressions import (
    render_references,
    resolve_derived_expression,
    resolve_rule_expression,
)
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.validation import validate_core_graph

from .export_mappings import MappingExporter
from .export_metrics import condition_sql
from .validator import BUILTIN_CONCEPTS, validate_schema, validate_semantics

BASES = {
    "string": "String",
    "integer": "Integer",
    "decimal": "Decimal",
    "float": "Float",
    "boolean": "Boolean",
    "date": "Date",
    "datetime": "DateTime",
}


def membership(model, obj, index):
    branches = []
    for branch in obj.derived_by:
        if isinstance(branch, DerivedExpression):
            branches.append(
                render_references(
                    resolve_derived_expression(model, obj.extends, branch.expression), model
                )
            )
            continue
        conditions = []
        for condition in branch.conditions:
            parts = [index.objects[obj.extends].technical_name]
            for step in condition.path.links:
                name = index.links[step.link_type_id].technical_name
                parts.append(
                    "REVERSE(" + name + ")" if str(step.direction) == "reverse" else name
                )
            parts.append(index.properties[condition.path.property_id].technical_name)
            conditions.append("(" + condition_sql(".".join(parts), condition) + ")")
        branches.append(" AND ".join(conditions))
    return branches


def export_document(model, ctx):
    report = ExportBuilder("ossie-0.2", model)
    filename = file_stem(ctx) + ".ossie.json"
    try:
        validate_core_graph(model)
    except ValueError as error:
        report.issue(
            "",
            "error",
            "document",
            "RT-61",
            "核心模型不能合法导出：" + str(error),
            completion=True,
        )
        return report.finish(None, filename)
    if not model.object_types:
        report.issue(
            "/object_types",
            "error",
            "document",
            None,
            "Ossie 要求至少一个业务对象；空模型或仅含数据集指标时请明确选择原生单文件",
        )
        return report.finish(None, filename)
    index = DraftIndex(model)
    used = {name.casefold() for name in BUILTIN_CONCEPTS} | {
        o.technical_name.casefold() for o in model.object_types
    }
    builtins = {name.casefold() for name in BUILTIN_CONCEPTS}
    for pos, obj in enumerate(model.object_types):
        if obj.technical_name.casefold() in builtins:
            report.issue(
                f"/object_types/{pos}",
                "error",
                "object_types",
                None,
                "对象技术名与 Ossie 内置概念冲突，请先改名",
                element=obj,
            )
    if any(i.outcome == "error" for i in report.report.issues):
        return report.finish(None, filename)
    value_names, values = {}, []
    for prop in sorted(
        (p for p in model.properties if p.identifier),
        key=lambda p: (index.objects[p.owner_type_id].technical_name, p.technical_name),
    ):
        owner = index.objects[prop.owner_type_id]
        base = owner.technical_name + "_" + prop.technical_name + "_value"
        name, suffix = base, 2
        while name.casefold() in used:
            name = base + "_" + str(suffix)
            suffix += 1
        used.add(name.casefold())
        value_names[prop.id] = name
        values.append(
            {"concept": name, "type": "ValueType", "extends": [BASES[str(prop.value_kind)]]}
        )
    extension = {
        "version": "core-1",
        "display_names": {},
        "link_role_names": {},
        "generated_link_readings": [],
        "synonyms": {},
        "tags": {},
        "title_properties": {},
        "required": [],
    }
    components, owners = [], {}

    def labels(element, key):
        if not isinstance(element, LinkType):
            extension["display_names"][key] = element.name
        if getattr(element, "synonyms", []):
            extension["synonyms"][key] = element.synonyms
        if getattr(element, "tags", []):
            extension["tags"][key] = element.tags

    for pos, obj in enumerate(model.object_types):
        value = {"concept": obj.technical_name, "type": "EntityType", "relationships": []}
        if obj.description:
            value["description"] = obj.description
        if obj.extends:
            value["extends"] = [index.objects[obj.extends].technical_name]
        identifiers = index.identifier(obj.id)
        if identifiers:
            value["identify_by"] = [p.technical_name for p in identifiers]
        if obj.derived_by:
            try:
                value["derived_by"] = membership(model, obj, index)
                report.issue(
                    f"/object_types/{pos}/derived_by",
                    "converted",
                    "DerivedBy",
                    "RT-67",
                    "完整输出成员分支并集、条件路径与方向，不生成重复规则",
                    element=obj,
                )
            except (ValueError, KeyError) as error:
                report.issue(
                    f"/object_types/{pos}/derived_by",
                    "error",
                    "DerivedBy",
                    "RT-31",
                    "成员定义无法完整输出：" + str(error),
                    element=obj,
                    completion=True,
                )
        owners[obj.id] = value
        components.append(value)
        labels(obj, obj.technical_name)
        if obj.title_property_id:
            extension["title_properties"][obj.technical_name] = index.properties[
                obj.title_property_id
            ].technical_name
        report.issue(
            f"/object_types/{pos}",
            "converted",
            "object_types",
            None,
            "输出业务对象、单父与有效标识",
            element=obj,
            target_path=f"/ontology/{pos}",
        )
    for pos, prop in enumerate(model.properties):
        owner = index.objects[prop.owner_type_id].technical_name
        concept = value_names.get(prop.id, BASES[str(prop.value_kind)])
        raw = {
            "name": prop.technical_name,
            "roles": [{"concept": concept}],
            "multiplicity": "OneToOne" if prop.unique else "ManyToOne",
            "verbalizes": [f"{{{owner}}}的{prop.technical_name}是{{{concept}}}"],
        }
        if prop.description:
            raw["description"] = prop.description
        owners[prop.owner_type_id]["relationships"].append(raw)
        owners[prop.id] = raw
        path = owner + "." + prop.technical_name
        labels(prop, path)
        if prop.required:
            extension["required"].append(path)
        report.issue(
            f"/properties/{pos}",
            "converted",
            "properties",
            "RT-23",
            "输出属性、七值类型及唯一性",
            element=prop,
        )
    for pos, link in enumerate(model.link_types):
        source = index.objects[link.source_type_id].technical_name
        target = index.objects[link.target_type_id].technical_name
        role_name = link.target_role_name
        if (
            role_name == source
            or source == target and role_name is None
            or role_name and any(char in role_name for char in "{}")
        ):
            role_name = "related" if source != "related" else "related_2"
        role = target + (":" + role_name if role_name else "")
        raw = {
            "name": link.technical_name,
            "roles": [
                {"concept": target, **({"name": role_name} if role_name else {})}
            ],
            "verbalizes": [
                re.sub(
                    r"\{(source|target)\}",
                    lambda match: "{" + (source if match[1] == "source" else role) + "}",
                    reading,
                )
                for reading in (link.verbalizes or ["{source}关联{target}"])
            ],
        }
        if str(link.multiplicity) != "many_to_many":
            raw["multiplicity"] = {"one_to_one": "OneToOne", "many_to_one": "ManyToOne"}[
                str(link.multiplicity)
            ]
        if link.description:
            raw["description"] = link.description
        owners[link.source_type_id]["relationships"].append(raw)
        owners[link.id] = raw
        path = source + "." + link.name
        if not link.verbalizes:
            extension["generated_link_readings"].append(path)
        labels(link, path)
        if link.source_role_name or link.target_role_name or source == target:
            extension["link_role_names"][path] = {
                "source_role_name": link.source_role_name,
                "target_role_name": link.target_role_name,
            }
        report.issue(
            f"/link_types/{pos}",
            "converted",
            "link_types",
            "RT-20",
            "输出二元关系、基数、完整读法及两端角色名",
            element=link,
        )
    for pos, rule in enumerate(model.rules):
        try:
            if (
                str(rule.rule_kind) == "derivation"
                and str(rule.owner_kind) == "object_type"
                and index.objects[rule.owner_id].extends
            ):
                raise ValueError("子对象的说明性派生规则不能混写为成员定义")
            text = render_references(resolve_rule_expression(model, rule), model)
            owners[rule.owner_id].setdefault(
                "requires" if str(rule.rule_kind) == "constraint" else "derived_by", []
            ).append(text)
            report.issue(
                f"/rules/{pos}",
                "converted",
                "rules",
                "RT-31",
                "规则按已解析引用输出当前名称、路径及方向",
                element=rule,
            )
        except (KeyError, ValueError) as error:
            report.issue(
                f"/rules/{pos}",
                "error",
                "rules",
                "RT-31",
                "规则无法等价输出：" + str(error),
                element=rule,
                completion=True,
            )
    for metric in model.metrics:
        labels(metric, "metric:" + metric.technical_name)
    extension["required"].sort()
    value = {
        "version": "0.2.0.dev0",
        "name": ctx.workspace_name,
        "ontology": sorted(values, key=lambda c: c["concept"])
        + sorted(components, key=lambda c: c["concept"]),
        "ai_context": {"ontofoundry": extension},
    }
    if ctx.workspace_description:
        value["description"] = ctx.workspace_description
    writer = MappingExporter(model, ctx, report)
    mappings = writer.finish()
    if mappings:
        for mapping in mappings:
            for dataset in mapping["semantic_model"]["datasets"]:
                dataset["fields"].sort(key=lambda field: field["name"])
        value["ontology_mappings"] = mappings
    for component in components:
        component["relationships"].sort(key=lambda relationship: relationship["name"])
    positions = {
        component["concept"]: pos for pos, component in enumerate(value["ontology"])
    }
    for pos, issue in enumerate(report.report.issues):
        if issue.construct == "object_types" and issue.target_path is not None:
            obj = index.objects[issue.target_element_ids[0]]
            report.report.issues[pos] = issue.model_copy(
                update={"target_path": f"/ontology/{positions[obj.technical_name]}"}
            )
    for collection in ("material_objects", "material_links"):
        for pos, fact in enumerate(getattr(model, collection)):
            report.issue(
                f"/{collection}/{pos}",
                "dropped",
                collection,
                None,
                "Ossie 不包含文档事实实例，请使用原生单文件保留定义",
                element=fact,
            )
    report.issue(
        "",
        "dropped",
        "EvidenceAndRuleMetadata",
        None,
        "Ossie 不包含证据和材料，也不保存规则名、技术名与描述；这些内容未放入平台扩展块",
    )
    validation = validate_schema(value)
    if not validation:
        validation += validate_semantics(value)
    for issue in validation:
        report.issue(
            issue["path"],
            "error" if issue["severity"] == "error" else "converted",
            "OfficialValidation",
            None,
            "Ossie 官方交付校验：" + issue["message"],
            severity=issue["severity"],
        )
    return report.finish(value, filename)
