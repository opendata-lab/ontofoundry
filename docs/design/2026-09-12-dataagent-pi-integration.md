# OntoFoundry DataAgent + Pi 集成设计

日期：2026-09-12
状态：已实施

## 1. 目标

OntoFoundry 不再维护独立的 Agent 循环。对话编排、任务生命周期、模型调用、工具执行、运行隔离和事件持久化统一复用 OpenDataWorks 已跑通的 DataAgent 后端与 Pi TypeScript runtime。

本次收敛的硬约束：

1. Pi 是唯一 Agent 执行引擎，不保留 Claude Agent SDK 运行时或切换开关。
2. `AgentEvent v1` 是唯一平台事件协议；前端不识别 Claude 原生事件，也不识别 `pi_event` 旧别名。
3. OntoFoundry API 是业务控制面，继续负责用户、工作空间、本体草稿、版本和候选变更。
4. DataAgent 负责 Topic、Task、会话历史、运行协调、Pi Cell、工具调用和可重放事件流。
5. Agent 只能产出建议或交付文件，不能绕过 OntoFoundry 的预览、校验、接受和发布流程。

## 2. 总体架构

```text
Browser
  │ POST /workspaces/{w}/sessions/{s}/messages
  │ GET  /workspaces/{w}/sessions/{s}/events
  ▼
OntoFoundry API
  ├─ 权限、workspace/session、草稿与版本
  ├─ 上传材料和当前草稿快照
  ├─ 将 OntoFoundry session 投影到 DataAgent topic/task
  └─ 同源代理 AgentEvent SSE
          │
          ▼
DataAgent backend
  ├─ Topic / Task / Message
  ├─ PostgreSQL public schema：任务与 AgentEvent 日志
  ├─ Redis 调度协调
  ├─ Skill / workspace / sandbox
  └─ Pi gateway
          │ stdio JSON frames
          ▼
Pi TypeScript Cell
  ├─ pi-agent-core
  ├─ 模型与工具循环
  └─ 原始事件标准化为 AgentEvent v1
```

## 3. 组件边界

### 3.1 OntoFoundry API

- 校验工作空间成员身份和 session revision。
- 首轮创建 DataAgent topic，后续复用。
- 将选中的 Markdown 材料上传到 topic workspace；同一材料不重复上传。
- 每轮上传当前 `draft_json`，文件名带 revision，保证 Agent 看到明确快照。
- 调用 `deliver-message` 创建 DataAgent task。
- 在本地消息上保存 `dataagent_topic_id`、`dataagent_task_id` 与已上传材料 ID。
- 代理 DataAgent AgentEvent SSE，避免浏览器跨域和重复认证。
- 任务结束后调用 `/sync`，把最终公开 Markdown、附件和任务状态投影回本地 session。

### 3.2 DataAgent backend

- 保留成熟的 Topic、Task、Message、调度、取消、恢复、文件工作区和 sandbox 能力。
- 仅调用 Pi runtime；删除 Claude Agent SDK 依赖、执行分支和 runtime kind 配置。
- 内置 `agent_ontofoundry` profile，默认启用本体建模 Skill 和 `md2ossie`。
- OntoFoundry profile 不挂载 OpenDataWorks Portal MCP，避免错误依赖另一套业务控制面。

### 3.3 Pi runtime

- 通过 stdin/stdout 与 Python gateway 交换版本化 JSON frame。
- 负责模型循环、Skills、MCP、工作区边界、上下文治理和工具输出折叠。
- Pi 原始事件只存在于 runtime 内部；`event-normalizer` 在边界处转换为 AgentEvent v1。

### 3.4 Web 前端

- 只消费 `record_type: agent_event` 和终态 `record_type: error`。
- 增量展示回答、思考过程和工具调用。
- 最终和流式文本都经过同一 Markdown + DOMPurify 渲染组件。
- SSE 解析支持任意网络分片、CRLF、多行 `data:` 和心跳注释。
- 断流后通过 `/sync` 对账；刷新页面时以 `after_id` 重放事件。

## 4. 唯一事件协议

### 4.1 对外信封

```json
{
  "seq_id": 42,
  "record_type": "agent_event",
  "event_type": "content.delta",
  "data": {
    "turn_id": "turn-1",
    "content_id": "c-0",
    "kind": "answer",
    "delta": "正在生成"
  }
}
```

`/agent-events` 与 SSE 对外输出的 `record_type` 只允许：

- `agent_event`：符合 AgentEvent v1 的业务事件。
- `error`：无法表示为正常运行事件的终态错误。

不允许 `stream`、`tool_result`、`pi_event`、`done` 等引擎或旧实现专用记录进入新链路。DataAgent 为等待确认/补充输入而保存的 interaction control records 属于后端内部协调数据，由专用接口读取，不进入 `/agent-events` 或前端 reducer。

