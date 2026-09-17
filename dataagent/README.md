# OntoFoundry DataAgent

本目录是 OntoFoundry 的 Agent 控制面和 Pi 执行时实现：

Agent master（Topic、Task、Message、文件工作区、调度、取消、恢复、AgentEvent SSE
与 Pi gateway）已并入统一 Python 后端，位于 `apps/api/src/dataagent_backend`，与
`ontofoundry_api` 同进程运行，镜像由 `apps/api/Dockerfile` 构建，发布名仍为
`of-agent-master`。本目录现在只保留执行引擎与契约：

- `../apps/api/Dockerfile` 是一个多阶段文件，三个角色共用同一份镜像内容，只有 CMD
  不同：`of-backend`（API）、`of-runner`（sandbox runner，多一个 docker CLI）。
  沙箱子容器直接复用 `of-backend`——它执行 `python .../sandbox_task_main.py`，
  需要完整 Python 包，因此不存在"纯 Pi runtime 镜像"这一说。
- `dataagent-runtime-pi`：唯一 Agent 执行引擎，Node.js 22.19+，通过 stdio 与后端通信。
- `contracts`：AgentEvent、任务状态和工作区边界契约。
- `.claude/skills`：Pi 沿用的 Skill 发现目录；不表示依赖 Claude Agent SDK。

本仓库不包含 DataAgent 独立前端。OntoFoundry Web 通过自身 API 的同源 SSE 代理消费平台 `agent_event`，并负责流式展示和 Markdown 渲染。

运行时没有 Claude Agent SDK 兼容分支，也没有 `pi_event` 对外协议。Pi 原始事件在后端边界统一转换成 AgentEvent v1。

内部持久化只使用 PostgreSQL：OntoFoundry 与 DataAgent 共用 `public` schema，由同一张 `alembic_version` 管理。Redis 只做任务协调；Agent master 不包含 MySQL/Doris 直连配置或查询代理。

系统只内置一个默认的 `agent_ontofoundry` profile，且只启用 `md2ossie` Skill。Agent、Skill 和 MCP server 的自定义管理入口保留，但不再预装其他业务 Skill。

该 profile 不挂载 Portal MCP。Pi 只保留通用 MCP 客户端，OntoFoundry 自身的 MCP 由 `of-api` 内的 `/api/v1/ontology/workspaces/{workspace_id}/mcp` 提供。本体草稿与材料由 OntoFoundry API 上传到 topic workspace；Agent 的 JSON 交付写入 `output/`，后续仍由 OntoFoundry 校验、预览并人工接受。

## 本地验证

```sh
make dataagent-build
make dataagent-test
```

## 本地启动

```sh
docker compose --env-file apps/api/.env up -d --build of-backend of-runner of-frontend
```

镜像启动时自动执行 `alembic upgrade head`，服务监听 `127.0.0.1:8900`。模型供应商配置通过 Compose 环境变量注入；Anthropic-compatible 是模型传输协议，不是 Claude Agent SDK。

完整边界和事件协议见 [集成设计](../docs/design/2026-09-12-dataagent-pi-integration.md)。
