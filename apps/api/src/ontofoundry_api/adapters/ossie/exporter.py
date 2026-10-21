"""Compile the approved core-1 exchange subset and gate delivery on official validation."""

import re

from ontofoundry_api.adapters.archive import write_archive
from ontofoundry_api.adapters.exporting import ExportBuilder, file_stem, json_bytes
from ontofoundry_api.domain.core import DerivedExpression
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
            parts = [index.objects[obj.extends].name]
            for step in condition.path.links:
                name = index.links[step.link_type_id].name
                parts.append(
                    "REVERSE(" + name + ")" if str(step.direction) == "reverse" else name
                )
            parts.append(index.properties[condition.path.property_id].name)
            conditions.append("(" + condition_sql(".".join(parts), condition) + ")")
        branches.append(" AND ".join(conditions))
    return branches


def export_document(model, ctx):
    report = ExportBuilder("ossie-0.2", model)
    filename = file_stem(ctx) + ".ossie.zip"
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
    builtins = {name.casefold() for name in BUILTIN_CONCEPTS}
    for pos, obj in enumerate(model.object_types):
        if obj.name.casefold() in builtins:
            report.issue(
                f"/object_types/{pos}",
                "error",
                "object_types",
                None,
                "对象英文标识与 Ossie 内置概念冲突，请先改名",
                element=obj,
            )
    if any(i.outcome == "error" for i in report.report.issues):
        return report.finish(None, filename)
    value_names, values = {}, []
    shared = {}
    for value_type in sorted(model.value_types, key=lambda v: v.name):
        concept = {"concept": value_type.name, "type": "ValueType", "extends": [BASES[str(value_type.value_kind)]]}
        if value_type.description:
            concept["description"] = value_type.description
        shared[value_type.id] = concept
        values.append(concept)
    for prop in model.properties:
        if prop.value_type_id in shared:
            value_names[prop.id] = shared[prop.value_type_id]["concept"]
    extension = {
        "version": "core-1",
        "display_names": {},
        "link_role_names": {},
        "generated_link_readings": [],
        "synonyms": {},
        "tags": {},
        "title_properties": {},
        "required": [],
        "rules": {},
    }
    components, owners = [], {}

    def labels(element, key):
        if element.display_name:
            extension["display_names"][key] = element.display_name
        if getattr(element, "synonyms", []) and not key.startswith("metric:"):
            extension["synonyms"][key] = element.synonyms
        if getattr(element, "tags", []):
            extension["tags"][key] = element.tags

    for value_type in model.value_types:
        owners[value_type.id] = shared[value_type.id]
        labels(value_type, value_type.name)

    for pos, obj in enumerate(model.object_types):
        value = {"concept": obj.name, "type": "EntityType", "relationships": []}
        if obj.description:
            value["description"] = obj.description
        if obj.extends:
            value["extends"] = [index.objects[obj.extends].name]
        identifiers = index.identifier(obj.id)
        if identifiers:
            value["identify_by"] = [p.name for p in identifiers]
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
        labels(obj, obj.name)
        if obj.title_property_id:
            extension["title_properties"][obj.name] = index.properties[
                obj.title_property_id
            ].name
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
        owner = index.objects[prop.owner_type_id].name
        concept = value_names.get(prop.id, BASES[str(prop.value_kind)])
        raw = {
            "name": prop.name,
            "roles": [{"concept": concept}],
            "multiplicity": "OneToOne" if prop.unique else "ManyToOne",
            "verbalizes": [f"{{{owner}}}的{prop.name}是{{{concept}}}"],
        }
        if prop.description:
            raw["description"] = prop.description
        owners[prop.owner_type_id]["relationships"].append(raw)
        owners[prop.id] = raw
        path = owner + "." + prop.name
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
        source = index.objects[link.source_type_id].name
        target = index.objects[link.target_type_id].name
        role_name = link.target_role_name
        if (
            role_name == source
            or source == target
            and role_name is None
            or role_name
            and any(char in role_name for char in "{}")
        ):
            role_name = "related" if source != "related" else "related_2"
        role = target + (":" + role_name if role_name else "")
        raw = {
            "name": link.name,
            "roles": [{"concept": target, **({"name": role_name} if role_name else {})}],
            "verbalizes": [
                re.sub(
                    r"\{(source|target)\}",
                    lambda match, source=source, role=role: (
                        "{" + (source if match[1] == "source" else role) + "}"
                    ),
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
            expressions = owners[rule.owner_id].setdefault(
                "requires" if str(rule.rule_kind) == "constraint" else "derived_by", []
            )
            owner = {**index.objects, **index.properties, **index.links, **index.value_types}[rule.owner_id]
            owner_path = owner.name
            if str(rule.owner_kind) == "property":
                owner_path = index.objects[owner.owner_type_id].name + "." + owner.name
            elif str(rule.owner_kind) == "link_type":
                owner_path = index.objects[owner.source_type_id].name + "." + owner.name
            key = owner_path + "." + rule.name
            extension["rules"][key] = {
                "owner": owner_path,
                "kind": str(rule.rule_kind),
                "position": len(expressions),
                "description": rule.description,
            }
            labels(rule, "rule:" + key)
            expressions.append(text)
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
        labels(metric, "metric:" + metric.name)
    extension["required"].sort()
    extension["generated_link_readings"].sort()
    value = {
        "version": "0.2.0.dev0",
        "name": ctx.workspace_name,
        "ontology": sorted(values, key=lambda c: c["concept"])
        + sorted(components, key=lambda c: c["concept"]),
    }
    if ctx.workspace_description:
        value["description"] = ctx.workspace_description
    writer = MappingExporter(model, ctx, report)
    mappings = writer.finish()
    from .extension import metadata_key
    extension["dataset_metadata"], extension["metric_metadata"] = {}, {}
    for dataset in model.datasets:
        map_name = writer.maps[writer.scope(dataset.id)]["name"]
        key = metadata_key(map_name, writer.names[dataset.id])
        extension["dataset_metadata"][key] = {"snapshot_date_column": dataset.snapshot_date_column, "connection_name": (ctx.connection_names or {}).get(dataset.id)}
        if dataset.display_name:
            extension["display_names"]["dataset:" + key] = dataset.display_name
    for metric in model.metrics:
        if getattr(metric, "time_field", None):
            map_name = writer.maps[writer.scope(metric.dataset_id)]["name"]
            extension["metric_metadata"][metadata_key(map_name, metric.name)] = {"time_field": {"column": writer.column_field(metric.dataset_id, metric.time_field.column)}}
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
                update={"target_path": f"/ontology/{positions[obj.name]}"}
            )
    report.issue(
        "",
        "dropped",
        "EvidenceMetadata",
        None,
        "Ossie 不包含证据和材料；规则英文标识、名称与描述保存在平台扩展文件",
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
    extension["unsupported"] = [
        {
            "source_path": issue.source_path,
            "construct": issue.construct,
            "message": issue.message,
        }
        for issue in report.report.issues
        if issue.outcome == "dropped"
    ]
    document = write_archive(
        {
            file_stem(ctx) + ".ossie.json": json_bytes(value),
            "ontofoundry-extension.json": json_bytes(extension),
        }
    )
    return report.finish(document, filename, "application/zip")
