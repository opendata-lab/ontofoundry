# OntoFoundry 移除内置 Agent，接入 DataAgent Conversation SDK

**日期:** 2026-09-21
**涉及栈:** FastAPI 后端、React 前端、Alembic 迁移、Docker Compose
**配套文档:** `docs/plans/2026-09-21-dataagent-conversation-sdk-integration-plan.md`
**上游依赖:** OpenDataWorks 仓库 `docs/design/2026-09-21-agent-conversation-sdk-design.md`
**取代:** `docs/design/2026-09-16-merge-dataagent-into-ontofoundry.md` 所确立的"同进程合并"形态（该文档保留为历史记录）

## 1. 背景与定位

| 平台 | 拥有 | 不拥有 |
| --- | --- | --- |
| OpenDataWorks | 数据源、元数据、存储、加工、查询、任务、数据权限、数据 MCP | 本体版本真相 |
| OntoFoundry | 业务概念、本体草稿、候选项、版本、发布、语义映射、本体 API/MCP | 通用会话运行时、模型 Provider、Skill 市场、沙箱 |
| DataAgent | 会话、Topic、Task、AgentEvent、Agent、Skill、MCP registry、模型、运行隔离 | 数据权限真相、本体版本真相 |

**OpenDataWorks 管数据，OntoFoundry 管数据的业务含义，DataAgent 用智能体把两者组织起来。**

OntoFoundry 是独立的领域产品和数据边界，**但不是独立的 Agent 技术栈**。

## 2. 现状

`2026-09-16` 的合并把 DataAgent 后端整体复制进了本仓库：

| 事实 | 位置 |
| --- | --- |
| DataAgent 后端 16,541 行 Python 挂进同一个 FastAPI 进程 | `apps/api/src/dataagent_backend/`，由 `main.py:24` 的 `include_dataagent_routes` / `start_dataagent` / `stop_dataagent` 挂载 |
| 分叉后的路由前缀是 `/api/v1/agent`，事件流是 `/agent-events/stream` | `dataagent_backend/api/routes.py:80,596` |
| Pi TypeScript 运行时在仓库内，且是根 npm workspace 成员 | `dataagent/dataagent-runtime-pi/` |
| 仓库内**唯一**的 Alembic 链属于 DataAgent | `dataagent_backend/alembic.ini`；`20260913_000001_postgresql_baseline` 同时建 11 张 OntoFoundry 表与 15 张 `da_*` 表 |
| 部署需要 Redis、runner 容器和宿主 docker socket | `compose.yaml` 的 `dataagent-redis`、`of-runner`、卷 `ontofoundry-dataagent-runtime` |
| 前端自制了一套流式会话 | `components/AgentStream.tsx`（119 行）、`lib/dataagentStream.ts`（219 行）、`pages/BuilderPage.tsx`（476 行）中的消息列表与输入框 |
| 聊天记录双写在本体库里 | `ModelingSessionRecord.messages_json`；topic/task id 从消息数组反查（`services/dataagent.py:36,44`） |
| BFF 已存在 | `api/agent.py`：`POST /messages`、`POST /sync`、`GET /events`、`POST /cancel` |
| 示例配置指向本机内置服务 | `.env.example:25` `ONTOFOUNDRY_DATAAGENT_BASE_URL=http://127.0.0.1:8900` |

### 2.1 必须先说清的现状缺口

**当前没有任何代码把 Agent 的产出写回候选项。** `candidates_json` 在全仓库只有两处触碰：`session_data()` 读出来给前端（`api/modeling.py:67`），`accept_candidates()` 改状态并合并进草稿（:299-342）。**没有任何生产者。**

今天的"自动建模"实际停在：Agent 回答一段文本，附件挂在聊天区，人再手工操作。右侧候选确认逻辑是完整的，但上游没接上。

因此本次不只是换 UI——要让工作台真正闭环，必须补上"建模任务 → OSSIE 结果 → 候选项"这一段。

## 3. 问题

1. **依赖方向反了。** OntoFoundry 进程拥有并启动 DataAgent，DataAgent 的默认 Agent profile 又硬编码了 OntoFoundry 与 `md2ossie`。
2. **Agent 能力在做第二遍**，且只覆盖一个子集——没有工具调用展示、权限确认、Agent 提问、附件预览。
3. **部署代价与本体平台不匹配。** 为跑 Agent 引入了 Redis、挂宿主 docker socket 的 runner 容器和 TS 运行时构建链。
4. **聊天有两份真相。** `_sync_dataagent`（`api/agent.py:67-143`）用手写状态机对账，DataAgent 侧语义一变就要再实现一次。
5. **自动建模未闭环。** 见 2.1。

## 4. 目标与非目标

### 目标

- 删除本仓库内的 DataAgent 后端与 Pi 运行时，改为通过同源 BFF 访问**外部**的 OpenDataWorks DataAgent。
- 中间会话区替换为 `@opendataworks/agent-conversation` 的 `<dataagent-conversation>`，删除自制 `AgentStream` 与 `dataagentStream` reducer。
- **自动建模页左侧（材料 / 业务场景 / 数据源）与右侧（`ModelResults`）的布局与交互保持不变。**
- 补上"建模任务 → 候选项"的回写闭环。
- DataAgent 成为聊天与运行记录的唯一权威来源。

### 非目标

- 不改本体领域模型、Ossie 编译器/校验器/导入器的语义。
- 不引入 launch token 或独立 integration 身份协议。
- 不把数据连接与凭据下沉到 OpenDataWorks。
- 不新增"顶层本体约束"候选类型（理由见 §7.5）。

## 5. 目标架构

```text
浏览器（只认识 OntoFoundry）
  └─ BuilderPage（左：材料/场景 · 中：<dataagent-conversation> · 右：ModelResults）
        │ 同源
        ▼
OntoFoundry API（FastAPI，单进程）
  ├─ 本体领域：草稿、候选、版本、发布、Ossie、MCP
  └─ Agent Conversation BFF ──── 服务端调用，带 access key ────▶ OpenDataWorks DataAgent
```

