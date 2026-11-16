"""Derive completeness for the dependency/atomic closure an accept would use."""

from ontofoundry_api.services.changes import check_accept
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposal_apply import stored_items
from ontofoundry_api.services.proposals import dependency_group


class AcceptanceIssues:
    def __init__(self, db, session, items, dependencies, settings):
        self._db, self._session, self._settings = db, session, settings
        self._items = {item.id: item for item in items}
        self._dependencies = dependencies
        self._cache = {}

    def __call__(self, item) -> list[str]:
        if item.status != "pending":
            return []
        selected = {item.id}
        while True:
            expanded = set(selected)
            groups = {self._items[i].atomic_group_id for i in selected} - {None}
            expanded.update(i.id for i in self._items.values() if i.atomic_group_id in groups)
            for identity in selected:
                expanded.update(dependency_group(identity, self._dependencies))
            expanded = {i for i in expanded if i in self._items and self._items[i].status != "accepted"}
            if expanded == selected:
                break
            selected = expanded
        key = tuple(sorted(selected))
        if key not in self._cache:
            rows = [self._items[i] for i in key]
            if any(row.status != "pending" for row in rows):
                self._cache[key] = ["依赖提案已拒绝，请先恢复"]
            else:
                try:
                    check_accept(self._db, self._session.workspace_id, self._session,
                                 stored_items(rows, self._dependencies), self._settings)
                    self._cache[key] = []
                except ServiceError as exc:
                    self._cache[key] = exc.details.get("issues") or [str(exc)]
        return self._cache[key]
