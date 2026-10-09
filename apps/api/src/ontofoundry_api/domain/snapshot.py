"""The only way into a stored snapshot or draft.

`read_snapshot` defaults to the v2 runtime boundary. P0 callers may explicitly
request target_version="3"; this accepts v1/v2/v3 and returns the same draft
model with the frozen v3 shape. Services never look at `schema_version` or at v1 nesting themselves; if
something needs a snapshot, it calls this. Historical v1 rows are never
rewritten — normalization happens on every read and is deterministic, so the
same v1 row always yields the same v2 snapshot and the same hashes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.models import OntologyDraft, RuleKind, RuleOwnerKind


def empty_snapshot(workspace_id: str | UUID) -> dict[str, Any]:
    return OntologyDraft(workspace_id=workspace_id).model_dump(mode="json")


def _legacy_evidence(workspace: UUID, owner_id: str, items: list[dict]) -> list[dict]:
    result = []
    for index, item in enumerate(items or []):
        if item.get("kind"):  # already v2
            result.append(item)
            continue
        material_id = str(item.get("material_id") or "")
        start, end = int(item.get("line_start") or 1), int(item.get("line_end") or 1)
        result.append(
            {
                "kind": "material",
                "id": str(
                    uuid5(workspace, f"evidence:{owner_id}:{index}:{material_id}:{start}:{end}")
                ),
                "material_id": material_id,
                "material_sha256": None,
                "locator": {"heading": None, "line_start": start, "line_end": max(start, end)},
                "quote": item.get("quote") or "",
            }
        )
    return result


def legacy_rule_id(
    workspace: UUID, owner_kind: str, owner_id: str, rule_kind: str, expression: str
) -> UUID:
    """Stable id for a v1 `requires`/`derived_by` string (design §10.2).

    The same expression on the same owner always gets the same id, so reading a
    v1 row twice never invents two rules. Once in v2, editing the expression keeps
    the id; across two v1 versions a changed expression cannot be proven to be
    the same rule and shows as remove + add.
    """
    normalized = " ".join(expression.split())
    return uuid5(workspace, f"rule:{owner_kind}:{owner_id}:{rule_kind}:{normalized}")


def normalize_v1(data: dict[str, Any]) -> dict[str, Any]:
    """Map a schema-v1 draft dict onto schema v2. Pure: no database access."""
    workspace = UUID(str(data["workspace_id"]))
    object_types, properties, link_types, rules = [], [], [], []
    seen_rules: set[str] = set()

    def add_rules(owner_kind: RuleOwnerKind, owner: dict, label: str) -> None:
        for field, kind in (("requires", RuleKind.CONSTRAINT), ("derived_by", RuleKind.DERIVATION)):
            for expression in owner.get(field) or []:
                rule_id = str(
                    legacy_rule_id(workspace, owner_kind.value, str(owner["id"]), kind.value, expression)
                )
                if rule_id in seen_rules:
                    continue
                seen_rules.add(rule_id)
                rules.append(
                    {
                        "id": rule_id,
                        "name": f"{label}·{'约束' if kind == RuleKind.CONSTRAINT else '派生'}"
                        f"{len([r for r in rules if r['owner_id'] == str(owner['id'])]) + 1}",
                        "technical_name": f"{kind.value}_{rule_id.replace('-', '')[:8]}",
                        "description": "",
                        "owner_kind": owner_kind.value,
                        "owner_id": str(owner["id"]),
                        "rule_kind": kind.value,
                        "expression": expression,
                        "verbalizes": [],
                        "evidence": [],
                    }
                )

    for item in data.get("object_types") or []:
        object_types.append(
            {
                "id": item["id"],
                "name": item["name"],
                "technical_name": item["technical_name"],
                "description": item.get("description") or "",
                "tags": item.get("tags") or [],
                "extends": item.get("extends") or [],
                "evidence": [],
            }
        )
        add_rules(RuleOwnerKind.OBJECT_TYPE, item, item["name"])
        for attribute in item.get("attributes") or []:
            prop = {
                key: value
                for key, value in attribute.items()
                if key not in ("requires", "derived_by")
            }
            prop["owner_type_id"] = item["id"]
            prop.setdefault("verbalizes", [])
            prop["evidence"] = []
            properties.append(prop)
            add_rules(RuleOwnerKind.PROPERTY, attribute, f"{item['name']}.{attribute['name']}")
    for item in data.get("link_types") or []:
        link = {key: value for key, value in item.items() if key not in ("requires", "derived_by")}
        link["evidence"] = []
        link_types.append(link)
        add_rules(RuleOwnerKind.LINK_TYPE, item, item["name"])

    material_objects = [
        {**obj, "evidence": _legacy_evidence(workspace, str(obj["id"]), obj.get("evidence"))}
        for obj in data.get("objects") or []
    ]
    material_links = [
        {**link, "evidence": _legacy_evidence(workspace, str(link["id"]), link.get("evidence"))}
        for link in data.get("links") or []
    ]
    return {
        "schema_version": "2",
        "workspace_id": str(workspace),
        "ontology_requires": list(data.get("requires") or []),
        "object_types": object_types,
        "properties": properties,
        "link_types": link_types,
        "rules": rules,
        "actions": [],
        "material_objects": material_objects,
        "material_links": material_links,
        "mappings": list(data.get("mappings") or []),
    }


def as_v2_dict(data: dict[str, Any] | None, workspace_id: str | UUID | None = None) -> dict[str, Any]:
    """Stored JSON of either schema → v2 JSON (unvalidated; see read_snapshot)."""
    if not data:
        if workspace_id is None:
            raise ValueError("空快照必须提供 workspace_id")
        return empty_snapshot(workspace_id)
    if workspace_id is not None and str(data.get("workspace_id")) != str(workspace_id):
        raise ValueError("快照不属于该工作空间")
    version = str(data.get("schema_version") or "1")
    if version == "2":
        return data
    if version == "1":
        return normalize_v1(data)
    raise ValueError(f"不支持的快照 schema_version：{version}")


def read_snapshot(
    data: dict[str, Any] | None, workspace_id: str | UUID | None = None,
    *, target_version: str = "2",
) -> OntologyDraft:
    """Validated v2 model for any stored snapshot or draft."""
    if target_version == "3":
        return OntologyDraft.model_validate(as_v3_dict(data, workspace_id))
    if target_version != "2":
        raise ValueError(f"不支持的目标 schema_version：{target_version}")
    return OntologyDraft.model_validate(as_v2_dict(data, workspace_id))


def read_snapshot_json(
    data: dict[str, Any] | None, workspace_id: str | UUID | None = None,
    *, target_version: str = "2",
) -> dict[str, Any]:
    return read_snapshot(data, workspace_id, target_version=target_version).model_dump(mode="json")


def normalized_snapshot_sha256(
    data: dict[str, Any] | None, workspace_id: str | UUID | None = None
) -> str:
    return snapshot_sha256(read_snapshot_json(data, workspace_id, target_version="3" if data and data.get("schema_version") == "3" else "2"))


def draft_sha256(data: dict[str, Any] | None, workspace_id: str | UUID | None = None) -> str:
    """`draft_sha256` of a stored draft of either schema (not validated)."""
    if data and data.get("schema_version") == "3":
        if workspace_id is not None and str(data.get("workspace_id")) != str(workspace_id):
            raise ValueError("快照不属于该工作空间")
        return snapshot_sha256(data)
    return snapshot_sha256(as_v2_dict(data, workspace_id))


def normalize_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, pure migration. Never write a row or reuse a mapping ID.

    This migrates what v2 actually retained; it cannot reconstruct discarded
    Ossie text. Runtime sessions opt in in P1, not as a side effect of reading.
    """
    import json

    from ontofoundry_api.domain.canonical import V3_HASH_ALGORITHM
    from ontofoundry_api.ossie.compiler import VALUE_BASES
    from ontofoundry_api.ossie.mappings import _column_sql, compile_mappings

    legacy = OntologyDraft.model_validate(data)
    if legacy.schema_version != "2":
        raise ValueError("normalize_v2_to_v3 只接受 schema_version 2")
    raw = legacy.model_dump(mode="json")
    workspace = legacy.workspace_id

    def identity(path):
        return str(uuid5(workspace, f"v3:{path}"))

    def ref(kind, ref_id):
        return {"kind": kind, "ref": str(ref_id)}

    def metadata(keys, position):
        return {"origin": "migrated", "position": position, "native_presence": list(keys)}

    result = {
        "schema_version": "3", "hash_algorithm": V3_HASH_ALGORITHM,
        "workspace_id": str(workspace), "document_origin": "migrated",
        "ontology_requires": raw["ontology_requires"],
        "native_presence": ["version", "ontology", "requires"],
        "object_types": [], "value_types": [], "properties": [], "link_types": [],
        "rules": [], "actions": raw["actions"], "material_objects": raw["material_objects"],
        "material_links": [], "semantic_models": [], "datasets": [], "dataset_fields": [],
        "dataset_relationships": [], "metrics": [], "concept_mappings": [], "mapping_nodes": [],
        "extension_v4": {"version": "4", "legacy_mapping_ids": {}},
    }
    values = {}
    for p in legacy.properties:
        base = VALUE_BASES[p.value_kind]
        if p.value_concept and p.value_concept not in VALUE_BASES.values():
            values.setdefault(p.value_concept, (identity(f"value:{p.value_concept}"), base))
    for index, (name, (value_id, base)) in enumerate(values.items()):
        result["value_types"].append({
            "id": value_id, "concept": name, "extends": [ref("builtin", base)],
            **metadata(["concept", "type", "extends"], len(legacy.object_types) + index),
        })
    for index, item in enumerate(raw["object_types"]):
        result["object_types"].append({
            **item, "concept": item["technical_name"],
            "extends": [ref("object_type", i) for i in item["extends"]],
            "identify_by": [p.technical_name for p in legacy.properties if p.owner_type_id == UUID(item["id"]) and p.identifier]
            + [link.technical_name for link in legacy.link_types if link.owner_type_id == UUID(item["id"]) and link.identifier],
            **metadata(["concept", "type", "description", "extends", "identify_by", "relationships"], index),
        })
    property_offsets = {}
    for p in legacy.properties:
        index = property_offsets.get(p.owner_type_id, 0)
        property_offsets[p.owner_type_id] = index + 1
        target = ref("value_type", values[p.value_concept][0]) if p.value_concept in values else ref("builtin", p.value_concept or VALUE_BASES[p.value_kind])
        result["properties"].append({
            "id": str(p.id), "name": p.name, "technical_name": p.technical_name,
            "description": p.description, "owner_ref": ref("object_type", p.owner_type_id),
            "roles": [{"id": str(uuid5(p.id, "role:0")), "name": p.target_role_name, "concept": target,
                       **metadata(["concept"] + (["name"] if p.target_role_name is not None else []), 0)}],
            "multiplicity": {"one_to_one": "OneToOne", "many_to_one": "ManyToOne"}.get(p.multiplicity),
            "required": p.required, "identifier": p.identifier, "value_kind": p.value_kind.value,
            "verbalizes": p.verbalizes, "evidence": [e.model_dump(mode="json") for e in p.evidence],
            **metadata(["name", "description", "roles", "verbalizes"] + (["multiplicity"] if p.multiplicity is not None else []), index),
        })
    offsets = {o.id: sum(p.owner_type_id == o.id for p in legacy.properties) for o in legacy.object_types}
    for link in legacy.link_types:
        reverse = link.multiplicity.value == "one_to_many"
        owner = link.target_type_id if reverse else link.source_type_id
        target = link.source_type_id if reverse else link.target_type_id
        role_name = link.source_role_name if reverse else link.target_role_name
        result["link_types"].append({
            "id": str(link.id), "name": link.name, "technical_name": link.technical_name,
            "description": link.description, "owner_ref": ref("object_type", owner),
            "roles": [{"id": str(uuid5(link.id, "role:0")), "name": role_name, "concept": ref("object_type", target),
                       **metadata(["concept"] + (["name"] if role_name is not None else []), 0)}],
            "multiplicity": "OneToOne" if link.multiplicity.value == "one_to_one" else "ManyToOne" if link.multiplicity.value in {"many_to_one", "one_to_many"} else None,
            "endpoint_direction": "reverse" if reverse else "forward",
            "owner_role_name": link.target_role_name if reverse else link.source_role_name,
            "legacy_multiplicity": link.multiplicity.value,
            "identifier": link.identifier, "tags": link.tags, "verbalizes": link.verbalizes,
            "evidence": [e.model_dump(mode="json") for e in link.evidence],
            **metadata(["name", "description", "roles", "verbalizes"] + ([] if link.multiplicity.value == "many_to_many" else ["multiplicity"]), offsets[owner]),
        })
        offsets[owner] += 1
    owners = {i["id"]: i for c in ("object_types", "properties", "link_types") for i in result[c]}
    for r in raw["rules"]:
        field = "requires" if r["rule_kind"] == "constraint" else "derived_by"
        owner = owners.get(r["owner_id"])
        position = len(owner.setdefault(field, [])) if owner else 0
        if owner is not None:
            owner[field].append(r["id"])
            if field not in owner["native_presence"]:
                owner["native_presence"].append(field)
        result["rules"].append({**r, **metadata([], position)})
    for fact in raw["material_links"]:
        link = next(i for i in result["link_types"] if i["id"] == fact["type_id"])
        reverse = link["endpoint_direction"] == "reverse"
        result["material_links"].append({
            **fact, "role_values": [
                {"role_id": str(uuid5(UUID(link["id"]), "role:owner")), "object_id": fact["target_id"] if reverse else fact["source_id"]},
                {"role_id": link["roles"][0]["id"], "object_id": fact["source_id"] if reverse else fact["target_id"]},
            ],
        })

    documents = compile_mappings(legacy, legacy.object_types)
    # v2 allowed joins across connection aliases, even though query execution
    # rejects them. Preserve them as a separate read-only bridge model.
    by_type = {i.id: i for i in legacy.object_types}
    mapped = {i.type_id: i for i in legacy.mappings}
    for link in legacy.link_types:
        if link.data_join is None:
            continue
        src, dst = mapped[link.source_type_id], mapped[link.target_type_id]
        if src.connection_alias == dst.connection_alias:
            continue
        datasets = []
        for mapping in (src, dst):
            name = by_type[mapping.type_id].technical_name
            datasets.append({"name": name, "source": f"{mapping.schema_name}." + mapping.table_name if mapping.schema_name else mapping.table_name,
                             "primary_key": [mapping.key_column], "fields": []})
        documents.append({
            "name": f"legacy_join_{link.id.hex}", "semantic_model": {
                "name": f"legacy_join_{link.id.hex}", "datasets": datasets,
                "relationships": [{"name": link.technical_name, "from": datasets[0]["name"], "to": datasets[1]["name"],
                                   "from_columns": [link.data_join.source_column], "to_columns": [link.data_join.target_column]}],
                "custom_extensions": [{"vendor_name": "ONTOFOUNDRY", "data": json.dumps({
                    "legacy_connection_aliases": {datasets[0]["name"]: src.connection_alias, datasets[1]["name"]: dst.connection_alias},
                    "read_only_reason": "cross_connection",
                }, ensure_ascii=False, sort_keys=True)}],
            }, "concept_mappings": [{
                "concept": by_type[link.owner_type_id].technical_name,
                "link_mappings": [{"relationship": link.technical_name, "object_mapping": {
                    "concept": datasets[0]["name"] if link.owner_type_id == dst.type_id else datasets[1]["name"],
                    "expression": f"{by_type[link.owner_type_id].technical_name}.{_column_sql(link.data_join.target_column if link.owner_type_id == dst.type_id else link.data_join.source_column)}",
                }}],
            }],
        })
    concept_refs = {o.technical_name: ref("object_type", o.id) for o in legacy.object_types}

    def flatten(node, cm_id, path, slot, position, parent_id=None):
        node_id = identity(path)
        kind = "link" if slot in {"link_mappings", "children"} else "referent" if slot == "referent_mappings" else "object"
        item = {"id": node_id, "concept_mapping_id": cm_id, "parent_id": parent_id,
                "kind": kind, "slot": slot, **metadata(node.keys(), position)}
        for field in ("relationship", "expression"):
            if field in node:
                item[field] = node[field]
        if "concept" in node:
            item["concept"] = concept_refs[node["concept"]]
        result["mapping_nodes"].append(item)
        for child_slot in ("object_mapping", "children", "referent_mappings"):
            children = [node[child_slot]] if child_slot == "object_mapping" and child_slot in node else node.get(child_slot, [])
            for index, child in enumerate(children):
                flatten(child, cm_id, f"{path}/{child_slot}/{index}", child_slot, index, node_id)

    for mi, document in enumerate(documents):
        path = f"ontology_mappings/{document['name']}"
        model_id = identity(path + "/semantic_model")
        model = document["semantic_model"]
        ext = list(model.get("custom_extensions", []))
        if not document["name"].startswith("legacy_join_"):
            ext.append({"vendor_name": "ONTOFOUNDRY", "data": json.dumps({"connection_alias": document["name"]}, ensure_ascii=False, sort_keys=True)})
        result["semantic_models"].append({
            "id": model_id, "name": model["name"], "map_name": document.get("name"), "map_description": document.get("description"),
            "map_presence": list(document), "custom_extensions": ext,
            **metadata([*model, *([] if "custom_extensions" in model else ["custom_extensions"])], mi),
        })
        for di, dataset in enumerate(model["datasets"]):
            ds_path = path + "/datasets/" + dataset["name"]
            ds_id = identity(ds_path)
            result["datasets"].append({"id": ds_id, "semantic_model_id": model_id,
                                       **{k: v for k, v in dataset.items() if k != "fields"}, **metadata(dataset.keys(), di)})
            for fi, field in enumerate(dataset.get("fields", [])):
                result["dataset_fields"].append({"id": identity(ds_path + "/fields/" + field["name"]), "dataset_id": ds_id,
                                                 **field, **metadata(field.keys(), fi)})
        relationship_names = set()
        if document["name"].startswith("legacy_join_"):
            join_ids = [document["name"].removeprefix("legacy_join_")]
        else:
            join_ids = [str(link.id) for link in sorted(legacy.link_types, key=lambda i: i.technical_name)
                        if link.data_join is not None
                        and mapped[link.source_type_id].connection_alias == document["name"]
                        and mapped[link.target_type_id].connection_alias == document["name"]]
        for ri, rel in enumerate(model.get("relationships", [])):
            # v2 permits equal link names under different concept owners.
            # Dataset relationships have one model-wide namespace; generate a
            # scoped name instead of dropping either join or reusing its ID.
            rel_path = f"{path}/relationships/{join_ids[ri]}"
            name = rel["name"]
            if name in relationship_names:
                name += "__" + identity(rel_path).replace("-", "")
            relationship_names.add(name)
            result["dataset_relationships"].append({"id": identity(rel_path),
                                                    "semantic_model_id": model_id, **rel, "name": name,
                                                    **metadata(rel.keys(), ri)})
        for ci, cm in enumerate(document["concept_mappings"]):
            cm_path = path + "/concept_mappings/" + cm["concept"]
            cm_id = identity(cm_path)
            result["concept_mappings"].append({"id": cm_id, "semantic_model_id": model_id,
                                              "concept_id": concept_refs[cm["concept"]], **metadata(cm.keys(), ci)})
            for slot in ("object_mappings", "link_mappings"):
                for index, node in enumerate(cm.get(slot, [])):
                    flatten(node, cm_id, f"{cm_path}/{slot}/{index}", slot, index)
            for old in legacy.mappings:
                if old.connection_alias == document["name"] and old.type_id == UUID(concept_refs[cm["concept"]]["ref"]):
                    result["extension_v4"]["legacy_mapping_ids"][str(old.id)] = cm_id
    # Legacy v2 omitted compiler defaults. Materialize its compatible readings
    # during migration, never during native import/export. These are reconstructed
    # platform semantics, explicitly marked migrated, not source-file presence.
    concept_names = {i["id"]: i["concept"] for c in ("object_types", "value_types") for i in result[c]}
    for link in [*result["properties"], *result["link_types"]]:
        role = link["roles"][0]
        if not link["verbalizes"]:
            owner_name = concept_names[link["owner_ref"]["ref"]]
            role = link["roles"][0]
            target_name = concept_names.get(role["concept"]["ref"], role["concept"]["ref"])
            target_ref = target_name + (":" + role["name"] if role["name"] else "")
            link["verbalizes"] = ["{" + owner_name + "}" + link["name"] + "{" + target_ref + "}"]
        if link in result["properties"] and link["multiplicity"] is None:
            link["multiplicity"] = "OneToOne" if link["identifier"] and sum(p["identifier"] for p in result["properties"] if p["owner_ref"] == link["owner_ref"]) == 1 else "ManyToOne"
            link["native_presence"].append("multiplicity")
    # Frozen identity registry includes role identities as well as elements.
    registry = {f"/{collection}/{i['id']}": i["id"] for collection in (
        *V3_MIGRATED_COLLECTIONS, "actions", "material_objects",
    ) for i in result[collection]}
    for link in [*result["properties"], *result["link_types"]]:
        registry[f"/relationships/{link['id']}/owner"] = str(uuid5(UUID(link["id"]), "role:owner"))
        for role in link["roles"]:
            registry[f"/relationships/{link['id']}/roles/{role['position']}"] = role["id"]
    result["extension_v4"]["ids"] = registry
    return OntologyDraft.model_validate(result).model_dump(mode="json")


V3_MIGRATED_COLLECTIONS = (
    "object_types", "value_types", "properties", "link_types", "rules", "material_links",
    "semantic_models", "datasets", "dataset_fields", "dataset_relationships",
    "metrics", "concept_mappings", "mapping_nodes",
)


def as_v3_dict(data: dict[str, Any] | None, workspace_id: str | UUID | None = None) -> dict[str, Any]:
    """v1 → v2 → v3 or validated v3; fresh JSON, no mutation even for v3."""
    if not data:
        if workspace_id is None:
            raise ValueError("空快照必须提供 workspace_id")
        return OntologyDraft(schema_version="3", hash_algorithm="ontofoundry-domain-v3", workspace_id=workspace_id).model_dump(mode="json")
    if data and str(data.get("schema_version")) == "3":
        if workspace_id is not None and str(data.get("workspace_id")) != str(workspace_id):
            raise ValueError("快照不属于该工作空间")
        return OntologyDraft.model_validate(data).model_dump(mode="json")
    return normalize_v2_to_v3(as_v2_dict(data, workspace_id))
