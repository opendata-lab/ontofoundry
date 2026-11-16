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
    def __init__(self, candidate: dict, elements: dict):
        """`candidate`: definitions with pending proposals applied; `elements`:
        id → (kind, element) for stored instances and this batch's proposals."""
        self._candidate, self._elements = candidate, elements
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
        if self._instances is None:
            objects = {i: e for i, (k, e) in self._elements.items() if k == "material_object"}
            links = [e for k, e in self._elements.values() if k == "material_link"]
            self._instances = (objects, links)
        return self._instances

    def __call__(self, item) -> list[str]:
        if item.status != "pending" or item.after_json is None:
            return []
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
