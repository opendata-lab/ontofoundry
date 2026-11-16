"""Why a pending proposal cannot be accepted as it stands (AC-05).

Derived on every batch read from the same checks acceptance runs, against the
candidate with all pending proposals applied, and never stored.
"""

from __future__ import annotations

from ontofoundry_api.domain.accept_checks import (
    Change,
    definition_issues,
    link_count_issues,
)
from ontofoundry_api.domain.core import MaterialObject
from ontofoundry_api.domain.graph import read_only_index
from ontofoundry_api.domain.instances import definitions, instance_value_errors
from ontofoundry_api.domain.models import OntologyDraft


class AcceptanceIssues:
    def __init__(self, candidate: dict, stored: dict, items: list):
        """`candidate`: definitions with pending proposals applied; `stored`: the
        session snapshot with its instances; `items`: this batch's proposals."""
        self._candidate, self._stored, self._items = candidate, stored, items
        self._model, self._built = None, False
        self._instances = None

    def _draft(self):
        if not self._built:
            self._built = True
            try:
                self._model = read_only_index(OntologyDraft.model_validate(definitions(self._candidate)))
            except ValueError:
                self._model = None  # the batch's own diagnostics report an invalid candidate
        return self._model

    def _instance_graph(self):
        """Stored instances with this batch's pending changes applied, as accept would."""
        if self._instances is None:
            graph = {
                kind: {str(e["id"]): e for e in self._stored.get(collection) or []}
                for kind, collection in (("material_object", "material_objects"), ("material_link", "material_links"))
            }
            for item in self._items:
                if item.status != "pending" or item.target_kind not in graph:
                    continue
                if item.after_json is None:
                    graph[item.target_kind].pop(str(item.target_id), None)
                else:
                    graph[item.target_kind][str(item.target_id)] = item.after_json
            objects = graph["material_object"]
            links = [
                link for link in graph["material_link"].values()
                if str(link["source_id"]) in objects and str(link["target_id"]) in objects
            ]
            self._instances = (objects, links)
        return self._instances

    def __call__(self, item) -> list[str]:
        if item.status != "pending":
            return []
        if item.after_json is None and item.target_kind in ("material_object", "material_link"):
            return []  # deleting an instance never needs completing
        model = self._draft()
        if model is None:
            return []
        try:
            if item.target_kind == "material_object":
                return instance_value_errors(model, MaterialObject.model_validate(item.after_json), strict=True)
            if item.target_kind == "material_link":
                objects, links = self._instance_graph()
                return link_count_issues(model, objects, links, {item.target_id})
            return definition_issues(
                model, [Change(item.target_kind, item.target_id, item.after_json, item.before_json)]
            )
        except (ValueError, KeyError):
            return []
