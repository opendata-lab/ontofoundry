"""The platform's own submission checks, run on a batch without a database.

The skill keeps no copy of the platform's rules (design §6); tests check kept
examples and generated fragments with the platform's contract parser and graph
validation instead. Data-source probes and stored-material quotes need the
running platform and are covered by its own tests.
"""

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps/api/src"))

from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    RunContext,
    parse_result,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.instances import validate_instances
from ontofoundry_api.domain.models import (
    COLLECTIONS,
    ElementKind,
    OntologyDraft,
)
from ontofoundry_api.domain.snapshot import empty_snapshot

INSTANCE_COLLECTIONS = {"material_object": "material_objects", "material_link": "material_links"}


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def empty_pinned():
    """A run pinned to an empty ontology."""
    pinned = json.loads((FIXTURES / "context.json").read_bytes())
    pinned["draft"] = empty_snapshot(pinned["run"]["workspace_id"])
    pinned["element_hashes"] = {}
    pinned["instance_baseline"] = {"change_sequence": 0, "items": []}
    pinned["run"]["source_draft_sha256"] = snapshot_sha256(pinned["draft"])
    return pinned


def any_material(_material_id):
    """Every material exists with enough lines; quotes are left to the platform."""
    return "0" * 64, [""] * 100_000


def context(pinned):
    run = pinned["run"]
    return RunContext(
        run["workspace_id"], run["session_id"], run["run_token"], run["base_version_id"],
        run["base_version_sha256"], run["source_session_revision"], run["source_draft_sha256"],
        pinned["draft"], pinned.get("instance_baseline") or {},
    )


def _unquoted(value):
    if isinstance(value, dict):
        material = value.get("kind", "material") == "material" and "material_id" in value
        return {k: _unquoted(v) for k, v in value.items() if not (material and k in {"quote", "material_sha256"})}
    if isinstance(value, list):
        return [_unquoted(v) for v in value]
    return value


def parse(batch, pinned, lookup=any_material):
    """The platform's parse of a batch (raises ProposalContractError)."""
    batch = _unquoted(batch) if lookup is any_material else batch
    return parse_result(json.dumps(batch).encode(), context(pinned), lookup)


def errors(batch, pinned, lookup=any_material):
    """Problems the platform would report on submit; [] when it would store the batch."""
    batch = _unquoted(batch) if lookup is any_material else batch
    try:
        parsed = parse_result(json.dumps(batch).encode(), context(pinned), lookup)
    except ProposalContractError as exc:
        return str(exc).splitlines()
    draft = deepcopy(pinned["draft"])
    instances = {c: [i["element"] for i in (pinned.get("instance_baseline") or {}).get("items", [])
                     if i["target_kind"] == k] for k, c in INSTANCE_COLLECTIONS.items()}
    for item in parsed.items:
        if item.target_kind in INSTANCE_COLLECTIONS:
            elements = instances[INSTANCE_COLLECTIONS[item.target_kind]]
        else:
            elements = draft.setdefault(COLLECTIONS[ElementKind(item.target_kind)], [])
        elements[:] = [e for e in elements if e["id"] != item.target_id]
        if item.after is not None:
            elements.append(item.after)
    try:
        model = OntologyDraft.model_validate(draft)
        if any(instances.values()):
            validate_instances(model, instances["material_objects"], instances["material_links"])
    except ValueError as exc:
        return [str(exc)]
    return []
