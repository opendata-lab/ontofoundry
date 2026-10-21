"""Version-scoped ontology retrieval, projections and shared REST/MCP pagination."""

import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from ontofoundry_api.contracts.read_models import OntologySearchRead, OntologySearchRequest
from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services.access import (
    authorization_fingerprint,
    can_read_mappings,
)
from ontofoundry_api.services.cursors import decode_cursor, encode_cursor
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metric_query import dataset_for
from ontofoundry_api.services.ontology_query import current_version, snapshot_of
from ontofoundry_api.services.workspaces import get_workspace

_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_ORDER = {
    "name_in_query": 0,
    "query_in_name": 1,
    "vector": 2,
    "description": 3,
    "expansion": 4,
}


def normalize(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKC", text).translate(_ASCII_LOWER)
        if not c.isspace()
    )


def normalized_positions(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Map NFKC compositions and expansions back to complete original spans."""
    previous = ""
    positions: list[tuple[int, int]] = []
    for i in range(len(text)):
        normalized = unicodedata.normalize("NFKC", text[: i + 1])
        common = 0
        while (
            common < min(len(previous), len(normalized))
            and previous[common] == normalized[common]
        ):
            common += 1
        start = min((p[0] for p in positions[common:]), default=i)
        positions[common:] = [(start, i + 1)] * (len(normalized) - common)
        previous = normalized
    kept = [
        (c.translate(_ASCII_LOWER), p)
        for c, p in zip(previous, positions, strict=True)
        if not c.isspace()
    ]
    return "".join(c for c, _ in kept), [p for _, p in kept]


def remaining_fragments(query: str, spans: Sequence[tuple[int, int]]) -> list[str]:
    covered = [False] * len(query)
    for start, end in spans:
        covered[start:end] = [True] * (end - start)
    fragments, current = [], []
    for i, char in enumerate(query):
        if covered[i] or char.isspace() or unicodedata.category(char).startswith("P"):
            if current:
                fragments.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        fragments.append("".join(current))
    return fragments


@dataclass(frozen=True)
class SearchElement:
    id: str
    kind: str
    definition: dict


@dataclass(frozen=True)
class RecallHit:
    id: str
    match: dict
    # All name occurrences count, even when a different alias wins the ranking.
    covered_spans: tuple[tuple[int, int], ...] = ()

    @property
    def sort_key(self):
        return (
            _ORDER[self.match["by"]],
            -len(normalize(self.match.get("text", ""))),
            self.id,
        )


class RecallSource(Protocol):
    name: Literal["keyword", "vector"]

    def recall(
        self, query: str, elements: Sequence[SearchElement]
    ) -> Sequence[RecallHit]: ...


def search_names(element: SearchElement) -> list[str]:
    d = element.definition
    identifier = d["name"]
    return list(
        dict.fromkeys(
            [
                *([d["display_name"]] if d.get("display_name") else []),
                identifier,
                *(
                    [" ".join(identifier.split("_")), *filter(None, identifier.split("_"))]
                    if "_" in identifier
                    else []
                ),
                *d.get("synonyms", []),
            ]
        )
    )


class KeywordRecall:
    name = "keyword"

    def recall(self, query: str, elements: Sequence[SearchElement]) -> Sequence[RecallHit]:
        q, positions = normalized_positions(query)
        hits: dict[str, RecallHit] = {}
        description_coverage = []
        for element in elements:
            candidates, spans = [], []
            for text in search_names(element):
                term = normalize(text)
                if not term:
                    continue
                if q and term in q:
                    candidates.append(
                        RecallHit(element.id, {"by": "name_in_query", "text": text})
                    )
                    start = q.find(term)
                    while start >= 0:
                        spans.append(
                            (positions[start][0], positions[start + len(term) - 1][1])
                        )
                        start = q.find(term, start + 1)
                elif q in term:
                    candidates.append(
                        RecallHit(element.id, {"by": "query_in_name", "text": query})
                    )
                    description_coverage.append((0, len(query)))
            if candidates:
                best = min(candidates, key=lambda h: h.sort_key)
                hits[element.id] = RecallHit(element.id, best.match, tuple(spans))
                description_coverage.extend(spans)
        fragments = remaining_fragments(query, description_coverage)
        for element in elements:
            if element.id in hits:
                continue
            description = normalize(element.definition.get("description", ""))
            matched = [
                fragment
                for fragment in fragments
                if len(normalize(fragment)) >= 2 and normalize(fragment) in description
            ]
            if matched:
                text = max(matched, key=lambda t: len(normalize(t)))
                hits[element.id] = RecallHit(
                    element.id, {"by": "description", "text": text}
                )
        return list(hits.values())


DEFAULT_SOURCES: tuple[RecallSource, ...] = (KeywordRecall(),)


def visible_elements(draft: CoreDraft, *, mappings: bool) -> list[SearchElement]:
    """Use an allowlist so recall sources never receive evidence or hidden columns."""
    elements = []
    for kind, values in (
        ("object_type", draft.object_types),
        ("property", draft.properties),
        ("link_type", draft.link_types),
        ("rule", draft.rules),
        ("metric", draft.metrics),
        ("dataset", draft.datasets if mappings else []),
        ("value_type", draft.value_types),
    ):
        for value in values:
            raw = value.model_dump(mode="json")
            allowed = {"id", "name", "display_name", "description", "synonyms"}
            if kind == "object_type":
                allowed |= {"title_property_id"}
            elif kind == "property":
                allowed |= {"owner_type_id", "value_kind", "value_type_id", "identifier"}
            elif kind == "link_type":
                allowed |= {
                    "source_type_id",
                    "target_type_id",
                    "source_role_name",
                    "target_role_name",
                    "multiplicity",
                }
            elif kind == "rule":
                allowed |= {"owner_id", "owner_kind"}
            elif kind == "metric":
                allowed |= {"kind", "aggregation", "numerator_id", "denominator_id"}
                if mappings:
                    allowed |= {"measure", "time_field", "filters", "expression"}
            elements.append(
                SearchElement(
                    str(value.id), kind, {k: v for k, v in raw.items() if k in allowed}
                )
            )
    return elements


def expansion_targets(element: SearchElement, draft: CoreDraft, *, mappings: bool):
    d = element.definition
    if element.kind == "metric":
        if mappings:
            metric = next(m for m in draft.metrics if str(m.id) == element.id)
            dataset = dataset_for(draft, metric)
            for obj in draft.object_types:
                binding = resolve_binding(draft, obj.id)
                if any(s.dataset_id == dataset.id for s in binding.sources.values()):
                    yield str(obj.id), "metric_dataset_bound_type"
        if d["kind"] == "ratio":
            yield d["numerator_id"], "metric_numerator"
            yield d["denominator_id"], "metric_denominator"
    elif element.kind == "object_type":
        if d.get("title_property_id"):
            yield d["title_property_id"], "object_title_property"
        for link in draft.link_types:
            if element.id in {str(link.source_type_id), str(link.target_type_id)}:
                yield str(link.id), "object_link_type"
    elif element.kind == "property":
        yield d["owner_type_id"], "property_owner"
    elif element.kind == "link_type":
        yield d["source_type_id"], "link_source_type"
        yield d["target_type_id"], "link_target_type"


def item_summary(
    element: SearchElement,
    match: dict,
    lookup: dict[str, SearchElement],
    draft: CoreDraft,
    *,
    mappings: bool,
    query: str,
):
    d = element.definition
    item = {
        "id": element.id,
        "kind": element.kind,
        "display_name": d.get("display_name"),
        "name": d["name"],
        "summary": d.get("description", ""),
        "match": match,
        "matched_synonyms": [
            s
            for s in d.get("synonyms", [])
            if normalize(query) in normalize(s) or normalize(s) in normalize(query)
        ]
        if match["by"] != "expansion"
        else [],
    }

    def reference(identity):
        target = lookup[identity].definition
        return {
            "id": identity,
            "name": target["name"],
            "display_name": target.get("display_name"),
        }

    owner = d.get("owner_type_id", d.get("source_type_id", d.get("owner_id")))
    if owner:
        item.update(owner_id=owner, owner_kind=d.get("owner_kind", "object_type"))
    if element.kind == "object_type":
        item.update(
            synonyms=d.get("synonyms", []), title_property_id=d.get("title_property_id")
        )
    elif element.kind == "property":
        item.update(
            owner=reference(d["owner_type_id"]),
            value_kind=d["value_kind"],
            value_type_id=d.get("value_type_id"),
            identifier=d["identifier"],
            synonyms=d.get("synonyms", []),
        )
    elif element.kind == "link_type":
        item.update(
            {
                key: d.get(key)
                for key in (
                    "source_type_id",
                    "target_type_id",
                    "source_role_name",
                    "target_role_name",
                    "multiplicity",
                )
            }
        )
        item.update(
            source=reference(d["source_type_id"]), target=reference(d["target_type_id"])
        )
    elif element.kind == "metric":
        item["definition"] = {
            key: d[key]
            for key in (
                "kind",
                "aggregation",
                "measure",
                "time_field",
                "filters",
                "expression",
                "numerator_id",
                "denominator_id",
            )
            if key in d
        }
        if mappings:
            metric = next(m for m in draft.metrics if str(m.id) == element.id)
            dataset = dataset_for(draft, metric)
            item["dataset"] = {"id": str(dataset.id), "name": dataset.name}
    return item


def retrieve(
    query: str,
    draft: CoreDraft,
    *,
    mappings: bool,
    kinds=None,
    expand=True,
    sources: Sequence[RecallSource] = DEFAULT_SOURCES,
):
    elements = visible_elements(draft, mappings=mappings)
    lookup = {e.id: e for e in elements}
    hits: dict[str, RecallHit] = {}
    coverage = []
    retrieval = {"keyword": False, "vector": False}
    for source in sources:
        retrieval[source.name] = True
        for hit in source.recall(query, elements):
            if hit.id not in lookup:
                continue
            if hit.match["by"] == "name_in_query":
                coverage.extend(hit.covered_spans)
            if hit.id not in hits or hit.sort_key < hits[hit.id].sort_key:
                hits[hit.id] = hit
    direct = sorted(hits.values(), key=lambda h: h.sort_key)
    if expand:
        for hit in direct:
            for identity, relation in expansion_targets(
                lookup[hit.id], draft, mappings=mappings
            ):
                if identity in lookup and identity not in hits:
                    hits[identity] = RecallHit(
                        identity,
                        {"by": "expansion", "via": {"id": hit.id, "relation": relation}},
                    )
    ordered = sorted(hits.values(), key=lambda h: h.sort_key)
    items = [
        item_summary(lookup[h.id], h.match, lookup, draft, mappings=mappings, query=query)
        for h in ordered
        if not kinds or lookup[h.id].kind in kinds
    ]
    return items, retrieval, remaining_fragments(query, coverage)


def search_ontology(
    db,
    workspace_id,
    principal,
    options: OntologySearchRequest,
    settings,
    *,
    pinned_version_id=None,
    sources: Sequence[RecallSource] = DEFAULT_SOURCES,
):
    workspace = get_workspace(db, workspace_id)
    version_id = (
        pinned_version_id if pinned_version_id is not None else workspace.current_version_id
    )
    if version_id:
        try:
            snapshot = snapshot_of(current_version(db, workspace_id, version_id))
        except ServiceError as exc:
            if pinned_version_id is None:
                raise
            raise ServiceError(
                "固定发布版已不可用", code="version_unavailable", status_code=404
            ) from exc
    else:
        snapshot = empty_snapshot(workspace_id)
    context = [
        workspace_id,
        version_id or None,
        "search_ontology",
        options.model_dump(mode="json", exclude={"cursor"}),
        authorization_fingerprint(db, workspace_id, principal),
    ]
    offset, section = decode_cursor(settings, options.cursor, context)
    if options.cursor:
        mode = section.get("retrieval") if isinstance(section, dict) else None
        if (
            not isinstance(section, dict)
            or section.get("kind") != "ontology_search"
            or not isinstance(mode, dict)
            or set(mode) != {"keyword", "vector"}
            or any(type(value) is not bool for value in mode.values())
            or any(
                enabled and not any(source.name == name for source in sources)
                for name, enabled in mode.items()
            )
        ):
            raise ServiceError(
                "游标召回方式无效或已不可用", code="INVALID_CURSOR", status_code=422
            )
        sources = tuple(source for source in sources if mode[source.name])
    items, retrieval, unmatched = retrieve(
        options.query,
        CoreDraft.model_validate(snapshot),
        mappings=can_read_mappings(db, workspace_id, principal),
        kinds=options.kinds,
        expand=options.expand,
        sources=sources,
    )
    page = []
    for item in items[offset : offset + options.limit]:
        if page and len(json.dumps([*page, item], ensure_ascii=False).encode()) > 55_000:
            break
        page.append(item)
    end = offset + len(page)
    cursor = (
        encode_cursor(
            settings, context, end, {"kind": "ontology_search", "retrieval": retrieval}
        )
        if end < len(items)
        else None
    )
    response = {
        "workspace_id": workspace_id,
        "version_id": version_id or None,
        "items": page,
        "total": len(items),
        "next_cursor": cursor,
        "retrieval": retrieval,
        "unmatched_terms": unmatched,
    }
    # Both text and structuredContent appear on the MCP wire.
    if len(json.dumps(response, ensure_ascii=False).encode()) > 120_000:
        raise ServiceError(
            "当前投影超过单页预算，请缩小 limit", code="response_too_large", status_code=422
        )
    return OntologySearchRead.model_validate(response).model_dump(
        mode="json", exclude_unset=True
    )
