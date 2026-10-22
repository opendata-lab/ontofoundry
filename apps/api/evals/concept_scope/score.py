"""Score a plan run's concept list against a scenario's gold answer.

Matching is exact on the gold's registered names after mechanical
normalization (NFKC, lowercase, spaces/underscores/hyphens removed); nothing
is guessed. An unregistered name is reported for a person to judge and, once
accepted, added to the gold's names.
"""

import unicodedata

KINDS = {
    "instance": "实例当概念",
    "attribute": "属性当概念",
    "metric": "指标当概念",
    "aggregate": "统计表当概念",
    "link_table": "关联表当概念",
    "background": "背景当概念",
}


def normalize(text) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).lower()
    return "".join(ch for ch in value if ch not in " _-　")


def _names(item) -> set[str]:
    return {normalize(item.get(key)) for key in ("display_name", "name") if item.get(key)} - {""}


def score(gold: dict, entities: dict | None) -> dict:
    items = [i for i in (entities or {}).get("items", []) if isinstance(i, dict)]
    concepts = gold["concepts"]
    accepted = [{normalize(n) for n in c["accepted"]} for c in concepts]
    wrong = {}
    for concept in concepts:
        for text in concept.get("instances", []):
            wrong[normalize(text)] = "instance"
    for entry in gold.get("not_concepts", []):
        for text in entry["texts"]:
            wrong[normalize(text)] = entry["kind"]

    matched, details = {}, []
    for item in items:
        names = _names(item)
        hit = next((i for i, names_ok in enumerate(accepted) if names & names_ok), None)
        if hit is not None and hit not in matched:
            matched[hit] = item
            details.append({"item": item.get("display_name") or item.get("name"), "result": "正确", "concept": concepts[hit]["key"]})
            continue
        if hit is not None:
            details.append({"item": item.get("display_name") or item.get("name"), "result": "重复"})
            continue
        kind = next((wrong[n] for n in names if n in wrong), None)
        details.append({"item": item.get("display_name") or item.get("name"),
                        "result": KINDS[kind] if kind else "未登记，待人工判定"})

    placed = total_examples = 0
    for i, concept in enumerate(concepts):
        expected = [normalize(t) for t in concept.get("instances", [])]
        total_examples += len(expected)
        if i not in matched:
            continue
        given = [normalize(e) for e in matched[i].get("examples") or []]
        placed += sum(any(e in g or g in e for g in given if g) for e in expected)

    tp = len(matched)
    predicted = len(items)
    precision = tp / predicted if predicted else 0.0
    recall = tp / len(concepts) if concepts else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    counts = {label: sum(d["result"] == label for d in details) for label in [*KINDS.values(), "重复", "未登记，待人工判定"]}
    return {
        "scenario": gold.get("scenario"),
        "level": gold.get("level", "basic"),
        "predicted": predicted,
        "expected": len(concepts),
        "correct": tp,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "missed": [c["key"] for i, c in enumerate(concepts) if i not in matched],
        "errors": {k: v for k, v in counts.items() if v},
        "examples_placed": placed,
        "examples_expected": total_examples,
        "details": details,
    }
