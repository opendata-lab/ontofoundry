# OntoFoundry 接入 DataAgent Conversation SDK 实施计划

**设计文档:** `docs/design/2026-09-21-dataagent-conversation-sdk-integration-design.md`
**上游计划:** OpenDataWorks 仓库 `docs/plans/2026-09-21-agent-conversation-sdk-plan.md`

## 跨仓库前置依赖

| 本计划的任务 | 依赖上游 | 说明 |
| --- | --- | --- |
| T1 – T6 | **无** | 按设计文档的协议表对着 mock 实现即可并行推进 |
| T7（集成包） | 上游 **T8**（站点 access key） | README 要写死密钥生成步骤，验收要连真实 DataAgent |
| T8（前端接入） | 上游 **T7**（npm 发布 `0.1.0`）+ 本仓库 **T7** | 没有发布的包装不上；没有集成包就没有可用的 Agent，跑不通
| 真实联调、生产部署 | 上游 **T8**（站点 access key） | 没有 access key，BFF 连不上受保护的站点 |

## 全局约束

实施者不得自行更改以下取值：

- 外部 DataAgent 运行时前缀 `/api/v1/nl2sql`，事件流 `/tasks/{task_id}/sdk-events/stream`。仓库里任何 `/api/v1/agent`、`/agent-events/stream` 都是内置分叉的残留。
- **Agent 存在性查询在不同前缀**：`GET /api/v1/dataagent/agents/{agent_id}`，不套用 `ONTOFOUNDRY_DATAAGENT_API_PREFIX`。`GET {prefix}/topics?agent_id=` 只过滤 Topic，**不能**用作存在性检查。
- BFF 基址 `/api/v1/workspaces/{workspace_id}/sessions/{session_id}/agent-conversation`。
- 状态转换表（写死，依据 `opendataworks/.../core/task_status.py:17,23`）：`waiting→queued`、`running→running`、`waiting_input→waiting_input`、`waiting_permission→waiting_permission`、`finished→finished`、`error→failed`、`suspended→cancelled`、任务不存在`→failed`。**活动态是 `submitting` + 前四个**，所有互斥条件必须覆盖全部五个。
- BFF 的 `/events` **不得字节透传**，必须输出 `event: agent-event` / `event: done`；`done` 在候选回写完成之后才发。
- **CAS 抢占必须发生在任何远端副作用之前。**
- 结果文件 `output/ontofoundry-result-{run_token}.json`，`schema_version` 固定 `ontofoundry.model-result/v1`，文件内 `run_token` 必须与请求一致。
- 候选 `id` 确定性构造 `f"{task_id}:{kind}:{value_id}"`，不得用 `uuid4`；必须带 `before` 字段。
- **任何情况下 Agent 产出都不得直接写入 `draft_json` 或触发发布。** 只写 `candidates_json`。
- 迁移链三个 revision：`20260921_000001`（加列）→ `20260921_000002`（删 `messages_json`）→ `20260921_000003`（删 `da_*`），与设计 §8.1 表格逐字一致。
- SDK 依赖写精确版本 `"@opendataworks/agent-conversation": "0.1.0"`，不用 `^`；**不 import 任何 CSS**。
- Python 3.13 + uv；测试 `cd apps/api && uv run --python 3.13 pytest -q`，lint `uv run --python 3.13 ruff check src tests`。前端 `npm test -w apps/web`。
- 每个任务结束提交一次，前缀 `feat(api):` / `feat(web):` / `refactor:` / `chore(deploy):`。

### 本地开发环境的分界点

**从 T3 完成起，本地开发必须指向一个外部 DataAgent。** T3 把客户端路径切到 `/api/v1/nl2sql/.../sdk-events`，而仓库内置分叉仍是 `/api/v1/agent/.../agent-events`，`.env.example:25` 当前又指向本机 8900 的内置服务——两者不兼容。

因此 T3 的步骤里包含更新 `.env.example` 与 README 的本地运行说明。**不要以为"删除发生在 T11，所以 T11 之前都能用本地 DataAgent"。**

### 任务顺序

T1 必须最先（迁移链在即将删除的目录里）。**T11 必须最后**——删除之后仓库内不再有可跑的 DataAgent，且 T7 的集成包要用到 `.claude/skills/md2ossie/`。每个任务结束时应用都应处于可运行状态。

---

## T1 — Alembic 所有权转移

**为什么先做：** 仓库里唯一的迁移链在 `apps/api/src/dataagent_backend/alembic/`，该目录在 T11 要被整个删除。先搬走，revision ID 一个都不能变，否则已部署库的 `alembic_version` 对不上。

**涉及文件**
- 移动 `apps/api/src/dataagent_backend/alembic.ini` → `apps/api/src/ontofoundry_api/alembic.ini`
- 移动 `apps/api/src/dataagent_backend/alembic/` → `apps/api/src/ontofoundry_api/alembic/`
- 修改 `apps/api/src/ontofoundry_api/alembic/env.py`
- 修改 `Makefile`、`apps/api/Dockerfile`、`compose.yaml`、`scripts/` 中指向旧路径的命令

