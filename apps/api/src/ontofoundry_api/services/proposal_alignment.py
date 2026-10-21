"""Review hints derived on read: similar existing definitions and physical differences (AR-01–AR-04)."""

from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.services.ontology_search import KeywordRecall, visible_elements

SIMILAR_KINDS = {"object_type", "property", "link_type", "metric"}
SIMILAR_LIMIT = 5


class AlignmentContext:
    """Built once per batch read; nothing here is stored."""

    def __init__(self, db, workspace_id, draft: dict):
        self.db = db
        self.workspace_id = workspace_id
        self.draft = draft
        self._elements = None
        self._snapshots = {}

    def elements(self):
        if self._elements is None:
            try:
                model = CoreDraft.model_validate(self.draft)
            except ValueError:
                # An invalid candidate graph still shows its proposals, just without hints.
                self._elements = []
            else:
                self._elements = visible_elements(model, mappings=False)
        return self._elements

    def similar_definitions(self, item) -> list[dict]:
        after = item.after_json or {}
        if item.operation != "create" or item.target_kind not in SIMILAR_KINDS or not after:
            return []
        candidates = [
            e for e in self.elements() if e.kind == item.target_kind and e.id != str(item.target_id)
        ]
        queries = [after.get("display_name"), after.get("name"), *(after.get("synonyms") or [])]
        best = {}
        for query in filter(None, queries):
            for hit in KeywordRecall().recall(query, candidates):
                if hit.id not in best or hit.sort_key < best[hit.id].sort_key:
                    best[hit.id] = hit
        by_id = {e.id: e for e in candidates}
        return [
            {
                "id": hit.id,
                "kind": item.target_kind,
                "display_name": by_id[hit.id].definition.get("display_name"),
                "name": by_id[hit.id].definition["name"],
                "match": hit.match,
            }
            for hit in sorted(best.values(), key=lambda h: h.sort_key)[:SIMILAR_LIMIT]
        ]

    def physical_differences(self, item, elements: dict[str, tuple[str, dict]]) -> list[dict]:
        after = item.after_json or {}
        if item.target_kind != "property" or item.operation == "delete" or not after.get("required"):
            return []
        mappings = [e for kind, e in elements.values() if kind == "mapping" and e.get("type_id") == after.get("owner_type_id")]
        result = []
        for mapping in mappings:
            binding = (mapping.get("fields") or {}).get(after.get("name"))
            if not binding or binding.get("kind") != "column":
                continue
            source = next((s for s in mapping.get("sources") or [] if s.get("id") == binding.get("source_id")), None)
            dataset = elements.get(str(source["dataset_id"])) if source else None
            if not dataset or dataset[0] != "dataset":
                continue
            column = self._column(dataset[1], binding["column"])
            if column and column.get("nullable"):
                result.append({"path": "required", "declared": "required", "observed": "nullable", **column["where"]})
        return result

    def _column(self, dataset: dict, name: str):
        if not dataset.get("connection_id") or not dataset.get("table_name"):
            return None
        connection = self.db.get(ConnectionRecord, dataset["connection_id"])
        if connection is None or connection.workspace_id != self.workspace_id:
            return None
        from ontofoundry_api.services.metadata_sync import normalize_schema

        schema = normalize_schema(connection, dataset.get("schema_name") or "")
        key = (connection.id, schema)
        if key not in self._snapshots:
            record = self.db.get(MetadataSnapshotRecord, key)
            self._snapshots[key] = record.snapshot_json.get("tables", []) if record else []
        table = next((t for t in self._snapshots[key] if t["name"] == dataset["table_name"] and not t.get("missing")), None)
        column = next((c for c in (table or {}).get("columns", []) if c["name"] == name), None)
        if column is None:
            return None
        return {
            "nullable": column.get("nullable"),
            "where": {
                "column": name,
                "table": table["name"],
                "schema": schema or None,
                "connection_name": connection.name,
                "observed_at": table.get("observed_at"),
            },
        }
