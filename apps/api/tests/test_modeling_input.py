"""Derived work packages retain authoritative inputs and bounded indices."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ontofoundry_api.services.dataagent import (
    DataAgentError,
    build_turn_prompt,
)
from ontofoundry_api.services.modeling_input import (
    build_work_pack,
    encode,
    execution_input,
    material_index,
)

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "integrations/dataagent/skills/ontofoundry-modeling/tests/fixtures"
)


def context():
    result = json.loads((FIXTURES / "budget-context.json").read_bytes())
    result["execution"] = execution_input(result["run"]["run_token"])
    return result


def test_six_datasets_and_original_material_are_lossless():
    ctx = context()
    before = deepcopy(ctx)
    content = "云帆订单\n退款30元\n".encode()
    material = material_index(
        {"id": "fictional", "sha256": hashlib.sha256(content).hexdigest()},
        content,
        "inputs/original.md",
    )
    pack, pages = build_work_pack(
        ctx, [material], context_file="context.json", schema_file="schema.json"
    )
    assert not pages and len(encode(pack)) <= 8192 and ctx == before
    assert [entry["id"] for entry in pack["elements"]] == sorted(
        d["id"] for d in ctx["draft"]["datasets"]
    )
    assert pack["materials"][0]["original_range"] == [1, 2]
    assert pack["materials"][0]["sha256"] == hashlib.sha256(content).hexdigest()
    assert build_work_pack(
        ctx, [material], context_file="context.json", schema_file="schema.json"
    ) == (pack, pages)


def test_large_graph_index_pages_keep_every_element_and_pointer():
    ctx = context()
    for i in range(300):
        ctx["draft"]["object_types"].append(
            {
                "id": f"object-{i:04}",
                "name": f"staff_{i}",
                "extends": "parent" if i else None,
            }
        )
    ctx["draft"]["mappings"] = [
        {
            "id": "mapping-a",
            "type_id": "object-0000",
            "sources": [{"id": "main"}, {"id": "extra"}],
        }
    ]
    before = deepcopy(ctx)
    pack, pages = build_work_pack(
        ctx, [], context_file="context.json", schema_file="schema.json"
    )
    assert pages and all(len(p) <= 6000 for p in pages)
    entries = [r["element"] for page in pages for r in json.loads(page)]
    assert len(entries) == 307 and ctx == before
    assert any(e.get("extends") == "parent" for e in entries)
    assert any(e.get("type_id") == "object-0000" for e in entries)
    assert all(e["pointer"].startswith("/draft/") for e in entries)
    assert len(encode(pack)) <= 8192


@pytest.mark.parametrize(
    "material",
    [{"id": "missing", "sha256": "a" * 64}, {"id": "missing", "path": "material.md"}],
)
def test_missing_index_is_explicit(material):
    with pytest.raises(DataAgentError):
        build_work_pack(
            context(), [material], context_file="context.json", schema_file="schema.json"
        )
    with pytest.raises(DataAgentError):
        material_index({"id": "missing", "sha256": "a" * 64}, b"original", "material.md")


def test_model_prompt_contains_only_dynamic_facts():
    from ontofoundry_api.services.dataagent import proposal_instructions

    for token in ["round-one", "round-two"]:
        entry = proposal_instructions(
            run_token=token,
            header={"secret_header": "absent"},
            materials=[],
            schema_file="schema.json",
            mcp=None,
            work_pack_file=f"inputs/pack-{token}.json",
        )
        rendered = build_turn_prompt(
            "改四个名称",
            mode="model",
            workspace_id="fictional",
            session_id="session",
            context_file="context.json",
            material_files=[],
            run_token=token,
            proposal_prompt=entry,
        )
        assert rendered.startswith("模式：建模\n工作包：")
        assert token in rendered
        for absent in [
            "secret_header",
            "schema.json",
            "context.json",
            "思考",
            "材料清单",
            "跨数据集",
        ]:
            assert absent not in rendered


def test_huge_index_upload_is_a_bounded_tree():
    import asyncio

    from ontofoundry_api.services.modeling_input import upload_work_pack

    uploads = {}

    class Client:
        async def upload(self, topic_id, name, body, media_type):
            uploads["inputs/" + name] = body
            return {"rel_path": "inputs/" + name}

    ctx = context()
    pack, _ = build_work_pack(
        ctx, [], context_file="context.json", schema_file="schema.json"
    )
    pack["index_pages"] = []
    pages = [encode([{"element": {"id": str(i)}}]) for i in range(300)]
    path = asyncio.run(upload_work_pack(Client(), "topic", "round", pack, pages))
    assert len(uploads[path]) <= 8192

    def count(path):
        value = json.loads(uploads[path])
        if isinstance(value, list):
            return len(value)
        return sum(count(p) for p in value["index_pages"])

    assert count(path) == 300
    assert all(len(data) <= 8192 for data in uploads.values())
