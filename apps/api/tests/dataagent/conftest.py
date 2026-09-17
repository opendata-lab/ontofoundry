"""Shared path anchors for the DataAgent tests.

These tests assert on files that live outside the Python package — Dockerfiles,
deploy config samples, the skills bundle. They used to compute those paths as
`Path(__file__).parents[N]`, which silently encodes how deep the test file sits.
Moving the suite once already broke every one of them at the same time.

Anchoring on the installed package instead means the constants survive the next
move: only the package's own location matters, and that is something Python
tells us rather than something we count.
"""

from __future__ import annotations

from pathlib import Path

import dataagent_backend

# apps/api/src/dataagent_backend
PACKAGE_ROOT = Path(dataagent_backend.__file__).resolve().parent
# apps/api/src/dataagent_backend -> src -> api -> apps -> <repo>
REPO_ROOT = PACKAGE_ROOT.parents[3]
# Assets that did not move with the backend.
REPO_DATAAGENT_DIR = REPO_ROOT / "dataagent"
