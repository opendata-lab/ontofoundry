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
RAW_RESPONSE_LIMIT = 120_000  # Final structuredContent byte cap enforced in invoke().
_NO_SEGMENT_KEYS = frozenset(
    {
        "id",
        "kind",
        "name",
        "direction",
        "multiplicity",
        "extends",
        "inherited_from",
        "column",
        "physical_type",
    }
)
_NO_SEGMENT_SUFFIXES = ("_id", "_ids", "_cursor", "_kind", "_status", "_mode", "_at")
_ACTION_SEGMENT_TIERS = (
    (12_000, 4_000),
    (4_000, 1_000),
    (1_500, 256),
    (950, 128),
)
_TRIM_COLLECTIONS = (
    "effective_bindings",
    "datasets",
    "sources",
    "links",
    "rules",
    "child_types",
    "columns",
    "referenced_by",
    "properties",
)
_DEFAULT_REQUEST_ID_RESERVE = "x" * 254  # 256 bytes in JSON including quotes.


def _skip_segment_key(key: str) -> bool:
    return key in _NO_SEGMENT_KEYS or key.endswith(_NO_SEGMENT_SUFFIXES)


def _invalid_cursor() -> ServiceError:
    return ServiceError(
        "游标无效或与当前版本、权限、筛选不一致",
        code="INVALID_CURSOR",
        status_code=422,
    )


def _resolve_field_path(root, path) -> str:
    value = root
    try:
        for token in path:
            if isinstance(value, list):
                idx = int(token)
                if idx < 0:
                    raise IndexError(idx)
                value = value[idx]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise TypeError(type(value))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise _invalid_cursor() from exc
    if not isinstance(value, str):
        raise _invalid_cursor()
    return value


def size(value):
    from fastapi.encoders import jsonable_encoder

    return len(
        json.dumps(
            jsonable_encoder(value), ensure_ascii=False, separators=(",", ":")
        ).encode()
    )


