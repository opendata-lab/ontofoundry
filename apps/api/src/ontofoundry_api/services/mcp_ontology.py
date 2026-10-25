"""Four read-only ontology tools with authorization-bound segmented pagination."""

import json
from copy import deepcopy
from typing import Literal
from uuid import UUID

from pydantic import Field

from ontofoundry_api.contracts.read_models import OntologySearchRequest
from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import CoreDraft, Strict
from ontofoundry_api.domain.graph import draft_index
from ontofoundry_api.domain.instance_display import document_display_text
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services.access import (
    authorization_fingerprint,
    can_read_instances,
    can_read_mappings,
    require_instances,
)
from ontofoundry_api.services.cursors import decode_cursor, encode_cursor
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.ontology_query import (
    current_version,
    read_context,
    resource_items,
    snapshot_of,
)
from ontofoundry_api.services.ontology_search import search_ontology
from ontofoundry_api.services.workspaces import get_workspace

Kind = Literal[
    "object_type", "property", "link_type", "rule", "metric", "dataset", "value_type"
]


class Paging(Strict):
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


SearchOntology = OntologySearchRequest


class GetOntology(Paging):
    ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    kinds: list[Kind] | None = None
    include: list[Literal["semantic", "physical", "rules", "adjacency"]] = Field(
        default_factory=lambda: ["semantic"]
    )


class SearchObjects(Paging):
    type_id: UUID | None = None
    q: str = Field(default="", max_length=240)


class GetObject(Paging):
    id: UUID
    include: list[Literal["properties", "evidence", "adjacency"]] = Field(
        default_factory=lambda: ["properties"]
    )


class ResolveEntity(Strict):
    mention: str = Field(min_length=1, max_length=240)
    object_type_id: UUID
    limit: int = Field(default=10, ge=1, le=50)
    # Shared tool plumbing reads a cursor; resolution returns one page and ignores it.
    cursor: str | None = None


INPUTS = {
    "resolve_entity": ResolveEntity,
    "search_ontology": SearchOntology,
    "get_ontology": GetOntology,
    "search_objects": SearchObjects,
    "get_object": GetObject,
}
BUDGET = 110_000  # Both text and structuredContent count toward the 256 KiB wire limit.


def size(value):
    from fastapi.encoders import jsonable_encoder

    return len(
        json.dumps(
            jsonable_encoder(value), ensure_ascii=False, separators=(",", ":")
        ).encode()
    )