### 4.2 事件闭集

- 运行：`run.started`、`run.completed`、`run.failed`、`run.cancelled`、`run.suspended`
- 回合：`turn.started`、`turn.completed`
- 内容：`content.started`、`content.delta`、`content.completed`
- 工具：`tool.started`、`tool.completed`、`tool.denied`
- 用量：`usage.updated`

Schema 位于 `dataagent/contracts/agent-events/v1/`。生产端、持久层和前端 reducer 必须以该闭集为准。

## 5. 任务与状态投影

```text
DataAgent waiting/queued      -> OntoFoundry queued
DataAgent running            -> OntoFoundry running
DataAgent waiting_*          -> OntoFoundry running（UI 展示等待原因）
DataAgent finished/success   -> OntoFoundry completed
DataAgent cancelled/suspended-> OntoFoundry cancelled
其他终态                     -> OntoFoundry failed
```

投影必须幂等：同一 `dataagent_task_id` 只能落一条最终 assistant 消息。任务完成但 message 尚未可见时保持 running，下一次同步重试，避免写入空答案。

## 6. 对话与文件契约

每轮向 DataAgent 提交的 prompt 包含：

- `workspace_id`、`session_id`；
- 当前本体快照相对路径；
- 本轮新增材料相对路径；
- `chat` 或 `model` 模式；
- 用户原始消息。

所有文件都被声明为待分析数据而不是指令。只有显式 `model` 请求才允许生成完整 Ossie JSON，并写入 topic workspace 的 `output/`。OntoFoundry 读取交付物后仍需执行 schema 校验、业务校验、diff 预览和人工接受。

## 7. 删除与保留

删除：

- Python `claude-agent-sdk` 依赖；
- Claude Agent SDK 执行器、SDK block writer、CLI path resolver；
- Claude/Pi runtime 切换配置；
- 前端 Claude `content_block_*` / `message_*` reducer；
- `pi_event` 读取兼容别名；
- SDK 专用 SSE 路由和模型类命名；
- OntoFoundry 旧的进程内 Agent 主链路。
- OntoFoundry B0.1 Worker、跨进程 runtime contracts 及其六张运行表；
- DataAgent eval API、模型、数据集工具和四张 eval 表。

保留：

- Anthropic-compatible provider 配置。它是模型传输协议，不等于 Claude Agent SDK；Pi runtime 仍可通过它调用模型。
- `.claude/skills` 目录约定。当前 Pi 运行时沿用该 Skill 发现目录，它不是 Claude Agent SDK 运行时依赖。
- Pi 原始事件到 AgentEvent 的后端适配器。这是隔离引擎实现与平台协议的必要边界。

## 8. 部署

本地 Compose 增加：

- `dataagent-redis`
- `dataagent-backend`（镜像内构建 Pi runtime）

OntoFoundry API 通过 `ONTOFOUNDRY_DATAAGENT_BASE_URL` 访问 DataAgent。生产环境应使用服务发现地址；浏览器不直接访问 DataAgent。

### 8.1 技术栈与数据职责

当前只有一个内部 PostgreSQL 数据库、一个 `public` schema 和一条 Alembic 迁移链：

| 层 | 技术 | 数据职责 |
| --- | --- | --- |
| Web | React、TypeScript、Vite | Builder UI、SSE 消费、AgentEvent reducer、Markdown + DOMPurify 渲染 |
| OntoFoundry API | FastAPI、SQLAlchemy | 用户、工作空间、本体草稿/版本、材料、建模 session；部署数据库为 PostgreSQL |
| DataAgent backend | FastAPI、psycopg、Alembic | Topic、Task、Message、AgentEvent、Agent profile、供应商与 Skill 配置；统一管理 `public` 中所有平台表 |
| 调度 | Redis | DataAgent task 队列、租约与并发协调，不保存业务真相 |
| Agent runtime | Node.js、TypeScript、Pi Agent Core | 模型/工具循环与原始事件生成，通过 stdio JSON frame 连接 DataAgent backend |
| 文件运行区 | 本地卷或对象存储挂载 | Topic workspace、上传材料、草稿快照、Agent 交付文件 |

PostgreSQL 是整个平台唯一内部关系数据库。OntoFoundry 与 DataAgent 表都位于 `public`，只保留 `public.alembic_version`；两者仍只通过 `dataagent_topic_id`、`dataagent_task_id` 做引用和最终状态投影，不做同表双写。`modeling_sessions` 是产品会话，`da_agent_task` 是可重试执行任务，两者职责不同，不是重复表。Redis 只承担队列、租约和并发协调，不保存业务真相。

MySQL 与 Doris 仅作为可选外部业务数据源，由只读查询/元数据连接器按需访问；`pymysql` 依赖因此保留，但 Compose 不再启动内部 MySQL，DataAgent 的 Topic、Task、Event 和管理配置也绝不写入 MySQL。