浏览器不知道 DataAgent 的地址，也拿不到任何 DataAgent 凭据。

## 6. Agent Conversation BFF

### 6.1 路由

基址：`/api/v1/workspaces/{workspace_id}/sessions/{session_id}/agent-conversation`

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `""` | — | `{ messages: [...], run: RunRef \| null }` |
| POST | `/messages` | `{ content, metadata }` | `RunRef` |
| GET | `/events` | `?after_id=` | SSE，格式见 6.3 |
| POST | `/cancel` | `{ task_id }` | `RunRef` |
| POST | `/interactions` | `{ task_id, kind, request_id, payload }` | `{ "ok": true }` |
| GET | `/files/{rel_path:path}` | — | 二进制 |

全部端点先 `require_member(db, workspace_id, user.id)`，再 `get_modeling_session(db, workspace_id, session_id)`。

`api/agent.py` 现有的四个端点全部删除。`/sync` 不再需要——任务状态由 SDK 经 `/events` 与 `GET ""` 获取，服务端不再维护消息投影状态机。

### 6.2 到 DataAgent 的映射

**外部 DataAgent 的运行时前缀是 `/api/v1/nl2sql`，事件流是 `/sdk-events/stream`**（`opendataworks/.../api/routes.py:76,594`），与本仓库分叉的 `/api/v1/agent`、`/agent-events/stream` 不同。沿用旧路径会全线 404。

| BFF 操作 | DataAgent 端点 |
| --- | --- |
| 创建 topic | `POST {prefix}/topics` |
| 读历史（**必须分页取全**） | `GET {prefix}/topics/{topic_id}/messages` |
| 上传材料/上下文 | `POST {prefix}/topics/{topic_id}/files` |
| 读结果文件 | `GET {prefix}/topics/{topic_id}/files/{rel_path}` |
| 提交任务 | `POST {prefix}/tasks/deliver-message` |
| 查任务 | `GET {prefix}/tasks/{task_id}` |
| 取终态消息 | `GET {prefix}/tasks/{task_id}/message` |
| 事件流 | `GET {prefix}/tasks/{task_id}/sdk-events/stream?after_id=` |
| 取消 | `POST {prefix}/tasks/{task_id}/cancel` |
| 权限确认 | `POST {prefix}/tasks/{task_id}/permission-decision` |
| 回答提问 | `POST {prefix}/tasks/{task_id}/question-answer` |

`{prefix}` 由配置提供，默认 `/api/v1/nl2sql`（历史上变更过，写死会让一次上游重命名变成本仓库的故障）。

**Agent 存在性查询是例外：** `GET /api/v1/dataagent/agents/{agent_id}`（`admin_routes.py:95,428`），前缀与运行时不同，**不套用 `{prefix}` 配置**。它在 `agents_public_router` 上，无 admin 依赖，Agent 不存在或不可见时返回 404。`GET {prefix}/topics?agent_id=` 只过滤已有 Topic，Agent 不存在时也返回 200 空数组，**不能**用作存在性检查。

历史消息接口默认 `page_size=200`、上限 500（`models/schemas.py:684`），BFF 必须循环取全，否则长会话静默截断。

### 6.3 任务状态与 SSE 线格式

**状态转换表（写死，依据 `core/task_status.py:17,23`）：**

| DataAgent `task_status` | SDK `RunStatus` |
| --- | --- |
| `waiting` | `queued` |
| `running` | `running` |
| `waiting_input` | `waiting_input` |
| `waiting_permission` | `waiting_permission` |
| `finished` | `finished` |
| `error` | `failed` |
| `suspended` | `cancelled` |
| 任务不存在 | `failed` |

活动态是前四个。**本地 `task_status` 列、编辑互斥条件、发布互斥条件必须覆盖全部四个活动态**，不能只判 `running`。现有 `revise()`（`api/modeling.py:89`）只排除 `queued/running`，需要一并扩展。

**SSE 不得字节透传。** DataAgent 原生流是无事件名的裸 `data:` 帧、靠 EOF 终止；SDK 需要显式终态。BFF 必须转换为：

```
event: agent-event
data: {"seq_id":12,"...":"原始事件记录"}

: ping

event: done
data: {"task_id":"t-1","status":"finished","detail":"...","metadata":{"mode":"model"}}
```

**`done` 必须在 BFF 完成候选回写之后才发出。** 这样前端收到 `dataagent-complete` 时刷新右侧一定能看到新候选，不需要额外的轮询或延迟重试。

### 6.4 身份与隔离

```
X-ODW-Client: widget
X-ODW-Website-Id: {ONTOFOUNDRY_DATAAGENT_WEBSITE_ID}
X-ODW-User-Id: ontofoundry:{workspace_id}:{session_id}
X-ODW-Access-Key: {ONTOFOUNDRY_DATAAGENT_ACCESS_KEY}
```

`X-ODW-User-Id` 用**建模会话**而非终端用户作标识，这是必须的：DataAgent 的可见性过滤是 `source='widget' AND website_id=? AND external_user_id=?`（`topic_task_store.py:446`）。填真实用户 ID，同一建模会话就无法被空间内第二个成员打开。真正的权限判断在 BFF 的 `require_member`。

`X-ODW-Access-Key` 依赖上游新增的站点服务端接入能力。没有它，任何能连到 DataAgent 的进程只要知道 `website_id` 就能创建会话——`_origin_allowed` 对空 `Origin` 无条件放行，而服务端调用恰好不带 `Origin`。

### 6.5 会话与任务生命周期

- 一个 Modeling Session 固定绑定一个 DataAgent Topic（1:1），一个 Topic 下多个 Task（1:N）。
- Topic **惰性创建**：只在首次发送消息时创建，避免进入页面就产生空会话。
- 同一会话同时最多一个活动任务。

