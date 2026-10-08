"""P0 frozen unsupported-path registry; presently empty (all native fields fit).

Only paths explicitly classified unsupported in the coverage matrix belong
here. Legacy parser limitations are not v3 contract limitations. Schema and
semantic validation keep their existing, separate behavior.
"""
from collections.abc import Iterator
from typing import Any

# Tuple segments are object keys or '*' for array indices. Reason must match
# docs/design/2026-10-08-ossie-coverage-matrix.md. No unsupported native paths in P0.
UNSUPPORTED_OSSIE_PATHS: dict[tuple[str, ...], str] = {}


def unsupported_constructs(document: Any) -> Iterator[tuple[str, str]]:
    def walk(value, parts, rendered):
        reason = UNSUPPORTED_OSSIE_PATHS.get(parts)
        if reason is not None:
            yield rendered, reason
        if isinstance(value, dict):
            for key, item in value.items():
                yield from walk(item, (*parts, key), f"{rendered}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from walk(item, (*parts, "*"), f"{rendered}[{index}]")

    yield from walk(document, (), "$")
