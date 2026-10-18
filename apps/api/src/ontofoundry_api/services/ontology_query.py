"""Core-1 resource projections shared by REST and MCP."""

from copy import deepcopy
from datetime import UTC

from ontofoundry_api.db_models import OntologyVersionRecord
from ontofoundry_api.domain.bindings import binding_readiness, resolve_binding
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.instance_display import document_display_text
from ontofoundry_api.domain.snapshot import read_snapshot_json
from ontofoundry_api.services.errors import NotFoundError
from ontofoundry_api.services.workspaces import get_workspace


def current_version(session, workspace_id, version_id=None):
    workspace = get_workspace(session, workspace_id)
    version = (
        session.get(OntologyVersionRecord, version_id or workspace.current_version_id)
        if version_id or workspace.current_version_id
        else None
    )
    if (
        version is None
        or version.workspace_id != workspace_id
        or version.status != "published"
    ):
        raise NotFoundError("该空间的已发布版本不存在")
    return version


def snapshot_of(version):
    return read_snapshot_json(version.snapshot_json, version.workspace_id)


def version_hashes(version):
    return {
        "version_sha256": version.sha256,
        "version_content_sha256": version.sha256,
        "normalized_snapshot_sha256": snapshot_sha256(snapshot_of(version)),
    }


def envelope(version):
    return {
        "workspace_id": version.workspace_id,
        "version_id": version.id,
        **version_hashes(version),
    }


def version_summary(version, *, include_mappings=True, include_instances=True):
    snapshot = snapshot_of(version)
    counts = {
        "object_types": len(snapshot["object_types"]),
        "link_types": len(snapshot["link_types"]),
        "attributes": len(snapshot["properties"]),
        "rules": len(snapshot["rules"]),
        "metrics": len(snapshot["metrics"]),
    }
    if include_mappings:
        counts.update(
            datasets=len(snapshot["datasets"]), mappings=len(snapshot["mappings"])
        )
    if include_instances:
        counts.update(
            material_objects=len(snapshot["material_objects"]),
            material_links=len(snapshot["material_links"]),
        )
    return {
        **envelope(version),
        "version": version.version_number,
        "status": version.status,
        "message": version.message,
        "published_at": version.created_at
        if version.created_at.tzinfo
        else version.created_at.replace(tzinfo=UTC),
        "validation": version.validation_json,
        "counts": counts,
    }


def binding_status(draft, type_id, db=None, workspace_id=None):
    status = binding_readiness(draft, type_id).status
    if db is not None:
        from ontofoundry_api.services.dataset_sources import resolve_dataset
        from ontofoundry_api.services.errors import ServiceError

        binding = resolve_binding(draft, type_id)
        sources = []
        for source in binding.sources.values():
            try:
                sources.append(
                    resolve_dataset(
                        db, workspace_id, DraftIndex(draft).datasets[source.dataset_id]
                    )
                )
            except ServiceError:
                return "unbound"
        if len({s.connection.id for s in sources}) > 1:
            return "cross_connection"
    return status


