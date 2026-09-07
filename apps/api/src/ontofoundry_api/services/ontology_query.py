from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy.orm import Session

from ontofoundry_api.db_models import OntologyVersionRecord

from .errors import NotFoundError
from .workspaces import get_workspace


def current_version(session: Session, workspace_id: str) -> OntologyVersionRecord:
    workspace = get_workspace(session, workspace_id)
    if not workspace.current_version_id:
        raise NotFoundError("该工作空间还没有已发布版本")
    version = session.get(OntologyVersionRecord, workspace.current_version_id)
    if version is None:
        raise NotFoundError("工作空间当前版本记录不存在")
    return version


def version_summary(version: OntologyVersionRecord) -> dict[str, Any]:
    snapshot = version.snapshot_json
    attributes = sum(
        len(item.get("attributes", [])) for item in snapshot.get("object_types", [])
    )
    return {
        "workspace_id": version.workspace_id,
        "version_id": version.id,
        "version": version.version_number,
        "version_sha256": version.sha256,
        "status": version.status,
        "message": version.message,
        "published_at": version.created_at,
        "validation": version.validation_json,
        "counts": {
            "object_types": len(snapshot.get("object_types", [])),
            "link_types": len(snapshot.get("link_types", [])),
            "attributes": attributes,
        },
    }


def workspace_overview(version: OntologyVersionRecord, *, include_private: bool) -> dict:
    """A bounded projection of one published snapshot; never query source databases."""
    result = {
        "version": version_summary(version),
        "graph": type_graph(version),
        "details": None,
    }
    if not include_private:
        return result
    snapshot = version.snapshot_json
    objects = snapshot.get("objects", [])
    links = snapshot.get("links", [])
    mappings = snapshot.get("mappings", [])
    sample_objects = [
        {key: item[key] for key in ("id", "name", "type_id")} for item in objects[:24]
    ]
    sample_ids = {item["id"] for item in sample_objects}
    material_ids = {
        evidence["material_id"]
        for item in [*objects, *links]
        for evidence in item.get("evidence", [])
    }
    result["details"] = {
        "object_count": len(objects),
        "link_count": len(links),
        "evidence_material_count": len(material_ids),
        "mapping_count": len(mappings),
        "objects": sample_objects,
        "links": [
            {key: item[key] for key in ("id", "type_id", "source_id", "target_id")}
            for item in links
            if item["source_id"] in sample_ids and item["target_id"] in sample_ids
        ][:48],
        "mappings": [
            {key: item[key] for key in ("id", "type_id", "table_name")}
            for item in mappings[:24]
        ],
    }
    return result