DataAgent 历史 MySQL 增量迁移已压平为统一 PostgreSQL baseline。全新部署直接执行 `alembic upgrade head`。既有双 schema 开发库升级时，migration 会把已知 `dataagent.da_*` 表移动到 `public`，删除旧 schema 的版本表，并拒绝覆盖同名 public 表；发现未知表时也会停止，而不是级联删除。eval 表与旧 B0.1 运行表属于明确废弃数据，会被删除，因此升级前必须备份。旧的独立 DataAgent MySQL 若有必须保留的生产历史，应先单独导出、转换和校验后再导入。

### 8.2 全新环境启动

当注册表为空时，DataAgent 从 `LLM_PROVIDER`、`CLAUDE_MODEL` 与对应凭证环境变量生成首个供应商记录。被环境变量明确选中的供应商会写为启用状态，再由凭证、地址和已启用模型的本地校验决定是否达到 `verified`；数据库中已有注册表后仍以数据库配置为准，避免重启覆盖管理员设置。

## 9. 验收标准

1. 新建会话后可连续多轮对话，复用同一 DataAgent topic。
2. Markdown 标题、列表、表格、代码块正确渲染，脚本和危险 HTML 被清洗。
3. SSE 任意分片下不丢字、不重复字；断线重连从 `after_id` 继续。
4. 思考、回答、工具开始/完成按 AgentEvent 顺序展示。
5. 完成、失败和取消能可靠投影回 OntoFoundry session。
6. 材料只上传一次，草稿每轮按 revision 上传。
7. 仓库不存在 `claude-agent-sdk` 依赖或 Claude SDK 运行分支。
8. 前端不存在 `stream` / `pi_event` / Claude 原生事件兼容 reducer。
9. Python、TypeScript 静态检查和相关单元/集成测试通过。
10. PostgreSQL 只存在一组 27 张受管表：11 张平台表、15 张 DataAgent 表和 `alembic_version`；不存在 eval 或旧 B0.1 运行表。

## 10. 后续约束

任何新执行引擎都必须在 DataAgent 后端边界转换为 AgentEvent v1，不得把引擎事件直接暴露给 OntoFoundry 或浏览器。任何本体写入能力都必须通过候选变更与人工接受流程，不得由 Agent 直接修改已发布版本。

## 11. 端到端验证记录（2026-09-13）

首次验证使用隔离的 PostgreSQL database 与 Redis logical DB 启动真实 OntoFoundry API、DataAgent backend 和构建后的 Pi TypeScript runtime，并通过浏览器完成验证：

1. 新建建模 session，经 OntoFoundry API 创建并复用 DataAgent topic/task。
2. 首次用不可用网关触发 403，`run.failed` 与终态 `error` 正确转换并在前端显示。
3. 切换至检测通过的 Anthropic-compatible 模型后，真实回答经 SSE 增量返回；二级标题“E2E通过”和无序列表“AgentEvent流式展示”按 Markdown DOM 渲染。
4. 刷新浏览器后，同一 session 的用户消息、失败消息、成功回答和完成状态全部恢复。
5. DataAgent 事件记录的公开 `record_type` 仅出现 `agent_event` 与 `error`；成功任务以 `run.started`、`turn.started`、`content.*`、`usage.updated`、`turn.completed`、`run.completed` 收口，没有 `pi_event` 或 Claude SDK 事件。
6. 测试发现并修复全新供应商注册表未继承环境变量启用意图的问题，新增回归用例覆盖冷启动。
7. 首次提交在 DataAgent 接受 task 前失败时，OntoFoundry 会回收刚创建且尚未写入本地 session 的 topic，避免重试产生孤儿 Topic 和工作目录。

随后把迁移收敛为同一个隔离 PostgreSQL database 的单一 `public` schema，验证统一 baseline、Provider/Topic/Task/Message/AgentEvent 的持久化 round-trip；内部持久化全程不依赖 MySQL。最终验收须重新确认 27 张受管表、单一 Alembic 版本表、无 eval 表、无旧 B0.1 运行表。

最终回归已完成：API pytest 85 通过、1 跳过；DataAgent pytest 520 通过、1 跳过；Pi runtime 147 通过；Web 42 通过；Pi 与 Web production build 均成功。真实浏览器创建 session `b6b77704-aa18-46b8-b349-322da5db9aec`，DataAgent task `task_0fd9171821544a23bcacdfc3` 以真实模型完成，SSE 输出的二级标题和列表被渲染为 Markdown DOM，刷新后仍可恢复。数据库只剩 `public` schema 的 27 张表和一张 `public.alembic_version`；`modeling_sessions` 为 completed，`da_agent_task` 为 finished，终态事件链完整，瞬时 `content.delta` 已按策略清理。
