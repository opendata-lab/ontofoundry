"""Create (or reuse) the Q&A agent on DataAgent, ask it the demo questions in
preview, and publish it once every answer is right.

    python dataagent_agent.py            # create/update, preview-check, publish
    python dataagent_agent.py ask "问题"  # one preview question
    python dataagent_agent.py sync       # update the agent and MCP config only, no questions
"""

from __future__ import annotations

import functools
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

print = functools.partial(print, flush=True)  # noqa: A001
DA = os.environ.get("DATAAGENT_API", "http://127.0.0.1:8900").rstrip("/") + "/api/v1"
ROOT = Path(__file__).resolve().parents[4]
PROMPT_DOC = ROOT / "integrations" / "dataagent" / "agents" / "agent_ontofoundry_qa.md"
NAME = "咖啡渠道销售 · 问数助手"
MCP_SERVER = "srv_ontofoundry"
QUESTIONS = [
    ("星海贸易在哪个城市？什么时候签约的？", ["上海", ("2025-10-02", "2025年10月2日")]),
    ("经典手冲壶是什么品类？标准单价多少？", ["咖啡器具", "168"]),
    ("一共有多少张订单？订单总金额是多少？", ["780", "269"]),
    ("销售额最高的客户是谁？销售额多少？", ["远山咖啡", "38"]),
    ("1 月有哪些退货？退款合计多少？", ["RT-202601-001", "RT-202601-003", "376"]),
]


def call(method, path, body=None):
    request = urllib.request.Request(DA + path, method=method,
                                     data=None if body is None else json.dumps(body).encode())
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read() or b"null")


def system_prompt() -> str:
    return re.search(r"## 系统提示词\s+```text\n(.*?)```", PROMPT_DOC.read_text(), re.S)[1].strip()


def agent() -> dict:
    profile = {
        "name": NAME,
        "description": "通过 OntoFoundry 本体 MCP 查询咖啡渠道销售数据：客户、订单、订单明细、商品。",
        "system_prompt": system_prompt(),
        "allowed_tools": ["Bash", "Read"],
        "mcp_server_ids": [MCP_SERVER],
        "skill_folders": [],
        "max_turns": 60,
        "visibility": {"mode": "all", "allowed_users": [], "allowed_groups": []},
        "preset_questions": [QUESTIONS[i][0] for i in (0, 2, 4)],
    }
    found = next((a for a in call("GET", "/dataagent/agents/workbench")
                  if a.get("name") == NAME), None)
    if found:
        print("更新智能体", found["agent_id"])
        return call("PUT", f"/dataagent/agents/{found['agent_id']}",
                    {**profile, "expected_revision": draft_revision(found["agent_id"])})
    print("创建智能体", NAME)
    return call("POST", "/dataagent/agents", profile)


def draft_revision(agent_id: str) -> int:
    draft = call("GET", f"/dataagent/agents/{agent_id}/draft")
    return int(draft["revision"])


def ask(agent_id: str, question: str) -> str:
    revision = draft_revision(agent_id)
    topic = call("POST", f"/dataagent/agents/{agent_id}/preview-topics",
                 {"expected_revision": revision})
    topic_id = topic.get("topic_id") or topic["id"]
    task = call("POST", f"/dataagent/agents/{agent_id}/preview-tasks", {
        "expected_revision": revision, "topic_id": topic_id, "message_content": question})
    task_id = task.get("task_id") or task["id"]
    started = time.time()
    while True:
        state = call("GET", f"/nl2sql/tasks/{task_id}")
        status = state.get("task_status") or state.get("status")
        if status in {"finished", "error", "failed", "cancelled", "suspended"}:
            break
        time.sleep(3)
    message = call("GET", f"/nl2sql/tasks/{task_id}/message")
    text = json.dumps(message, ensure_ascii=False)
    content = (message or {}).get("content") if isinstance(message, dict) else None
    print(f"  [{status} {time.time() - started:.0f}s]")
    return content if isinstance(content, str) else text


def import_mcp() -> None:
    config = Path(__file__).resolve().parent.parent / "generated" / "mcp-config.json"
    call("POST", "/dataagent/mcp/servers/import", json.loads(config.read_text()))
    found = call("POST", f"/dataagent/mcp/servers/{MCP_SERVER}/detections", {})
    print("MCP:", found.get("message"))


def main() -> None:
    import_mcp()
    profile = agent()
    agent_id = profile.get("agent_id") or profile["id"]
    if sys.argv[1:] == ["sync"]:
        call("POST", f"/dataagent/agents/{agent_id}/publish",
             {"expected_revision": draft_revision(agent_id)})
        print("已同步并发布智能体", agent_id)
        return
    if len(sys.argv) == 3 and sys.argv[1] == "ask":
        print(ask(agent_id, sys.argv[2]))
        return
    ok = True
    for question, expected in QUESTIONS:
        print("问:", question)
        answer = ask(agent_id, question)
        print("答:", answer[-600:])
        # Each expectation is a string or a tuple of acceptable spellings.
        text = answer.replace(",", "")
        hit = all(
            any(alt in text for alt in (item if isinstance(item, tuple) else (item,)))
            for item in expected
        )
        print("  ✓" if hit else "  ✗ 期望包含 " + "、".join(map(str, expected)))
        ok &= hit
    if ok:
        call("POST", f"/dataagent/agents/{agent_id}/publish",
             {"expected_revision": draft_revision(agent_id)})
        print("全部答对，已发布智能体", agent_id)
    else:
        print("有答案不符，未发布；请看上面的输出")


if __name__ == "__main__":
    main()
