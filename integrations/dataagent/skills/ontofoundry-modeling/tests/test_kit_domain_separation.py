"""Keep acceptance literals out of every public authoring example, offline only."""

import json
import re

import pytest
from test_extract_kit import KIT, RETAIL
from test_stepwise_workflow import lookup
from test_workflow import CATALOG, SKILL

# These are reusable metadata words, not retail concepts. No business-specific
# noun, physical key or metric is exempted; the same list applies to every surface.
GENERIC_WORDS = {"id", "name", "status"}
IDENTIFIER_KEYS = {"name", "client_ref", "table_name", "schema_name", "column"}


def retail_vocabulary():
    english, chinese = set(), set()

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str):
                    if key in IDENTIFIER_KEYS and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", child):
                        english.add(child)
                    if key in {"display_name", "comment"} and re.search(r"[\u4e00-\u9fff]", child):
                        chinese.add(child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for path in sorted(RETAIL.rglob("*.json")):
        visit(json.loads(path.read_bytes()))
    # This fixture preserves the acceptance material verbatim. Include its bold
    # business names, metric table labels, backtick identifiers and workspace name.
    material = (RETAIL / "material.md").read_text()
    chinese.update(re.findall(r"\*\*([^*]+)\*\*", material))
    chinese.update(re.findall(r"^\| ([^|]+?) \|", material, re.MULTILINE)[2:])
    chinese.update(re.findall(r"^# (.+?)经营管理说明", material, re.MULTILINE))
    english.update(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", material))
    return english - GENERIC_WORDS, chinese


def leaks(text):
    english, chinese = retail_vocabulary()
    # Underscores delimit name segments, so prefixes such as demo_ cannot hide
    # an acceptance identifier. Longer alphabetic words are separate concepts.
    return {word for word in english if re.search(
        rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text, re.IGNORECASE
    )} | {word for word in chinese if word in text}


def test_vocabulary_is_derived_from_acceptance_inputs_and_exemptions_are_generic():
    english, chinese = retail_vocabulary()
    assert {"order", "order_item", "refund", "order_status", "pay_amount", "refund_amount", "sku", "xinghe_retail", "order_items"} <= english
    assert {"星河零售", "订单", "订单明细", "退款", "销售额", "商品 SKU"} <= chinese
    assert not english & GENERIC_WORDS
    assert not leaks("id name status membership_source_id")
    # Catch identifiers in embedded names, SQL, Chinese prose and future columns.
    for text in ("demo_orders", "r.refund_amount", "补退款金额", "星河零售"):
        assert leaks(text)


def test_all_kit_files_and_non_protocol_examples_are_separate_from_acceptance():
    examples = SKILL / "references/examples"
    files = [p for p in KIT.rglob("*") if p.is_file()]
    files += [p for p in examples.rglob("*") if p.is_file() and "protocol" not in p.relative_to(examples).parts]
    failures = {str(p.relative_to(SKILL)): sorted(found) for p in files if (found := leaks(p.read_text()))}
    assert not failures, failures


def public_queries():
    for entry in CATALOG["lookup"]:
        for operation in ("create", "update", "delete"):
            yield entry, "--operation", operation
            yield entry, "--operation", operation, "--with-deps"
    from show_example import VARIANTS

    for kind, variants in VARIANTS.items():
        for variant in variants:
            yield kind, "--variant", variant
            yield kind, "--variant", variant, "--with-deps"
    for part in ("01", "02", "03", "04", "05", "update", "edit"):
        yield "--part", part
    for flag in ("--guide", "--values", "--incremental-guide"):
        yield (flag,)


@pytest.mark.parametrize("args", list(public_queries()))
def test_public_default_and_part_outputs_do_not_leak_acceptance(args):
    result = lookup(*args)
    assert result.returncode == 0, result.stdout.decode()
    assert len(result.stdout) <= 8192
    assert not leaks(result.stdout.decode()), (args, leaks(result.stdout.decode()))