**并发控制顺序是关键。** 现有 `api/agent.py` 的做法是先向远端上传并 `deliver`（:208），之后才做本地条件更新（:232）——两个并发请求都可能在远端成功建任务，最后只有一个写入本地，另一个成为仍在运行的**孤儿任务**。新实现必须反过来：

```text
1. CAS 抢占：UPDATE modeling_sessions
              SET task_status='submitting', dataagent_run_token=:token, revision=revision+1
            WHERE id=:sid AND revision=:expected AND task_status NOT IN
                  ('submitting','queued','running','waiting_input','waiting_permission')
   rowcount != 1 → 409，不发生任何远端副作用
   （:expected 由 BFF 读当前记录得到，不来自请求体——SDK 不发送 revision）
2. 远端：创建 topic（如需）→ 上传材料与上下文 → deliver
3. 成功：UPDATE ... SET task_status='queued',
                        dataagent_topic_id=:topic,     ← 必须写，含本轮新建的
                        dataagent_task_id=:task,
                        uploaded_material_ids=:uploaded
   失败：UPDATE ... SET task_status='failed', task_detail=…   （释放占位）
        若 topic 是本轮新建 → delete_topic
```

`submitting` 是新增的活动状态，必须纳入所有互斥条件。

**第 3 步必须持久化 `dataagent_topic_id`**（包括本轮新建的）。漏掉它的后果是：首次发送成功后本地仍认为没有 Topic，下一轮发送会再建一个，历史也读不到——一个会话会散成多个 Topic。

**这个方案消除了什么，没消除什么。** 说清楚边界比声称"无孤儿"重要：

| 故障 | 是否消除 |
| --- | --- |
| 两个并发请求同时 deliver，产生两个远端任务 | **已消除**（CAS 在远端副作用之前） |
| deliver 已被远端接受但响应丢失/超时 | **未消除** |
| deliver 返回成功但第 3 步本地写库失败 | **未消除** |
| 释放占位后用户重试，产生第二个远端任务 | **未消除**（上游 deliver 无幂等键） |
| 本轮新建 topic 的 `delete_topic` 调用失败 | **未消除** |

后四种属于分布式不确定性，单靠本地 CAS 解决不了。v1 的处理是**对账而非预防**：

- `GET ""` 发现本地处于 `submitting` 且超过 `submitting` 超时阈值（120 秒）时，向 DataAgent 查询该 topic 下的任务列表，若存在本地未记录、且其提示词含本会话 `run_token` 的任务，则**认领**它（写回 `dataagent_task_id`、置 `queued`），而不是再发一个。
- 认领不到则置 `failed` 并提示用户重试。
- 第 3 步写库失败时，BFF 必须补偿性地 `cancel` 已拿到的 task_id；补偿失败只记日志，由上面的对账兜底。

`run_token` 在这里同时充当了**弱幂等键**——它写在提示词里，可被检索。真正的幂等提交需要上游为 deliver 增加幂等键与按键查询能力，那是独立的上游变更，不在本次范围。

### 6.6 材料与上下文上传

状态从 `messages_json` 搬到显式列：

- `uploaded_material_ids` 记录已上传到该 topic 的材料 ID，逐个幂等跳过。
- 每轮上传当前草稿快照 `ontofoundry-context-r{revision}.json`。
- 材料总量超过 2 GB 拒绝（沿用 `api/agent.py:161-163`）。

### 6.7 轮次提示词与 run_token

`build_turn_prompt` 保留，触发方式改为读 `metadata.mode`（`metadata` 来自浏览器，是不可信输入；只接受 `mode ∈ {"chat","model"}`，其余键忽略，非法值按 `chat`）。

**BFF 在 deliver 之前生成 `run_token`**（16 字节随机 hex），写入提示词并持久化到会话。

- `mode == "model"`：建模请求。提示词强制要求把完整 Ossie 结果按 §7.1 的信封写入 `output/ontofoundry-result-{run_token}.json`。
- `mode == "chat"`：普通对话，明确不要生成或覆盖本体文件。

`run_token` 的作用见 §7.3。

### 6.8 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ONTOFOUNDRY_DATAAGENT_BASE_URL` | `""` | 外部 DataAgent 地址。空表示未配置 |
| `ONTOFOUNDRY_DATAAGENT_API_PREFIX` | `/api/v1/nl2sql` | 运行时路由前缀 |
| `ONTOFOUNDRY_DATAAGENT_WEBSITE_ID` | `ontofoundry` | Widget 站点标识 |
| `ONTOFOUNDRY_DATAAGENT_ACCESS_KEY` | `""` | 服务端接入密钥 |
| `ONTOFOUNDRY_DATAAGENT_AGENT_ID` | `agent_ontofoundry` | 建模 Agent |
| `ONTOFOUNDRY_DATAAGENT_REQUEST_TIMEOUT_SECONDS` | `30` | 非流式请求超时 |

沿用现有 `Settings` 的 `dataagent_*` 字段命名。

**应用不得因 DataAgent 不可用而启动失败。** 本体的查看、编辑、版本、发布、MCP 都不依赖 Agent。

### 6.9 可诊断的失败

错误响应统一 `{ "message": ..., "hint": ... }`。六种情况：

| 情况 | HTTP | message | hint |
| --- | --- | --- | --- |
| `base_url` 为空 | 503 | DataAgent 未配置 | 设置 `ONTOFOUNDRY_DATAAGENT_BASE_URL` 后重启 |
| 连接失败 | 503 | 无法连接 DataAgent | 检查地址与网络连通性；当前地址 `{base_url}` |
| 403 站点未放行 | 502 | DataAgent 拒绝了本站点 | 在管理端 → Widget 接入设置中放行 `website_id={website_id}` |
| 403 密钥不匹配 | 502 | DataAgent 拒绝了服务端接入密钥 | 在管理端重新生成密钥并更新 `ONTOFOUNDRY_DATAAGENT_ACCESS_KEY` |
| Agent 不存在或不可见 | 502 | DataAgent 上找不到该 Agent | 创建 `agent_id={agent_id}`、安装 `md2ossie` Skill，并确认其可见性允许 Widget 访问 |
| 访问密钥缺失（本地未配） | 503 | 未配置服务端接入密钥 | 设置 `ONTOFOUNDRY_DATAAGENT_ACCESS_KEY` |

