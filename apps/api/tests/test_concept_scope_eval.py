"""Concept-scope eval: gold consistency, scoring rules and no leakage into skills."""

import json
from pathlib import Path

import pytest

from evals.concept_scope.score import normalize, score

EVAL = Path(__file__).resolve().parents[1] / "evals/concept_scope"
SKILLS = Path(__file__).resolve().parents[3] / "integrations/dataagent"
SCENARIOS = sorted(p for p in (EVAL / "scenarios").iterdir() if (p / "gold.json").is_file())


def gold_of(folder):
    return json.loads((folder / "gold.json").read_text(encoding="utf-8"))


def material_text(folder):
    return "\n".join(p.read_text(encoding="utf-8") for p in (folder / "materials").glob("*.md"))


HELDOUT = sorted(p for p in (EVAL / "heldout").glob("*") if (p / "gold.json").is_file())


def test_basic_and_advanced_sets_each_have_one_table_scenario():
    golds = [gold_of(f) for f in SCENARIOS]
    for level, count in (("basic", 3), ("advanced", 2)):
        chosen = [g for g in golds if g.get("level") == level]
        assert len(chosen) == count
        assert sum(bool(g.get("schema")) for g in chosen) == 1


@pytest.mark.parametrize("folder", SCENARIOS + HELDOUT, ids=lambda p: p.name)
def test_gold_is_unambiguous_and_grounded_in_the_material(folder):
    gold = gold_of(folder)
    seen = {}
    for concept in gold["concepts"]:
        for name in concept["accepted"]:
            key = normalize(name)
            assert key not in seen, f"{name} 同时属于 {seen[key]} 与 {concept['key']}"
            seen[key] = concept["key"]
    wrong = [normalize(t) for c in gold["concepts"] for t in c.get("instances", [])]
    wrong += [normalize(t) for e in gold["not_concepts"] for t in e["texts"]]
    assert not set(wrong) & set(seen), "不应成为概念的条目与概念叫法冲突"
    text = material_text(folder)
    for concept in gold["concepts"]:
        for instance in concept.get("instances", []):
            assert instance in text, f"实例 {instance} 不在材料原文中"
    if gold.get("schema"):
        ddl = (folder / "tables.sql").read_text(encoding="utf-8")
        assert all(f"EXISTS {t} " in ddl for t in gold["tables"])


def test_scoring_separates_correct_duplicate_and_each_wrong_kind():
    gold = gold_of(EVAL / "scenarios/wind_inspection")
    entities = {"items": [
        {"name": "wind_farm", "display_name": "风电场", "examples": ["东岭一号风电场", "西坡风电场"]},
        {"name": "turbine", "display_name": "风机", "examples": ["F-07 风机"]},
        {"name": "wind_turbine", "display_name": "风电机组"},
        {"name": "f07", "display_name": "F-07"},
        {"name": "rated_power", "display_name": "额定功率"},
        {"name": "closure_rate", "display_name": "缺陷闭环率"},
        {"name": "region", "display_name": "片区"},
    ]}
    result = score(gold, entities)
    assert result["correct"] == 2 and result["expected"] == 7 and result["predicted"] == 7
    assert result["errors"] == {"实例当概念": 1, "属性当概念": 1, "指标当概念": 1, "重复": 1, "未登记，待人工判定": 1}
    assert result["recall"] == round(2 / 7, 3) and result["precision"] == round(2 / 7, 3)
    assert result["examples_placed"] == 3  # 东岭一号、西坡、F-07（包含匹配）
    assert "defect" in result["missed"]


def test_full_marks_and_empty_plan():
    gold = gold_of(EVAL / "scenarios/contract_approval")
    perfect = {"items": [{"name": c["key"], "display_name": c["accepted"][0], "examples": c.get("instances", [])} for c in gold["concepts"]]}
    result = score(gold, perfect)
    assert result["precision"] == result["recall"] == result["f1"] == 1.0
    assert result["examples_placed"] == result["examples_expected"]
    assert score(gold, None)["recall"] == 0.0


def test_skills_never_contain_eval_scenario_terms():
    """Tuning skills to the exam would make the baseline meaningless."""
    skill_text = "\n".join(p.read_text(encoding="utf-8") for p in SKILLS.rglob("*") if p.suffix in {".md", ".json"} and "tests" not in p.parts and "dist" not in p.parts)
    for folder in SCENARIOS + HELDOUT:
        gold = gold_of(folder)
        for concept in gold["concepts"]:
            for instance in concept.get("instances", []):
                assert instance not in skill_text, f"技能中出现评测实例 {instance}"
