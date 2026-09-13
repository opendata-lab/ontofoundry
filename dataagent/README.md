# OntoFoundry DataAgent

本目录从 OpenDataWorks 合并成熟的 Agent 能力，并按 OntoFoundry 边界精简：

- `dataagent-backend`：Topic、Task、Message、文件工作区、调度、取消、恢复、AgentEvent SSE 与 Pi gateway。
- `dataagent-runtime-pi`：唯一 Agent 执行引擎，Node.js 22.19+，通过 stdio 与后端通信。
- `contracts`：AgentEvent、任务状态和工作区边界契约。
- `.claude/skills`：Pi 沿用的 Skill 发现目录；不表示依赖 Claude Agent SDK。

本仓库不包含 DataAgent 独立前端。OntoFoundry Web 通过自身 API 的同源 SSE 代理消费平台 `agent_event`，并负责流式展示和 Markdown 渲染。

运行时没有 Claude Agent SDK 兼容分支，也没有 `pi_event` 对外协议。Pi 原始事件在后端边界统一转换成 AgentEvent v1。

内部持久化只使用 PostgreSQL：OntoFoundry 与 DataAgent 共用 `public` schema，由同一张 `alembic_version` 管理。Redis 只做任务协调；MySQL/Doris 仅是可选外部数据源，不承载 Agent 状态。

内置 `agent_ontofoundry` profile 启用：

- `ontofoundry-modeling-assistant`
- `md2ossie`

该 profile 不挂载 OpenDataWorks Portal MCP。本体草稿与材料由 OntoFoundry API 上传到 topic workspace；Agent 的 JSON 交付写入 `output/`，后续仍由 OntoFoundry 校验、预览并人工接受。

## 本地验证

```sh
make dataagent-build
make dataagent-test
```

## 本地启动

```sh
docker compose --env-file apps/api/.env up -d --build dataagent-backend
```

镜像启动时自动执行 `alembic upgrade head`，服务监听 `127.0.0.1:8900`。模型供应商配置通过 Compose 环境变量注入；Anthropic-compatible 是模型传输协议，不是 Claude Agent SDK。

完整边界和事件协议见 [集成设计](../docs/design/2026-09-12-dataagent-pi-integration.md)。