同一组诊断在空间设置页以只读连通性检查呈现（`GET /api/v1/workspaces/{id}/settings/dataagent-health`），Agent 一项用 §6.2 的 `/api/v1/dataagent/agents/{agent_id}` 探测。**设置页不提供密钥写入**——凭据由部署环境注入，不进数据库、不经浏览器。

## 7. 自动建模结果回写

本次唯一的新增业务能力，风险最高。原则：**DataAgent 只负责提出方案，OntoFoundry 始终掌握校验、冲突检测和人工接受。Agent 在任何情况下都不能直接改写草稿或发布版本。**

### 7.1 结果契约

```json
{
  "schema_version": "ontofoundry.model-result/v1",
  "run_token": "9f2a…",
  "ontology": { "...": "完整的 Apache Ossie 0.2.0.dev0 文档" },
  "annotations": [
    {
      "target": { "kind": "object_type", "key": "Customer" },
      "reason": "材料中反复出现的核心业务实体",
      "evidence": [
        { "material_id": "m-1", "line_start": 12, "line_end": 18, "quote": "客户是……" }
      ]
    }
  ]
}
```

文件路径：`output/ontofoundry-result-{run_token}.json`。

- `ontology` 是**完整模型**而非差异。`md2ossie` 天然产出完整 Ossie JSON；完整模型可以直接过 `validate_schema` 与 `import_ossie`，复用已被测试锁定的路径。
- `annotations` 是可选解释层，`target.key` 用 Ossie 文档中的概念名，匹配不上的条目忽略（只丢失理由展示）。
- `evidence[]` 结构与前端 `Evidence` 类型一致（`types.ts:151`）。

### 7.2 消费时机

只有 `mode == "model"` 的任务到达成功终态时才消费。普通聊天任务**永不触碰草稿或候选**。

触发入口有二，共用同一个函数：

1. `/events` 的 SSE 流读到 DataAgent 终态后、发出 `event: done` 之前（主路径）。
2. `GET ""` 发现活动任务已终态时（刷新页面 / 流中断后的兜底）。

### 7.3 为什么需要 run_token

同一 Topic 的多轮任务**共享工作区与文件名空间**。若结果文件用固定名 `output/ontofoundry-result.json`，那么"新任务成功结束但没写文件"时，上一轮的旧文件仍在，会被当作本轮结果消费，静默产出错误候选。

`run_token` 由 BFF 在 deliver 前生成并写进提示词，消费时只读 `output/ontofoundry-result-{run_token}.json`，并校验文件内 `run_token` 字段与之一致。两处不匹配即判定本轮没有产出结果。

### 7.4 处理流水线与幂等

```text
claim：UPDATE modeling_sessions SET result_state='processing', last_result_task_id=:tid
       WHERE id=:sid AND (last_result_task_id IS DISTINCT FROM :tid OR result_state='failed_retriable')
       rowcount != 1 → 已被处理或正在处理，直接返回
  ↓
下载 output/ontofoundry-result-{run_token}.json
  ↓ 网络错误/超时 → result_state='failed_retriable'，返回（下次可重试）
  ↓ 404 / 非 JSON / schema_version 不符 / run_token 不符 → 永久失败（见 7.7）
validate_schema(ontology)              Ossie 官方 Schema
  ↓ 不通过 → 永久失败
import_ossie(ontology, workspace_id=…, base=draft_json, mode="merge")
  ↓ OssieImportError → 永久失败
diff(draft_json, imported_draft) → 候选项
附加 reason / evidence
旧 pending 候选标记 superseded
  ↓
一次事务写入：candidates_json + result_state='done' + revision+1 + task_status='finished'
```

**关键点一：`result_state` 区分 `processing` / `done` / `failed_retriable` / `failed_permanent`。** 可重试的网络错误不得把任务永久标记为已处理——否则一次下载超时就让这轮建模结果永久丢失。

**关键点二：`processing` 必须带租约。** 只靠 `last_result_task_id IS DISTINCT FROM :tid` 抢占，一旦进程在 claim 之后崩溃，该记录会永久停在 `processing`——既不满足"不同 task"也不是 `failed_retriable`，再也抢不到。因此增加 `result_claimed_at` 列，claim 条件扩展为：

```sql
WHERE id = :sid
  AND (   last_result_task_id IS DISTINCT FROM :tid
       OR result_state = 'failed_retriable'
       OR (result_state = 'processing' AND result_claimed_at < now() - interval '5 minutes') )
```

最终写入时校验 `result_claimed_at` 仍是本次 claim 写下的值，否则说明已被另一个执行者接管，放弃本次结果。

**关键点三：`failed_retriable` 时不得发 `done`。** 否则 SDK 收到终态就停止重连，"可重试"没有任何自动重试路径，只能靠用户手动刷新。规则：`/events` 在 reconcile 得到 `failed_retriable` 时，**按 2s/4s/8s 退避重试 reconcile**，最多三次；三次仍失败则降级为 `failed_permanent` 并发 `done`（携带失败原因），让用户看到明确结果而不是无限转圈。

### 7.5 候选项生成规则

比较 `item.draft_json` 与 `import_ossie` 输出：

| 集合 | 候选 `kind` | 规则 |
| --- | --- | --- |
| `object_types` | `object_type` | 新增，或已有项字段有变化 |
| `link_types` | `link_type` | 同上 |
| `mappings` | `mapping` | **仅新增**（见下） |

**mapping 只产出新增候选。** `import_ossie` 的 merge 语义对已有 mapping 直接跳过（`importer.py:523-531`：`if type_id is None or type_id in mapped: continue`），因此"mapping 字段变化"在 merge 结果里根本不会出现。若将来需要更新候选，必须先改 importer 的 merge 语义并补回归测试，属独立变更。

