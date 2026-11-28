"""Four read-only ontology tools with authorization-bound segmented pagination."""

import json
from copy import deepcopy
from typing import Literal
from uuid import UUID

from pydantic import Field

from ontofoundry_api.contracts.read_models import (
    OntologyKind as Kind,
    OntologySearchRequest,
)
from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import CoreDraft, Strict
from ontofoundry_api.domain.graph import draft_index
from ontofoundry_api.domain.instance_display import document_display_text
from ontofoundry_api.domain.models import COLLECTIONS, ElementKind
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services.access import (
    authorization_fingerprint,
    can_read_instances,
    can_read_mappings,
    require_instances,
    require_read,
)
from ontofoundry_api.services.cursors import decode_cursor, encode_cursor
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.ontology_query import (
    current_version,
    read_context,
    resource_items,
)
from ontofoundry_api.services.ontology_search import search_ontology
from ontofoundry_api.services.workspaces import get_workspace

# MCP get_ontology separates resource-projected kinds from direct definition kinds;
# mappings are internal physical bindings and excluded from both.
PHYSICAL_PROJECTION_KINDS = frozenset({"object_type", "link_type", "metric"})
LIST_RESOURCE_KINDS = ("object_type", "link_type", "metric", "dataset", "action")
DIRECT_ELEMENT_KINDS = ("property", "rule", "value_type")


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
MCP_WIRE_LIMIT = 262_144  # 256 KiB HTTP JSON-RPC response cap.
# Reserve 2 KiB for gateway _meta (versions list) and request IDs.
ACTION_WIRE_BUDGET = MCP_WIRE_LIMIT - 2_048
ACTION_RAW_BUDGET = 118_000  # Stay safely under the final 120,000-byte structuredContent cap.
_ACTION_NO_SEGMENT_KEYS = frozenset(
    {
        "id",
        "kind",
        "name",
        "property_id",
        "link_type_id",
        "object_type_id",
        "target_type_id",
        "value_type_id",
        "value_kind",
    }
)


def size(value):
    from fastapi.encoders import jsonable_encoder

    return len(
        json.dumps(
            jsonable_encoder(value), ensure_ascii=False, separators=(",", ":")
        ).encode()
    )


