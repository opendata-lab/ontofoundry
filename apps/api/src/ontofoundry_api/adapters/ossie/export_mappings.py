"""Export shared datasets, row keys and explicitly expressible business bindings."""

from collections import defaultdict

from sqlglot import exp

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import (
    ColumnBinding,
    DirectJoin,
    ExpressionBinding,
    PropertiesKey,
)
from ontofoundry_api.domain.expressions import resolve_field_expression
from ontofoundry_api.domain.graph import DraftIndex

from .ids import technical_name


class MappingExporter:
    def __init__(self, model, ctx, report):
        self.model, self.ctx, self.report = model, ctx, report
        self.index = DraftIndex(model)
        self.datasets, self.maps, self.names = {}, {}, {}
        self.fields = defaultdict(dict)
        self.physical = defaultdict(dict)
        self.property_fields = {}
        self.keys = defaultdict(list)
        self.key_candidates = defaultdict(set)
        self.join_names = set()
        used = set()
        for d in sorted(model.datasets, key=lambda d: (d.name, str(d.id))):
            self.names[d.id] = technical_name(d.name, used)
            if self.names[d.id] != d.name:
                report.issue(
                    f"/datasets/{self.position(d)}",
                    "converted",
                    "DatasetName",
                    "RT-62",
                    "外部字段作用域使用稳定且无冲突的数据集名",
                    element=d,
                )
            scope = self.scope(d.id)
            if scope not in self.maps:
                name = "source_" + str(len(self.maps) + 1)
                self.maps[scope] = {
                    "name": name,
                    "semantic_model": {
                        "name": name,
                        "datasets": [],
                        "relationships": [],
                        "metrics": [],
                    },
                    "concept_mappings": [],
                }
            parts = [*(d.schema_name.split(".") if d.schema_name else []), d.table_name]
            source = ".".join(exp.to_identifier(part, quoted=True).sql() for part in parts)
            self.datasets[d.id] = {"name": self.names[d.id], "source": source, "fields": []}
            self.maps[scope]["semantic_model"]["datasets"].append(self.datasets[d.id])
            description = d.description
            if d.snapshot_date_column:
                description += (
                    ("\n\n" if description else "")
                    + f"快照日期列：{d.snapshot_date_column}。各数据集独立取最新日或周期内末日，同一数据集所有行使用同一天。"
                )
                report.issue(
                    f"/datasets/{self.position(d)}/snapshot_date_column",
                    "dropped",
                    "DatasetSnapshot",
                    "RT-60",
                    "快照日期及独立选日约定写入本数据集说明，无法从说明自动恢复",
                    element=d,
                )
            if d.dialect or any(c.physical_type or c.comment for c in d.columns or []):
                metadata = "；".join(
                    filter(
                        None,
                        [
                            "来源方言：" + d.dialect if d.dialect else "",
                            *[
                                c.name
                                + (" " + c.physical_type if c.physical_type else "")
                                + (" " + c.comment if c.comment else "")
                                for c in d.columns or []
                            ],
                        ],
                    )
                )
                description += (
                    ("\n\n" if description else "") + "物理元数据说明：" + metadata
                )
                report.issue(
                    f"/datasets/{self.position(d)}",
                    "dropped",
                    "DatasetMetadata",
                    "RT-66",
                    "来源方言与物理列元数据写入说明，不承诺同构回读",
                    element=d,
                )
            if description:
                self.datasets[d.id]["description"] = description
        self.populate_fields()
        self.populate_keys()

    def position(self, dataset):
        return self.model.datasets.index(dataset)

    def scope(self, dataset_id):
        # Unknown connections remain separate; neither table nor schema proves a connection.
        return (self.ctx.dataset_scopes or {}).get(
            dataset_id, "unresolved:" + str(dataset_id)
        )

    @staticmethod
    def expression(text):
        return {"dialects": [{"dialect": "ANSI_SQL", "expression": text}]}

    def add_field(self, dataset_id, wanted, text, *, column=None):
        fields = self.fields[dataset_id]
        name, suffix = wanted, 2
        while (
            name.casefold() in {f.casefold() for f in fields} and fields.get(name) != text
        ):
            name = wanted + ("_col" if suffix == 2 else "_col_" + str(suffix - 1))
            suffix += 1
        if name not in fields:
            fields[name] = text
            self.datasets[dataset_id]["fields"].append(
                {"name": name, "expression": self.expression(text)}
            )
        if column is not None:
            self.physical[dataset_id].setdefault(column, name)
        if name != wanted:
            self.report.issue(
                "/datasets",
                "converted",
                "FieldName",
                "RT-40",
                f"字段 {wanted} 存在不同定义，稳定分配为 {name}",
            )
        return name

    def column_field(self, dataset_id, column):
        if column not in self.physical[dataset_id]:
            self.add_field(
                dataset_id,
                column,
                exp.to_identifier(column, quoted=True).sql(),
                column=column,
            )
        return self.physical[dataset_id][column]

    def ref(self, dataset_id, column):
        return exp.column(
            self.column_field(dataset_id, column), table=self.names[dataset_id], quoted=True
        ).sql()

    def populate_fields(self):
        for obj in sorted(
            self.model.object_types, key=lambda o: (o.technical_name, str(o.id))
        ):
            binding = resolve_binding(self.model, obj.id)
            for prop in self.index.effective_properties(obj.id):
                field = binding.fields.get(prop.technical_name)
                if isinstance(field, ColumnBinding):
                    source = binding.sources[field.source_id]
                    name = self.add_field(
                        source.dataset_id,
                        prop.technical_name,
                        exp.to_identifier(field.column, quoted=True).sql(),
                        column=field.column,
                    )
                    self.property_fields[obj.id, prop.id] = (
                        source.dataset_id,
                        name,
                        field.column,
                    )
                elif isinstance(field, ExpressionBinding):
                    try:
                        mapping = next(
                            m
                            for m in reversed(binding.mappings)
                            if prop.technical_name in m.fields
                        )
                        resolved = resolve_field_expression(
                            self.model, mapping, field.expression
                        )
                        scopes = {r.dataset_id for r in resolved.references}
                        dataset_id = (
                            next(iter(scopes))
                            if len(scopes) == 1
                            else binding.main.dataset_id
                        )
                        text = resolved.text
                        for ref in reversed(resolved.references):
                            replacement = (
                                exp.to_identifier(ref.column, quoted=True).sql()
                                if len(scopes) <= 1
                                else self.ref(ref.dataset_id, ref.column)
                            )
                            text = text[: ref.start] + replacement + text[ref.end :]
                        name = self.add_field(dataset_id, prop.technical_name, text)
                        self.property_fields[obj.id, prop.id] = dataset_id, name, None
                        if len(scopes) > 1:
                            self.report.issue(
                                "/mappings",
                                "converted",
                                "FieldExpression",
                                "RT-54",
                                "跨来源计算保留已解析引用；回读作用域无法确定时需要补全",
                                element=mapping,
                                severity="warning",
                            )
                    except (KeyError, ValueError, AttributeError) as error:
                        self.report.issue(
                            "/mappings",
                            "dropped",
                            "FieldExpression",
                            "RT-54",
                            "计算绑定无法表达：" + str(error),
                            element=prop,
                        )
        for d in self.model.datasets:
            for column in d.columns or []:
                self.column_field(d.id, column.name)

    def populate_keys(self):
        for mapping in self.model.mappings:
            for source in mapping.sources:
                if source.key_columns:
                    d = self.index.datasets[source.dataset_id]
                    key = list(source.key_columns)
                    if d.snapshot_date_column and d.snapshot_date_column not in key:
                        key.append(d.snapshot_date_column)
                    self.key_candidates[d.id].add(tuple(key))
        for d in self.model.datasets:
            candidates = self.key_candidates[d.id]
            if len(candidates) == 1:
                physical = next(iter(candidates))
                self.keys[d.id].append(physical)
                self.datasets[d.id]["primary_key"] = [
                    self.column_field(d.id, c) for c in physical
                ]
            elif len(candidates) > 1:
                self.report.issue(
                    f"/datasets/{self.position(d)}",
                    "dropped",
                    "DatasetKey",
                    "RT-64",
                    "同一数据集有冲突的来源键，省略主键且不任取其一",
                    element=d,
                )
        for obj in self.model.object_types:
            for prop in self.index.effective_properties(obj.id):
                value = self.property_fields.get((obj.id, prop.id))
                if not prop.unique or value is None or value[2] is None:
                    continue
                dataset_id, _, column = value
                if self.index.datasets[dataset_id].snapshot_date_column:
                    continue
                key = (column,)
                if key not in self.keys[dataset_id]:
                    self.keys[dataset_id].append(key)
                    self.datasets[dataset_id].setdefault("unique_keys", []).append(
                        [self.column_field(dataset_id, column)]
                    )

    def physical_join(self, source, target, left, right, *, path, element=None):
        if self.scope(source) != self.scope(target):
            self.report.issue(
                path,
                "dropped",
                "PhysicalRelationship",
                "RT-53",
                "来源连接未确定或跨连接，只保留本体关系和数据集",
                element=element,
            )
            return False
        target_keys = [
            k for k in self.keys[target] if len(k) == len(right) and set(k) == set(right)
        ]
        if len(left) != len(right) or not target_keys:
            self.report.issue(
                path,
                "dropped",
                "PhysicalRelationship",
                "RT-64",
                "目标完整历史键或唯一键无法成立，不伪造连接或日期相等",
                element=element,
            )
            return False
        key = target_keys[0]
        left = [left[right.index(c)] for c in key]
        raw = {
            "from": self.names[source],
            "to": self.names[target],
            "from_columns": [self.column_field(source, c) for c in left],
            "to_columns": [self.column_field(target, c) for c in key],
        }
        relationships = self.maps[self.scope(source)]["semantic_model"]["relationships"]
        if any(all(r[k] == v for k, v in raw.items()) for r in relationships):
            return True
        raw["name"] = technical_name(
            self.names[source] + "_to_" + self.names[target], self.join_names
        )
        relationships.append(raw)
        return True

    def identity(self, obj_id, *, columns=None):
        identifiers = self.index.identifier(obj_id)
        if not identifiers:
            raise ValueError("对象没有完整业务标识")
        pairs = []
        for prop in identifiers:
            value = (
                columns.get(prop.id)
                if columns
                else self.property_fields.get((obj_id, prop.id))
            )
            if value is None:
                raise ValueError("业务标识属性缺可表达绑定")
            dataset_id, name, _ = value
            pairs.append(
                (prop, exp.column(name, table=self.names[dataset_id], quoted=True).sql())
            )
        if len(pairs) == 1:
            return {"expression": pairs[0][1]}
        return {
            "referent_mappings": [
                {"relationship": p.technical_name, "expression": text} for p, text in pairs
            ]
        }

    def object_mappings(self):
        for index, obj in enumerate(self.model.object_types):
            path = f"/object_types/{index}"
            binding = resolve_binding(self.model, obj.id)
            if not binding.main:
                if self.index.children(obj.id):
                    self.report.issue(
                        path,
                        "dropped",
                        "VirtualPopulation",
                        "RT-65",
                        "虚拟父对象的实例并集不能表达为外部单一来源",
                        element=obj,
                    )
                continue
            if any(
                m.membership_source_id or m.inherited_link_bindings
                for m in binding.mappings
            ):
                self.report.issue(
                    path,
                    "dropped",
                    "MembershipBinding",
                    "RT-57",
                    "成员扩展来源或额外继承绑定不能机械往返，派生定义与数据集仍保留",
                    element=obj,
                )
            try:
                identity = self.identity(obj.id)
                main = binding.main
                identity_datasets = {
                    self.property_fields[obj.id, p.id][0]
                    for p in self.index.identifier(obj.id)
                }
                if identity_datasets != {main.dataset_id}:
                    raise ValueError("主身份不能由单一主来源表达")
                for source in binding.sources.values():
                    if source.id != "main" and not self.physical_join(
                        main.dataset_id,
                        source.dataset_id,
                        main.key_columns,
                        source.key_columns,
                        path=path,
                        element=obj,
                    ):
                        raise ValueError("附来源的唯一星形连接不完整")
                children = []
                for prop in self.index.effective_properties(obj.id):
                    value = self.property_fields.get((obj.id, prop.id))
                    if value is not None:
                        ds, field, _ = value
                        children.append(
                            {
                                "relationship": prop.technical_name,
                                "object_mapping": {
                                    "expression": exp.column(
                                        field, table=self.names[ds], quoted=True
                                    ).sql()
                                },
                            }
                        )
                concept = {
                    "concept": obj.technical_name,
                    "object_mappings": [identity],
                    "link_mappings": [{"object_mapping": identity, "children": children}],
                }
                self.maps[self.scope(main.dataset_id)]["concept_mappings"].append(concept)
                self.report.issue(
                    path,
                    "converted",
                    "mappings",
                    "RT-52",
                    "单一主身份与平铺属性子节点共享已登记数据集",
                    element=obj,
                )
            except (ValueError, KeyError) as error:
                self.report.issue(
                    path,
                    "dropped",
                    "ObjectMapping",
                    "RT-43",
                    "对象映射未导出：" + str(error),
                    element=obj,
                )

    def property_columns(self, obj_id, props):
        values = [self.property_fields[obj_id, p] for p in props]
        if (
            not values
            or any(v[2] is None for v in values)
            or len({v[0] for v in values}) != 1
        ):
            raise ValueError("连接键必须对应同一来源的直接列")
        return values[0][0], [v[2] for v in values]

    def end_key(self, obj_id, key):
        if isinstance(key, PropertiesKey):
            return self.property_columns(obj_id, key.property_ids)
        main = resolve_binding(self.model, obj_id).main
        if not main or not main.key_columns:
            raise ValueError("端点主来源键不完整")
        return main.dataset_id, list(main.key_columns)

    def foreign_identity(
        self, obj_id, end_dataset, end_columns, from_dataset, from_columns
    ):
        replacements = {}
        for prop in self.index.identifier(obj_id):
            ds, _, column = self.property_fields[obj_id, prop.id]
            if ds != end_dataset or column not in end_columns:
                raise ValueError("引用列无法表达目标完整业务标识，保留物理连接")
            physical = from_columns[end_columns.index(column)]
            replacements[prop.id] = (
                from_dataset,
                self.column_field(from_dataset, physical),
                physical,
            )
        return self.identity(obj_id, columns=replacements)

    def link_mappings(self):
        for index, link in enumerate(self.model.link_types):
            path = f"/link_types/{index}/data_join"
            join = link.data_join
            if join is None:
                continue
            try:
                if isinstance(join, DirectJoin):
                    source, left = self.property_columns(
                        link.source_type_id, join.source_property_ids
                    )
                    target, right = self.property_columns(
                        link.target_type_id, join.target_property_ids
                    )
                    if not self.physical_join(
                        source, target, left, right, path=path, element=link
                    ):
                        continue
                    root = self.identity(link.source_type_id)
                    child = self.foreign_identity(
                        link.target_type_id, target, right, source, left
                    )
                    scope = self.scope(source)
                else:
                    source, left = self.end_key(link.source_type_id, join.source_key)
                    target, right = self.end_key(link.target_type_id, join.target_key)
                    first = self.physical_join(
                        join.dataset_id,
                        source,
                        join.source_columns,
                        left,
                        path=path,
                        element=link,
                    )
                    second = self.physical_join(
                        join.dataset_id,
                        target,
                        join.target_columns,
                        right,
                        path=path,
                        element=link,
                    )
                    if not first or not second:
                        continue
                    root = self.foreign_identity(
                        link.source_type_id,
                        source,
                        left,
                        join.dataset_id,
                        join.source_columns,
                    )
                    child = self.foreign_identity(
                        link.target_type_id,
                        target,
                        right,
                        join.dataset_id,
                        join.target_columns,
                    )
                    scope = self.scope(join.dataset_id)
                concept = next(
                    (
                        c
                        for c in self.maps[scope]["concept_mappings"]
                        if c["concept"]
                        == self.index.objects[link.source_type_id].technical_name
                    ),
                    None,
                )
                if concept is None:
                    raise ValueError("源对象映射不完整")
                concept["link_mappings"].append(
                    {
                        "object_mapping": root,
                        "children": [
                            {"relationship": link.technical_name, "object_mapping": child}
                        ],
                    }
                )
                self.report.issue(
                    path,
                    "converted",
                    "RelationshipBinding",
                    "RT-53",
                    "业务链接与精确物理列组同时输出",
                    element=link,
                )
            except (KeyError, ValueError) as error:
                self.report.issue(
                    path,
                    "dropped",
                    "RelationshipBinding",
                    "RT-53",
                    str(error),
                    element=link,
                )

    def finish(self):
        self.object_mappings()
        self.link_mappings()
        from .export_metrics import export_metrics

        export_metrics(self)
        for d in self.model.datasets:
            self.report.issue(
                f"/datasets/{self.position(d)}",
                "converted",
                "datasets",
                "RT-62",
                "每个登记数据集只输出一次，属性、关联和指标共用",
                element=d,
            )
        return list(self.maps.values())