候选结构（与 `accept_candidates` 的读取方式严格对齐）：

```json
{
  "id": "{task_id}:{kind}:{value_id}",
  "kind": "object_type",
  "status": "pending",
  "value": { "...": "导入后的定义" },
  "before": { "...": "草稿中同 id 的定义，不存在时为 null" },
  "reason": "",
  "evidence": [],
  "source_task_id": "t-123"
}
```

- `id` 确定性构造而非 `uuid4`，使重复消费同一 task 不可能产生重复候选。
- `before` 是**必需**的：`accept_candidates` 用 `current != candidate.get("before") and current != value` 判定"模型已被手工修改"（`modeling.py:327`）。缺了它所有接受操作都会误判为冲突。
- **不生成 `object` / `link`（实例）候选。** 自动建模产出类型层模型；实例导入是另一条链路。
- **不生成顶层本体约束候选。** `accept_candidates` 的 `collection` 映射表没有对应键，新 kind 会走进 `if not key: continue` 被静默丢弃。

**顶层差异的处理：本次完全忽略，并产生一条 warning。** `import_ossie` 会把 `requires` 等顶层构造合入 imported draft（`importer.py:594`），而 diff 只看三个集合——不写清楚就会静默丢失。因此回写结果中附带 `result_warnings: string[]`，当检测到顶层差异时写入一条"本轮结果包含顶层本体约束变更，v1 不生成候选，如需应用请手工编辑或导入 Ossie 文件"。该字段随 `session_data()` 返回，前端在右侧候选区上方以一行提示展示。这是一条**有数据通道的**承诺，不是空头说明。

### 7.6 替代与冲突

- 新一轮建模成功后，该会话内所有 `status == "pending"` 的旧候选置为 `superseded`。已 `accepted` / `ignored` 的保留不动。
- `ModelResults` 只渲染 `status == "pending"` 的候选（`ModelResults.tsx:53`），因此 `superseded` 自动从界面消失。
- 冲突检测完全沿用 `accept_candidates` 既有逻辑。

### 7.7 失败语义

| 情况 | 分类 | 行为 |
| --- | --- | --- |
| 下载超时 / 连接错误 | 可重试 | `result_state='failed_retriable'`，草稿与候选不变；`/events` 按 2s/4s/8s 重试三次，仍失败才降级为永久失败并发 `done` |
| claim 后进程崩溃 | 可恢复 | `result_claimed_at` 租约 5 分钟后过期，下次 reconcile 可重新抢占 |
| 结果文件 404 | 永久 | `task_status='failed'`，`task_detail`="建模任务没有产出 `output/ontofoundry-result-{run_token}.json`" |
| 非 JSON / `schema_version` 不符 / `run_token` 不符 | 永久 | 同上，附具体原因 |
| `validate_schema` 不通过 | 永久 | 同上，附第一条 schema 错误 |
| `OssieImportError` | 永久 | 同上，附异常消息 |
| **任意一种失败** | — | **草稿与候选一律不变**，用户可直接重试 |

## 8. 数据模型变更

`ModelingSessionRecord`（`db_models.py:94`）：

| 变更 | 列 | 类型 | 说明 |
| --- | --- | --- | --- |
| 新增 | `dataagent_topic_id` | `String(64)` nullable | 绑定的 Topic |
| 新增 | `dataagent_task_id` | `String(64)` nullable | 当前/最近一次任务 |
| 新增 | `dataagent_task_mode` | `String(8)` NOT NULL，server_default `''` | `chat` / `model` |
| 新增 | `dataagent_run_token` | `String(32)` nullable | 本轮结果文件令牌 |
| 新增 | `uploaded_material_ids` | `JSON` NOT NULL，server_default `'[]'` | 已上传到 topic 的材料 |
| 新增 | `last_result_task_id` | `String(64)` nullable | 已消费/在消费的建模结果任务 |
| 新增 | `result_state` | `String(20)` NOT NULL，server_default `''` | `processing` / `done` / `failed_retriable` / `failed_permanent` |
| 新增 | `result_claimed_at` | `DateTime(timezone=True)` nullable | 回写租约时间戳，用于回收崩溃留下的 `processing` |
| 新增 | `result_warnings` | `JSON` NOT NULL，server_default `'[]'` | §7.5 的顶层差异提示 |
| 删除 | `messages_json` | — | 聊天不再双写 |
| 保留 | `task_status`、`task_detail` | — | 运行状态投影；`task_status` 新增 `submitting` 取值 |

**非空列必须带 `server_default` 回填存量行**，否则存量记录为 NULL，与 `Mapped[str]` / `Mapped[list]` 及后续迭代逻辑冲突（现有表全部非空，见 baseline:148）。三个 ID 类字段保持 nullable。

`services/dataagent.py` 中 `topic_id_from_messages`、`task_id_from_messages`、`uploaded_material_ids` 三个反查函数随 `messages_json` 一并删除。

`session_data()` 不再返回 `messages`，改为返回上述显式字段与 `result_warnings`。前端 `ModelingSession` 类型同步去掉 `messages`。

### 8.1 迁移

Alembic 所有权必须先转移：仓库内唯一的迁移链在 `dataagent_backend/alembic/`，而该目录要被删除。

1. 把 `alembic.ini` 与 `alembic/` 移到 `apps/api/src/ontofoundry_api/`，**revision ID 保持原样**（`20260913_000001`、`20260916_000001`），使已部署库的 `alembic_version` 仍能对上。
2. `env.py` 改为指向 `ontofoundry_api.database.Base` 与 `ontofoundry_api.config.Settings`。
3. **三个新 revision，线性链，与实施计划逐字一致：**

| revision | down_revision | 内容 | downgrade |
| --- | --- | --- | --- |
| `20260921_000001` | `20260916_000001` | `modeling_sessions` 加九个新列（带 server_default） | 删除这九列 |
| `20260921_000002` | `20260921_000001` | 删除 `messages_json` | 重建为空数组列（**内容不可恢复**） |
| `20260921_000003` | `20260921_000002` | 删除 15 张 `da_*` 表 | `raise NotImplementedError` |

