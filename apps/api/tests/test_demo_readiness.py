"""Behaviour added while preparing the end-to-end demo: a modeling transcript
the browser can render, and validation that names what a model is missing."""

import json
from uuid import uuid4

from test_stage_a import ROOT

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
            {"event_type": "tool.completed",
             "data": {"output": [{"type": "text", "text": huge}],
                      "input": {"command": huge, "file_path": "a.json"}}},
            {"event_type": "content.completed", "data": {"kind": "reasoning", "text": huge}},
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
    big = json.dumps({"event_type": "tool.completed",
                      "data": {"output": [{"type": "text", "text": "y" * 9000}]}})
    assert len(_compact_payload(big)) < 2000


def test_object_without_properties_is_a_warning(client):
    draft = client.post(ROOT + "/sessions", json={}).json()["draft"]
    kind = draft["object_types"][0]
    bare = {**kind, "id": str(uuid4()), "name": "退货单", "technical_name": "return_order"}
    draft["object_types"].append(bare)
    # A concept named in a document, with an instance known only by name.
    draft["material_objects"] = [{
        "id": str(uuid4()), "type_id": bare["id"], "name": "RT-202601-001",
        "values": {}, "evidence": [],
    }]
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
    parent = {**kind, "id": str(uuid4()), "name": "保证金账户", "technical_name": "margin_account",
              "extends": []}
    child = {**kind, "id": str(uuid4()), "name": "专用资金账户", "technical_name": "fund_account",
             "extends": [parent["id"]]}
    draft["object_types"] += [parent, child]
    report = include_instance_validation(
        {"errors": [], "warnings": [], "publishable": True},
        OntologyDraft.model_validate(draft),
    )
    flagged = " ".join(w["message"] for w in report["warnings"])
    assert "保证金账户" not in flagged and "专用资金账户" in flagged


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
    assert replacement_task_id([{"sender_type": "assistant", "task_id": "t0"}, *messages[:2]],
                               "t1") is None