def _invoke(db, workspace_id, principal, name, arguments, settings):
    args = INPUTS[name].model_validate(arguments)
    space = get_workspace(db, workspace_id)
    version_id = (
        principal.pinned_version_id
        if principal.pinned_version_id is not None
        else space.current_version_id
    )
    if version_id:
        try:
            version = current_version(db, workspace_id, version_id)
        except ServiceError as exc:
            raise ServiceError(
                "固定发布版已不可用", code="version_unavailable", status_code=404
            ) from exc
        snapshot = snapshot_of(version)
    else:
        snapshot = empty_snapshot(workspace_id)
    envelope = {"workspace_id": workspace_id, "version_id": version_id or None}
    from ontofoundry_api.services.instance_store import change_sequence

    context = [
        workspace_id,
        version_id or None,
        name,
        args.model_dump(mode="json", exclude={"cursor"}),
        authorization_fingerprint(db, workspace_id, principal),
        change_sequence(db, workspace_id)
        if name in {"search_objects", "get_object"}
        else None,
    ]
    offset, section = decode_cursor(settings, args.cursor, context)
    mappings = can_read_mappings(db, workspace_id, principal)
    instances = can_read_instances(db, workspace_id, principal)
    draft = (
        read_context(version).draft if version_id else CoreDraft.model_validate(snapshot)
    )
    index = draft_index(draft)

    def page(values, path, start=0):
        items, cursor = [], None
        for n in range(start, min(len(values), start + args.limit)):
            if items and size(items + [values[n]]) > BUDGET // 2:
                break
            items.append(values[n])
        end = start + len(items)
        if end < len(values):
            cursor = encode_cursor(settings, context, end, {"kind": "list", "path": path})
        return {"total": len(values), "items": items, "next_cursor": cursor}

    def paginate_nested(item, path):
        values = item
        for token in path:
            values = values[token]
        return page(values, path, offset)

    fields = []

    def segment_fields(value, element_id, path=()):
        if isinstance(value, dict):
            result = {}
            for key, entry in value.items():
                if isinstance(entry, str) and len(entry.encode()) > 12000:
                    pointer = "/" + "/".join((*path, key))
                    text = entry[:2000]
                    fields.append(
                        {
                            "element_id": element_id,
                            "field": pointer,
                            "start": 0,
                            "end": len(text),
                            "total": len(entry),
                            "text": text,
                            "next_cursor": encode_cursor(
                                settings,
                                context,
                                len(text),
                                {
                                    "kind": "field",
                                    "element_id": element_id,
                                    "path": [*path, key],
                                },
                            )
                            if len(text) < len(entry)
                            else None,
                        }
                    )
                else:
                    result[key] = segment_fields(entry, element_id, (*path, key))
            return result
        if isinstance(value, list):
            return [
                segment_fields(v, element_id, (*path, str(n))) for n, v in enumerate(value)
            ]
        return value

    resources = resource_items(
        snapshot,
        draft=draft,
        mappings=mappings,
        instances=instances,
        db=db if mappings else None,
        workspace_id=workspace_id,
    )
    if mappings and name == "get_ontology" and "physical" in args.include:
        from ontofoundry_api.services.physical_projection import physical_projection

        datasets = [r["definition"] for r in resources if r["kind"] == "dataset"]
        for resource in resources:
            if resource["kind"] not in {"object_type", "link_type", "metric"}:
                continue
            definition = resource["definition"]
            definition.update(
                physical_projection(draft, resource["kind"], definition["id"], datasets)
            )
            if resource["kind"] == "object_type":
                binding = resolve_binding(draft, UUID(definition["id"]))
                definition["sources"] = [
                    s.model_dump(mode="json") for s in binding.sources.values()
                ]
    lookup = {
        r["definition"]["id"]: r for r in resources if mappings or r["kind"] != "dataset"
    }
    for kind, collection in (
        ("property", "properties"),
        ("rule", "rules"),
        ("value_type", "value_types"),
    ):
        for e in snapshot.get(collection, []):
            definition = deepcopy(e)
            if not instances:
                definition.pop("evidence", None)
            if kind == "value_type":
                # Constraints and usage are derived on read, never stored on the type.
                definition["constraints"] = [
                    r["expression"]
                    for r in snapshot["rules"]
                    if r["owner_kind"] == "value_type" and r["owner_id"] == e["id"]
                ]
                definition["used_by_property_ids"] = [
                    p["id"]
                    for p in snapshot["properties"]
                    if p.get("value_type_id") == e["id"]
                ]
            lookup[e["id"]] = {"kind": kind, "definition": definition}
    if name == "get_ontology":
        values = []
        wanted = {str(i) for i in args.ids} if args.ids is not None else None
        for identity, r in sorted(lookup.items()):
            if (wanted is not None and identity not in wanted) or (
                args.kinds and r["kind"] not in args.kinds
            ):
                continue
            d = r["definition"]
            element = {
                "id": identity,
                "kind": r["kind"],
                "display_name": d.get("display_name"),
                "name": d["name"],
            }
            if wanted is not None:
                for field in ("description", "synonyms", "binding_status"):
                    if field in d:
                        element[field] = d[field]
                definition = deepcopy(
                    next(
                        (
                            e
                            for e in snapshot[
                                {
                                    "object_type": "object_types",
                                    "link_type": "link_types",
                                    "property": "properties",
                                    "rule": "rules",
                                    "metric": "metrics",
                                    "dataset": "datasets",
                                    "value_type": "value_types",
                                }[r["kind"]]
                            ]
                            if e["id"] == identity
                        ),
                        {},
                    )
                )
                if not instances:
                    definition.pop("evidence", None)
                if not mappings or "physical" not in args.include:
                    definition.pop("data_join", None)
                    if r["kind"] in {"metric", "dataset"}:
                        definition = None
                if definition is not None and r["kind"] == "value_type":
                    definition["constraints"] = d["constraints"]
                    definition["used_by_property_ids"] = d["used_by_property_ids"]
                if definition is not None:
                    definition.pop("connection_id", None)
                    if r["kind"] == "dataset":
                        columns = definition.pop("columns", None) or []
                        d["columns"] = columns
                        element["columns"] = page(columns, [len(values), "columns"])
                        if "adjacency" in args.include:
                            from ontofoundry_api.services.dataset_sources import (
                                dataset_references,
                            )

                            refs = dataset_references(draft, identity)
                            d["referenced_by"] = [
                                {"category": category, **ref}
                                for category, values in refs.items()
                                for ref in values
                            ]
                            element["referenced_by"] = page(
                                d["referenced_by"], [len(values), "referenced_by"]
                            )
                    element["definition"] = definition
                for key in ("properties", "child_types"):
                    if key in d:
                        element[key] = page(d[key], [len(values), key])
                if "rules" in args.include and "rules" in d:
                    element["rules"] = page(d["rules"], [len(values), "rules"])
                if "adjacency" in args.include and "links" in d:
                    element["links"] = page(d["links"], [len(values), "links"])
                if mappings and "physical" in args.include:
                    if "sql_reference" in d:
                        element["sql_reference"] = d["sql_reference"]
                    for key in ("sources", "datasets", "effective_bindings"):
                        if key in d:
                            element[key] = page(d[key], [len(values), key])
                    for key in (
                        "instance_source_type_ids",
                        "components",
                        "dataset_id",
                        "value_kind",
                    ):
                        if key in d:
                            element[key] = d[key]
            values.append(element)
        if section and section["kind"] == "list":
            path = section["path"]
            # Rebuild the unpaged section by requesting the matching resource.
            n, key = path
            d = lookup[values[n]["id"]]["definition"]
            raw = d.get(key)
            values[n][key] = page(raw, path, offset)
            return {
                **envelope,
                "total": len(values),
                "elements": [values[n]],
                "missing": [],
                "next_cursor": None,
            }
        if section and section["kind"] == "field":
            value = next(v for v in values if v["id"] == section["element_id"])
            for token in section["path"]:
                value = value[int(token)] if isinstance(value, list) else value[token]
            text = value[offset : offset + 2000]
            segment = {
                "element_id": section["element_id"],
                "field": "/" + "/".join(section["path"]),
                "start": offset,
                "end": offset + len(text),
                "total": len(value),
                "text": text,
                "next_cursor": encode_cursor(settings, context, offset + len(text), section)
                if offset + len(text) < len(value)
                else None,
            }
            return {
                **envelope,
                "total": len(values),
                "elements": [],
                "missing": [],
                "next_cursor": None,
                "field_segments": [segment],
            }
        cleaned = [segment_fields(v, v["id"]) for v in values]
        data = page(cleaned, [], offset)
        return {
            **envelope,
            "total": len(values),
            "elements": data["items"],
            "missing": sorted(wanted - set(lookup)) if wanted else [],
            "next_cursor": encode_cursor(settings, context, offset + len(data["items"]))
            if offset + len(data["items"]) < len(values)
            else None,
            **(
                {
                    "field_segments": [
                        f
                        for f in fields
                        if f["element_id"] in {e["id"] for e in data["items"]}
                    ]
                }
                if fields
                else {}
            ),
        }
    require_instances(db, workspace_id, principal)
    from ontofoundry_api.domain.core import MaterialLink, MaterialObject
    from ontofoundry_api.services.instance_store import visible

    stored = visible(db, workspace_id, draft)
    envelope.update({k: v for k, v in stored.items() if k not in {"objects", "links"}})
    if name == "resolve_entity":
        if not instances:
            raise ServiceError(
                "需要空间成员身份及实例读取授权",
                code="INSTANCES_FORBIDDEN",
                status_code=403,
            )
        from ontofoundry_api.services.entity_resolution import resolve_entity

        return {
            **envelope,
            **resolve_entity(
                db,
                workspace_id,
                draft,
                mention=args.mention,
                object_type_id=args.object_type_id,
                limit=args.limit,
                settings=settings,
                mappings_readable=mappings,
            ),
        }
    if name == "search_objects":
        objects = [
            o
            for entry in stored["objects"]
            for o in [MaterialObject.model_validate(entry["element"])]
            if (args.type_id is None or index.is_a(o.type_id, args.type_id))
            and args.q.casefold()
            in (
                document_display_text(draft, o)
                + " "
                + " ".join(map(str, o.values.values()))
            ).casefold()
        ]
        objects.sort(key=lambda o: o.id.bytes)
        return {
            **envelope,
            **page(
                [
                    {
                        "id": str(o.id),
                        "type_id": str(o.type_id),
                        "display_text": document_display_text(draft, o),
                        "values": dict(list(o.values.items())[:4]),
                    }
                    for o in objects
                ],
                [],
                offset,
            ),
        }
    entry = next((e for e in stored["objects"] if e["target_id"] == str(args.id)), None)
    fact = MaterialObject.model_validate(entry["element"]) if entry else None
    if fact is None:
        raise ServiceError(
            "文档实例不存在",
            code="not_found",
            status_code=404,
            details={
                k: stored[k]
                for k in ("filtered_count", "warnings", "instance_change_sequence")
            },
        )
    item = {
        "id": str(fact.id),
        "type_id": str(fact.type_id),
        "display_text": document_display_text(draft, fact),
        "values": dict(list(fact.values.items())[:4]),
    }
    sections = {
        "properties": [
            {"property_id": str(p.id), "value": fact.values[p.name]}
            for p in index.effective_properties(fact.type_id)
            if p.name in fact.values
        ],
        "evidence": [e.model_dump(mode="json") for e in fact.evidence],
        "adjacency": [],
    }
    for entry in stored["links"]:
        link = MaterialLink.model_validate(entry["element"])
        for direction, endpoint in (
            ("forward", link.source_id),
            ("reverse", link.target_id),
        ):
            if endpoint == fact.id:
                sections["adjacency"].append(
                    {
                        "link_type_id": str(link.type_id),
                        "direction": direction,
                        "source_id": str(link.source_id),
                        "target_id": str(link.target_id),
                    }
                )
    sections["adjacency"].sort(
        key=lambda e: (e["link_type_id"], e["direction"], e["source_id"], e["target_id"])
    )
    for key in args.include:
        item[key] = page(
            sections[key], [key], offset if section and section.get("path") == [key] else 0
        )
    return {**envelope, "item": item}