拆成三个而不是一个，是为了让 §12 的任务顺序里每一步结束时仓库都处于可运行状态。

**旧聊天记录不迁移。** 旧 topic 存在即将删除的本地 `da_*` 表里，对外部 DataAgent 毫无意义。`dataagent_topic_id` 全部置 NULL，升级后首次发送会在外部 DataAgent 创建新会话。

**领域数据零丢失：** workspaces、workspace_members、users、ontology_versions、modeling_sessions（除 `messages_json`）、materials、material_chunks、data_connections、service_tokens、service_token_scopes、metadata_snapshots 全部保留。

## 9. 前端接入

### 9.1 保持不变

左侧材料上传/材料库/业务场景/数据源选择，右侧 `ModelResults`（语义图谱、候选列表、接受/忽略），顶部会话切换与发布入口，全部保持现有布局与交互。

### 9.2 会话区替换

```tsx
const conversation = useRef<AgentConversationElement>(null)

<dataagent-conversation
  ref={conversation}
  endpoint={session ? conversationUrl(workspace.id, session.id) : ""}
  placeholder="描述你的建模需求"
>
  <div slot="composer-actions">
    <button onClick={startModeling}>开始建模</button>
  </div>
</dataagent-conversation>
```

**会话地址生命周期（对应 SDK 设计 §6.1）：**

- **`endpoint` 必须由 `sessionId` 直接推导，不能依赖异步加载完成的 `session` 对象。** `useModeling` 的 `sessionId` 来自 URL search param（`useModeling.ts:15`），切换时同步变化；而 `session` 对象要等请求回来才更新。若写成 `session ? url(session.id) : ""`，一次真实切换会表现为"旧地址 → 空地址 → 新地址"，中间那次空值会让元素多做一轮清空与重连；`endpointResolver` 首次写回的地址也可能被下一次渲染覆盖成空。

  正确写法：

```ts
const endpoint = sessionId
  ? `/api/v1/workspaces/${workspace.id}/sessions/${sessionId}/agent-conversation`
  : ""
```

- `sessionId` 为空（尚未创建会话）→ `endpoint=""`，通过 `ref` 设 `endpointResolver`，它在首次发送时调用 `model.ensure()` 并返回新地址。`ensure()` 内部会把新 id 写进 URL param，于是下一次渲染的 `endpoint` 自然等于 resolver 写回的值，不会互相覆盖。
- **切换会话 → 只改 `endpoint`，不调 `reload()`。** 元素自己负责 abort 旧流、清空状态、装载新会话。

"开始建模"读取元素当前输入并拼上左侧业务场景，沿用 `BuilderPage.tsx:93-103` 的文案组合逻辑：

```ts
const startModeling = () => {
  const text = conversation.current.value.trim()
  const content =
    scenario.trim() && text ? `业务场景：${scenario.trim()}\n本次需求：${text}`
    : text || scenario.trim() || "基于已选材料开始建模"
  conversation.current.sendMessage(content, { metadata: { mode: "model" } })
}
```

### 9.3 宿主状态同步

这是容易漏掉的一处。`POST /messages` 只返回 `RunRef`，宿主的 `ModelingSession` 仍持有旧 `revision` 和 `idle` 状态；而 BFF 在 CAS 抢占时已经把 `revision` 加了 1。若不同步，后续保存草稿、接受候选、发布都会带着过期 revision 被 409 拒绝。

规则：

- 监听 `dataagent-run-change`，**首次进入活动态时立即 `model.reload()`**，把新的 revision 与 `task_status` 同步回宿主。
- 监听 `dataagent-complete`，**所有终态都 `model.reload()`**（不只是建模轮次）——因为任何一轮都可能改变 revision 与运行状态。
- 只有"是否需要特别关注右侧候选区"才按 `detail.metadata?.mode === "model"` 区分（例如滚动到候选区、展示 `result_warnings`）。
- 宿主的 busy/禁用态由 `dataagent-run-change` 驱动，不再自己维护 `running` 推断。

```ts
conversation.current.addEventListener("dataagent-run-change", onRunChange)
conversation.current.addEventListener("dataagent-complete", (e) => {
  model.reload()
  if (e.detail.metadata?.mode === "model") focusCandidates()
})
```

`metadata` 跨刷新恢复由 BFF 保证：`GET ""` 返回的 `run.metadata` 从 `dataagent_task_mode` 列重建为 `{ mode }`。

### 9.4 删除

- `apps/web/src/components/AgentStream.tsx`
- `apps/web/src/lib/dataagentStream.ts` 及 `dataagentStream.test.ts`
- `BuilderPage.tsx` 中的消息列表渲染、输入框、发送/取消按钮、`chatEnd` 滚动逻辑、`running` 推断
- `api/client.ts` 的 `modelingApi.chat` / `cancel` / `sync`
- `api/types.ts` 中 `ModelingSession.messages`

### 9.5 新增

- `Candidate` 联合类型增加 `{ kind: "mapping"; value: DataMapping }` 分支（**类型名是 `DataMapping`**，`types.ts:171`），并在公共部分增加可选字段 `before?: unknown`、`source_task_id?: string`。
- `ModelResults` 增加 mapping 候选的最小展示。`DataMapping` **没有 `name` 字段**，展示项为 `connection_alias`、`schema_name`/`table_name`、`key_column`，以及所属 `type_id` 对应的对象类型名。接受/忽略入口复用现有候选卡片。
- `ModelingSession` 类型增加 `result_warnings: string[]`，在候选区上方以一行提示展示。

### 9.6 依赖

`apps/web/package.json` 增加精确版本依赖 `"@opendataworks/agent-conversation": "0.1.0"`。该包自带 Vue runtime 与内联样式，**不需要 import 任何 CSS**，OntoFoundry 不引入 Vue 编程模型。