def resource_items(snapshot, *, mappings=True, instances=True, db=None, workspace_id=None):
    draft = CoreDraft.model_validate(snapshot)
    index = DraftIndex(draft)

    def project(value):
        if isinstance(value, dict):
            return {
                key: project(entry)
                for key, entry in value.items()
                if instances or key != "evidence"
            }
        if isinstance(value, list):
            return [project(entry) for entry in value]
        return value

    def dump(item):
        return project(item.model_dump(mode="json"))

    items = []
    for obj in draft.object_types:
        status = (
            binding_status(draft, obj.id, db, workspace_id) if mappings else "forbidden"
        )
        binding = resolve_binding(draft, obj.id)
        properties = []
        for prop in index.effective_properties(obj.id):
            p = {
                **dump(prop),
                "inherited_from": str(prop.owner_type_id)
                if prop.owner_type_id != obj.id
                else None,
                "binding_status": status,
            }
            if mappings and prop.technical_name in binding.fields:
                b = binding.fields[prop.technical_name]
                p["binding"] = b.model_dump(mode="json")
                if b.kind == "column":
                    ds = index.datasets[binding.sources[b.source_id].dataset_id]
                    p["physical_type"] = next(
                        (c.physical_type for c in ds.columns or [] if c.name == b.column),
                        None,
                    )
            properties.append(p)
        links = []
        for link in index.effective_links(obj.id):
            forward = index.is_a(obj.id, link.source_type_id)
            owner = link.source_type_id if forward else link.target_type_id
            link_view = {
                **dump(link),
                "direction": "forward" if forward else "reverse",
                "inherited_from": str(owner) if owner != obj.id else None,
                "binding_status": status,
            }
            if mappings:
                effective_join = binding.link_bindings.get(link.id, link.data_join)
                link_view["data_join"] = (
                    effective_join.model_dump(mode="json") if effective_join else None
                )
            else:
                link_view.pop("data_join", None)
            links.append(link_view)
        definition = {
            **dump(obj),
            "properties": properties,
            "links": links,
            "rules": [
                {
                    **dump(r),
                    "inherited_from": str(r.owner_id) if r.owner_id != obj.id else None,
                    "binding_status": status,
                }
                for r in index.effective_rules(obj.id)
            ],
            "child_types": [
                {"id": str(o.id), "name": o.name, "technical_name": o.technical_name}
                for o in index.children(obj.id)
            ],
            "binding_status": status,
        }
        if mappings:
            local = next((m for m in draft.mappings if m.type_id == obj.id), None)
            definition["mapping"] = (
                {**dump(local), "binding_status": status} if local else None
            )
            definition["instance_source_type_ids"] = [str(i) for i in binding.virtual_types]
        items.append({"kind": "object_type", "definition": definition})
    for link in draft.link_types:
        definition = {
            **dump(link),
            "direction": "forward",
            "inherited_from": None,
            "binding_status": "bound" if link.data_join else "unbound",
        }
        if not mappings:
            definition.pop("data_join", None)
            definition["binding_status"] = "forbidden"
        items.append({"kind": "link_type", "definition": definition})
    from ontofoundry_api.services.metric_query import metric_projection

    for metric in draft.metrics:
        if mappings:
            definition = metric_projection(draft, metric, db=db, workspace_id=workspace_id)
            definition = project(definition)
        else:
            definition = {
                k: v
                for k, v in dump(metric).items()
                if k in {"id", "name", "technical_name", "description", "synonyms"}
            }
            definition["binding_status"] = "forbidden"
        items.append({"kind": "metric", "definition": definition})
    if mappings:
        for dataset in draft.datasets:
            if db is not None:
                from ontofoundry_api.services.dataset_sources import (
                    authorized_dataset_projection,
                )

                definition = authorized_dataset_projection(db, workspace_id, dataset)
            else:
                definition = {**dump(dataset), "binding_status": "unbound"}
            items.append({"kind": "dataset", "definition": definition})
    return items


def search_types(
    version,
    *,
    query="",
    kind=None,
    include_context_elements=True,
    include_document_context=False,
    include_instances=True,
    db=None,
):
    items = resource_items(
        snapshot_of(version),
        mappings=include_context_elements,
        instances=include_instances,
        db=db,
        workspace_id=version.workspace_id,
    )
    query = query.casefold()
    items = [
        item
        for item in items
        if (kind is None or item["kind"] == kind)
        and (
            not query
            or any(
                query in str(item["definition"].get(k, "")).casefold()
                for k in ("name", "technical_name", "description", "synonyms")
            )
        )
    ]
    return {**envelope(version), "items": items, "next_cursor": None, "ambiguous": False}


