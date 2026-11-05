"""Derive extraction contracts from the platform schema, without importing apps."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[1] / "apps/api/src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json"
TARGETS = {
    "ontology-discovery": {"object_type", "property", "value_type", "link_type", "dataset", "mapping", "metric", "rule"},
    "entity-extraction": {"material_object", "material_link"},
}


def references(value):
    if isinstance(value, dict):
        ref = value.get("$ref")
        if ref:
            if not ref.startswith("#/$defs/"):
                raise ValueError(f"Unsupported schema reference: {ref}")
            yield ref.removeprefix("#/$defs/")
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def project_schema(source, targets):
    """Restrict item discriminants and retain precisely their reachable definitions."""
    schema = deepcopy(source)
    definitions = schema.pop("$defs")
    item = definitions["item"]
    known = set(item["properties"]["target_kind"]["enum"])
    if not targets <= known:
        raise ValueError(f"Unknown target kinds: {targets - known}")
    item["properties"]["target_kind"]["enum"] = [kind for kind in item["properties"]["target_kind"]["enum"] if kind in targets]
    item["oneOf"] = [branch for branch in item["oneOf"] if branch["properties"]["target_kind"]["const"] in targets]
    kept, pending = {}, set(references(schema))
    while pending:
        name = min(pending)
        pending.remove(name)
        if name in kept:
            continue
        kept[name] = definitions[name]
        pending.update(set(references(kept[name])) - kept.keys())
    schema["$defs"] = dict(sorted(kept.items()))
    return schema


def generate(source=SOURCE, output_dir=BASE / "skills"):
    source_schema = json.loads(Path(source).read_bytes())
    for name, targets in TARGETS.items():
        destination = Path(output_dir) / name / "output-schema.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(project_schema(source_schema, targets), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description="从平台提案契约生成两个抽取技能的输出 Schema")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output-dir", type=Path, default=BASE / "skills")
    args = parser.parse_args()
    generate(args.source, args.output_dir)


if __name__ == "__main__":
    main()
