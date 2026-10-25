"""Small authorized catalog pages and explicitly incomplete inspector projections."""

from contextlib import suppress
from uuid import UUID

from ontofoundry_api.domain.bindings import resolve_binding
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services.access import (
    authorization_fingerprint,
    can_read_instances,
    can_read_mappings,
)
from ontofoundry_api.services.cursors import decode_cursor, encode_cursor
from ontofoundry_api.services.errors import NotFoundError
from ontofoundry_api.services.ontology_query import (
    envelope,
    read_context,
)
from ontofoundry_api.services.public_projection import authorized_snapshot

RESOURCE_KINDS = {"object_type", "link_type", "metric", "dataset"}
COLLECTIONS = {
    "object_type": "object_types",
    "link_type": "link_types",
    "property": "properties",
    "rule": "rules",
    "metric": "metrics",
    "dataset": "datasets",
    "mapping": "mappings",
    "value_type": "value_types",
}


def catalog_page(
    db, version, principal, settings, *, kind=None, q="", tag=None, limit=20, cursor=None
):
    context = read_context(version)
    index, draft = context.index, context.draft
    mappings = can_read_mappings(db, version.workspace_id, principal)
    instances_readable = can_read_instances(db, version.workspace_id, principal)
    permission = authorization_fingerprint(db, version.workspace_id, principal)
    identity = [
        str(version.workspace_id),
        str(version.id),
        permission,
        "catalog-1",
        kind,
        q,
        tag,
        limit,
    ]
    offset, _ = decode_cursor(settings, cursor, identity)
    visible = [
        (k, e)
        for k, e in index.elements.values()
        if k in RESOURCE_KINDS and (mappings or k != "dataset")
    ]
    counts = {
        name: len(getattr(draft, collection))
        for name, collection in (
            ("object_types", "object_types"),
            ("link_types", "link_types"),
            ("metrics", "metrics"),
            ("value_types", "value_types"),
            ("datasets", "datasets"),
        )
    }
    if not mappings:
        counts["datasets"] = 0
    options = sorted(
        {t for k, e in visible if kind is None or k == kind for t in getattr(e, "tags", [])}
    )

    def matches(k, e):
        text = " ".join(
            str(getattr(e, f, ""))
            for f in (
                "name",
                "display_name",
                "description",
                "synonyms",
                "verbalizes",
                "source_role_name",
                "target_role_name",
            )
        )
        return (
            (kind is None or k == kind)
            and (not tag or tag in getattr(e, "tags", []))
            and q.casefold() in text.casefold()
        )

    selected = sorted(
        ((k, e) for k, e in visible if matches(k, e)),
        key=lambda pair: (pair[0], pair[1].name, str(pair[1].id)),
    )

    def reference(identity):
        item = index.elements.get(identity)
        if item is None:
            return None
        e = item[1]
        return {
            "id": str(e.id),
            "name": e.name,
            "display_name": getattr(e, "display_name", None),
        }

    # Instance counts are independent live data; only a page's authorized counts are returned.
    document_counts = {}
    if db is not None and instances_readable:
        from ontofoundry_api.services.instance_store import visible as instances

        for entry in instances(db, version.workspace_id, draft)["objects"]:
            owner = UUID(entry["element"]["type_id"])
            for ancestor in index.lineage(owner):
                document_counts[ancestor] = document_counts.get(ancestor, 0) + 1
    items = []
    for k, e in selected[offset : offset + limit]:
        item = {
            "id": str(e.id),
            "kind": k,
            "name": e.name,
            "display_name": getattr(e, "display_name", None),
            "description": e.description,
            "tags": getattr(e, "tags", []),
        }
        if k == "object_type":
            binding = resolve_binding(draft, e.id)
            props = index.effective_properties(e.id)
            covered = sum(prop.name in binding.fields for prop in props) if mappings else 0
            state = (
                "unmapped"
                if not covered
                else "mapped"
                if covered == len(props)
                else "partial"
            )
            virtual = not binding.mappings and bool(binding.virtual_types)
            label = (
                "虚拟父对象，实例来自子对象"
                if virtual
                else "未绑定数据集"
                if not binding.mappings
                else "已映射"
                if state == "mapped"
                else f"已映射 {covered}/{len(props)} 个属性"
                if state == "partial"
                else "未映射属性"
            )
            if not mappings:
                label = "未绑定数据集"
            item.update(
                parent=reference(e.extends),
                property_count=len(index.effective_properties(e.id)),
                link_count=len(index.effective_links(e.id)),
                document_instance_count=document_counts.get(e.id, 0)
                if instances_readable
                else None,
                mapping_state=state,
                mapping_label=label,
            )
        elif k == "link_type":
            item.update(
                source=reference(e.source_type_id),
                target=reference(e.target_type_id),
                multiplicity=e.multiplicity,
                verbalizes=e.verbalizes,
                source_role_name=e.source_role_name,
                target_role_name=e.target_role_name,
            )
        elif k == "dataset":
            item.update(
                source_kind=e.source_kind,
                column_count=len(e.columns) if e.columns is not None else None,
            )
        elif k == "metric":
            from ontofoundry_api.services.metric_query import dataset_for

            ds = dataset_for(draft, e) if mappings else None
            item.update(metric_kind=e.kind, dataset_name=ds.name if ds else None)
        items.append(item)
    end = offset + len(items)
    return {
        **envelope(version),
        "items": items,
        "counts": counts,
        "tags": options,
        "total": len(selected),
        "next_cursor": encode_cursor(settings, identity, end)
        if end < len(selected)
        else None,
    }


