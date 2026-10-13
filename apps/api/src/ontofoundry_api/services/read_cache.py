"""A small per-process memo for values derived from immutable inputs.

Session reads rebuild the legacy mapping form, the graph, the diff against
the base version and the proposal summary from a large draft. Each of those
is a pure function of content that only changes together with the session
revision and draft hash, so callers key entries by those and a changed draft
simply misses. Cached values are shared: callers must not mutate them.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any


class ReadCache:
    def __init__(self, max_entries: int) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
        # Compute outside the lock; two concurrent misses compute the same value.
        value = compute()
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Bounded by memory, not hit rate: a large draft's graph, mapping form and diff
# take megabytes. Three entries per session revision; the latest is what's read.
session_reads = ReadCache(max_entries=64)
# Normalized published snapshots, keyed by version id and content hash. Sessions
# mostly share the workspace's current version.
version_snapshots = ReadCache(max_entries=8)
