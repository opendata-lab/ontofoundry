"""Bounded per-worker pure reads with single-flight computation and diagnostics."""

from __future__ import annotations

import sys
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import Callable, Hashable
from concurrent.futures import Future
from typing import Any


def estimated_bytes(value: Any) -> int:
    """Count retained Python structures once, including Pydantic and index objects."""
    seen = set()

    def visit(item):
        identity = id(item)
        if identity in seen:
            return 0
        seen.add(identity)
        size = sys.getsizeof(item)
        if isinstance(item, dict):
            size += sum(visit(k) + visit(v) for k, v in item.items())
        elif isinstance(item, (list, tuple, set, frozenset)):
            size += sum(visit(v) for v in item)
        elif hasattr(item, "__dict__"):
            size += visit(vars(item))
        return size

    return visit(value)


class ReadCache:
    def __init__(self, max_entries: int, max_bytes: int = 64 * 1024 * 1024) -> None:
        self._max_entries, self._max_bytes = max_entries, max_bytes
        self._entries: OrderedDict[Hashable, tuple[Any, int]] = OrderedDict()
        self._pending: dict[Hashable, Future] = {}
        self._lock = threading.Lock()
        self._bytes = 0
        self._generation = 0
        self._metrics = Counter()

    def get(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._entries:
                self._metrics["hits"] += 1
                self._entries.move_to_end(key)
                return self._entries[key][0]
            pending = self._pending.get(key)
            owner = pending is None
            if owner:
                pending = self._pending[key] = Future()
                self._metrics["misses"] += 1
            else:
                self._metrics["coalesced"] += 1
            generation = self._generation
        if not owner:
            return pending.result()
        started = time.perf_counter()
        try:
            value = compute()
            size = estimated_bytes(value)
            with self._lock:
                self._metrics["compute_us"] += int(
                    (time.perf_counter() - started) * 1_000_000
                )
                if generation == self._generation:
                    if size <= self._max_bytes:
                        self._entries[key] = (value, size)
                        self._bytes += size
                        while (
                            len(self._entries) > self._max_entries
                            or self._bytes > self._max_bytes
                        ):
                            _, (_, removed) = self._entries.popitem(last=False)
                            self._bytes -= removed
                            self._metrics["evictions"] += 1
                    else:
                        self._metrics["oversized"] += 1
            pending.set_result(value)
            return value
        except BaseException as error:
            with self._lock:
                self._metrics["errors"] += 1
            pending.set_exception(error)
            raise
        finally:
            with self._lock:
                if self._pending.get(key) is pending:
                    self._pending.pop(key)

    def stats(self) -> dict:
        with self._lock:
            return {
                **self._metrics,
                "entries": len(self._entries),
                "estimated_bytes": self._bytes,
                "pending": len(self._pending),
            }

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._entries.clear()
            self._pending.clear()
            self._bytes = 0
            self._metrics.clear()


# A single aggregate budget per worker covers sessions, definitions and projections.
session_reads = ReadCache(max_entries=96)
version_snapshots = session_reads
published_reads = session_reads
