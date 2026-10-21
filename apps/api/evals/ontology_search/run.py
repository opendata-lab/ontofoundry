"""Evaluate the ontology retrieval service without HTTP, databases or models."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services.core_validation import validation_report
from ontofoundry_api.services.ontology_search import (
    DEFAULT_SOURCES,
    RecallSource,
    retrieve,
    visible_elements,
)

ROOT = Path(__file__).resolve().parent
TOP_K = 10
SEMANTIC_GAP = "叫法不同"
QUESTION_TYPES = (
    "名称内嵌长句",
    "同义词",
    "英文标识",
    "只有描述能命中",
    "需要关系扩展才能带出",
    SEMANTIC_GAP,
)


def load_inputs(seed_path=ROOT / "seed.json", questions_path=ROOT / "questions.json"):
    raw = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    report = validation_report(raw)
    if not report["publishable"]:
        raise ValueError(f"种子未通过 core-1 发布校验：{report['errors']}")
    draft = OntologyDraft.model_validate(raw)
    questions = json.loads(Path(questions_path).read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise ValueError("题目必须是非空数组")
    searchable = {e.id for e in visible_elements(draft, mappings=True)}
    seen = set()
    for question in questions:
        identity = question["id"]
        expected = question["expected_ids"]
        if not identity or identity in seen:
            raise ValueError(f"题号为空或重复：{identity}")
        seen.add(identity)
        if question["type"] not in QUESTION_TYPES:
            raise ValueError(f"未知题型：{identity}")
        if not isinstance(question["query"], str) or not question["query"].strip():
            raise ValueError(f"查询不能为空：{identity}")
        if not expected or len(expected) != len(set(expected)):
            raise ValueError(f"期望元素为空或重复：{identity}")
        if not set(expected) <= searchable:
            raise ValueError(f"期望元素不存在或不可检索：{identity}")
        expanded = question.get("expansion_expected_ids", [])
        if not set(expanded) <= set(expected):
            raise ValueError(f"扩展期望须属于期望元素：{identity}")
    return draft, questions


def summarize(rows):
    """Keep both question-averaged recall and element-weighted recall explicit."""
    count = len(rows)
    expected = sum(len(row["expected_ids"]) for row in rows)
    matched = sum(len(row["matched_ids"]) for row in rows)
    return {
        "question_count": count,
        "all_expected_count": sum(row["all_expected_in_top10"] for row in rows),
        "all_expected_rate": sum(row["all_expected_in_top10"] for row in rows) / count
        if count
        else 0.0,
        "recall_at_10": sum(row["recall_at_10"] for row in rows) / count if count else 0.0,
        "matched_expected_count": matched,
        "expected_count": expected,
        "micro_recall_at_10": matched / expected if expected else 0.0,
        "average_response_bytes": sum(row["response_bytes"] for row in rows) / count
        if count
        else 0.0,
    }


def evaluate(
    draft,
    questions,
    *,
    sources: Sequence[RecallSource] = DEFAULT_SOURCES,
):
    """Use identical questions and permissions for the expansion ablation."""
    modes = {}
    for mode, expand in (("keyword_only", False), ("keyword_expanded", True)):
        rows = []
        for question in questions:
            items, retrieval, unmatched = retrieve(
                question["query"], draft, mappings=True, expand=expand, sources=sources
            )
            payload = {
                "items": items[:TOP_K],
                "total": len(items),
                "retrieval": retrieval,
                "unmatched_terms": unmatched,
            }
            returned = {item["id"] for item in payload["items"]}
            expected = question["expected_ids"]
            matched = [identity for identity in expected if identity in returned]
            rows.append(
                {
                    "id": question["id"],
                    "type": question["type"],
                    "query": question["query"],
                    "expected_ids": expected,
                    "matched_ids": matched,
                    "missing_ids": [i for i in expected if i not in returned],
                    "all_expected_in_top10": len(matched) == len(expected),
                    "recall_at_10": len(matched) / len(expected),
                    "response_bytes": len(
                        json.dumps(
                            payload, ensure_ascii=False, separators=(",", ":")
                        ).encode("utf-8")
                    ),
                    "response": payload,
                }
            )
        modes[mode] = {
            "expand": expand,
            "overall": summarize(rows),
            "regression": summarize([row for row in rows if row["type"] != SEMANTIC_GAP]),
            "by_type": {
                kind: summarize([row for row in rows if row["type"] == kind])
                for kind in QUESTION_TYPES
                if any(row["type"] == kind for row in rows)
            },
            "questions": rows,
        }
    return {"top_k": TOP_K, "mappings": True, "modes": modes}


def print_report(report):
    for name, mode in report["modes"].items():
        print(f"\n{name}（expand={mode['expand']}）")
        for row in mode["questions"]:
            print(
                f"{row['id']} [{row['type']}] {row['query']} | "
                f"全中={'是' if row['all_expected_in_top10'] else '否'} "
                f"召回={len(row['matched_ids'])}/{len(row['expected_ids'])} "
                f"({row['recall_at_10']:.2%}) 返回={row['response_bytes']} 字节 "
                f"漏召={','.join(row['missing_ids']) or '无'}"
            )
        for label, stats in (
            ("总体", mode["overall"]),
            ("回归集（除叫法不同）", mode["regression"]),
            *mode["by_type"].items(),
        ):
            print(
                f"{label}: {stats['question_count']} 题，"
                f"全中={stats['all_expected_count']}/{stats['question_count']}，"
                f"平均召回={stats['recall_at_10']:.2%}，"
                f"元素召回={stats['micro_recall_at_10']:.2%}，"
                f"平均返回={stats['average_response_bytes']:.2f} 字节"
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description="本体检索离线验收（不访问网络或大模型）")
    parser.add_argument(
        "--seed", type=Path, default=ROOT / "seed.json", help="core-1 种子路径"
    )
    parser.add_argument(
        "--questions", type=Path, default=ROOT / "questions.json", help="题目路径"
    )
    parser.add_argument("--output", type=Path, help="将完整评测结果另存为 JSON")
    args = parser.parse_args(argv)
    report = evaluate(*load_inputs(args.seed, args.questions))
    print_report(report)
    if args.output:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report


if __name__ == "__main__":
    main()
