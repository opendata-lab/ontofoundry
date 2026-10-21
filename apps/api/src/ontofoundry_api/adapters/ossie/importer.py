"""Deterministic Ossie ontology import; no sessions, SQL execution or publishing."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from uuid import UUID

from ontofoundry_api.adapters.archive import read_ossie
from ontofoundry_api.adapters.base import ImportOnlyAdapter, ReportBuilder
from ontofoundry_api.adapters.documents import (
    SourceDocument,
    escape_pointer,
    parse_document,
)
from ontofoundry_api.domain.core import (
    DirectJoin,
    LinkType,
    ObjectType,
    Property,
    ValueKind,
    ValueType,
    empty_draft,
)
from ontofoundry_api.domain.graph import DraftIndex

from .extension import read_extension
from .ids import identifier_name
from .translation import Translation
from .validator import BUILTIN_VALUE_CONCEPTS, validate_schema, validate_semantics

BUILTINS = {name: ValueKind(name.lower()) for name in BUILTIN_VALUE_CONCEPTS}


class OntologyImporter:
    def __init__(self, translation):
        self.t = translation
        self.document = translation.source.value
        self.concepts = {
            c["concept"]: c
            for i, c in enumerate(self.document["ontology"])
            if translation.valid(f"/ontology/{i}")
        }
        self.paths = {
            c["concept"]: f"/ontology/{i}"
            for i, c in enumerate(self.document["ontology"])
            if translation.valid(f"/ontology/{i}")
        }
        self.extension = read_extension(translation)
        self.object_names = set()
        self.object_labels = set()
        self.symbols = {}
        self.origins = []
        self.invalid = set()
        self.value_cache = {}
        self.value_types = {}
        self.role_bindings = {}

    def issue(self, *args, **kwargs):
        return self.t.issue(*args, **kwargs)

    def value_kind(self, name, visiting=frozenset()):
        if name in BUILTINS:
            return BUILTINS[name]
        if name in self.value_cache:
            return self.value_cache[name]
        if name in visiting or self.concepts.get(name, {}).get("type") != "ValueType":
            return None
        parents = self.concepts[name].get("extends", [])
        kinds = [self.value_kind(p, visiting | {name}) for p in parents]
        result = kinds[0] if kinds and None not in kinds and len(set(kinds)) == 1 else None
        self.value_cache[name] = result
        return result

    def member_names(self, obj):
        if obj.id not in self.t.names:
            index = DraftIndex(self.t.model)
            members = [*index.effective_properties(obj.id), *index.outgoing_links(obj.id)]
            self.t.names[obj.id] = (
                {p.name.casefold() for p in members},
                {p.name.casefold() for p in members},
            )
        return self.t.names[obj.id]

    def names(self, obj, raw_name, label):
        names, labels = self.member_names(obj)
        return identifier_name(raw_name, names), label

    def import_value_types(self):
        """Ossie value types become shared core value types (no type inheritance)."""
        self.value_types = {}
        for name, c in self.concepts.items():
            if c["type"] != "ValueType" or name in BUILTINS:
                continue
            kind = self.value_kind(name)
            if kind is None:
                self.issue(
                    self.paths[name],
                    "dropped",
                    "ValueType",
                    "RT-35",
                    "值类型无法沿全部祖先闭合为唯一兼容基础类型",
                    completion=True,
                )
                continue
            value_type = ValueType(
                id=self.t.id("value-type:" + name),
                name=identifier_name(name, set()),
                display_name=self.extension.name(name, None),
                description=c.get("description", ""),
                value_kind=kind,
            )
            if self.t.accept("value_types", value_type, self.paths[name], rule="RT-23", message="值类型按共享值域导入"):
                self.value_types[name] = value_type
                if any(p not in BUILTINS for p in c.get("extends", [])):
                    self.issue(
                        self.paths[name] + "/extends",
                        "converted",
                        "ValueType",
                        "RT-24",
                        "值类型之间的继承折叠为基础类型，祖先约束复制到本值类型",
                        targets=[value_type.id],
                    )

    def import_objects(self):
        pending = [n for n, c in self.concepts.items() if c["type"] == "EntityType"]
        self.import_value_types()
        for name, c in self.concepts.items():
            if c["type"] == "ValueType":
                for field in ("relationships", "derived_by", "identify_by"):
                    if c.get(field):
                        self.issue(
                            self.paths[name] + "/" + field,
                            "dropped",
                            "ValueType",
                            "RT-24",
                            "值域的独立结构不进入核心，原文保留",
                            completion=True,
                        )
        while pending:
            progressed = False
            for name in list(pending):
                c = self.concepts[name]
                parents = c.get("extends", [])
                parent = parents[0] if parents else None
                if parent in pending:
                    continue
                pending.remove(name)
                progressed = True
                path = self.paths[name]
                if (
                    name in BUILTINS
                    or name == "Any"
                    or any(
                        p in BUILTINS or self.concepts.get(p, {}).get("type") == "ValueType"
                        for p in parents
                    )
                    or (parent and parent != "Any" and parent not in self.t.objects)
                ):
                    self.invalid.add(name)
                    self.issue(
                        path,
                        "error",
                        "EntityType",
                        None,
                        "实体父类不存在、无效或属于值类型；本对象及其依赖暂不导入",
                    )
                    continue
                for i in range(1, len(parents)):
                    self.issue(
                        path + f"/extends/{i}",
                        "dropped",
                        "Inheritance",
                        "RT-34",
                        "按文件顺序保留首个父类，不自动改写额外父类",
                        completion=True,
                    )
                tech = identifier_name(name, self.object_names)
                label = self.extension.name(name, None)
                try:
                    obj = ObjectType(
                        id=self.t.id("object:" + name),
                        display_name=label,
                        name=tech,
                        description=c.get("description", ""),
                        extends=self.t.objects[parent].id
                        if parent in self.t.objects
                        else None,
                        synonyms=self.extension.labels("synonyms", name),
                        tags=self.extension.labels("tags", name),
                    )
                except ValueError as error:
                    self.invalid.add(name)
                    self.issue(
                        path,
                        "error",
                        "EntityType",
                        None,
                        f"对象不能形成合法核心定义：{error}",
                    )
                    continue
                if self.t.accept("object_types", obj, path):
                    self.t.objects[name] = obj
                    self.t.object_paths[obj.id] = path
                    self.symbols[name] = tech
                    if tech != name:
                        self.issue(
                            path + "/concept",
                            "converted",
                            "ConceptName",
                            "RT-12",
                            "英文标识规范化并确定性消歧",
                            targets=[obj.id],
                        )
            if not progressed:
                for name in pending:
                    self.invalid.add(name)
                    self.issue(
                        self.paths[name],
                        "error",
                        "Inheritance",
                        None,
                        "继承成环或依赖无法转换的父对象，不生成残缺继承定义",
                    )
                break

    def import_property(self, owner, name, rel, path, kind, *, unary=False, concept=None):
        obj = self.t.objects[owner]
        shared = self.value_types.get(concept) if concept else None
        key = owner + "." + name
        label = self.extension.name(key, None)
        tech, label = self.names(obj, name, label)
        prop = Property(
            id=self.t.id("property:" + key),
            owner_type_id=obj.id,
            display_name=label,
            name=tech,
            description=rel.get("description", ""),
            value_kind=kind,
            value_type_id=shared.id if shared else None,
            required=self.extension.required(key),
            unique=rel.get("multiplicity") == "OneToOne",
            synonyms=self.extension.labels("synonyms", key),
        )
        if self.t.accept("properties", prop, path, rule="RT-26" if unary else None):
            self.t.members[(owner, name)] = prop
            self.t.property_sources[prop.id] = (owner, name, path)
            self.origins.append((prop, rel, path, "property:" + key))
            if tech != name:
                self.issue(
                    path + "/name",
                    "converted",
                    "RelationshipName",
                    "RT-12",
                    "属性英文标识已规范化",
                    targets=[prop.id],
                )
            if not unary and "multiplicity" not in rel:
                self.issue(
                    path,
                    "converted",
                    "Property",
                    "RT-22",
                    "外部未声明基数，核心属性收窄为单值",
                    targets=[prop.id],
                    severity="warning",
                )
            if not unary and rel.get("verbalizes"):
                self.issue(
                    path + "/verbalizes",
                    "dropped",
                    "Verbalization",
                    "RT-20",
                    "属性读法不单独存储",
                )
        return prop

    def import_binary_link(self, owner, name, rel, path):
        target = rel["roles"][0]["concept"]
        if target not in self.t.objects:
            self.issue(
                path,
                "dropped",
                "Relationship",
                "RT-29",
                "关系目标未承载或不存在，保留原文",
                completion=True,
            )
            return
        key = owner + "." + name
        source_role = "{" + owner + "}"
        target_role = (
            "{"
            + target
            + (":" + rel["roles"][0]["name"] if rel["roles"][0].get("name") else "")
            + "}"
        )
        readings = [
            re.sub(
                r"\{[^{}]+\}",
                lambda match: {source_role: "{source}", target_role: "{target}"}.get(
                    match.group(), match.group()
                ),
                reading,
            )
            for reading in rel.get("verbalizes", [])
        ]
        if key in self.extension.data.get("generated_link_readings", []) and readings == [
            "{source}关联{target}"
        ]:
            readings = []
        tech, _label = self.names(self.t.objects[owner], name, name)
        role_names = self.extension.data.get("link_role_names", {}).get(key, {})
        link = LinkType(
            id=self.t.id("link:" + key),
            name=tech,
            display_name=self.extension.name(key, None),
            verbalizes=readings,
            source_role_name=role_names.get("source_role_name"),
            target_role_name=role_names.get(
                "target_role_name", rel["roles"][0].get("name")
            ),
            description=rel.get("description", ""),
            synonyms=self.extension.labels("synonyms", key),
            tags=self.extension.labels("tags", key),
            source_type_id=self.t.objects[owner].id,
            target_type_id=self.t.objects[target].id,
            multiplicity={"ManyToOne": "many_to_one", "OneToOne": "one_to_one"}.get(
                rel.get("multiplicity"), "many_to_many"
            ),
        )
        if self.t.accept("link_types", link, path):
            self.t.members[(owner, name)] = link
            self.origins.append((link, rel, path, "link:" + key))

    def import_relationships(self):
        # Parents precede children, so inherited names are already reserved.
        for owner, _obj in sorted(
            self.t.objects.items(),
            key=lambda pair: len(DraftIndex(self.t.model).ancestors(pair[1].id)),
        ):
            relationship_counts = Counter(
                r.get("name")
                for r in self.concepts[owner].get("relationships", [])
                if isinstance(r, dict)
            )
            for i, rel in enumerate(self.concepts[owner].get("relationships", [])):
                path = self.paths[owner] + f"/relationships/{i}"
                if not self.t.valid(path):
                    continue
                name = rel["name"]
                roles = rel.get("roles", [])
                if relationship_counts[name] > 1:
                    self.issue(path, "error", "Relationship", None, "同一归属的关系名重复")
                    self.t.invalid_paths.add(path)
                    continue
                role_names = [owner, *[r.get("name", r["concept"]) for r in roles]]
                if len(role_names) != len(set(role_names)):
                    self.issue(
                        path,
                        "error",
                        "Relationship",
                        None,
                        "角色名有歧义，需为重复概念指定不同角色名",
                    )
                    self.t.invalid_paths.add(path)
                    continue
                if len(roles) > 1:
                    continue
                try:
                    if not roles:
                        if rel.get("multiplicity"):
                            self.issue(
                                path,
                                "error",
                                "Relationship",
                                None,
                                "一元关系不能声明二元基数",
                            )
                        else:
                            self.import_property(
                                owner, name, rel, path, ValueKind.BOOLEAN, unary=True
                            )
                    elif (
                        roles[0]["concept"] in BUILTINS
                        or self.concepts.get(roles[0]["concept"], {}).get("type")
                        == "ValueType"
                    ):
                        kind = self.value_kind(roles[0]["concept"])
                        if kind:
                            self.import_property(owner, name, rel, path, kind, concept=roles[0]["concept"])
                        else:
                            self.issue(
                                path,
                                "dropped",
                                "Property",
                                "RT-35",
                                "属性值类型未闭合，不能默认转字符串",
                                completion=True,
                            )
                    else:
                        self.import_binary_link(owner, name, rel, path)
                except ValueError as error:
                    self.issue(
                        path,
                        "error",
                        "Relationship",
                        None,
                        f"关系不能形成合法核心定义：{error}",
                    )
                for j, role in enumerate(roles):
                    if role.get("name"):
                        member = self.t.members.get((owner, name))
                        if isinstance(member, LinkType):
                            continue
                        self.issue(
                            path + f"/roles/{j}/name",
                            "dropped",
                            "Role",
                            "RT-21",
                            "独立角色名不存储；规则转换单独核对变量绑定",
                        )

    def identifiers(self):
        for name, obj in sorted(
            self.t.objects.items(),
            key=lambda p: len(DraftIndex(self.t.model).ancestors(p[1].id)),
        ):
            names = self.concepts[name].get("identify_by", [])
            if not names:
                continue
            path = self.paths[name] + "/identify_by"
            index = DraftIndex(self.t.model)
            props = []
            for n in names:
                prop = self.t.members.get((name, n))
                if prop is None:
                    for ancestor in index.ancestors(obj.id):
                        source = next(
                            k for k, v in self.t.objects.items() if v.id == ancestor
                        )
                        prop = self.t.members.get((source, n))
                        if prop is not None:
                            break
                props.append(prop)
            if not all(isinstance(p, Property) for p in props) or len(set(names)) != len(
                names
            ):
                rule = "RT-32" if any(isinstance(p, LinkType) for p in props) else "RT-30"
                self.issue(
                    path,
                    "dropped",
                    "Identifier",
                    rule,
                    "标识必须整组转换；存在关系成员或缺失属性，不裁剪为较小键",
                    completion=True,
                )
                continue
            inherited = index.identifier(obj.extends) if obj.extends else []
            conflict = inherited and {p.id for p in props} != {p.id for p in inherited}
            for prop in props:
                if len(props) == 1:
                    if not prop.unique:
                        self.issue(
                            path,
                            "converted",
                            "Identifier",
                            "RT-33",
                            "单属性编号补充唯一性",
                            targets=[prop.id],
                        )
                    prop.unique = True
                if not conflict and not inherited:
                    prop.identifier = True
            if conflict:
                self.issue(
                    path,
                    "dropped",
                    "Identifier",
                    "RT-68",
                    "子类沿用完整父标识；本地编号保留普通属性，不改变父身份",
                    completion=True,
                )
            else:
                self.issue(
                    path,
                    "converted",
                    "Identifier",
                    None,
                    "完整标识已转换",
                    targets=[p.id for p in props],
                )

    def reify_nary(self, owner, name, rel, path):
        if rel.get("multiplicity") == "OneToOne":
            self.issue(
                path,
                "error",
                "Relationship(n-ary)",
                None,
                "多元 OneToOne 为非法输入，不转换",
            )
            return
        roles = [{"concept": owner, "name": owner}, *rel["roles"]]
        if any(
            r["concept"] not in self.t.objects and self.value_kind(r["concept"]) is None
            for r in roles
        ):
            self.issue(
                path,
                "dropped",
                "Relationship(n-ary)",
                "RT-29",
                "多元关系包含未承载角色，整项保留原文",
                completion=True,
            )
            return
        tech = identifier_name(owner + "_" + name, self.object_names)
        obj = ObjectType(
            id=self.t.id("reified:" + owner + "." + name),
            display_name=None,
            name=tech,
            description=rel.get("description", ""),
        )
        if not self.t.accept("object_types", obj, path, rule="RT-27"):
            return
        # Build all role representations before setting the tuple identifier.
        representations = []
        missing = []
        bindings = {}
        for position, role in enumerate(roles):
            label = role.get("name", role["concept"])
            target = self.t.objects.get(role["concept"])
            role_key = path + f":role:{position}"
            props = []
            if target:
                identifiers = DraftIndex(self.t.model).identifier(target.id)
                for identifier in identifiers:
                    ptech, plabel = self.names(
                        obj,
                        label + "_" + identifier.name,
                        label + "·" + identifier.name,
                    )
                    prop = Property(
                        id=self.t.id(
                            "reified-property:" + role_key + ":" + str(identifier.id)
                        ),
                        owner_type_id=obj.id,
                        display_name=None,
                        name=ptech,
                        value_kind=identifier.value_kind,
                        required=True,
                    )
                    if self.t.accept("properties", prop, path, rule="RT-28"):
                        props.append(prop)
                ltech, _label = self.names(obj, label, label)
                link = LinkType(
                    id=self.t.id(
                        "reified-link:" + owner + "." + name + "." + str(position)
                    ),
                    name=ltech,
                    source_type_id=obj.id,
                    target_type_id=target.id,
                    target_role_name=role.get("name"),
                    multiplicity="many_to_one",
                    data_join=DirectJoin(
                        kind="direct",
                        source_property_ids=[p.id for p in props],
                        target_property_ids=[p.id for p in identifiers],
                    )
                    if identifiers
                    else None,
                )
                self.t.accept("link_types", link, path, rule="RT-27")
                if not identifiers:
                    missing.append(position)
            else:
                ptech, plabel = self.names(obj, label, label)
                prop = Property(
                    id=self.t.id("reified-property:" + role_key),
                    owner_type_id=obj.id,
                    display_name=None,
                    name=ptech,
                    value_kind=self.value_kind(role["concept"]),
                    value_type_id=self.value_types[role["concept"]].id if role["concept"] in self.value_types else None,
                    required=True,
                )
                if self.t.accept("properties", prop, path, rule="RT-27"):
                    props.append(prop)
                    self.t.property_sources[prop.id] = (role["concept"], label, path)
            if target:
                for original, prop in zip(identifiers, props, strict=True):
                    original_name = self.t.property_sources.get(
                        original.id, ("", original.name, "")
                    )[1]
                    bindings[(label, original_name)] = prop.name
            elif props:
                bindings[("", label)] = props[0].name
            representations.append(props)
        determinant = range(
            len(roles) - 1 if rel.get("multiplicity") == "ManyToOne" else len(roles)
        )
        if any(i in missing for i in determinant):
            self.issue(
                path,
                "error",
                "Identifier(n-ary)",
                "RT-28",
                "决定角色缺完整业务标识，整个中间标识待补全；不使用随机 UUID 代替",
                completion=True,
            )
        else:
            keys = [p for i in determinant for p in representations[i]]
            for p in keys:
                p.identifier = True
                p.unique = len(keys) == 1
            self.issue(
                path,
                "converted",
                "Identifier(n-ary)",
                "RT-28",
                "按 owner 和文件角色顺序构造完整元组标识",
                targets=[p.id for p in keys],
            )
        for i in missing:
            if i not in determinant:
                self.issue(
                    path,
                    "error",
                    "RoleIdentifier",
                    "RT-28",
                    "最后实体角色缺业务标识，仅该角色编号待补全",
                    completion=True,
                )
        self.role_bindings[obj.id] = bindings
        self.origins.append((obj, rel, path, "reified:" + owner + "." + name))
        if rel.get("verbalizes"):
            self.issue(
                path + "/verbalizes",
                "dropped",
                "Verbalization",
                "RT-27",
                "重化对象不保留多元读法结构",
            )

    def run(self):
        self.import_objects()
        self.import_relationships()
        self.identifiers()
        for owner in self.t.objects:
            for i, rel in enumerate(self.concepts[owner].get("relationships", [])):
                if (
                    self.t.valid(self.paths[owner] + f"/relationships/{i}")
                    and len(rel.get("roles", [])) > 1
                ):
                    previous = self.t.model.model_copy(deep=True)
                    try:
                        self.reify_nary(
                            owner,
                            rel["name"],
                            rel,
                            self.paths[owner] + f"/relationships/{i}",
                        )
                    except ValueError as error:
                        self.t.model = previous
                        self.issue(
                            self.paths[owner] + f"/relationships/{i}",
                            "error",
                            "Relationship(n-ary)",
                            "RT-28",
                            f"多元关系不能完整形成核心定义：{error}",
                            completion=True,
                        )
        from .rules import import_rules

        import_rules(self)
        from .mappings import import_mappings

        scopes = import_mappings(self)
        from .metrics import import_metrics

        for scope in scopes:
            import_metrics(self, scope)
        for field, rule in [
            ("name", "RT-01"),
            ("description", "RT-01"),
            ("requires", "RT-04"),
        ]:
            if self.document.get(field):
                self.issue(
                    "/" + field,
                    "dropped",
                    "Document",
                    rule,
                    "文档名称、描述使用目标工作空间；工作空间级规则不进入核心",
                    completion=field == "requires",
                )
        context = self.document.get("ai_context")
        if isinstance(context, dict):
            for key in context.keys() - {"ontofoundry"}:
                self.issue(
                    "/ai_context/" + escape_pointer(key),
                    "dropped",
                    "AIContext",
                    "RT-02",
                    "文档上下文没有明确对象归属，不复制到全部对象",
                    completion=True,
                )
        return self.t.finish()


class OssieAdapter(ImportOnlyAdapter):
    def export_document(self, model, ctx):
        from ontofoundry_api.adapters.ossie.exporter import export_document

        return export_document(model, ctx)

    id = "ossie-0.2"
    label = "Apache Ossie 0.2"
    file_extensions = (".ossie.zip", ".zip", ".ossie.json", ".json")

    def detect(self, raw):
        try:
            document, _ = read_ossie(raw)
        except ValueError:
            return False
        return b'"ontology"' in document

    def import_document(self, raw, ctx):
        report = ReportBuilder(self.id, ctx.workspace_id, hashlib.sha256(raw).hexdigest())
        empty = empty_draft(ctx.workspace_id)
        try:
            document, extension_raw = read_ossie(raw)
            extension_source = (
                SourceDocument.parse(extension_raw) if extension_raw is not None else None
            )
            extension = extension_source.value if extension_source else None
            if extension is not None and (
                not isinstance(extension, dict) or extension.get("version") != "core-1"
            ):
                raise ValueError("扩展文件必须是 version=core-1 的对象")
        except (ValueError, UnicodeError) as error:
            report.add(
                outcome="error", construct="document", source_path="", message=str(error)
            )
            return report.finish(empty)
        source = parse_document(document, report)
        if source is None:
            return report.finish(empty)
        value = source.value
        if (
            not isinstance(value, dict)
            or value.get("version") != "0.2.0.dev0"
            or not isinstance(value.get("ontology"), list)
        ):
            report.add(
                outcome="error",
                construct="document",
                source_path="",
                locator=source.locator(""),
                original=source.original(""),
                message="仅支持 0.2.0.dev0 ontology 文档和内嵌 ontology_mappings；不支持独立 OSI 或 mapping documents",
            )
            return report.finish(empty)
        schema_issues = validate_schema(value)
        invalid = []
        for issue in schema_issues:
            pointer = "".join(
                "/" + escape_pointer(a or b)
                for a, b in re.findall(r"\.([^.[\]]+)|\[(\d+)\]", issue["path"])
            )
            if pointer not in source.spans:
                pointer = ""
            report.add(
                outcome="error",
                construct="document" if not pointer else "InputItem",
                source_path=pointer,
                locator=source.locator(pointer),
                original=source.original(pointer),
                message="Ossie 官方结构校验失败：" + issue["message"],
            )
            candidates = re.findall(
                r"^(?:/ontology/\d+(?:/relationships/\d+)?|/ontology_mappings/\d+(?:/semantic_model/(?:datasets|metrics|relationships)/\d+(?:/fields/\d+)?)?(?:/concept_mappings/\d+)?)",
                pointer,
            )
            if not candidates:
                return report.finish(empty)
            invalid.append(candidates[0])
        names = [
            c["concept"]
            for i, c in enumerate(value["ontology"])
            if f"/ontology/{i}" not in invalid
        ]
        if any(n > 1 for n in Counter(names).values()):
            report.add(
                outcome="error",
                construct="document",
                source_path="/ontology",
                locator=source.locator("/ontology"),
                original=source.original("/ontology"),
                message="概念名重复，无法确定引用身份",
            )
            return report.finish(empty)
        translation = Translation(source, report, invalid)
        translation.extension = extension
        translation.extension_source = extension_source
        translation.import_context = ctx
        return OntologyImporter(translation).run()

    def validate_document(self, document):
        report = ReportBuilder(self.id, UUID(int=0), hashlib.sha256(document).hexdigest())
        try:
            document, _ = read_ossie(document)
        except ValueError as error:
            report.add(
                outcome="error", construct="document", source_path="", message=str(error)
            )
            return report.issues
        source = parse_document(document, report)
        if source is None:
            return report.issues
        diagnostics = validate_schema(source.value)
        if not diagnostics:
            diagnostics = validate_semantics(source.value)
        for diagnostic in diagnostics:
            pointer = "".join(
                "/" + escape_pointer(a or b)
                for a, b in re.findall(r"\.([^.[\]]+)|\[(\d+)\]", diagnostic["path"])
            )
            if pointer not in source.spans:
                pointer = ""
            report.add(
                outcome="error" if diagnostic["severity"] == "error" else "dropped",
                construct="Validation",
                source_path=pointer,
                locator=source.locator(pointer),
                original=source.original(pointer),
                message="Ossie 格式校验："
                + diagnostic["code"]
                + " "
                + diagnostic["message"],
            )
        return report.issues
