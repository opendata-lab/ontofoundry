"""Per-document translation state; only validated additions enter the result."""

from __future__ import annotations

from copy import deepcopy

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.validation import validate_core_graph

from .ids import source_id


class Translation:
    def __init__(self, source, report, invalid_paths=()):
        self.invalid_paths = set(invalid_paths)
        self.source = source
        self.report = report
        self.model = CoreDraft(workspace_id=report.workspace_id)
        self.objects = {}
        self.members = {}
        self.object_paths = {}
        self.property_sources = {}
        self.names = {}
        self.relationship_candidates = {}
        self.ambiguous_links = set()

    def valid(self, path):
        return not any(path == p or path.startswith(p + "/") for p in self.invalid_paths)

    def id(self, key):
        return source_id(self.model.workspace_id, key)

    def issue(
        self,
        path,
        outcome,
        construct,
        rule,
        message,
        *,
        targets=(),
        completion=False,
        severity=None,
    ):
        return self.report.add(
            outcome=outcome,
            construct=construct,
            source_path=path,
            rule_id=rule,
            locator=self.source.locator(path),
            original=self.source.original(path),
            message=message,
            targets=targets,
            completion=completion,
            severity=severity,
        )

    def accept(
        self, collection, item, path, *, rule=None, message="已转换", completion=True
    ):
        candidate = self.model.model_copy(deep=True)
        getattr(candidate, collection).append(item)
        try:
            validate_core_graph(candidate)
        except ValueError as error:
            self.issue(
                path,
                "error",
                collection,
                rule,
                f"不能形成合法核心定义：{error}",
                completion=completion,
            )
            return False
        getattr(self.model, collection).append(item)
        self.issue(path, "converted", collection, rule, message, targets=[item.id])
        return True

    def replace(self, collection, item, path, *, rule=None, message="已转换"):
        candidate = self.model.model_copy(deep=True)
        values = getattr(candidate, collection)
        values[next(i for i, old in enumerate(values) if old.id == item.id)] = item
        try:
            validate_core_graph(candidate)
        except ValueError as error:
            self.issue(
                path,
                "error",
                collection,
                rule,
                f"本条无法完整转换：{error}",
                completion=True,
            )
            return False
        originals = getattr(self.model, collection)
        originals[next(i for i, old in enumerate(originals) if old.id == item.id)] = (
            deepcopy(item)
        )
        if collection == "object_types":
            for name, old in self.objects.items():
                if old.id == item.id:
                    self.objects[name] = originals[
                        next(i for i, old in enumerate(originals) if old.id == item.id)
                    ]
        saved = next(element for element in originals if element.id == item.id)
        for key, old in self.members.items():
            if old.id == item.id:
                self.members[key] = saved
        self.issue(path, "converted", collection, rule, message, targets=[item.id])
        return True

    def finish(self):
        # A child field may have parsed before its owning aggregate was rejected.
        # Never advertise a target that does not exist in the final valid graph.
        from ontofoundry_api.domain.core import COLLECTIONS

        ids = {e.id for name in COLLECTIONS for e in getattr(self.model, name)}
        self.report.issues = [
            i.model_copy(
                update={
                    "outcome": "dropped",
                    "severity": "warning",
                    "target_element_ids": [],
                    "message": i.message + "；所属聚合未通过校验，未写入核心模型",
                }
            )
            if any(target not in ids for target in i.target_element_ids)
            else i
            for i in self.report.issues
        ]
        return self.report.finish(validate_core_graph(self.model))
