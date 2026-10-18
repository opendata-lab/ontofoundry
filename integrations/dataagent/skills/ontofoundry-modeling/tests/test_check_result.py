"""The standalone skill checker uses the supplied schema, never a vendor validator."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("skill_checker",Path(__file__).parents[1]/"scripts/check_result.py")
checker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_references_and_context():
    result={"run_token":"round", "items":[{"operation":"create","client_ref":"sale","after":{"owner_type_id":{"client_ref":"missing"}}}]}
    errors=checker.check_result(result,{"type":"object"},{"run_token":"other"})
    assert any("未闭合" in e for e in errors)
    assert any("上下文" in e for e in errors)


def test_duplicates_and_schema():
    result={"items":[{"client_ref":"a"},{"client_ref":"a"}]}
    errors=checker.check_result(result,{"required":["run_token"]})
    assert len(errors)==2


def test_closed_batch():
    result={"items":[{"operation":"create","client_ref":"a","after":{}},{"operation":"create","client_ref":"b","after":{"type_id":{"client_ref":"a"}},"depends_on":["a"]}]}
    assert checker.check_result(result,{"type":"object"})==[]
