"""Behaviour added while preparing the end-to-end demo: a modeling transcript
the browser can render, and validation that names what a model is missing."""

from uuid import uuid4

from test_modeling import ROOT

from ontofoundry_api.api.agent_conversation import present_messages
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


def test_transcript_is_passed_through_without_truncation():
    original = run_message()
    assert present_messages([original]) == [original]





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
    from ontofoundry_api.services.modeling_runs import replacement_task_id

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