## 10. 待删除清单

| 类别 | 项 |
| --- | --- |
| Python | `apps/api/src/dataagent_backend/`（16,541 行）、`apps/api/tests/dataagent/` |
| Python | `main.py` 中 `dataagent_backend` 的 import 与三处调用 |
| TypeScript | `dataagent/`（含 `dataagent-runtime-pi/`、`contracts/`、`.claude/skills/`、`README.md`） |
| 构建 | 根 `package.json` workspaces 中的 `dataagent/dataagent-runtime-pi` |
| 构建 | `Makefile` 的 `dataagent-build`、`dataagent-images`、`dataagent-test`，以及 `test`/`lint` 中对 `@ontofoundry/agent-runtime-pi` 的引用 |
| 部署 | `compose.yaml` 的 `dataagent-redis`、`of-runner`、卷 `ontofoundry-dataagent-runtime`；`of-backend` 对 `/dataagent_runtime` 与 `./dataagent/.claude/skills` 的挂载；健康检查路径 `/api/v1/agent/health` |
| 部署 | `apps/api/Dockerfile` 的 `pi-cell` 与 `runner` 两个 stage |
| 配置 | `.env.example` 中 `DATAAGENT_DATABASE_URL`、`DATAAGENT_DATABASE_SCHEMA` 等内置运行时变量 |
| 依赖 | `apps/api` 中随之无引用的 Python 包。**`psycopg` 必须保留**（OntoFoundry 自己连 PostgreSQL 用），逐个核实后再删 |

`.claude/skills/md2ossie/` **保留**，迁移为集成包的一部分（§11）。

## 11. DataAgent 集成包

新建 `integrations/dataagent/`，由 OntoFoundry 维护、管理员在 DataAgent 管理端手工安装：

```text
integrations/dataagent/
├── README.md                    安装步骤
├── skills/md2ossie/             从 .claude/skills/md2ossie/ 迁入（源码形态，唯一真相，纳入版本控制）
├── Makefile                     `make zip` 由 skills/ 生成 dist/md2ossie.zip
└── agents/agent_ontofoundry.md  Agent 定义示例
```

两个必须写清的接入细节：

1. **Skill 导入的实际格式是 ZIP，不是目录。** 管理端只接受 ZIP 上传（`admin_routes.py:526`）。**ZIP 是生成产物，不提交到 Git**（`dist/` 进 `.gitignore`）——提交二进制会让 diff 不可读，还会与源码目录产生第二份真相。README 写明打包命令与 ZIP 内根目录结构；安装前执行 `make -C integrations/dataagent zip` 现场生成。
2. **Agent 的可见性必须允许 Widget 访问。** Widget 身份不会成为 DataAgent 的登录用户，`_require_agent_profile` 对不可见的 Agent 与不存在的 Agent 返回同样的 `agent not found`（`routes.py:1046`）。`agent_ontofoundry` 若配成仅限特定用户可见，创建 Topic 会直接 400。示例定义中明确写死 `visibility.mode = all`。

`agent_ontofoundry.md` 的提示词必须包含 §7.1 的结果文件约定与 `run_token` 占位说明，否则回写链路不会触发。

**OntoFoundry 不自动创建 Agent 或 Skill**，只通过 `ONTOFOUNDRY_DATAAGENT_AGENT_ID` 引用已存在的 `agent_id`。自动创建意味着 OntoFoundry 需要 DataAgent 的管理权限，那会让"复用运行时"重新滑回"拥有运行时"。

## 12. 测试策略

### 后端（pytest，`apps/api/tests/`）

**BFF 契约**
- 非空间成员访问六个端点全部 403；会话不属于该空间 → 404。
- 首次 `GET ""` 不创建 topic；首次 `POST /messages` 创建且只创建一次；第二次发送复用同一 topic。
- 请求头四项完整且 `X-ODW-User-Id == ontofoundry:{ws}:{sid}`。
- 历史消息**分页取全**：DataAgent 返回 3 页时，`GET ""` 返回全部消息。
- 材料上传幂等：同一材料第二轮不重复上传。
- **并发控制**：两个并发 `POST /messages`，其中一个 409，且**远端只收到一次 deliver**（关键——验证 CAS 在远端副作用之前）。
- CAS 抢占后远端失败 → `task_status` 释放为 `failed`，本轮新建的 topic 被删除。
- 已有活动任务（含 `submitting` / `waiting_input` / `waiting_permission`）时再次发送 → 409。
- `/events` 输出 `event: agent-event` 与 `event: done`，**不是**原始字节；`done` 在候选回写之后发出。
- 状态转换表七种输入各自映射正确。
- `GET ""` 的 `run.metadata` 从 `dataagent_task_mode` 重建为 `{mode}`。
- `metadata` 未知键被忽略；`mode` 非法值按 `chat`。
- `/files` 透传二进制与 content-type。

**诊断**
- §6.9 六种失败各返回约定的状态、`message`、`hint`。
- Agent 存在性检查打的是 `/api/v1/dataagent/agents/{id}`；该端点 404 时诊断项失败。
- `base_url` 为空时应用正常启动，本体查看/编辑/发布/MCP 全部可用。

**结果回写**
- 有效结果 → 生成 object_type / link_type / mapping 候选，`before` 正确。
- `annotations` 的 reason 与 evidence 正确附加；匹配不上的 annotation 被忽略且不报错。
- 普通聊天任务完成 → 草稿与候选零变化。
- merge 语义：Agent 结果中缺失的既有 object_type **不产生删除**。
- **mapping 只产出新增候选**：已有 mapping 的 type_id 不产生更新候选。
- **run_token 隔离**：上一轮留下 `ontofoundry-result-{old}.json`，本轮 Agent 未写文件 → 判定无结果，不消费旧文件。
- **文件内 run_token 与请求不符 → 永久失败，草稿与候选不变。**
- 幂等：对同一 task 连续消费两次，候选数量不变。
- **可重试失败不锁死**：下载超时 → `result_state='failed_retriable'`；再次触发能成功消费。
- 旧 pending 候选被置 `superseded`；已 accepted / ignored 的不变。
- 四种永久失败输入各自：任务失败、`task_detail` 含具体原因、草稿与候选不变。
- 顶层约束差异 → `result_warnings` 有一条，候选不含该 kind。
- 生成的候选喂给现有 `accept_candidates`，接受后草稿正确更新；人工先改过同一项时命中冲突提示。

