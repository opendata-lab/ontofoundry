"""Entity resolution: link a mention to instances of one object type (ER-01–ER-13).

Candidates come from the business database through the existing read-only
instance plan and from live document instances; each is graded here, in
Python, so the agent never matches names in its prompt.
"""

import unicodedata
from uuid import UUID

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.instance_display import document_display_text
from ontofoundry_api.services.errors import NotFoundError, ServiceError

# Rows fetched per source before grading; beyond it uniqueness cannot be shown.
CANDIDATE_CAP = 200
LEVELS = {"identifier_exact": 1, "name_exact": 2, "name_contains": 3}


def normalize(value) -> str:
    """Mechanical normalization only (ER-05): trim, NFKC, lowercase."""
    return unicodedata.normalize("NFKC", str(value)).strip().lower()


def _title_property(index: DraftIndex, type_id: UUID):
    for current in [type_id, *index.ancestors(type_id)]:
        object_type = index.objects.get(current)
        if object_type and object_type.title_property_id:
            return index.properties.get(object_type.title_property_id)
    return None


def _grade(mention: str, values: dict, identifier, title):
    """The best level a candidate's values reach, with the property and value that reached it."""
    target = normalize(mention)
    if identifier is not None and values.get(identifier.name) is not None and normalize(values[identifier.name]) == target:
        return "identifier_exact", identifier, values[identifier.name]
    if title is not None and values.get(title.name) is not None:
        name = normalize(values[title.name])
        if name == target:
            return "name_exact", title, values[title.name]
        if target and target in name:
            return "name_contains", title, values[title.name]
    return None


def resolve_entity(db, workspace_id, draft: CoreDraft, *, mention, object_type_id, limit, settings, mappings_readable):
    index = DraftIndex(draft)
    type_id = UUID(str(object_type_id))
    if type_id not in index.objects:
        raise NotFoundError("实体类型不存在")
    properties = index.effective_properties(type_id)
    identifiers = [p for p in properties if p.identifier]
    # A composite identifier only counts when the whole tuple is given (ER-09);
    # a single mention cannot be one, so it falls back to the name.
    identifier = identifiers[0] if len(identifiers) == 1 else None
    title = _title_property(index, type_id)
    if identifier is None and title is None:
        raise ServiceError(
            "该实体类型没有标题属性或业务标识，无法解析；请先在模型中设置",
            code="NOT_RESOLVABLE",
            status_code=422,
        )

    graded, truncated, sources_skipped = [], False, []
    if mappings_readable and any(m.type_id == type_id for m in draft.mappings):
        from ontofoundry_api.services.instance_plan import query_instances

        rows, seen = [], set()
        # Try the typed and the NFKC form so full-width source values are not missed (ER-12).
        for query in dict.fromkeys([mention.strip(), unicodedata.normalize("NFKC", mention).strip()]):
            result = query_instances(db, workspace_id, draft, type_id, settings, q=query, offset=0, limit=CANDIDATE_CAP)
            truncated = truncated or result["has_more"]
            for row in result["items"]:
                if row["__ref"] not in seen:
                    seen.add(row["__ref"])
                    rows.append(row)
        for row in rows:
            grade = _grade(mention, row["values"], identifier, title)
            if grade:
                graded.append(("database", row["__ref"], row["display_text"], row["values"], grade))
    else:
        sources_skipped.append("database")

    from ontofoundry_api.services.instance_store import visible

    for entry in visible(db, workspace_id, draft)["objects"]:
        element = entry["element"]
        if not index.is_a(UUID(element["type_id"]), type_id):
            continue
        grade = _grade(mention, element.get("values") or {}, identifier, title)
        if grade:
            from ontofoundry_api.domain.core import MaterialObject

            obj = MaterialObject.model_validate(element)
            graded.append(("document", f"doc.{element['id']}", document_display_text(draft, obj), element.get("values") or {}, grade))

    best = min((LEVELS[g[4][0]] for g in graded), default=None)
    top = [g for g in graded if LEVELS[g[4][0]] == best] if best else []
    if not top:
        status = "NOT_FOUND"
    elif len(top) == 1 and not truncated:
        status = "MATCHED"
    else:
        # More rows than were read may reach the same level, so one hit is not proven unique (ER-10).
        status = "AMBIGUOUS"
    top.sort(key=lambda g: (len(str(g[4][2])), g[1]))
    return {
        "mention": mention,
        "object_type_id": str(type_id),
        "status": status,
        "truncated": truncated or len(top) > limit,
        "coverage": "partial" if truncated or sources_skipped else "complete",
        "candidates": [
            {
                "source": source,
                "entity_ref": ref,
                "display": display,
                "match": {"level": level, "property_id": str(prop.id), "value": value},
                "identifiers": {p.name: values.get(p.name) for p in identifiers},
            }
            for source, ref, display, values, (level, prop, value) in top[:limit]
        ],
    }