**步骤**
- [ ] `git mv` 两个路径，保持 `versions/20260913_000001_postgresql_baseline.py` 与 `20260916_000001_add_api_format.py` 的**文件名与文件内 `revision` / `down_revision` 完全不变**。
- [ ] 改 `alembic.ini` 的 `script_location`。
- [ ] 改 `env.py`：`target_metadata` 指向 `ontofoundry_api.database.Base.metadata`；URL 从 `ontofoundry_api.config.get_settings().database_url` 读，不再读 `DATAAGENT_DATABASE_URL`。
- [ ] `grep -rn "dataagent_backend/alembic\|DATAAGENT_DATABASE_URL" Makefile apps/api/Dockerfile compose.yaml scripts/` 逐处改到新路径/新变量。
- [ ] 在干净库与含数据的库副本上各跑一次 `alembic upgrade head`。
- [ ] 提交。

**验收：** 两种库上均成功；`alembic history` 的 revision ID 与迁移前逐行一致；应用正常启动。

---

## T2 — Modeling Session 新增显式字段

**产出：** DataAgent 绑定关系从 `messages_json` 反查改为显式列。`messages_json` 仍保留，旧链路不受影响。

**涉及文件**
- 修改 `apps/api/src/ontofoundry_api/db_models.py`
- 新增 `apps/api/src/ontofoundry_api/alembic/versions/20260921_000001_modeling_session_dataagent_columns.py`
- 修改 `apps/api/src/ontofoundry_api/api/modeling.py`（`session_data`、`revise`）
- 新增 `apps/api/tests/test_modeling_session_columns.py`

**步骤**
- [ ] 先写失败测试：新建记录断言九个新属性存在且默认值正确；**并断言一条"存量行"（用原生 SQL 插入不含新列的行后执行迁移）迁移后非空列不是 NULL**。
- [ ] `ModelingSessionRecord` 增加：

