"""Which published definitions a synced table structure change touches (SC-01).

Derived on read from the latest recorded changes and the published model;
nothing is stored.
"""

from ontofoundry_api.domain.core import CoreDraft


def _item(kind, element, via):
    return {"kind": kind, "id": str(element.id), "name": element.name, "display_name": element.display_name, "via": via}


def _metric_columns(metric):
    refs = [getattr(metric, "measure", None), getattr(metric, "time_field", None)]
    refs += [f.column for f in getattr(metric, "filters", None) or []]
    return [r for r in refs if r is not None]


def schema_impact(draft: CoreDraft, connection, schema: str, changes: list[dict]):
    from ontofoundry_api.services.dataset_sources import dataset_references
    from ontofoundry_api.services.metadata_sync import normalize_schema

    tables = {}
    for dataset in draft.datasets:
        if (
            dataset.source_kind in (None, "table")
            and str(dataset.connection_id or "") == connection.id
            and normalize_schema(connection, dataset.schema_name or "") == schema
            and dataset.table_name
        ):
            tables.setdefault(dataset.table_name, []).append(dataset)

    items = []
    for change in changes:
        datasets = tables.get(change["table"], [])
        ids = {str(d.id) for d in datasets}
        column = change.get("column")
        affected = {}
        if column:
            for mapping in draft.mappings:
                sources = {s.id for s in mapping.sources if str(s.dataset_id) in ids}
                if not sources:
                    continue
                owner = next((o for o in draft.object_types if o.id == mapping.type_id), None)
                if owner and any(column in s.key_columns for s in mapping.sources if s.id in sources):
                    affected[("object_type", str(owner.id))] = _item("object_type", owner, "column")
                for name, binding in mapping.fields.items():
                    if getattr(binding, "kind", None) == "column" and binding.source_id in sources and binding.column == column:
                        prop = next((p for p in draft.properties if p.owner_type_id == mapping.type_id and p.name == name), None)
                        if prop:
                            affected[("property", str(prop.id))] = _item("property", prop, "column")
            for metric in draft.metrics:
                if any(str(r.dataset_id) in ids and r.column == column for r in _metric_columns(metric)):
                    affected[("metric", str(metric.id))] = _item("metric", metric, "column")
        for dataset in datasets:
            refs = dataset_references(draft, dataset.id)
            for ref in [*refs["object_mappings"], *refs["relationship_mappings"], *refs["metrics"]]:
                affected.setdefault((ref["kind"], ref["id"]), {**ref, "via": "table"})
        items.append(
            {
                "table": change["table"],
                "column": column,
                "kind": change["kind"],
                "before": change.get("before"),
                "after": change.get("after"),
                "datasets": [{"id": str(d.id), "name": d.name} for d in datasets],
                # Column-level references first: they break first.
                "affected": sorted(affected.values(), key=lambda a: (a["via"] != "column", a["kind"], a["name"])),
            }
        )
    return items
