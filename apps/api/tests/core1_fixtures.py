"""The 13 core-1 design examples as test fixtures.

Read straight from docs/design/core-1-examples so tests and documentation
cannot drift apart.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from ontofoundry_api.domain.core import CoreDraft

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "design" / "core-1-examples"


def example_names() -> list[str]:
    return sorted(path.stem for path in EXAMPLES_DIR.glob("*.json"))


@cache
def example_document(name: str) -> dict:
    """The whole native file: format, schema_version, exported_at and draft."""
    return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def example_draft_json(name: str) -> dict:
    return json.loads(json.dumps(example_document(name)["draft"]))


def example_draft(name: str) -> CoreDraft:
    return CoreDraft.model_validate(example_draft_json(name))
