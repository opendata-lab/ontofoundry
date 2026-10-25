"""Behaviour added while preparing the end-to-end demo: a modeling transcript
the browser can render, and validation that names what a model is missing."""

import json
from uuid import uuid4

from test_modeling import ROOT

from ontofoundry_api.api.agent_conversation import (
    REASONING_LIMIT,
    TOOL_TEXT_LIMIT,
    _compact_payload,
    present_messages,
)
from ontofoundry_api.domain.instance_validation import include_instance_validation
from ontofoundry_api.domain.models import OntologyDraft


def run_message():
    huge = "x" * 30000
    return {
        "sender_type": "assistant",
        "content": "最终回答" * 1000,
        "blocks": [{"type": "tool_use", "output": [{"type": "text", "text": huge}]}],
        "records": [
            {
                "event_type": "tool.completed",
                "data": {
                    "output": [{"type": "text", "text": huge}],
                    "input": {"command": huge, "file_path": "a.json"},
                },
            },
            {
                "event_type": "content.completed",
                "data": {"kind": "reasoning", "text": huge},
            },
            {"event_type": "content.completed", "data": {"kind": "answer", "text": huge}},
        ],
    }


def test_transcript_is_bounded_but_answers_are_whole():
    original = run_message()
    shown = present_messages([original])[0]
    tool, reasoning, answer = shown["records"]
    assert len(tool["data"]["output"][0]["text"]) < TOOL_TEXT_LIMIT + 40
    assert len(tool["data"]["input"]["command"]) < TOOL_TEXT_LIMIT + 40
    assert tool["data"]["input"]["file_path"] == "a.json"
    assert len(reasoning["data"]["text"]) < REASONING_LIMIT + 40
    assert answer["data"]["text"] == original["records"][2]["data"]["text"]
    assert shown["content"] == original["content"]
    # The SDK renders from records; the duplicate copy is not sent.
    assert shown["blocks"] == []


def test_live_events_are_compacted_and_small_ones_pass_verbatim():
    small = '{"seq_id":1,"type":"delta"}'
    assert _compact_payload(small) == small
    big = json.dumps(
        {
            "event_type": "tool.completed",
            "data": {"output": [{"type": "text", "text": "y" * 9000}]},
        }
    )
    assert len(_compact_payload(big)) < 2000


def test_object_without_properties_is_a_warning(client):
    draft = client.post(ROOT + "/sessions", json={}).json()["draft"]
    kind = draft["object_types"][0]
    bare = {
        **kind,
        "id": str(uuid4()),
        "display_name": "退货单",
        "name": "return_order",
        "title_property_id": None,
    }
    draft["object_types"].append(bare)
    report = include_instance_validation(
        {"errors": [], "warnings": [], "publishable": True},
        OntologyDraft.model_validate(draft),
    )
    codes = {w["code"]: w["message"] for w in report["warnings"]}
    assert "退货单" in codes["OBJECT_WITHOUT_PROPERTIES"]
    # Neither blocks publishing.
    assert report["publishable"] and report["instance_status"] == "passed"


def test_abstract_parents_are_not_flagged(client):
    draft = client.post(ROOT + "/sessions", json={}).json()["draft"]
    kind = draft["object_types"][0]
    parent = {
        **kind,
        "id": str(uuid4()),
        "display_name": "故事页柜",
        "name": "storybook_cabinet",
        "extends": None,
        "title_property_id": None,
    }
    child = {
        **kind,
        "id": str(uuid4()),
        "display_name": "虚构阅览柜",
        "name": "storybook_reading_cabinet",
        "extends": parent["id"],
        "title_property_id": None,
    }
    draft["object_types"] += [parent, child]
    report = include_instance_validation(
        {"errors": [], "warnings": [], "publishable": True},
        OntologyDraft.model_validate(draft),
    )
    flagged = " ".join(w["message"] for w in report["warnings"])
    assert "故事页柜" not in flagged and "虚构阅览柜" in flagged


def test_follows_the_task_dataagent_started_to_replace_a_suspended_one():
    from ontofoundry_api.api.agent_conversation import replacement_task_id

    messages = [
        {"sender_type": "user", "task_id": "t1"},
        {"sender_type": "assistant", "task_id": "t1", "status": "suspended"},
        {"sender_type": "assistant", "task_id": "t2", "status": "running"},
    ]
    assert replacement_task_id(messages, "t1") == "t2"
    # An earlier turn is not a replacement, and no later task means none.
    assert replacement_task_id(messages, "t2") is None
    assert (
        replacement_task_id(
            [{"sender_type": "assistant", "task_id": "t0"}, *messages[:2]], "t1"
        )
        is None
    )


def test_tool_paths_are_presented_without_changing_records_or_answers():
    from copy import deepcopy

    skill = "/Users/fictional/project/dataagent/.claude/skills/entity-extraction/references/extract-facts.md"
    workspace = "/srv/dataagent_runtime/topic_fictional/workspace/modeling/parts/05-facts.json"
    original = {
        "sender_type": "assistant", "content": skill,
        "records": [{"event_type": "tool.completed", "data": {
            "title": f"读取文件：{skill}",
            "input": {"file_path": skill, "nested": [workspace]},
            "output": [{"type": "text", "text": f"已写入 {workspace}"}],
        }}],
    }
    stored = deepcopy(original)
    shown = present_messages([original])[0]
    data = shown["records"][0]["data"]
    assert data["title"] == "读取文件：技能 entity-extraction/references/extract-facts.md"
    assert data["input"]["file_path"] == "技能 entity-extraction/references/extract-facts.md"
    assert data["input"]["nested"] == ["modeling/parts/05-facts.json"]
    assert data["output"][0]["text"] == "已写入 modeling/parts/05-facts.json"
    assert shown["content"] == skill
    assert original == stored
    event = original["records"][0]
    assert json.loads(_compact_payload(json.dumps(event)))["data"] == data
    block = present_messages([{"blocks": [{"type": "tool_use", "input": {"file_path": skill}}]}])[0]
    assert block["blocks"][0]["input"]["file_path"].startswith("技能 entity-extraction/")


def test_tool_path_presentation_preserves_relative_paths_and_urls():
    from ontofoundry_api.services.tool_presentation import present_tool_value

    value = {
        "relative": "uploads/需求.md", "url": "https://fictional.example/Users/guide.md",
        "legacy": "/home/fictional/topic_fictional/uploads/需求.md",
        "other": "/tmp/fictional-host/log.txt",
        "windows": r"C:\Users\fictional\.claude\skills\ontology-discovery\SKILL.md",
    }
    shown = present_tool_value(value)
    assert shown["relative"] == value["relative"] and shown["url"] == value["url"]
    assert shown["legacy"] == "uploads/需求.md"
    assert shown["other"] == "log.txt"
    assert shown["windows"] == "技能 ontology-discovery/SKILL.md"