def get_type(
    version,
    type_id,
    *,
    include_context_elements=True,
    include_document_context=False,
    include_instances=True,
    db=None,
):
    items = search_types(
        version,
        include_context_elements=include_context_elements,
        include_instances=include_instances,
        db=db,
    )["items"]
    found = [i for i in items if i["definition"]["id"] == type_id]
    if not found:
        found = [
            i
            for i in items
            if i["definition"].get("technical_name", "").casefold() == type_id.casefold()
        ]
    if not found:
        raise NotFoundError("没有找到该资源")
    return {
        **envelope(version),
        "ambiguous": len(found) > 1,
        "item": found[0] if len(found) == 1 else None,
        **({"candidates": found} if len(found) > 1 else {}),
    }


def _all_graph(snapshot):
    nodes = [
        {
            "id": o["id"],
            "kind": "object_type",
            "label": o["name"],
            "technical_name": o["technical_name"],
            "description": o["description"],
            "tags": o["tags"],
        }
        for o in snapshot["object_types"]
    ]
    edges = [
        {
            "id": link_view["id"],
            "kind": "link_type",
            "link_type_id": link_view["id"],
            "label": link_view["name"],
            "technical_name": link_view["technical_name"],
            "source": link_view["source_type_id"],
            "target": link_view["target_type_id"],
            "multiplicity": link_view["multiplicity"],
            "description": link_view["description"],
            "tags": link_view["tags"],
        }
        for link_view in snapshot["link_types"]
    ]
    edges.extend(
        {
            "id": "extends:" + o["id"],
            "kind": "extends",
            "label": "继承",
            "technical_name": "extends",
            "source": o["id"],
            "target": o["extends"],
        }
        for o in snapshot["object_types"]
        if o["extends"]
    )
    return nodes, edges


def _query_view(snapshot):
    return deepcopy(snapshot)


def query_view(version):
    return snapshot_of(version)


def type_graph(version, *, focus_id=None, depth=1):
    nodes, edges = _all_graph(snapshot_of(version))
    if focus_id:
        selected = {focus_id}
        for _ in range(depth):
            selected |= {
                e[k]
                for e in edges
                if e["source"] in selected or e["target"] in selected
                for k in ("source", "target")
            }
        nodes = [n for n in nodes if n["id"] in selected]
        edges = [e for e in edges if e["source"] in selected and e["target"] in selected]
    return {**envelope(version), "nodes": nodes, "edges": edges}


def workspace_overview(
    version, *, include_private=False, include_mappings=None, include_instances=None
):
    if version is None:
        return {"version": None, "graph": None, "details": None}
    mappings = include_private if include_mappings is None else include_mappings
    instances = include_private if include_instances is None else include_instances
    snapshot = snapshot_of(version)
    details = {}
    if mappings:
        details.update(
            mapping_count=len(snapshot["mappings"]),
            mappings=[
                {"id": m["id"], "type_id": m["type_id"], "binding_status": "unbound"}
                for m in snapshot["mappings"][:24]
            ],
        )
    if instances:
        draft = CoreDraft.model_validate(snapshot)
        details.update(
            object_count=len(draft.material_objects),
            link_count=len(draft.material_links),
            evidence_material_count=len(
                {
                    e.material_id
                    for f in [*draft.material_objects, *draft.material_links]
                    for e in f.evidence
                    if e.kind == "material"
                }
            ),
            objects=[
                {
                    "id": str(f.id),
                    "type_id": str(f.type_id),
                    "display_text": document_display_text(draft, f),
                }
                for f in draft.material_objects[:24]
            ],
            links=[
                {
                    k: v
                    for k, v in f.model_dump(mode="json").items()
                    if k in {"id", "type_id", "source_id", "target_id"}
                }
                for f in draft.material_links[:48]
            ],
        )
    return {
        "version": version_summary(
            version, include_mappings=mappings, include_instances=instances
        ),
        "graph": type_graph(version),
        "details": details or None,
    }