def invoke(db, workspace_id, principal, name, arguments, settings):
    args = INPUTS[name].model_validate(arguments)
    if name == "search_ontology":
        return search_ontology(
            db,
            workspace_id,
            principal,
            args,
            settings,
            pinned_version_id=principal.pinned_version_id,
        )
    space = get_workspace(db, workspace_id)
    version_id = (
        principal.pinned_version_id
        if principal.pinned_version_id is not None
        else space.current_version_id
    )
    from ontofoundry_api.services.instance_store import change_sequence

    context = [
        workspace_id,
        version_id or None,
        name,
        args.model_dump(mode="json", exclude={"cursor"}),
        authorization_fingerprint(db, workspace_id, principal),
        change_sequence(db, workspace_id)
        if name in {"search_objects", "get_object"}
        else None,
    ]
    offset, section = decode_cursor(settings, args.cursor, context)
    if section and section.get("kind") == "wire_field":
        original = {**arguments, "cursor": section.get("base_cursor")}
        value = _invoke(db, workspace_id, principal, name, original, settings)
        field = value
        for token in section["path"]:
            field = field[int(token)] if isinstance(field, list) else field[token]
        chunk = field[offset : offset + 2000]
        return {
            "workspace_id": workspace_id,
            "version_id": version_id or None,
            "field_segments": [
                {
                    "element_id": section["element_id"],
                    "field": section["pointer"],
                    "start": offset,
                    "end": offset + len(chunk),
                    "total": len(field),
                    "text": chunk,
                    "next_cursor": encode_cursor(
                        settings, context, offset + len(chunk), section
                    )
                    if offset + len(chunk) < len(field)
                    else None,
                }
            ],
        }
    result = _invoke(db, workspace_id, principal, name, arguments, settings)
    segments = []

    def bounded(value, path=(), element_id=None, relative=()):
        if isinstance(value, dict):
            if "id" in value:
                element_id, relative = value["id"], ()
            copied = {}
            for key, entry in value.items():
                if isinstance(entry, str) and len(entry.encode()) > 12000 and element_id:
                    pointer = "/" + "/".join((*relative, key))
                    part = entry[:2000]
                    state = {
                        "kind": "wire_field",
                        "path": [*path, key],
                        "pointer": pointer,
                        "element_id": element_id,
                        "base_cursor": args.cursor,
                    }
                    segments.append(
                        {
                            "element_id": element_id,
                            "field": pointer,
                            "start": 0,
                            "end": len(part),
                            "total": len(entry),
                            "text": part,
                            "next_cursor": encode_cursor(
                                settings, context, len(part), state
                            )
                            if len(part) < len(entry)
                            else None,
                        }
                    )
                else:
                    copied[key] = bounded(entry, (*path, key), element_id, (*relative, key))
            return copied
        if isinstance(value, list):
            return [
                bounded(entry, (*path, str(n)), element_id, (*relative, str(n)))
                for n, entry in enumerate(value)
            ]
        return value

    result = bounded(result)
    if segments:
        result.setdefault("field_segments", []).extend(segments)
    if size(result) > 120000:
        raise ServiceError(
            "当前投影超过单页预算，请缩小 limit 或 include",
            code="response_too_large",
            status_code=422,
        )
    return result