def _response_fits(value, *, request_id=None) -> bool:
    """Check structuredContent cap and full JSON-RPC HTTP wire size <= 256 KiB."""
    from fastapi.encoders import jsonable_encoder

    structured = jsonable_encoder(value)
    if (
        len(
            json.dumps(structured, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        > RAW_RESPONSE_LIMIT
    ):
        return False
    text = json.dumps(structured, ensure_ascii=False)
    envelope = {
        "jsonrpc": "2.0",
        "id": request_id if request_id is not None else _DEFAULT_REQUEST_ID_RESERVE,
        "result": {
            "content": [{"type": "text", "text": text}],
            "structuredContent": structured,
            "isError": False,
            "resultType": "complete",
            "_meta": {
                "io.modelcontextprotocol/serverInfo": {
                    "name": "ontofoundry",
                    "version": "0.1.0",
                },
                "io.github.opendata-lab.ontofoundry/versions": [
                    {
                        "workspace_id": structured.get("workspace_id"),
                        "version_id": structured.get("version_id"),
                        "version_number": 9999,
                    }
                ],
            },
        },
    }
    return (
        len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        <= MCP_WIRE_LIMIT
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


def _invoke(db, workspace_id, principal, name, arguments, settings, *, request_id=None):
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

    def make_collection_page(raw_items, path, start, count):
        end = start + count
        cursor = (
            encode_cursor(settings, context, end, {"kind": "list", "path": path})
            if end < len(raw_items)
            else None
        )
        return {
            "total": len(raw_items),
            "items": raw_items[start:end],
            "next_cursor": cursor,
        }

    def paginate_nested(item, path):
        values = item
        for token in path:
            values = values[token]
        return page(values, path, offset)

    fields = []

    def segment_value(
        value,
        element_id,
        out_fields,
        path=(),
        *,
        wire_threshold=None,
        chunk_wire_cap=None,
        cursor_extra=None,
    ):
        if isinstance(value, dict):
            result = {}
            for key, entry in value.items():
                over_utf8 = isinstance(entry, str) and len(entry.encode()) > 12000
                over_wire = (
                    wire_threshold is not None
                    and isinstance(entry, str)
                    and not _skip_segment_key(key)
                    and _str_wire_bytes(entry) > max(wire_threshold, chunk_wire_cap + 800)
                )
                if over_utf8 or over_wire:
                    pointer = "/" + "/".join((*path, key))
                    text = (
                        _initial_segment_chunk(entry, chunk_wire_cap)
                        if chunk_wire_cap is not None
                        else entry[:2000]
                    )
                    state = {
                        "kind": "field",
                        "element_id": element_id,
                        "path": [*path, key],
                        **(cursor_extra or {}),
                    }
                    out_fields.append(
                        {
                            "element_id": element_id,
                            "field": pointer,
                            "start": 0,
                            "end": len(text),
                            "total": len(entry),
                            "text": text,
                            "next_cursor": encode_cursor(
                                settings, context, len(text), state
                            )
                            if len(text) < len(entry)
                            else None,
                        }
                    )
                else:
                    result[key] = segment_value(
                        entry,
                        element_id,
                        out_fields,
                        (*path, key),
                        wire_threshold=wire_threshold,
                        chunk_wire_cap=chunk_wire_cap,
                        cursor_extra=cursor_extra,
                    )
            return result
        if isinstance(value, list):
            return [
                segment_value(
                    v,
                    element_id,
                    out_fields,
                    (*path, str(n)),
                    wire_threshold=wire_threshold,
                    chunk_wire_cap=chunk_wire_cap,
                    cursor_extra=cursor_extra,
                )
                for n, v in enumerate(value)
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
        wanted = {str(i) for i in args.ids} if args.ids is not None else None
        entries = [
            (identity, r)
            for identity, r in sorted(lookup.items())
            if (wanted is None or identity in wanted)
            and (not args.kinds or r["kind"] in args.kinds)
        ]
        total = len(entries)
        missing = sorted(wanted - set(lookup)) if wanted else []

        def build_element(idx):
            identity, r = entries[idx]
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
                    if r["kind"] == "action":
                        definition.pop("evidence", None)
                    if r["kind"] == "dataset":
                        columns = definition.pop("columns", None) or []
                        d["columns"] = columns
                        element["columns"] = page(columns, [idx, "columns"])
                        if "adjacency" in args.include:
                            from ontofoundry_api.services.dataset_sources import (
                                dataset_references,
                            )

                            refs = dataset_references(draft, identity)
                            d["referenced_by"] = [
                                {"category": category, **ref}
                                for category, ref_values in refs.items()
                                for ref in ref_values
                            ]
                            element["referenced_by"] = page(
                                d["referenced_by"], [idx, "referenced_by"]
                            )
                    element["definition"] = definition
                for key in ("properties", "child_types"):
                    if key in d:
                        element[key] = page(d[key], [idx, key])
                if "rules" in args.include and "rules" in d:
                    element["rules"] = page(d["rules"], [idx, "rules"])
                if "adjacency" in args.include and "links" in d:
                    element["links"] = page(d["links"], [idx, "links"])
                if mappings and "physical" in args.include:
                    if "sql_reference" in d:
                        element["sql_reference"] = d["sql_reference"]
                    for key in ("sources", "datasets", "effective_bindings"):
                        if key in d:
                            element[key] = page(d[key], [idx, key])
                    for key in (
                        "instance_source_type_ids",
                        "components",
                        "dataset_id",
                        "value_kind",
                    ):
                        if key in d:
                            element[key] = d[key]
            return element

        def action_collection(idx):
            if wanted is None:
                return None, None, None
            _, r = entries[idx]
            if r["kind"] == "action" and instances:
                return "evidence", r["definition"].get("evidence") or [], [idx, "evidence"]
            if r["kind"] == "object_type" and r["definition"].get("actions"):
                return "actions", r["definition"]["actions"], [idx, "actions"]
            return None, None, None

        def build_response(elements, segs, next_cursor, missing_ids):
            return {
                **envelope,
                "total": total,
                "elements": elements,
                "missing": missing_ids,
                "next_cursor": next_cursor,
                **({"field_segments": segs} if segs else {}),
            }

        def fits(resp):
            return _response_fits(resp, request_id=request_id)

        def checked_response(elements, segs, next_cursor, missing_ids, verified):
            resp = build_response(elements, segs, next_cursor, missing_ids)
            if not verified and not fits(resp):
                raise ServiceError(
                    "当前投影超过单页预算，请缩小 limit 或 include",
                    code="response_too_large",
                    status_code=422,
                )
            return resp

        def fit_first_element(
            base_el,
            col_key,
            raw_col,
            col_path,
            start,
            next_cursor,
            missing_ids,
            *,
            elem_idx=None,
            raw_def=None,
            cursor_extra=None,
            require_progress=False,
        ):
            # Fast path: reuse standard segmentation and collection paging, sizing once.
            el_fields = []
            seg_el = segment_value(
                base_el, base_el["id"], el_fields, cursor_extra=cursor_extra
            )
            initial_col = page(raw_col, col_path, start) if col_key is not None else None
            candidate_el = (
                {**seg_el, col_key: initial_col} if col_key is not None else seg_el
            )
            if fits(build_response([candidate_el], el_fields, next_cursor, missing_ids)):
                return candidate_el, el_fields, True

            # Ensure base (+ empty collection cursor) fits, progressively segmenting if needed.
            empty_col = (
                make_collection_page(raw_col, col_path, start, 0)
                if col_key is not None
                else None
            )
            base_fits = False
            segmented_further = False
            if col_key is not None and initial_col["items"]:
                base_fits = fits(
                    build_response(
                        [{**seg_el, col_key: empty_col}],
                        el_fields,
                        next_cursor,
                        missing_ids,
                    )
                )
            if not base_fits:
                segmented_further = True
                for wire_threshold, chunk_wire_cap in _ACTION_SEGMENT_TIERS:
                    el_fields = []
                    seg_el = segment_value(
                        base_el,
                        base_el["id"],
                        el_fields,
                        wire_threshold=wire_threshold,
                        chunk_wire_cap=chunk_wire_cap,
                        cursor_extra=cursor_extra,
                    )
                    test_el = (
                        {**seg_el, col_key: empty_col} if col_key is not None else seg_el
                    )
                    if fits(build_response([test_el], el_fields, next_cursor, missing_ids)):
                        base_fits = True
                        break
            if not base_fits and raw_def is not None and elem_idx is not None:
                # Last-resort guard: trim paged collections (e.g. properties with heavy
                # synonyms) to what fits while advancing each collection's cursor.
                trimmed_base = dict(base_el)
                last_wt, last_cap = _ACTION_SEGMENT_TIERS[-1]
                for k in _TRIM_COLLECTIONS:
                    if base_fits:
                        break
                    col = trimmed_base.get(k)
                    raw_k = raw_def.get(k)
                    if not isinstance(col, dict) or not col.get("items") or not raw_k:
                        continue
                    k_start = (
                        cursor_extra["list_offset"]
                        if cursor_extra and cursor_extra.get("list_key") == k
                        else 0
                    )
                    min_count = (
                        1 if (cursor_extra and cursor_extra.get("list_key") == k) else 0
                    )

                    def eval_trim(
                        count,
                        base_snapshot=trimmed_base,
                        key=k,
                        raw_items=raw_k,
                        start_idx=k_start,
                    ):
                        cand = {
                            **base_snapshot,
                            key: make_collection_page(
                                raw_items, [elem_idx, key], start_idx, count
                            ),
                        }
                        cand_fields = []
                        cand_seg = segment_value(
                            cand,
                            base_el["id"],
                            cand_fields,
                            wire_threshold=last_wt,
                            chunk_wire_cap=last_cap,
                            cursor_extra=cursor_extra,
                        )
                        test = (
                            {**cand_seg, col_key: empty_col}
                            if col_key is not None
                            else cand_seg
                        )
                        ok = fits(
                            build_response([test], cand_fields, next_cursor, missing_ids)
                        )
                        return ok, cand, cand_seg, cand_fields

                    fits_min, cand_min, seg_min, fields_min = eval_trim(min_count)
                    if not fits_min:
                        trimmed_base, seg_el, el_fields = cand_min, seg_min, fields_min
                        continue
                    lo_k, hi_k = min_count, len(col["items"]) - 1
                    best = (cand_min, seg_min, fields_min)
                    while lo_k < hi_k:
                        mid_k = (lo_k + hi_k + 1) // 2
                        ok_k, c_k, s_k, f_k = eval_trim(mid_k)
                        if ok_k:
                            lo_k = mid_k
                            best = (c_k, s_k, f_k)
                        else:
                            hi_k = mid_k - 1
                    trimmed_base, seg_el, el_fields = best
                    base_fits = True

            if col_key is None:
                return seg_el, el_fields, base_fits

            lo = 0
            if base_fits:
                hi = (
                    len(initial_col["items"])
                    if segmented_further
                    else max(0, len(initial_col["items"]) - 1)
                )
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    col_page = make_collection_page(raw_col, col_path, start, mid)
                    if fits(
                        build_response(
                            [{**seg_el, col_key: col_page}],
                            el_fields,
                            next_cursor,
                            missing_ids,
                        )
                    ):
                        lo = mid
                    else:
                        hi = mid - 1
            if lo == 0 and require_progress and start < len(raw_col):
                single_el = {
                    **seg_el,
                    col_key: make_collection_page(raw_col, col_path, start, 1),
                }
                fitted, cont_fields = single_el, []
                for wire_threshold, chunk_wire_cap in (
                    (None, None),
                    *_ACTION_SEGMENT_TIERS,
                ):
                    cont_fields = []
                    fitted = segment_value(
                        single_el,
                        base_el["id"],
                        cont_fields,
                        wire_threshold=wire_threshold,
                        chunk_wire_cap=chunk_wire_cap,
                        cursor_extra={"list_key": col_key, "list_offset": start},
                    )
                    if fits(
                        build_response([fitted], cont_fields, next_cursor, missing_ids)
                    ):
                        return fitted, cont_fields, True
                return fitted, cont_fields, False
            return (
                {**seg_el, col_key: make_collection_page(raw_col, col_path, start, lo)},
                el_fields,
                base_fits,
            )

        if section and section["kind"] == "list":
            path = section.get("path")
            if (
                not isinstance(path, list)
                or len(path) != 2
                or not isinstance(path[0], int)
                or not (0 <= path[0] < total)
                or not isinstance(path[1], str)
            ):
                raise _invalid_cursor()
            # Rebuild the unpaged section by requesting the matching resource.
            n, key = path
            identity, r = entries[n]
            d = r["definition"]
            header = {
                "id": identity,
                "kind": r["kind"],
                "display_name": d.get("display_name"),
                "name": d["name"],
            }
            if (key == "evidence" and r["kind"] == "action") or (
                key == "actions" and r["kind"] == "object_type"
            ):
                fitted, segs, ok = fit_first_element(
                    header,
                    key,
                    d.get(key) or [],
                    path,
                    offset,
                    None,
                    [],
                    require_progress=True,
                )
                return checked_response([fitted], segs, None, [], ok)
            element = build_element(n)
            raw = d.get(key)
            if not isinstance(raw, list):
                raise _invalid_cursor()
            element[key] = page(raw, path, offset)
            if r["kind"] == "object_type" and d.get("actions"):
                fitted, segs, ok = fit_first_element(
                    element,
                    "actions",
                    d["actions"],
                    [n, "actions"],
                    0,
                    None,
                    [],
                    elem_idx=n,
                    raw_def=d,
                    cursor_extra={"list_key": key, "list_offset": offset},
                )
                if not ok:
                    fitted, segs, ok = fit_first_element(
                        header,
                        key,
                        raw,
                        path,
                        offset,
                        None,
                        [],
                        require_progress=True,
                    )
                return checked_response([fitted], segs, None, [], ok)
            return {
                **envelope,
                "total": total,
                "elements": [element],
                "missing": [],
                "next_cursor": None,
            }
        if section and section["kind"] == "field":
            n = next(
                (
                    i
                    for i, (identity, _) in enumerate(entries)
                    if identity == section.get("element_id")
                ),
                None,
            )
            if n is None:
                raise _invalid_cursor()
            value = build_element(n)
            if "list_key" in section:
                lk = section["list_key"]
                raw_lk = entries[n][1]["definition"].get(lk)
                if not isinstance(raw_lk, list) or not isinstance(
                    section.get("list_offset"), int
                ):
                    raise _invalid_cursor()
                value[lk] = page(raw_lk, [n, lk], section["list_offset"])
            value = _resolve_field_path(value, section.get("path", ()))
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
                "total": total,
                "elements": [],
                "missing": [],
                "next_cursor": None,
                "field_segments": [segment],
            }
        has_action_content = any(
            r["kind"] == "action"
            or (wanted is not None and bool(r["definition"].get("actions")))
            for _, r in entries
        )
        if not has_action_content:
            values = [build_element(i) for i in range(total)]
            cleaned = [segment_value(v, v["id"], fields) for v in values]
            data = page(cleaned, [], offset)
            return {
                **envelope,
                "total": total,
                "elements": data["items"],
                "missing": missing,
                "next_cursor": encode_cursor(settings, context, offset + len(data["items"]))
                if offset + len(data["items"]) < total
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

        items = []
        page_fields = []
        verified = True
        for n in range(offset, min(total, offset + args.limit)):
            base_el = build_element(n)
            col_key, raw_col, col_path = action_collection(n)
            cand_next_cursor = (
                encode_cursor(settings, context, n + 1) if n + 1 < total else None
            )
            if not items:
                el, el_fields, verified = fit_first_element(
                    base_el,
                    col_key,
                    raw_col,
                    col_path,
                    0,
                    cand_next_cursor,
                    missing,
                    elem_idx=n,
                    raw_def=entries[n][1]["definition"],
                )
                items.append(el)
                page_fields.extend(el_fields)
                continue
            el_fields = []
            cand_el = segment_value(base_el, base_el["id"], el_fields)
            if col_key is not None:
                cand_el[col_key] = page(raw_col, col_path, 0)
            candidate_items = items + [cand_el]
            if size(candidate_items) > BUDGET // 2:
                break
            candidate_fields = page_fields + el_fields
            if not fits(
                build_response(candidate_items, candidate_fields, cand_next_cursor, missing)
            ):
                break
            items = candidate_items
            page_fields = candidate_fields
        next_cursor = (
            encode_cursor(settings, context, offset + len(items))
            if offset + len(items) < total
            else None
        )
        return checked_response(items, page_fields, next_cursor, missing, verified)
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


def invoke(db, workspace_id, principal, name, arguments, settings, *, request_id=None):
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
        value = _invoke(
            db, workspace_id, principal, name, original, settings, request_id=request_id
        )
        field = _resolve_field_path(value, section.get("path", ()))
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
    result = _invoke(
        db, workspace_id, principal, name, arguments, settings, request_id=request_id
    )
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