def _supertypes(type_id: str, by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Ancestors closest first; consumers should not have to walk `extends`."""
    ordered: list[dict[str, Any]] = []
    seen: set[str] = {type_id}
    frontier = list(by_id.get(type_id, {}).get("extends", []))
    while frontier:
        parent_id = str(frontier.pop(0))
        if parent_id in seen or parent_id not in by_id:
            continue
        seen.add(parent_id)
        ordered.append(by_id[parent_id])
        frontier.extend(by_id[parent_id].get("extends", []))
    return ordered


def _type_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {str(item["id"]): item for item in snapshot.get("object_types", [])}
    objects = []
    for item in snapshot.get("object_types", []):
        supertypes = _supertypes(str(item["id"]), by_id)
        inherited = [
            {**attribute, "declared_by": parent["id"]}
            for parent in supertypes
            for attribute in parent.get("attributes", [])
        ]
        objects.append(
            {
                **item,
                "kind": "object_type",
                "supertypes": [
                    {key: parent[key] for key in ("id", "name", "technical_name")}
                    for parent in supertypes
                ],
                "inherited_attributes": inherited,
                "attribute_count": len(item.get("attributes", [])) + len(inherited),
            }
        )
    links = [
        {
            **{key: value for key, value in item.items() if key != "data_join"},
            "kind": "link_type",
            "attribute_count": 0,
        }
        for item in snapshot.get("link_types", [])
    ]
    return objects + links


def search_types(
    version: OntologyVersionRecord,
    *,
    query: str = "",
    kind: str | None = None,
) -> dict[str, Any]:
    normalized_query = query.strip().casefold()
    items = _type_items(version.snapshot_json)
    if kind:
        items = [item for item in items if item["kind"] == kind]
    if normalized_query:
        items = [
            item
            for item in items
            if normalized_query
            in " ".join(
                [
                    item.get("name", ""),
                    item.get("technical_name", ""),
                    item.get("description", ""),
                    " ".join(item.get("tags", [])),
                ]
            ).casefold()
        ]
    items.sort(key=lambda item: (item["kind"], item["technical_name"].casefold()))
    return {
        "workspace_id": version.workspace_id,
        "version_id": version.id,
        "version_sha256": version.sha256,
        "items": items,
        "next_cursor": None,
    }


def get_type(version: OntologyVersionRecord, type_id: str) -> dict[str, Any]:
    for item in _type_items(version.snapshot_json):
        if item["id"] == type_id or item["technical_name"] == type_id:
            return {
                "workspace_id": version.workspace_id,
                "version_id": version.id,
                "version_sha256": version.sha256,
                "item": item,
            }
    raise NotFoundError("没有找到该本体类型")


def _all_graph(snapshot: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for object_type in snapshot.get("object_types", []):
        nodes.append(
            {
                "id": object_type["id"],
                "kind": "object_type",
                "label": object_type["name"],
                "technical_name": object_type["technical_name"],
                "description": object_type.get("description", ""),
                "tags": object_type.get("tags", []),
                "attribute_count": len(object_type.get("attributes", [])),
            }
        )
        for attribute in object_type.get("attributes", []):
            value_id = f"value:{attribute['id']}"
            nodes.append(
                {
                    "id": value_id,
                    "kind": "value_type",
                    "label": attribute["name"],
                    "technical_name": (
                        f"{object_type['technical_name']}_{attribute['technical_name']}_value"
                    ),
                    "description": attribute.get("description", ""),
                    "tags": [],
                    "value_kind": attribute["value_kind"],
                    "identifier": attribute["identifier"],
                }
            )
            edges.append(
                {
                    "id": f"attribute:{attribute['id']}",
                    "kind": "attribute",
                    "label": attribute["name"],
                    "technical_name": attribute["technical_name"],
                    "source": object_type["id"],
                    "target": value_id,
                }
            )
        # Inheritance is part of the picture: a subtype points at its supertypes.
        for parent in object_type.get("extends", []):
            edges.append(
                {
                    "id": f"extends:{object_type['id']}:{parent}",
                    "kind": "extends",
                    "label": "继承",
                    "technical_name": "extends",
                    "source": object_type["id"],
                    "target": parent,
                    "description": f"{object_type['name']} 继承自上级业务对象",
                }
            )
    for link in snapshot.get("link_types", []):
        edges.append(
            {
                "id": link["id"],
                "kind": "link_type",
                "label": link["name"],
                "technical_name": link["technical_name"],
                "source": link["source_type_id"],
                "target": link["target_type_id"],
                "multiplicity": link["multiplicity"],
                "description": link.get("description", ""),
                "tags": link.get("tags", []),
                "identifier": link.get("identifier", False),
            }
        )
    return nodes, edges


def type_graph(
    version: OntologyVersionRecord,
    *,
    focus_id: str | None = None,
    depth: int = 1,
) -> dict[str, Any]:
    nodes, edges = _all_graph(version.snapshot_json)
    if focus_id:
        neighbors: dict[str, set[str]] = {}
        for edge in edges:
            neighbors.setdefault(edge["source"], set()).add(edge["target"])
            neighbors.setdefault(edge["target"], set()).add(edge["source"])
        visible = {focus_id}
        queue = deque([(focus_id, 0)])
        while queue:
            node_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for neighbor in neighbors.get(node_id, set()):
                if neighbor not in visible:
                    visible.add(neighbor)
                    queue.append((neighbor, current_depth + 1))
        nodes = [node for node in nodes if node["id"] in visible]
        edges = [
            edge
            for edge in edges
            if edge["source"] in visible and edge["target"] in visible
        ]
    return {
        "workspace_id": version.workspace_id,
        "version_id": version.id,
        "version_sha256": version.sha256,
        "nodes": nodes,
        "edges": edges,
    }