**迁移**
- 含数据的库上 `alembic upgrade head`：领域表行数不变；九个新列存在且非空列已回填默认值；`dataagent_topic_id` 全 NULL；`messages_json` 消失；`da_*` 表全不存在。
- `alembic_version` 能从 `20260916_000001` 正常前进（验证 revision ID 未因目录迁移改变）。

### 前端（vitest）

- `session` 为 null 时挂载：`endpoint` 为空，`endpointResolver` 未被调用，无建会话请求。
- 首次发送：`endpointResolver` 调用一次并返回正确 URL。
- `session` 已存在时挂载：`endpoint` 直接有值。
- 切换会话：只改 `endpoint`，不调 `reload()`；消息区重置。
- "开始建模"提交的 content 与 `metadata.mode === "model"` 正确；业务场景为空/非空两种拼接。
- `dataagent-run-change` 首次进入活动态 → `model.reload()`；`dataagent-complete` 任意终态 → `model.reload()`；仅 `mode === "model"` 时额外聚焦候选区。
- 左侧材料区与右侧 `ModelResults` 现有测试全部通过（回归门禁）。
- mapping 候选展示 `connection_alias` / 表 / `key_column`，接受/忽略调用参数正确。
- `result_warnings` 非空时在候选区上方展示。

### 端到端（手工，上线前必做一次）

在真实外部 DataAgent 上：管理端建站点 `ontofoundry` → 生成 access key → 上传 `md2ossie.zip` → 创建 `agent_ontofoundry` 并设 `visibility.mode=all` → 配置 OntoFoundry 环境变量 → 设置页连通性全绿 → 上传材料 → 普通问答一轮 → "开始建模" → 右侧出现候选 → 接受 → 校验 → 发布 → 刷新页面确认聊天历史来自 DataAgent 且恢复后的终态仍能刷新候选。

## 13. 发布顺序与回滚

| # | 步骤 | 依赖 |
| --- | --- | --- |
| 1 | OpenDataWorks 完成 SDK 与 Widget 改造（上游 T1–T6） | — |
| 2 | OpenDataWorks 发布 `@opendataworks/agent-conversation@0.1.0`（上游 T7） | 1 |
| 3 | OpenDataWorks 上线站点 access key 能力（上游 T8） | — |
| 4 | 管理员在目标环境配置站点、密钥、Skill ZIP、Agent | 3 |
| 5 | **进入只读维护窗口** | — |
| 6 | **备份 OntoFoundry 数据库** | 5 |
| 7 | 执行迁移并部署新版本 | 2, 4, 6 |
| 8 | 完整冒烟（§12 端到端） | 7 |
| 9 | 退出维护窗口 | 8 |

**第 5 步的只读维护窗口是必需的，不是保守。** 回滚手段是整库恢复；若备份之后仍允许编辑、发布或上传，回滚会连同这些领域写入一起丢失。窗口从备份开始到冒烟通过结束。

回滚 = 恢复第 6 步的备份 + 部署旧镜像。`da_*` 表的删除不可逆，`20260921_000003` 的 `downgrade()` 直接抛错。

**回滚的外部残留：** 部署后在外部 DataAgent 上创建的 Topic 不会随本地数据库恢复而删除。回滚后需按 `website_id=ontofoundry` 清理该时间窗内创建的 Topic，否则它们成为无主会话。冒烟阶段创建的 Topic 数量有限，手工清理即可；README 中记录清理方式。

## 14. 取舍与风险

| 决策 | 理由 | 风险与缓解 |
| --- | --- | --- |
| 删除本地 DataAgent 而非逐步解耦 | 保留分叉会持续与上游分叉，且部署代价已经在付 | 变更面大。用迁移测试 + 端到端冒烟 + 数据库备份 + 维护窗口四道防线 |
| 结果契约用完整 Ossie 而非差异指令 | `md2ossie` 天然产出完整文档；复用已被测试锁定的 `import_ossie` | Agent 漏写被 `mode="merge"` 兜住，不会删除既有模型 |
| 引入 `run_token` | 同 Topic 多轮共享工作区，固定文件名会误消费上一轮 | 增加一次提示词约定；Agent 未遵守时表现为"无结果"而非"错结果"，失败方向安全 |
| CAS 抢占先于远端副作用 | 否则并发会在 DataAgent 上留下孤儿任务 | 多一个 `submitting` 状态，所有互斥条件都要覆盖 |
| `result_state` 区分可重试与永久失败 | 否则一次下载超时让建模结果永久丢失 | 状态机变复杂；用测试锁定四种取值的转换 |
| mapping 仅新增候选 | merge 语义决定，不是偷懒 | 已有 mapping 的变更无法通过建模流入；需要时另行修改 importer |
| 顶层约束忽略 + warning | `accept_candidates` 无对应集合键，硬加会被静默丢弃 | 用户需手工处理；有 `result_warnings` 通道确保不静默 |
| 不迁移旧聊天记录 | 旧 topic 在即将删除的本地表里 | 升级后用户看到空会话，发布说明中告知 |
| v1 不做 launch token | 浏览器不直连 DataAgent，BFF 已是可信边界 | DataAgent 必须只暴露在可信内网 |
| `X-ODW-User-Id` 用会话 ID | DataAgent 按 `external_user_id` 过滤可见性，用真实用户 ID 会破坏多人协作 | 管理端呈现为"每会话一个伪用户"，已接受 |
| 保留 API prefix 配置 | 上游前缀历史上变更过 | Agent 查询端点前缀不同，已单独标注 |