```python
    dataagent_topic_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataagent_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataagent_task_mode: Mapped[str] = mapped_column(String(8), nullable=False, server_default="")
    dataagent_run_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_material_ids: Mapped[list] = mapped_column(JSON, nullable=False, server_default="[]")
    last_result_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="")
    result_warnings: Mapped[list] = mapped_column(JSON, nullable=False, server_default="[]")
    result_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] 写 `20260921_000001`，`down_revision = "20260916_000001"`。**非空列必须带 `server_default` 回填存量行**：

```python
    op.add_column("modeling_sessions",
        sa.Column("dataagent_task_mode", sa.String(8), nullable=False, server_default=""))
    op.add_column("modeling_sessions",
        sa.Column("uploaded_material_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("modeling_sessions",
        sa.Column("result_state", sa.String(20), nullable=False, server_default=""))
    op.add_column("modeling_sessions",
        sa.Column("result_warnings", sa.JSON(), nullable=False, server_default="[]"))
    # 三个 ID 类字段与 run_token 保持 nullable
```

  `result_claimed_at` 为 nullable，无需 server_default。`downgrade()` 对应九个 `op.drop_column`。
- [ ] `session_data()` 返回新字段（`dataagent_topic_id` 改为读列）与 `result_warnings`。
- [ ] **`revise()` 的互斥条件从 `["queued","running"]` 扩展为五个活动态**：`["submitting","queued","running","waiting_input","waiting_permission"]`。同步改 `modeling.py:90` 与 `:97`。
- [ ] 跑测试与 `alembic upgrade head`。
- [ ] 提交。

**验收：** 新测试通过（含存量行回填断言）；现有测试全绿；迁移可升可降。

---

## T3 — DataAgentClient 路径、认证与分页

**产出：** 客户端能打到真实的外部 DataAgent。**本任务完成后本地开发需要外部 DataAgent。**

**涉及文件**
- 修改 `apps/api/src/ontofoundry_api/config.py`、`services/dataagent.py`
- 新增 `apps/api/src/ontofoundry_api/services/run_status.py`
- 修改 `apps/api/tests/` 现有客户端用例
- 修改 `.env.example`、`README.md`

**步骤**
- [ ] `Settings` 增加 `dataagent_api_prefix: str = "/api/v1/nl2sql"`、`dataagent_website_id: str = "ontofoundry"`、`dataagent_access_key: str = ""`。保留已有的 `dataagent_base_url`、`dataagent_agent_id`、`dataagent_request_timeout_seconds`、`dataagent_execution_mode`。
- [ ] 新建 `services/run_status.py`：实现全局约束的转换表与 `ACTIVE_RUN_STATUSES` / `TERMINAL_RUN_STATUSES`，附单元测试（七种状态 + 未知状态 → `failed`）。
- [ ] 先写失败测试（`respx` 或 `httpx.MockTransport`）：`create_topic` 打 `{base}/api/v1/nl2sql/topics`；`stream` 打 `{base}/api/v1/nl2sql/tasks/{id}/sdk-events/stream`；`agent_profile` 打 `{base}/api/v1/dataagent/agents/{id}`；四个请求头齐全；`messages()` 在 DataAgent 返回 3 页时取全。
- [ ] `DataAgentClient.__init__` 增加 `prefix`、`website_id`、`access_key`、`session_ref`。运行时路径改为 `f"{self.prefix}/..."`。
- [ ] 每次请求注入：

```python
{
    "X-ODW-Client": "widget",
    "X-ODW-Website-Id": self.website_id,
    "X-ODW-User-Id": self.session_ref,          # "ontofoundry:{workspace_id}:{session_id}"
    **({"X-ODW-Access-Key": self.access_key} if self.access_key else {}),
}
```

- [ ] 新增方法：
  - `messages(topic_id)` → `GET {prefix}/topics/{id}/messages`，**内部分页循环**（`page_size=500`，按 `seq_id` 递增取尽），返回完整列表。
  - `permission_decision(task_id, request_id, payload)` → `POST {prefix}/tasks/{id}/permission-decision`
  - `question_answer(task_id, request_id, payload)` → `POST {prefix}/tasks/{id}/question-answer`
  - `download(topic_id, rel_path)` → `(bytes, content_type)`
  - `agent_profile(agent_id)` → `GET /api/v1/dataagent/agents/{agent_id}`，**硬编码此前缀，不用 `self.prefix`**，404 抛带 `hint` 的 `DataAgentError`。
- [ ] `.env.example` 补齐六个变量与注释；删除 `DATAAGENT_DATABASE_URL`、`DATAAGENT_DATABASE_SCHEMA`；把 `ONTOFOUNDRY_DATAAGENT_BASE_URL` 的注释从 "`make dataagent-up` exposes the service locally" 改为"指向外部 OpenDataWorks DataAgent"。
- [ ] README 的本地运行章节增加一行：**从本版本起需要一个可达的外部 DataAgent**，并说明 `make dataagent-up` 起的内置服务已不再兼容（T11 会删除它）。
- [ ] 跑测试。
- [ ] 提交。

**验收：** 新旧测试全绿；`grep -rn "api/v1/agent\b" apps/api/src/ontofoundry_api` 无结果；分页测试覆盖 3 页场景。

---

## T4 — Agent Conversation BFF

**产出：** SDK 协议的六个端点可用。旧 `api/agent.py` 暂时保留，前端尚未切换。

**涉及文件**
- 新增 `apps/api/src/ontofoundry_api/api/agent_conversation.py`
- 修改 `apps/api/src/ontofoundry_api/main.py`
- 新增 `apps/api/tests/test_agent_conversation_bff.py`

**步骤**
- [ ] 先写测试（全部先失败）：设计 §12"BFF 契约"小节的十三条断言各一个测试函数，用 `httpx.MockTransport` 伪造 DataAgent。**并发那条用两个并发任务断言远端只收到一次 deliver。**
- [ ] 实现 `GET ""`：`require_member` → `get_modeling_session` → 无 `dataagent_topic_id` 时返回 `{"messages": [], "run": None}`（不创建 topic）→ 有则 `client.messages()` 取全历史 + 查当前任务，投影成 `ConversationSnapshot`。`run.metadata` 由 `dataagent_task_mode` 重建为 `{"mode": ...}`。若活动任务已终态，先调 T5 的 `reconcile_run()` 再返回。
- [ ] **`submitting` 对账**：`GET ""` 发现 `task_status='submitting'` 且 `updated_at` 超过 120 秒时，说明上一次提交在远端调用途中失败或响应丢失。此时查询该 topic 下的任务，若存在本地未记录、且提示词含本会话 `dataagent_run_token` 的任务则**认领**（写回 `dataagent_task_id`、置 `queued`）；认领不到则置 `failed` 并提示重试。**不得直接再发一个任务**——上游 deliver 没有幂等键。
- [ ] 实现 `POST /messages`，**严格按设计 §6.5 的三步顺序**：

```python
# 0. expected_revision 来自当前记录，不来自请求体
#    —— SDK 的 POST /messages 只发 {content, metadata}，没有 revision 字段
expected = item.revision

# 1. CAS 抢占（远端零副作用）
run_token = secrets.token_hex(16)
changed = db.execute(
    update(ModelingSessionRecord)
    .where(
        ModelingSessionRecord.id == item.id,
        ModelingSessionRecord.revision == expected,
        ModelingSessionRecord.task_status.not_in(ACTIVE_RUN_STATUSES),
    )
    .values(task_status="submitting", dataagent_task_mode=mode,
            dataagent_run_token=run_token, revision=expected + 1,
            updated_at=utc_now())
)
if changed.rowcount != 1:
    db.rollback()
    raise HTTPException(409, "会话正在处理或已更新，请刷新后重试")
db.commit()

# 2. 远端：create_topic（如需）→ 上传材料与上下文 → deliver

# 3. 成功：必须把 topic_id 一起写回，否则下一轮会再建一个 Topic
db.execute(update(ModelingSessionRecord)
    .where(ModelingSessionRecord.id == item.id)
    .values(task_status="queued",
            dataagent_topic_id=topic_id,          # 含本轮新建的
            dataagent_task_id=task_id,
            uploaded_material_ids=uploaded,
            task_detail="等待 DataAgent 调度",
            updated_at=utc_now()))
#    失败：task_status='failed' + task_detail（释放占位）；
#          若 topic 为本轮新建 → delete_topic；
#          若已拿到 task_id 但本地写库失败 → 补偿性 cancel(task_id)
```

  校验 `metadata.mode ∈ {"chat","model"}`（非法按 `chat`）；材料总量 > 2 GB → 422。
  **请求体模型只有 `content` 与 `metadata` 两个字段，不得出现 `revision`。**
- [ ] `build_turn_prompt` 在 `mode == "model"` 时写入 `run_token` 与结果文件路径（T5 完善提示词正文，此处先把参数打通）。
- [ ] 实现 `GET /events`：**转换而非透传**。读 `client.stream(task_id, after_id)` 的裸 `data:` 帧 → 逐条输出 `event: agent-event`；上游流结束后**先查任务状态**，仍是活动态则继续订阅（不得发 `done`）；确认终态后调 `reconcile_run()`，**再**输出 `event: done` + 终态 `RunRef`。响应头 `Cache-Control: no-cache`、`X-Accel-Buffering: no`；空闲时输出 `: ping`。
  本任务的 `reconcile_run()` 是空实现钩子，因此 **T4 只验收 `mode=chat` 路径**：`done` 的时序正确、内容正确。"done 在候选回写之后"这条语义连同建模路径的验收归 T5。
- [ ] 实现 `POST /cancel`、`POST /interactions`（按 `kind` 分派）、`GET /files/{rel_path:path}`（透传字节与 content-type）。
- [ ] `main.py` 注册新 router。
- [ ] 跑测试与 lint。
- [ ] 提交。

**验收：** 契约测试全绿（建模回写相关的三条延到 T5），**其中并发测试必须证明远端只收到一次 deliver**；"首次发送后刷新仍读到同一 Topic、第二次发送不创建 Topic"必须通过；`submitting` 超时对账测试通过；旧 `api/agent.py` 既有测试仍全绿。

---

## T5 — 自动建模结果回写

**产出：** 建模任务完成后自动产出候选项，右侧"构建产出"第一次真正接通。

**涉及文件**
- 新增 `apps/api/src/ontofoundry_api/services/model_result.py`
- 修改 `apps/api/src/ontofoundry_api/api/agent_conversation.py`（接上 `reconcile_run`）
- 修改 `apps/api/src/ontofoundry_api/services/dataagent.py`（`build_turn_prompt` 的 model 分支）
- 新增 `apps/api/tests/test_model_result.py`
- 新增 `apps/api/tests/fixtures/ontofoundry_result_v1.json`

**步骤**
- [ ] 写夹具：一份有效结果（2 个 object_type、1 个 link_type、1 个新 mapping、3 条 annotation、1 处顶层 `requires` 差异），以及六份异常输入（文件 404 / 非 JSON / `schema_version` 错 / `run_token` 不符 / Ossie schema 不通过 / 下载超时）。
- [ ] 先写测试（全部先失败）：设计 §12"结果回写"小节的十五条断言各一个测试函数。
- [ ] 实现 `reconcile_run(app, workspace_id, session_id)`：
  - 读会话；任务非终态 → 只更新 `task_status` / `task_detail` 后返回。
  - `dataagent_task_mode != "model"` → 只更新状态后返回（**普通聊天永不触碰草稿与候选**）。
  - **claim**：

```python
UPDATE modeling_sessions
   SET result_state='processing', last_result_task_id=:tid, result_claimed_at=now()
 WHERE id=:sid
   AND (   last_result_task_id IS DISTINCT FROM :tid
        OR result_state='failed_retriable'
        OR (result_state='processing' AND result_claimed_at < now() - interval '5 minutes') )
```

    `rowcount != 1` → 已处理或正在被他人处理，返回。**租约那一行不能省**：没有它，claim 之后进程崩溃会让该 task 永久停在 `processing`，既不满足"不同 task"也不是 `failed_retriable`，再也抢不到。最终写入时校验 `result_claimed_at` 仍是本次写下的值，否则说明已被接管，放弃本次结果。
  - `client.download(topic_id, f"output/ontofoundry-result-{run_token}.json")`。
    - 超时 / 连接错误 → `result_state='failed_retriable'`，草稿与候选不变，返回（**下次可重试**）。
    - 404 / 非 JSON / `schema_version` 不符 / 文件内 `run_token` ≠ 会话 `run_token` → 永久失败（`result_state='failed_permanent'`、`task_status='failed'`、具体 `task_detail`），草稿与候选不变。
  - `validate_schema(payload["ontology"])` → 不通过则永久失败。
  - `import_ossie(payload["ontology"], workspace_id=workspace_id, base=item.draft_json, mode="merge")` → `OssieImportError` 则永久失败。
  - `build_candidates(...)`；旧 `pending` 候选置 `superseded`；一次事务写 `candidates_json` + `result_warnings` + `result_state='done'` + `task_status='finished'` + `revision+1`。
- [ ] 实现 `build_candidates(before_draft, imported_draft, annotations, task_id)`：

```python
{
    "id": f"{task_id}:{kind}:{value['id']}",
    "kind": kind,                     # object_type | link_type | mapping
    "status": "pending",
    "value": value,
    "before": before_item,            # 草稿中同 id 的原值，不存在为 None
    "reason": annotation_reason,      # 匹配不到为 ""
    "evidence": annotation_evidence,  # 匹配不到为 []
    "source_task_id": task_id,
}
```

  - `object_types` / `link_types`：新增或字段有变化都产出。
  - `mappings`：**只产出新增**。`import_ossie` 的 merge 对已有 mapping 直接跳过（`importer.py:523-531`），更新候选不可能出现，不要写这个分支。
  - 不产出 `object` / `link` 候选；不产出顶层约束候选。
- [ ] 顶层差异检测：比较 `before_draft` 与 `imported_draft` 中除三个集合外的字段（本体名、描述、`requires` 等），有差异则向 `result_warnings` 追加一条"本轮结果包含顶层本体约束变更，v1 不生成候选，如需应用请手工编辑或导入 Ossie 文件"。
- [ ] `build_turn_prompt` 的 `mode == "model"` 分支写全：必须把完整 Apache Ossie 0.2.0.dev0 文档按 `ontofoundry.model-result/v1` 信封（含 `run_token` 字段，值为 `{run_token}`）写入 `output/ontofoundry-result-{run_token}.json`。
- [ ] 把 T4 的钩子接到 `reconcile_run`。
- [ ] **`failed_retriable` 不得发 `done`**：`/events` 在 reconcile 得到 `failed_retriable` 时按 2s/4s/8s 退避重试 reconcile，最多三次；三次仍失败才降级为 `failed_permanent` 并发 `done`（携带失败原因）。否则 SDK 收到终态即停止重连，"可重试"没有任何自动重试路径。
- [ ] 把 T4 延后的三条验收补上：`done` 在候选回写之后发出；建模路径的 `done` 携带 `metadata.mode='model'`；`failed_retriable` 期间不出现 `done`。
- [ ] 跑测试与 lint。
- [ ] 提交。

**验收：** 回写测试全绿，**其中"上一轮遗留文件不被误消费"、"下载超时可重试"、"claim 后进程终止再次 reconcile 仍能成功"三条是核心门禁**；生成的候选喂给现有 `accept_candidates`，接受后草稿正确更新，人工先改过同一项时命中冲突提示。

---

## T6 — 可诊断的失败与连通性检查

**产出：** DataAgent 没配好时应用照常可用，且界面告诉管理员该去哪改。

**涉及文件**
- 新增 `apps/api/src/ontofoundry_api/services/dataagent_health.py`
- 修改 `apps/api/src/ontofoundry_api/services/dataagent.py`（错误分类）
- 修改 `apps/api/src/ontofoundry_api/api/settings.py`
- 修改 `apps/web/src/pages/SettingsPage.tsx`
- 新增 `apps/api/tests/test_dataagent_diagnostics.py`

**步骤**
- [ ] 先写测试：设计 §6.9 表格的**六种**情况各断言 HTTP 状态、`message`、`hint`；再加一条：`dataagent_base_url=""` 时应用可启动且 `GET /api/v1/workspaces/{id}/ontology` 正常返回。
- [ ] `DataAgentError` 增加 `hint: str = ""`；在 `_json` 中按状态与 detail 分类填充（403 + "site is not allowed" → 站点未放行；403 + "access key" → 密钥不匹配；`agent_profile` 的 404 → Agent 不存在或不可见）。
- [ ] BFF 异常处理把 `message` 与 `hint` 一起返回。
- [ ] 新增 `GET /api/v1/workspaces/{workspace_id}/settings/dataagent-health`，返回 `{ ok, checks: [{ name, ok, message, hint }] }`，检查项：配置完整性（base_url / access_key）、连通性、站点放行、**Agent 存在性（调 `client.agent_profile(agent_id)`，即 `/api/v1/dataagent/agents/{id}`）**。
- [ ] 设置页增加只读"DataAgent 连通性"区块。**不提供任何密钥输入框。**
- [ ] 跑测试。
- [ ] 提交。

**验收：** 七条诊断测试全绿；本地把 `ONTOFOUNDRY_DATAAGENT_BASE_URL` 置空启动，本体查看/编辑/发布/MCP 全部可用，设置页明确提示未配置；把 `agent_id` 改成不存在的值，Agent 检查项报红（验证没有用 `/topics?agent_id=` 这种测不出来的方式）。

---

## T7 — DataAgent 集成包

**为什么排在前端接入之前：** T8 的验收要连真实 DataAgent 跑通"开始建模 → 出现候选"，而可用的 Agent、`md2ossie` ZIP 和安装说明都由本任务产出。放在后面会让 T8 无法验收。它同时也必须早于 T11——那一步会清理 `.claude/skills/`。

**前置：** 验收需要上游 T8 的 access key 能力。

**涉及文件**
- 新增 `integrations/dataagent/README.md`
- 移动 `.claude/skills/md2ossie/` → `integrations/dataagent/skills/md2ossie/`
- 新增 `integrations/dataagent/agents/agent_ontofoundry.md`
- 新增 `integrations/dataagent/Makefile`（打 ZIP）
- 修改仓库根 `README.md`

**步骤**
- [ ] `git mv .claude/skills/md2ossie integrations/dataagent/skills/md2ossie`；`grep -rn "\.claude/skills/md2ossie"` 逐处改引用（README 中有一处）。
- [ ] 写 `integrations/dataagent/Makefile`，一条 `zip` 目标把 `skills/md2ossie/` 打成 `dist/md2ossie.zip`，并写明 ZIP 内根目录结构（`md2ossie/SKILL.md` 的相对路径）。**管理端只接受 ZIP 上传**（`admin_routes.py:526`）。
- [ ] **`dist/` 加入 `.gitignore`——ZIP 是生成产物，不提交。** 源码目录 `skills/md2ossie/` 是唯一真相；提交二进制会产生第二份真相且 diff 不可读。README 中安装第一步就是现场 `make zip`。
- [ ] 写 `agents/agent_ontofoundry.md`：Agent 名称、系统提示词、绑定 `md2ossie` Skill、**`visibility.mode = all`**（Widget 身份不是 DataAgent 登录用户，可见性不放开会让创建 Topic 返回 `agent not found`，见 `routes.py:1046`），以及设计 §7.1 的结果文件约定与 `run_token` 占位说明。
- [ ] 写 `README.md`，按顺序写死：
  1. 管理端 → Widget 接入设置 → 新建站点 `website_id=ontofoundry`，`allowed_origins` 留空，**开启服务端接入并生成 access key（明文只显示一次）**。
  2. `make -C integrations/dataagent zip`，把 `dist/md2ossie.zip` 上传到管理端 Skill 导入。
  3. 按 `agents/agent_ontofoundry.md` 创建 Agent，`agent_id=agent_ontofoundry`，可见性设为全部可见。
  4. 在 OntoFoundry 部署环境设置六个 `ONTOFOUNDRY_DATAAGENT_*` 变量。
  5. 打开空间设置页，确认连通性检查全绿。
  6. **回滚清理**：若需回滚，按 `website_id=ontofoundry` 在管理端删除该时间窗内创建的 Topic。
- [ ] 提交。

**验收：** 一位没参与本次改造的同事只读 `integrations/dataagent/README.md` 就能在测试环境完成接入并让连通性检查全绿。

---

## T8 — 前端接入 SDK

**前置：** 上游 T7 已发布 `@opendataworks/agent-conversation@0.1.0`。

**涉及文件**
- 修改 `apps/web/package.json`、`apps/web/src/main.tsx`
- 新增 `apps/web/src/types/agent-conversation.d.ts`
- 修改 `apps/web/src/pages/BuilderPage.tsx`、`api/client.ts`、`api/types.ts`
- 新增 `apps/web/src/pages/BuilderPage.test.tsx`

**步骤**
- [ ] `npm i -E @opendataworks/agent-conversation@0.1.0 -w apps/web`。
- [ ] `main.tsx` 中 `import { defineAgentConversation } from "@opendataworks/agent-conversation"`，渲染前调用一次。**不 import 任何 CSS**（样式由元素内联注入 Shadow Root）。
- [ ] 写 `agent-conversation.d.ts`：声明 JSX 内在元素 `"dataagent-conversation"` 及其属性，并导出元素实例类型（`endpointResolver`、`transport`、`value`、`sendMessage`、`cancel`、`reload`、`focus`）。
- [ ] 先写失败测试（设计 §12"前端"小节前七条）。
- [ ] `BuilderPage.tsx`：删除消息列表渲染、输入框、发送/取消按钮、`chatEnd` 滚动 effect、`prompt` 状态、`running` 推断；保留 `scenario`、材料区、会话切换、发布入口。
- [ ] 插入 `<dataagent-conversation>`，**`endpoint` 由 `sessionId` 推导，不能依赖异步加载完成的 `session` 对象**：

```ts
// sessionId 来自 URL search param（useModeling.ts:15），切换时同步变化
const endpoint = sessionId ? conversationUrl(workspace.id, sessionId) : ""
```

  写成 `session ? ... : ""` 会让一次真实切换表现为"旧地址 → 空地址 → 新地址"（`session` 要等请求回来才更新），中间那次空值触发多余的清空与重连；`endpointResolver` 首次写回的地址也可能被下一次渲染覆盖成空。
- [ ] 通过 `ref` 设 `endpointResolver = async () => conversationUrl(workspace.id, (await model.ensure()).id)`。`ensure()` 会把新 id 写进 URL param，因此下一次渲染的 `endpoint` 自然等于 resolver 的返回值，两者不会互相覆盖。
- [ ] **会话切换只改 `endpoint`，不调 `reload()`。**
- [ ] 补测试：连续快速切换两次会话，`endpoint` 不经过空字符串；首次 `ensure()` 后立即重渲染，`endpoint` 保持为新地址。
- [ ] `composer-actions` slot 放"开始建模"，实现设计 §9.2 的 `startModeling`。
- [ ] 监听 `dataagent-run-change`：首次进入活动态 → `model.reload()`；并用它驱动宿主的 busy/禁用态。
- [ ] 监听 `dataagent-complete`：**任意终态都 `model.reload()`**；仅 `metadata.mode === "model"` 时额外聚焦候选区。
- [ ] 删除 `modelingApi.chat` / `cancel` / `sync` 与 `ModelingSession.messages` 类型；增加 `result_warnings: string[]`。
- [ ] 跑 `npm test -w apps/web`，`ModelResults` 与材料区既有测试必须全绿。
- [ ] 提交。

**验收：** 前端测试全绿；连真实 DataAgent 手工走通"上传材料 → 普通问答 → 开始建模 → 右侧出现候选"，且发送后保存草稿不报 409（验证 revision 已同步）。

---

## T9 — mapping 候选与结果提示

**涉及文件**
- 修改 `apps/web/src/api/types.ts`、`components/ModelResults.tsx`、`components/ModelResults.test.tsx`

**步骤**
- [ ] `Candidate` 联合类型增加 `| { kind: "mapping"; value: DataMapping }`（**类型名是 `DataMapping`，已存在于 `types.ts:171`；不存在 `MappingDefinition`**），公共部分增加 `before?: unknown`、`source_task_id?: string`。
- [ ] 先写失败测试：给 `ModelResults` 一个 mapping 候选，断言渲染出 `connection_alias`、表名、`key_column`，点击接受时 `onCandidate([id], "accept")` 被调用；再断言 `result_warnings` 非空时候选区上方出现提示。
- [ ] `ModelResults` kind 切换栏增加"映射"页签。**`DataMapping` 没有 `name` 字段**，卡片展示 `connection_alias`、`schema_name`/`table_name`、`key_column`，以及 `type_id` 对应的对象类型名；reason 与 evidence 复用现有渲染。
- [ ] 候选区上方渲染 `result_warnings` 每条一行。
- [ ] 跑测试。
- [ ] 提交。

**验收：** 新测试通过；现有 `ModelResults.test.tsx` 全绿；object_type / link_type 页签展示无变化。

---

## T10 — 删除旧会话实现与 `messages_json`

**涉及文件**
- 删除 `apps/api/src/ontofoundry_api/api/agent.py` 及其测试
- 删除 `apps/web/src/components/AgentStream.tsx`、`apps/web/src/lib/dataagentStream.ts`、`dataagentStream.test.ts`
- 修改 `db_models.py`、`api/modeling.py`、`services/dataagent.py`、`main.py`
- 新增 `alembic/versions/20260921_000002_drop_messages_json.py`

**步骤**
- [ ] 删除 `api/agent.py`，从 `main.py` 移除注册；删除对应测试。
- [ ] 删除 `services/dataagent.py` 中的 `topic_id_from_messages`、`task_id_from_messages`、`uploaded_material_ids`，以及 `public_answer` 等已无引用的符号。**逐个 `grep` 确认无引用后再删。**
- [ ] `ModelingSessionRecord` 删除 `messages_json`；`session_data()` 删除 `messages` 键。
- [ ] 写 `20260921_000002`，`down_revision = "20260921_000001"`：`op.drop_column("modeling_sessions", "messages_json")`；`downgrade()` 重建为空数组列，docstring 写明**内容不可恢复**。
- [ ] 删除前端两个文件，`grep -rn "AgentStream\|dataagentStream" apps/web/src` 清零。
- [ ] 跑后端与前端全量测试、lint。
- [ ] 提交。

**验收：** 全量测试与 lint 通过；`grep -rn "messages_json" apps/` 只剩迁移文件。

---

## T11 — 删除内置 DataAgent、Pi Runtime 与配套部署

**这是最后一个任务。** 完成后仓库内不再有 DataAgent 实现。

**涉及文件**
- 删除 `apps/api/src/dataagent_backend/`、`apps/api/tests/dataagent/`、`dataagent/`
- 修改 `main.py`、`package.json`、`Makefile`、`compose.yaml`、`apps/api/Dockerfile`、`apps/api/pyproject.toml`、`README.md`
- 新增 `alembic/versions/20260921_000003_drop_dataagent_tables.py`

**步骤**
- [ ] `main.py` 删除 `from dataagent_backend.app import ...` 与三处调用。
- [ ] 删除 `apps/api/src/dataagent_backend/`、`apps/api/tests/dataagent/`、`dataagent/` 整个目录。
- [ ] 根 `package.json` 的 `workspaces` 移除 `dataagent/dataagent-runtime-pi`，`description` 相应修改。
- [ ] `Makefile` 删除 `dataagent-build`、`dataagent-images`、`dataagent-test`；`dataagent-up` / `dataagent-down` 改名 `compose-up` / `compose-down` 并只起 `postgres` + `of-backend` + `of-frontend`；`test` / `lint` 删除 `@ontofoundry/agent-runtime-pi` 相关行。
- [ ] `compose.yaml` 删除 `dataagent-redis`、`of-runner` 与卷 `ontofoundry-dataagent-runtime`；`of-backend` 删除 `/dataagent_runtime` 与 `./dataagent/.claude/skills` 挂载；健康检查从 `/api/v1/agent/health` 改为 OntoFoundry 自己的健康端点。
- [ ] `apps/api/Dockerfile` 删除 `pi-cell` 与 `runner` 两个 stage。
- [ ] `pyproject.toml` 逐个核实并删除无引用依赖。**`psycopg` 必须保留。** 删除后 `uv sync` 并 `uv run python -c "import ontofoundry_api.main"` 确认无 ImportError。
- [ ] 写 `20260921_000003`，`down_revision = "20260921_000002"`。**删除顺序直接复用 baseline `downgrade()` 的前 15 项**（`20260913_000001_postgresql_baseline.py:586` 起），该顺序已经是外键安全的反向序：

```python
for table in (
    "da_mcp_server", "da_model_provider", "da_agent_widget_event",
    "da_agent_message_schedule_log", "da_agent_message_schedule",
    "da_agent_message_queue", "da_agent_event_record", "da_agent_chunk",
    "da_agent_message", "da_agent_task", "da_agent_topic",
    "da_agent_profile", "da_skill_document_version", "da_skill_document",
    "da_agent_settings",
):
    op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
```

  `downgrade()` 抛 `NotImplementedError("da_* 表删除不可逆，回滚请恢复数据库备份")`。
- [ ] `README.md`：本地运行前置改为"需要一个可达的 OpenDataWorks DataAgent"，补六个环境变量说明，删除 `make dataagent-up` 段落与 Pi runtime 描述，md2ossie 链接指向 `integrations/dataagent/skills/md2ossie/`。
- [ ] 跑全量测试、lint、`docker compose config`、一次完整镜像构建。
- [ ] 提交。

**验收：** `uv sync` 干净；全量测试与 lint 通过；`docker compose up` 只起三个服务且应用健康；`grep -rn "dataagent_backend\|agent-runtime-pi\|dataagent-redis\|of-runner" . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=docs` 无结果。

---

## 合并前一次性验证清单

- [ ] `cd apps/api && uv run --python 3.13 pytest -q`
- [ ] `cd apps/api && uv run --python 3.13 ruff check src tests`
- [ ] `npm ci && npm test -w apps/web && npm run build -w apps/web`
- [ ] 在**含真实数据的库副本**上 `alembic upgrade head`，逐项核对：领域表行数不变；九个新列存在且非空列已回填；`dataagent_topic_id` 全 NULL；`messages_json` 不存在；15 张 `da_*` 表全部不存在
- [ ] `docker compose config` + 完整镜像构建 + `docker compose up` 三服务健康
- [ ] `grep -rn "api/v1/agent\b\|agent-events/stream" apps/ --exclude-dir=node_modules` 无结果
- [ ] 端到端手工冒烟（设计 §12"端到端"流程）全部通过

## 发布与回滚

发布顺序见设计 §13 的九步表。两个硬门禁：

1. **第 5 步进入只读维护窗口**，从备份开始到冒烟通过结束。回滚手段是整库恢复，窗口内若允许编辑/发布/上传，这些领域写入会被一并回滚掉。
2. **第 6 步备份数据库。** `20260921_000003` 删除 `da_*` 表不可逆，`downgrade()` 直接抛错。

回滚 = 恢复备份 + 部署旧镜像 + 按 `website_id=ontofoundry` 清理该时间窗内在外部 DataAgent 上创建的 Topic（本地数据库恢复不会删除它们）。发布窗口前必须与运维确认备份可用且恢复流程演练过。
