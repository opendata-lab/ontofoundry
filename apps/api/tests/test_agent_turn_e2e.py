"""一次完整的 agent 回合：HTTP 请求 → 执行 → 结果落库。

在此之前没有任何测试跨过这条线。`test_dataagent_integration` 把整个
DataAgentClient mock 掉了，验证的是 OntoFoundry 侧的编排；
`test_pi_runtime_e2e` 跑真实 cell，但只验证协议往返，不经过 HTTP。两者中间那
一段——路由、任务存储、协调器、执行器、消息持久化——从来没有被一起验证过。

合并之后这才第一次可测：以前要起两个服务互相 HTTP 调用。

**模型是 stub 的，执行链路不是。** 真实模型在 CI 里不可复现、需要密钥、要花钱，
而它证明不了这条链路的正确性——它只证明模型还活着。被替换掉的只有 cell 进程
本身，任务状态机、事件持久化和消息收口走的都是真实代码。
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from dataagent_backend.core.task_status import TERMINAL_TASK_STATUSES

from conftest_agent_e2e import client, dataagent_schema, stub_cell  # noqa: F401


pytestmark = pytest.mark.usefixtures("dataagent_schema")


def _given_a_topic(client) -> str:
    response = client.post("/api/v1/agent/topics", json={"title": "e2e"})
    assert response.status_code == 200, response.text
    return response.json()["topic_id"]


def _when_a_turn_is_submitted(client, topic_id: str, question: str) -> str:
    response = client.post(
        "/api/v1/agent/tasks",
        json={
            "topic_id": topic_id,
            "message_type": "text",
            "message_content": question,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("accepted") is True, body
    return body["task_id"]


def _then_task_settles(client, task_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """轮询到终态。

    断言的是"到达某个终态"，而不是"到达 success"——失败也是一种收口，
    而卡在 running 不是。测试要区分这两者。
    """
    # 从源头导入而不是抄一份：终态集合变了，这里要跟着变，而不是悄悄失配。
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/agent/tasks/{task_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if str(last.get("task_status")) in TERMINAL_TASK_STATUSES:
            return last
        time.sleep(0.2)
    pytest.fail(f"任务 {task_id} 在 {timeout}s 内没有收口，最后状态：{last}")


def test_a_submitted_turn_runs_and_persists_its_answer(client, stub_cell):
    """提交一个回合，它应当执行完成，并把助手回答落库。"""
    stub_cell.will_answer("订单域包含 Order、OrderLine 两个实体。")

    topic_id = _given_a_topic(client)
    task_id = _when_a_turn_is_submitted(client, topic_id, "帮我梳理订单域")

    task = _then_task_settles(client, task_id)
    assert task["task_status"] == "finished", task

    messages = client.get(f"/api/v1/agent/topics/{topic_id}/messages").json()["items"]
    senders = [m["sender_type"] for m in messages]
    assert senders == ["user", "assistant"], senders
    assert "订单域包含" in messages[1]["content"]


def test_a_failing_run_settles_as_failed_rather_than_hanging(client, stub_cell):
    """cell 失败时任务必须收口到 failed。

    悬在 running 的任务比失败的任务更糟：前端会一直转圈，用户没有重试入口。
    """
    stub_cell.will_fail("模型网关不可达")

    topic_id = _given_a_topic(client)
    task_id = _when_a_turn_is_submitted(client, topic_id, "随便问点什么")

    task = _then_task_settles(client, task_id)
    assert task["task_status"] == "error", task


def test_agent_events_are_persisted_for_replay(client, stub_cell):
    """事件流要能在任务结束后重放——前端刷新页面依赖这一点。"""
    stub_cell.will_answer("好的。")

    topic_id = _given_a_topic(client)
    task_id = _when_a_turn_is_submitted(client, topic_id, "在吗")
    _then_task_settles(client, task_id)

    page = client.get(f"/api/v1/agent/tasks/{task_id}/agent-events").json()
    types = [r["event_type"] for r in page["records"]]
    assert types, "任务结束后事件应当可重放，实际一条都没有"
    assert types[0] == "run.started", types
    assert types[-1] in {"run.completed", "run.failed"}, types
