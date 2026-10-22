"""Score an extraction run's proposals: properties, relations, instances, mappings, metrics.

Proposal items carry resolved UUIDs, so each property, relation, mapping and
instance is traced back to its object type, and the object type to a gold
concept by its registered names (same exact matching as score.py). Extra
properties are not penalized: keeping a foreign key as a property is allowed.
"""

try:
    from score import normalize
except ModuleNotFoundError:  # imported as a package by the tests
    from .score import normalize

# Seen from the other end; there is no one_to_many kind, so a reversed many_to_one never matches.
REVERSED = {"many_to_one": "one_to_many", "one_to_one": "one_to_one", "many_to_many": "many_to_many"}


def _after(item):
    return item.get("after") or {}


def _names(element):
    return {normalize(element.get(k)) for k in ("display_name", "name") if element.get(k)} - {""}


def _section(found, total):
    return {"found": found, "expected": total, "recall": round(found / total, 3) if total else 1.0}


def score_extraction(gold: dict, extraction: dict, items: list[dict], datasets: list[dict] | None = None) -> dict:
    """items: the batch's proposal items; datasets: those already in the session draft."""
    by_kind = {}
    for item in items:
        if item.get("operation") == "create":
            by_kind.setdefault(item["target_kind"], []).append(_after(item))
    concept_of = {}
    for element in by_kind.get("object_type", []):
        names = _names(element)
        for concept in gold["concepts"]:
            if names & {normalize(n) for n in concept["accepted"]}:
                concept_of[element["id"]] = concept["key"]
                break

    # Properties: each expected property found on its concept's object type.
    props = {}
    for element in by_kind.get("property", []):
        key = concept_of.get(element.get("owner_type_id"))
        if key:
            props.setdefault(key, []).append(_names(element))
    property_details, found = [], 0
    for key, expected in extraction["properties"].items():
        for prop in expected:
            accepted = {normalize(n) for n in prop["accepted"]}
            hit = any(names & accepted for names in props.get(key, []))
            found += hit
            property_details.append({"concept": key, "property": prop["accepted"][0], "found": hit})
    total_props = sum(len(v) for v in extraction["properties"].values())

    # Relations: the pair in either direction, with the multiplicity read accordingly.
    links = []
    for element in by_kind.get("link_type", []):
        source, target = concept_of.get(element.get("source_type_id")), concept_of.get(element.get("target_type_id"))
        if source and target:
            links.append((source, target, element.get("multiplicity")))
    relation_details, pairs, exact = [], 0, 0
    for relation in extraction["relations"]:
        allowed = set(relation["multiplicity"])
        seen = [m for s, t, m in links if (s, t) == (relation["source"], relation["target"])]
        seen += [REVERSED.get(m, m) for s, t, m in links if (s, t) == (relation["target"], relation["source"])]
        pair, right = bool(seen), any(m in allowed for m in seen)
        pairs += pair
        exact += right
        relation_details.append({"relation": f"{relation['source']}→{relation['target']}", "found": pair,
                                 "multiplicity_ok": right, "seen": seen})

    # Mappings: the concept's mapping reads the expected table.
    tables = {str(d["id"]): d.get("table_name") for d in [*(datasets or []), *by_kind.get("dataset", [])]}
    mapped = {}
    for element in by_kind.get("mapping", []):
        key = concept_of.get(element.get("type_id"))
        if key:
            mapped.setdefault(key, set()).update(tables.get(str(s.get("dataset_id"))) for s in element.get("sources") or [])
    mapping_details = [{"concept": k, "table": t, "found": t in mapped.get(k, set())} for k, t in extraction["mappings"].items()]

    # Instances: the gold's named things proposed as document instances of their concept.
    values = {}
    for element in by_kind.get("material_object", []):
        key = concept_of.get(element.get("type_id"))
        if key:
            values.setdefault(key, []).extend(normalize(v) for v in (element.get("values") or {}).values() if isinstance(v, str))
    instance_details = []
    for concept in gold["concepts"]:
        for text in concept.get("instances", []):
            needle = normalize(text)
            hit = any(needle in v or (v and v in needle) for v in values.get(concept["key"], []))
            instance_details.append({"concept": concept["key"], "instance": text, "found": hit})

    metric_names = [_names(m) for m in by_kind.get("metric", [])]
    metric_details = [{"metric": m["accepted"][0], "found": any(n & {normalize(a) for a in m["accepted"]} for n in metric_names)}
                      for m in extraction.get("metrics", [])]

    return {
        "scenario": gold.get("scenario"),
        "proposals": len(items),
        "properties": _section(found, total_props),
        "relations": {**_section(pairs, len(extraction["relations"])), "multiplicity_correct": exact},
        "mappings": _section(sum(d["found"] for d in mapping_details), len(mapping_details)),
        "instances": _section(sum(d["found"] for d in instance_details), len(instance_details)),
        "metrics": _section(sum(d["found"] for d in metric_details), len(metric_details)),
        "details": {"properties": property_details, "relations": relation_details, "mappings": mapping_details,
                    "instances": instance_details, "metrics": metric_details},
    }
