"""Evaluate entity resolution offline: the real resolver over fixed candidate rows.

No database, HTTP or model is used. Database rows come from instances.json and
document instances are empty; grading and status come from the platform's
services/entity_resolution.py unchanged. "叫法不同" and "需要上下文" are known
gaps (no fuzzy or contextual disambiguation yet) and are reported separately.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from unittest import mock

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.services import entity_resolution

ROOT = Path(__file__).resolve().parent
SEED = ROOT.parent / "ontology_search/seed.json"
GAPS = ("叫法不同", "需要上下文")


def load(instances_path=ROOT / "instances.json", questions_path=ROOT / "questions.json"):
    draft = CoreDraft.model_validate(json.loads(SEED.read_text(encoding="utf-8")))
    instances = json.loads(Path(instances_path).read_text(encoding="utf-8"))
    questions = json.loads(Path(questions_path).read_text(encoding="utf-8"))
    type_id = next(o.id for o in draft.object_types if o.name == instances["object_type"])
    return draft, type_id, instances["rows"], questions


def resolve(draft, type_id, rows, mention):
    items = [{"__ref": r["ref"], "display_text": r["values"].get("supplier_name"), "values": r["values"]} for r in rows]
    with mock.patch("ontofoundry_api.services.instance_plan.query_instances",
                    lambda *a, **k: {"items": items, "has_more": False}), \
         mock.patch("ontofoundry_api.services.instance_store.visible", lambda *a, **k: {"objects": []}):
        return entity_resolution.resolve_entity(
            None, str(draft.workspace_id), draft, mention=mention, object_type_id=type_id,
            limit=10, settings=None, mappings_readable=True,
        )


def evaluate(draft, type_id, rows, questions):
    by_type = defaultdict(lambda: {"total": 0, "correct": 0})
    details = []
    for question in questions:
        result = resolve(draft, type_id, rows, question["mention"])
        refs = sorted(c["entity_ref"] for c in result["candidates"]) if result["status"] != "NOT_FOUND" else []
        ok = result["status"] == question["expected"]["status"] and refs == sorted(question["expected"]["refs"])
        by_type[question["type"]]["total"] += 1
        by_type[question["type"]]["correct"] += ok
        details.append({"id": question["id"], "type": question["type"], "mention": question["mention"],
                        "expected": question["expected"], "status": result["status"], "refs": refs, "correct": ok})
    core = [d for d in details if d["type"] not in GAPS]
    return {
        "accuracy": round(sum(d["correct"] for d in details) / len(details), 3),
        "accuracy_excluding_gaps": round(sum(d["correct"] for d in core) / len(core), 3),
        "by_type": dict(by_type),
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(description="实体解析离线评测")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = evaluate(*load())
    for name, value in report["by_type"].items():
        print(f"{name}: {value['correct']}/{value['total']}")
    print(f"总体 {report['accuracy']}，不含已知缺口 {report['accuracy_excluding_gaps']}")
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