def _jsonrpc_wire_size(value):
    """UTF-8 byte size of the full JSON-RPC response for tool_result(value)."""
    from fastapi.encoders import jsonable_encoder

    structured = jsonable_encoder(value)
    text = json.dumps(structured, ensure_ascii=False)
    envelope = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": text}],
            "structuredContent": structured,
            "isError": False,
            "resultType": "complete",
            "_meta": {
                "io.modelcontextprotocol/serverInfo": {
                    "name": "ontofoundry",
                    "version": "0.1.0",
                }
            },
        },
    }
    return len(
        json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _str_wire_bytes(text: str) -> int:
    """Wire bytes contributed by one JSON string value across structuredContent + content[].text."""
    compact = json.dumps(text, ensure_ascii=False)
    escaped = json.dumps(compact, ensure_ascii=False)
    return len(compact.encode("utf-8")) + len(escaped.encode("utf-8"))


def _initial_segment_chunk(entry: str, max_wire_bytes: int = 4_000) -> str:
    """Take up to 2000 chars, shrinking if heavy escaping would bloat the segment."""
    chunk = entry[:2000]
    if _str_wire_bytes(chunk) <= max_wire_bytes:
        return chunk
    lo, hi = 1, len(chunk)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _str_wire_bytes(chunk[:mid]) <= max_wire_bytes:
            lo = mid
        else:
            hi = mid - 1
    return chunk[:lo]


def _invoke(db, workspace_id, principal, name, arguments, settings):
    require_read(db, workspace_id, principal)
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
        # Shared immutable definitions are read directly; every response projection is new.
        snapshot = read_context(version).snapshot
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

    def segment_action_base(element, build_base_response):
        # First try the exact same 12,000-byte rule as other elements.
        def run_segment(value, path=(), wire_threshold=None, chunk_wire_cap=None, out_fields=None):
            if isinstance(value, dict):
                result = {}
                for key, entry in value.items():
                    over_utf8 = isinstance(entry, str) and len(entry.encode()) > 12000
                    over_wire = (
                        wire_threshold is not None
                        and isinstance(entry, str)
                        and key not in _ACTION_NO_SEGMENT_KEYS
                        and _str_wire_bytes(entry) > wire_threshold
                    )
                    if over_utf8 or over_wire:
                        pointer = "/" + "/".join((*path, key))
                        text = (
                            _initial_segment_chunk(entry, chunk_wire_cap)
                            if chunk_wire_cap is not None
                            else entry[:2000]
                        )
                        out_fields.append(
                            {
                                "element_id": element["id"],
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
                                        "element_id": element["id"],
                                        "path": [*path, key],
                                    },
                                )
                                if len(text) < len(entry)
                                else None,
                            }
                        )
                    else:
                        result[key] = run_segment(
                            entry, (*path, key), wire_threshold, chunk_wire_cap, out_fields
                        )
                return result
            if isinstance(value, list):
                return [
                    run_segment(
                        v, (*path, str(n)), wire_threshold, chunk_wire_cap, out_fields
                    )
                    for n, v in enumerate(value)
                ]
            return value

        el_fields = []
        candidate = run_segment(element, out_fields=el_fields)
        resp = build_base_response(candidate, el_fields)
        if size(resp) <= ACTION_RAW_BUDGET and _jsonrpc_wire_size(resp) <= ACTION_WIRE_BUDGET:
            return candidate, el_fields

        # Base projection alone still exceeds budget: progressively segment escape-heavy
        # or long string fields using the same field_segments mechanism.
        for wire_threshold, chunk_wire_cap in (
            (12_000, 4_000),
            (4_000, 2_000),
            (1_000, 512),
            (256, 128),
        ):
            el_fields = []
            candidate = run_segment(
                element,
                wire_threshold=wire_threshold,
                chunk_wire_cap=chunk_wire_cap,
                out_fields=el_fields,
            )
            resp = build_base_response(candidate, el_fields)
            if size(resp) <= ACTION_RAW_BUDGET and _jsonrpc_wire_size(resp) <= ACTION_WIRE_BUDGET:
                return candidate, el_fields
        return candidate, el_fields

    def page_action_evidence(raw_evidence, path, base_el, el_fields, build_response, start=0):
        # Budget against the full serialized JSON-RPC response; never append evidence
        # when the base projection leaves no room (return a cursor instead).
        items, cursor = [], None
        max_end = min(len(raw_evidence), start + args.limit)
        for n in range(start, max_end):
            candidate_items = items + [raw_evidence[n]]
            next_c = (
                encode_cursor(settings, context, n + 1, {"kind": "list", "path": path})
                if n + 1 < len(raw_evidence)
                else None
            )
            candidate_el = {
                **base_el,
                "evidence": {
                    "total": len(raw_evidence),
                    "items": candidate_items,
                    "next_cursor": next_c,
                },
            }
            candidate_resp = build_response(candidate_el, el_fields)
            if (
                size(candidate_resp) > ACTION_RAW_BUDGET
                or _jsonrpc_wire_size(candidate_resp) > ACTION_WIRE_BUDGET
            ):
                break
            items.append(raw_evidence[n])
        end = start + len(items)
        if end < len(raw_evidence):
            cursor = encode_cursor(settings, context, end, {"kind": "list", "path": path})
        return {"total": len(raw_evidence), "items": items, "next_cursor": cursor}

    def page_object_actions(raw_actions, path, base_el, total_elements, start=0):
        # Allocate object action summaries from the object's remaining budget so
        # properties and their cursor behave identically to main.
        items, cursor = [], None
        max_end = min(len(raw_actions), start + args.limit)
        for n in range(start, max_end):
            candidate_items = items + [raw_actions[n]]
            if items and size(candidate_items) > BUDGET // 2:
                break
            next_c = (
                encode_cursor(settings, context, n + 1, {"kind": "list", "path": path})
                if n + 1 < len(raw_actions)
                else None
            )
            candidate_el = {
                **base_el,
                "actions": {
                    "total": len(raw_actions),
                    "items": candidate_items,
                    "next_cursor": next_c,
                },
            }
            candidate_resp = {
                **envelope,
                "total": total_elements,
                "elements": [candidate_el],
                "missing": [],
                "next_cursor": None,
            }
            if (
                size(candidate_items) > BUDGET // 2
                or size(candidate_resp) > ACTION_RAW_BUDGET
                or _jsonrpc_wire_size(candidate_resp) > ACTION_WIRE_BUDGET
            ):
                break
            items.append(raw_actions[n])
        end = start + len(items)
        if end < len(raw_actions):
            cursor = encode_cursor(settings, context, end, {"kind": "list", "path": path})
        return {"total": len(raw_actions), "items": items, "next_cursor": cursor}

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

    wanted = (
        {str(i) for i in args.ids}
        if name == "get_ontology" and args.ids is not None
        else None
    )
    resources = (
        resource_items(
            snapshot,
            draft=draft,
            selected=[UUID(i) for i in wanted],
            mappings=mappings,
            instances=instances,
            db=db if mappings else None,
            workspace_id=workspace_id,
        )
        if name == "get_ontology" and wanted is not None
        else []
    )
    if (
        mappings
        and name == "get_ontology"
        and wanted is not None
        and "physical" in args.include
    ):
        from ontofoundry_api.services.dataset_sources import authorized_dataset_projection
        from ontofoundry_api.services.physical_projection import physical_projection

        def datasets(identities):
            return [
                authorized_dataset_projection(db, workspace_id, index.datasets[i])
                for i in sorted(identities, key=str)
                if i in index.datasets
            ]

        for resource in resources:
            if resource["kind"] not in PHYSICAL_PROJECTION_KINDS:
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
    if name == "get_ontology" and wanted is None:
        for kind in LIST_RESOURCE_KINDS:
            collection = COLLECTIONS[ElementKind(kind)]
            if kind == "dataset" and not mappings:
                continue
            for element in snapshot[collection]:
                lookup[element["id"]] = {
                    "kind": kind,
                    "definition": {
                        key: element.get(key) for key in ("id", "name", "display_name")
                    },
                }
    for kind in DIRECT_ELEMENT_KINDS:
        collection = COLLECTIONS[ElementKind(kind)]
        for e in snapshot.get(collection, []) if name == "get_ontology" else []:
            if wanted is not None and e["id"] not in wanted:
                continue
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
                definition = index.elements[UUID(identity)][1].model_dump(mode="json")
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
                    action_evidence = None
                    if r["kind"] == "action":
                        action_evidence = definition.pop("evidence", None) or []
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
                    if action_evidence is not None and instances:
                        d["evidence"] = action_evidence
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
                if d.get("actions"):
                    element["actions"] = page_object_actions(
                        d["actions"],
                        [len(values), "actions"],
                        element,
                        total_elements=max(1, len(lookup)),
                        start=0,
                    )
            values.append(element)
        if section and section["kind"] == "list":
            path = section["path"]
            # Rebuild the unpaged section by requesting the matching resource.
            n, key = path
            d = lookup[values[n]["id"]]["definition"]
            raw = d.get(key)
            if key == "evidence" and values[n]["kind"] == "action":
                base_el = {k: v for k, v in values[n].items() if k != "evidence"}
                sample_ev_cursor = (
                    encode_cursor(settings, context, offset, {"kind": "list", "path": path})
                    if offset < len(raw)
                    else None
                )

                def build_cont(el, segs):
                    return {
                        **envelope,
                        "total": len(values),
                        "elements": [el],
                        "missing": [],
                        "next_cursor": None,
                        **({"field_segments": segs} if segs else {}),
                    }

                def build_cont_base(el, segs):
                    return build_cont(
                        {
                            **el,
                            "evidence": {
                                "total": len(raw),
                                "items": [],
                                "next_cursor": sample_ev_cursor,
                            },
                        },
                        segs,
                    )

                seg_el, cont_fields = segment_action_base(base_el, build_cont_base)
                ev_page = page_action_evidence(
                    raw, path, seg_el, cont_fields, build_cont, offset
                )
                if not ev_page["items"] and offset < len(raw):
                    # Base projection left no room for the next evidence entry even after
                    # field segmentation; serve the continuation with a minimal header so
                    # evidence pagination always makes forward progress under 256 KiB.
                    stub_el = {
                        k: values[n][k]
                        for k in ("id", "kind", "display_name", "name")
                        if k in values[n]
                    }
                    cont_fields = []
                    ev_page = page_action_evidence(
                        raw, path, stub_el, cont_fields, build_cont, offset
                    )
                    seg_el = stub_el
                return build_cont({**seg_el, "evidence": ev_page}, cont_fields)
            if key == "actions" and values[n]["kind"] == "object_type":
                base_el = {k: v for k, v in values[n].items() if k != "actions"}
                act_page = page_object_actions(
                    raw, path, base_el, total_elements=len(values), start=offset
                )
                if not act_page["items"] and offset < len(raw):
                    stub_el = {
                        k: values[n][k]
                        for k in ("id", "kind", "display_name", "name")
                        if k in values[n]
                    }
                    act_page = page_object_actions(
                        raw, path, stub_el, total_elements=len(values), start=offset
                    )
                    return {
                        **envelope,
                        "total": len(values),
                        "elements": [{**stub_el, "actions": act_page}],
                        "missing": [],
                        "next_cursor": None,
                    }
                values[n][key] = act_page
                return {
                    **envelope,
                    "total": len(values),
                    "elements": [values[n]],
                    "missing": [],
                    "next_cursor": None,
                }
            values[n][key] = page(raw, path, offset)
            if values[n]["kind"] == "object_type" and "actions" in values[n]:
                base_el = {k: v for k, v in values[n].items() if k != "actions"}
                values[n]["actions"] = page_object_actions(
                    d["actions"], [n, "actions"], base_el, total_elements=len(values), start=0
                )
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
        missing = sorted(wanted - set(lookup)) if wanted else []
        cleaned = []
        for idx, v in enumerate(values):
            if v["kind"] == "action" and wanted is not None:
                raw_ev = lookup[v["id"]]["definition"].get("evidence") if instances else None
                base_el = {k: val for k, val in v.items() if k != "evidence"}
                sample_outer_cursor = (
                    encode_cursor(settings, context, idx + 1)
                    if len(values) > 1
                    else None
                )

                def build_single(el, segs, outer_cursor=sample_outer_cursor):
                    return {
                        **envelope,
                        "total": len(values),
                        "elements": [el],
                        "missing": missing,
                        "next_cursor": outer_cursor,
                        **({"field_segments": segs} if segs else {}),
                    }

                def build_base(el, segs, ev_raw=raw_ev, elem_idx=idx, single=build_single):
                    if ev_raw is None:
                        return single(el, segs)
                    sample_ev_cursor = (
                        encode_cursor(
                            settings, context, 0, {"kind": "list", "path": [elem_idx, "evidence"]}
                        )
                        if ev_raw
                        else None
                    )
                    return single(
                        {
                            **el,
                            "evidence": {
                                "total": len(ev_raw),
                                "items": [],
                                "next_cursor": sample_ev_cursor,
                            },
                        },
                        segs,
                    )

                seg_el, el_fields = segment_action_base(base_el, build_base)
                fields.extend(el_fields)
                if raw_ev is not None:
                    seg_el["evidence"] = page_action_evidence(
                        raw_ev, [idx, "evidence"], seg_el, el_fields, build_single, 0
                    )
                cleaned.append(seg_el)
            else:
                cleaned.append(segment_fields(v, v["id"]))
        has_action_content = any(
            e["kind"] == "action" or "actions" in e for e in cleaned
        )
        if not has_action_content:
            data = page(cleaned, [], offset)
        else:
            items = []
            for n in range(offset, min(len(cleaned), offset + args.limit)):
                candidate_items = items + [cleaned[n]]
                if items:
                    if size(candidate_items) > BUDGET // 2:
                        break
                    item_ids = {e["id"] for e in candidate_items}
                    item_fields = [f for f in fields if f["element_id"] in item_ids]
                    candidate_resp = {
                        **envelope,
                        "total": len(values),
                        "elements": candidate_items,
                        "missing": missing,
                        "next_cursor": encode_cursor(settings, context, n + 1)
                        if n + 1 < len(values)
                        else None,
                        **({"field_segments": item_fields} if item_fields else {}),
                    }
                    if (
                        size(candidate_resp) > ACTION_RAW_BUDGET
                        or _jsonrpc_wire_size(candidate_resp) > ACTION_WIRE_BUDGET
                    ):
                        break
                items.append(cleaned[n])
            data = {"total": len(cleaned), "items": items, "next_cursor": None}
        return {
            **envelope,
            "total": len(values),
            "elements": data["items"],
            "missing": missing,
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
    require_read(db, workspace_id, principal)
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
