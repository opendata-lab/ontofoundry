from ontofoundry_api.services.dataagent import (
    DataAgentClient,
    DataAgentError,
    public_answer,
)
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"


def create_session(client):
    response = client.post(ROOT + "/sessions", json={"title": "DataAgent 集成测试"})
    assert response.status_code == 201
    return response.json()


def test_public_answer_prefers_projected_main_text():
    assert public_answer(
        {
            "content": "legacy",
            "blocks": [
                {"kind": "thinking", "text": "hidden"},
                {"kind": "main_text", "text": "# 可见答案"},
            ],
        }
    ) == "# 可见答案"


def test_modeling_turn_is_submitted_and_reconciled_through_dataagent(client, monkeypatch):
    client.app.state.settings.dataagent_base_url = "http://dataagent.invalid"
    client.app.state.settings.dataagent_access_key = "server-secret"
    session = create_session(client)
    uploads = []

    async def create_topic(self, title, agent_id):
        assert title == "DataAgent 集成测试"
        assert agent_id == "agent_ontofoundry"
        return {"topic_id": "topic-1"}

    async def upload(self, topic_id, name, content, media_type):
        uploads.append((topic_id, name, media_type, content))
        return {"rel_path": f"uploads/{name}"}

    async def deliver(self, **payload):
        assert payload["topic_id"] == "topic-1"
        assert "[用户消息]\n开始建模" in payload["content"]
        return {"task_id": "task-1", "task_status": "waiting"}

    monkeypatch.setattr(DataAgentClient, "create_topic", create_topic)
    monkeypatch.setattr(DataAgentClient, "upload", upload)
    monkeypatch.setattr(DataAgentClient, "deliver", deliver)

    response = client.post(
        ROOT + f"/sessions/{session['id']}/messages",
        json={"revision": session["revision"], "content": "开始建模", "mode": "model"},
    )
    assert response.status_code == 202, response.text
    submitted = response.json()
    assert submitted["dataagent_topic_id"] == "topic-1"
    assert submitted["dataagent_task_id"] == "task-1"
    assert submitted["task_status"] == "queued"
    assert uploads[0][1].startswith("ontofoundry-context-r")

    async def task(self, task_id):
        return {"task_id": task_id, "task_status": "finished"}

    async def task_message(self, task_id):
        return {
            "message_id": "answer-1",
            "content": "fallback",
            "blocks": [{"kind": "main_text", "text": "## 建模建议\n\n完成"}],
            "attachments": [{"name": "proposal.json", "rel_path": "output/proposal.json"}],
        }

    monkeypatch.setattr(DataAgentClient, "task", task)
    monkeypatch.setattr(DataAgentClient, "task_message", task_message)
    synced = client.post(ROOT + f"/sessions/{session['id']}/sync")
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert body["task_status"] == "completed"
    assert body["dataagent_task_id"] is None
    assert body["messages"][-1]["content"].startswith("## 建模建议")
    assert body["messages"][-1]["attachments"][0]["name"] == "proposal.json"


def test_failed_first_submission_removes_unreferenced_dataagent_topic(client, monkeypatch):
    client.app.state.settings.dataagent_base_url = "http://dataagent.invalid"
    client.app.state.settings.dataagent_access_key = "server-secret"
    session = create_session(client)
    deleted = []

    async def create_topic(self, title, agent_id):
        return {"topic_id": "topic-orphan"}

    async def upload(self, topic_id, name, content, media_type):
        return {"rel_path": f"uploads/{name}"}

    async def deliver(self, **payload):
        raise DataAgentError("供应商不可用", status_code=400)

    async def delete_topic(self, topic_id):
        deleted.append(topic_id)
        return {"ok": True}

    monkeypatch.setattr(DataAgentClient, "create_topic", create_topic)
    monkeypatch.setattr(DataAgentClient, "upload", upload)
    monkeypatch.setattr(DataAgentClient, "deliver", deliver)
    monkeypatch.setattr(DataAgentClient, "delete_topic", delete_topic)

    response = client.post(
        ROOT + f"/sessions/{session['id']}/messages",
        json={"revision": session["revision"], "content": "开始", "mode": "chat"},
    )

    assert response.status_code == 400
    assert deleted == ["topic-orphan"]


def test_dataagent_cancel_uses_remote_task(client, monkeypatch):
    client.app.state.settings.dataagent_base_url = "http://dataagent.invalid"
    client.app.state.settings.dataagent_access_key = "server-secret"
    session = create_session(client)

    async def create_topic(self, title, agent_id):
        return {"topic_id": "topic-cancel"}

    async def upload(self, topic_id, name, content, media_type):
        return {"rel_path": f"uploads/{name}"}

    async def deliver(self, **payload):
        return {"task_id": "task-cancel", "task_status": "waiting"}

    async def cancel(self, task_id):
        assert task_id == "task-cancel"
        return {"task_id": task_id, "task_status": "suspended"}

    monkeypatch.setattr(DataAgentClient, "create_topic", create_topic)
    monkeypatch.setattr(DataAgentClient, "upload", upload)
    monkeypatch.setattr(DataAgentClient, "deliver", deliver)
    monkeypatch.setattr(DataAgentClient, "cancel", cancel)
    submitted = client.post(
        ROOT + f"/sessions/{session['id']}/messages",
        json={"revision": session["revision"], "content": "分析", "mode": "chat"},
    ).json()
    response = client.post(ROOT + f"/sessions/{session['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["task_status"] == "cancelled"
    assert response.json()["revision"] == submitted["revision"] + 1