def element_projection(version, kind, identity, *, mappings, instances):
    """Return a target's definitions and reference closure, never a save baseline."""
    context = read_context(version)
    index, draft = context.index, context.draft
    try:
        identity = UUID(identity)
    except ValueError as exc:
        raise NotFoundError("没有找到该元素") from exc
    located = index.elements.get(identity)
    if (
        located is None
        or located[0] != kind
        or (kind in {"dataset", "mapping"} and not mappings)
    ):
        raise NotFoundError("没有找到该元素")
    focus = identity
    if kind == "property":
        focus = located[1].owner_type_id
    if kind == "mapping":
        focus = located[1].type_id
    if kind == "rule":
        focus = located[1].owner_id
        if focus in index.properties:
            focus = index.properties[focus].owner_type_id
    selected = {identity, focus}
    object_ids = set()

    def descendants(type_id):
        seen, pending = {type_id}, [type_id]
        while pending:
            for child in index.children(pending.pop()):
                if child.id not in seen:
                    seen.add(child.id)
                    pending.append(child.id)
        return seen

    if focus in index.objects:
        focus_types = descendants(focus)
        object_ids.update(focus_types)
        for owner in focus_types:
            selected.update(link.id for link in index.effective_links(owner))
    if focus in index.links:
        selected.add(focus)
    for link_id in list(selected):
        link = index.links.get(link_id)
        if link:
            object_ids.update(descendants(link.source_type_id))
            object_ids.update(descendants(link.target_type_id))
    for type_id in list(object_ids):
        object_ids.update(index.lineage(type_id))
    selected.update(object_ids)
    for type_id in object_ids:
        selected.update(p.id for p in index.effective_properties(type_id))
        selected.update(r.id for r in index.effective_rules(type_id))
        selected.update(m.id for m in resolve_binding(draft, type_id).mappings)
    # Dataset details list every definition that references that dataset.
    if kind == "dataset":
        for e in [*draft.mappings, *draft.link_types, *draft.metrics]:
            if str(identity) in e.model_dump_json():
                selected.add(e.id)
                if hasattr(e, "type_id"):
                    selected.add(e.type_id)

    # Follow explicit UUID references once. This does not expand neighbors' adjacency.
    def references(value):
        if isinstance(value, dict):
            for entry in value.values():
                yield from references(entry)
        elif isinstance(value, list):
            for entry in value:
                yield from references(entry)
        elif isinstance(value, str):
            with suppress(ValueError):
                yield UUID(value)

    pending = list(selected)
    while pending:
        element = index.elements.get(pending.pop())
        if element is None:
            continue
        for ref in references(element[1].model_dump(mode="json")):
            if ref in index.elements and ref not in selected:
                selected.add(ref)
                pending.append(ref)
    selected.update(rule.id for rule in draft.rules if rule.owner_id in selected)
    model = empty_snapshot(version.workspace_id)
    for item_id in selected:
        element = index.elements.get(item_id)
        if element:
            item_kind, e = element
            model[COLLECTIONS[item_kind]].append(e.model_dump(mode="json"))
    # Stable ordering keeps inherited/property table order identical to full definitions.
    for collection in COLLECTIONS.values():
        order = {str(e.id): n for n, e in enumerate(getattr(draft, collection))}
        model[collection].sort(key=lambda e: order[e["id"]])
    return {
        **envelope(version),
        "representation": "element-1",
        "complete": False,
        "model": authorized_snapshot(model, mappings=mappings, instances=instances),
    }


def document_context(db, version, kind, identity):
    """Read current document instances against one fixed definition, scoped to a target."""
    from ontofoundry_api.services.instance_store import visible

    context = read_context(version)
    index = context.index
    try:
        identity = UUID(identity)
    except ValueError as exc:
        raise NotFoundError("没有找到该元素") from exc
    if identity not in index.elements or index.elements[identity][0] != kind:
        raise NotFoundError("没有找到该元素")
    stored = visible(db, version.workspace_id, context.draft)
    objects = {UUID(item["element"]["id"]): item["element"] for item in stored["objects"]}
    if kind == "object_type":
        selected = {
            key
            for key, obj in objects.items()
            if index.is_a(UUID(obj["type_id"]), identity)
        }
        links = [
            item["element"]
            for item in stored["links"]
            if UUID(item["element"]["source_id"]) in selected
            or UUID(item["element"]["target_id"]) in selected
        ]
    elif kind == "link_type":
        selected = set()
        links = [
            item["element"]
            for item in stored["links"]
            if UUID(item["element"]["type_id"]) == identity
        ]
    else:
        links, selected = [], set()
    selected.update(
        UUID(link[field]) for link in links for field in ("source_id", "target_id")
    )
    return {
        **envelope(version),
        "material_objects": [obj for key, obj in objects.items() if key in selected],
        "material_links": links,
    }
