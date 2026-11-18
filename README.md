<div align="center">

<img src="docs/assets/logo.svg" width="72" height="72" alt="OntoFoundry Logo" />

<h1>OntoFoundry</h1>

<p>
  <strong>企业级本体建模与语义服务平台</strong><br />
  将业务制度、多源库表与领域知识治理为可版本化、可追溯、可被 AI 智能体直接消费的可信语义底座
</p>

<p>
  <a href="https://github.com/opendata-lab/ontofoundry/actions/workflows/ci.yml"><img src="https://github.com/opendata-lab/ontofoundry/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/opendata-lab/ontofoundry/releases"><img src="https://img.shields.io/github/v/release/opendata-lab/ontofoundry?style=flat-square&color=0061ef" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-156d3b?style=flat-square" alt="License Apache-2.0" /></a>
  <img src="https://img.shields.io/badge/MCP-2026--07--28-716096?style=flat-square" alt="MCP 2026-07-28" />
  <img src="https://img.shields.io/badge/Apache%20Ossie-0.2.0.dev0-94600b?style=flat-square" alt="Apache Ossie" />
</p>

<p>
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
</p>

<p>
  <a href="#核心能力">核心能力</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#ai-与-mcp-接入">AI 与 MCP 接入</a> ·
  <a href="#模块与文档">模块与文档</a>
</p>

</div>

---

库表结构不等于业务口径，零散文档喂给大模型容易产生指标幻觉。**OntoFoundry** 把“业务文档 + 数据库结构 + 人工治理”收敛到统一语义模型中，为应用与 AI Agent 提供受版本和权限控制的标准语义服务。

## 核心能力

| 能力维度 | 核心特性 |
| --- | --- |
| **Core-1 语义模型** | 统一表达业务对象（单父继承与成员分支）、属性、共享值类型、二元关系、规则、独立指标（`simple` / `ratio` / `expression`）及物理映射，业务语义与 SQL 执行解耦 |
| **Proposal-First 治理** | AI 抽取与人工编辑均先落入隔离草稿的变更提案；每条定义和文档实例均保留原文行号/SHA-256 或表结构收据，接受时自动校验规则与绑定完整性，经三方合并后发布不可变版本 |
| **多源只读数据融合** | 原生接入 **PostgreSQL / MySQL / Apache Doris**，支持物理表与 `sqlglot` AST 只读校验的 SQL 数据集、`snapshot_date_column` 快照口径及指标 SQL 在线预览 |
| **MCP 网关与反馈闭环** | 提供个人令牌驱动的跨空间 MCP 网关与单空间 MCP 接口，开箱接入 **Claude Code / Codex / OpenCode / ZCode**，支持网关调用审计与 `submit_feedback` 口径纠偏回流 |
| **企业安全与开放标准** | 支持本地账号与可插拔 SSO、工作空间 RBAC 与个人令牌；内置 **Apache Ossie** Schema 校验适配器（产出逐条转换报告）及 Core-1 原生无损备份包 |

---

## 系统架构

```mermaid
flowchart TB
    subgraph Inputs["多源输入"]
        M["业务材料 (Markdown / TXT / JSON / YAML / CSV)"]
        DB["只读数据源 (PostgreSQL / MySQL / Apache Doris)"]
        STD["外部模型 (Apache Ossie / Core-1 原生包)"]
    end

    subgraph Core["OntoFoundry 平台核心"]
        AI["AI 建模桥接 (可选 DataAgent)"]
        PW["Proposal 工作台 (证据追溯 · 接受时校验 · 冲突裁决)"]
        MODEL["Core-1 引擎 (对象继承 · 指标 · 映射 · 文档实例 · 三方合并)"]
        AUTH["企业底座 (本地账号/SSO · 空间 RBAC · 个人令牌 · 只读防护)"]
    end

    subgraph Consumers["服务与消费生态"]
        GW["MCP 网关 /api/v1/mcp & 空间 MCP"]
        REST["版本化 REST API & 格式导出"]
        AGENTS["Claude Code / ZCode / Codex / OpenCode / BI 应用"]
    end

    M --> AI -->|"变更提案"| PW
    DB -->|"元数据同步 & sqlglot 校验"| MODEL
    STD -->|"Schema 校验导入"| MODEL
    PW -->|"校验通过写入草稿"| MODEL
    MODEL --> AUTH --> GW --> AGENTS
    AUTH --> REST --> AGENTS
    AGENTS -->|"submit_feedback 口径纠偏"| PW
```

---

## 快速开始

> 不配置任何外部大模型或 DataAgent，平台的人工建模、Ossie 导入导出、数据映射、指标预览、版本发布与 MCP 服务均可独立运行。

### Docker Compose（2 分钟体验）

需要 Docker 与 Docker Compose：

```sh
git clone https://github.com/opendata-lab/ontofoundry.git
cd ontofoundry
cp .env.example apps/api/.env
make compose-up
```

容器启动时自动执行数据库迁移，随后访问：

- **Web 工作台**：http://127.0.0.1:8010
- **API 文档**：http://127.0.0.1:8910/docs（健康检查：http://127.0.0.1:8910/healthz）

> [`.env.example`](.env.example) 默认以 `ONTOFOUNDRY_AUTH_MODE=dev`、`ONTOFOUNDRY_SEED_DEMO=true` 启动（自动初始化虚构示例空间「星港销售」并免登录进入）。生产或内网部署请改为 `ONTOFOUNDRY_AUTH_MODE=login`（默认管理员 `admin` / `admin123`）和 `ONTOFOUNDRY_SEED_DEMO=false`。停服保留数据用 `make compose-down`，清空重置用 `make compose-reset`。

<details>
<summary><b>更多方式：源码开发 · 离线安装包 · 生产配置与测试命令</b></summary>

#### 从源码运行（Python 3.13 + uv · Node.js 22.19+ · PostgreSQL 17）

```sh
cp .env.example apps/api/.env
make install
docker compose up -d postgres
(cd apps/api && uv run --python 3.13 alembic -c src/ontofoundry_api/alembic.ini upgrade head)
make api-dev     # 后端 :8000
make web-dev     # 另开终端，前端 :5174
# 单进程托管：先停止 make api-dev，再执行 make build && make serve（:8000）
```

#### 离线安装包（无外网环境）

从 [GitHub Releases](https://github.com/opendata-lab/ontofoundry/releases) 下载安装包及对应的 `.sha256`，或本地执行 `./scripts/create-offline-package.sh` 打包后安装。以下以 [`latest`](https://github.com/opendata-lab/ontofoundry/releases/tag/latest)（main 最新构建）的 `ontofoundry-offline-latest.tar.gz` 为例，固定版本的包名为 `ontofoundry-offline.tar.gz`：

```sh
shasum -a 256 -c ontofoundry-offline-latest.tar.gz.sha256
tar -xzf ontofoundry-offline-latest.tar.gz && cd offline
cp .env.example .env && ./install.sh
```

#### 生产部署要点

- 完整环境变量见 [`.env.example`](.env.example) 与 [`config.py`](apps/api/src/ontofoundry_api/config.py)。
- `ONTOFOUNDRY_ENVIRONMENT=production` 强制要求：`ONTOFOUNDRY_AUTH_MODE=login`、`ONTOFOUNDRY_SEED_DEMO=false`、`ONTOFOUNDRY_COOKIE_SECURE=true`（经 HTTPS 入口访问）、`ONTOFOUNDRY_SESSION_SECRET` ≥ 32 位随机字符。
- **必须修改 `ONTOFOUNDRY_MCP_TOKEN`**：默认值 `ontofoundry-mcp-default-token` 是公开的，启动检查不会拒绝它；改为随机值，或显式设为空以关闭单空间 MCP。
- 业务数据库请使用只读账号：平台的 SQL 白名单是应用层防护，连接密码按原样保存在平台数据库中。
- 本地账号、SSO 钩子契约、平台管理员与用户名冲突风险，以及版本升级与旧 OAuth 迁移，见 [部署、登录与升级](docs/deployment.md)；配置模板在 [`deploy/docker/ontofoundry/`](deploy/docker/ontofoundry/)。

#### 测试与校验

```sh
make lint   # Python ruff + 前端 eslint
make test   # API pytest + 前端 vitest
make build  # TypeScript 检查 + 前端构建
```

默认 API 测试使用隔离 SQLite。验证 PostgreSQL 事务、迁移和并发行为时，提供可创建临时数据库（CREATEDB）的 PostgreSQL 账号：

```sh
cd apps/api
ONTOFOUNDRY_TEST_POSTGRES_URL='postgresql+psycopg://user:password@127.0.0.1:5432/test_db' \
  uv run --python 3.13 pytest -q
```

</details>

---

## AI 与 MCP 接入

### 1. 让外部 AI Agent 消费已发布语义

仓库内置客户端插件 [`plugins/ontofoundry/`](plugins/ontofoundry/README.md)（含 `ontology-grounding` Skill 与 `.mcp.json`），让编程与分析 Agent 在写查询前先拉取平台权威口径：

```text
# Claude Code 一键安装（网关地址填 https://<your-host>/api/v1/mcp，令牌在平台「个人中心 → 个人令牌」签发）
/plugin install ontofoundry --marketplace opendata-lab/ontofoundry
```

同时支持 **ZCode / Codex / OpenCode**，详细配置片断见 [`plugins/ontofoundry/README.md`](plugins/ontofoundry/README.md)。

| MCP / 目录端点 | 鉴权方式 | 核心工具 / 用途 |
| --- | --- | --- |
| `POST /api/v1/mcp` | 个人访问令牌（PAT） | 跨空间智能体网关：`list_spaces`、`search_ontology`、`get_ontology`、`submit_feedback` |
| `POST /api/v1/workspaces/{workspace_id}/mcp` | `ONTOFOUNDRY_MCP_TOKEN` / 运行凭据 | 单空间读取与实体解析：`search_ontology`、`get_ontology`、`search_objects`、`get_object`、`resolve_entity` |
| `GET /api/v1/mcp/workspaces` | Bearer Token | 获取当前令牌可访问的工作空间与发布版本目录 |

### 2. AI 辅助建模（可选接入 OpenDataWorks DataAgent）

在 `apps/api/.env` 配置 `ONTOFOUNDRY_DATAAGENT_BASE_URL` 与 `ONTOFOUNDRY_DATAAGENT_AGENT_ID` 并按 [`integrations/dataagent/README.md`](integrations/dataagent/README.md) 安装技能包后，可在「本体构建」页基于万行级业务材料与百表级数据库自动生成可审阅提案。

---

## 模块与文档

| 路径 / 文档 | 说明 |
| --- | --- |
| [`apps/api/`](apps/api/) · [`apps/web/`](apps/web/) | FastAPI 后端（Core-1 引擎、适配器、Alembic）与 React 19 + Ant Design 5 工作台 |
| [`plugins/ontofoundry/`](plugins/ontofoundry/README.md) | 外部 Agent 客户端插件（Claude Code / ZCode / Codex / OpenCode） |
| [`integrations/dataagent/`](integrations/dataagent/README.md) | OpenDataWorks DataAgent 建模与问数语义技能源码及打包脚本 |
| [`docs/concepts/`](docs/concepts/README.md) | Core-1 概念手册（对象、继承、值类型、关系、指标、规则、时间与快照、查询语义） |
| [`docs/design/`](docs/design/2026-10-14-core-model-and-format-adapters.md) | 架构与核心设计基线（[Core-1](docs/design/2026-10-14-core-model-and-format-adapters.md) · [Proposal 生命周期](docs/design/2026-09-26-proposal-first-ontology-lifecycle-implementation-design.md) · [外部智能体语义层](docs/design/2026-11-11-runtime-agnostic-semantic-layer-for-agents.md)） |
| [`docs/demo/coffee-channel-sales/`](docs/demo/coffee-channel-sales/README.md) | 精品咖啡渠道销售端到端演示案例（自上而下/自下而上建模 + 问数校验） |
| [`docs/design/2026-09-01-…-design.md`](docs/design/2026-09-01-enterprise-ontology-intelligence-platform-design.md) · [`Ossie 覆盖矩阵`](docs/design/2026-10-08-ossie-coverage-matrix.md) | 产品与架构总体设计；Ossie 字段逐项往返覆盖情况 |
| [`docs/deployment.md`](docs/deployment.md) | 生产配置、平台登录与 SSO、升级与迁移说明 |
| [`docs/releases/`](docs/releases/) | 版本发布日志（另有 [`已知问题`](docs/known-issues.md) 与 [`演进规划`](docs/TODO.md)） |

---

## 边界与演进

OntoFoundry 专注**语义定义、数据映射与只读语义服务**，不替代上游 ETL 或业务执行系统：暂不包含通用 Action 执行引擎、物化调度或跨数据源联表 SQL 编译（跨库计算由消费端 Agent 按本体口径分源对齐）。后续演进重点为 **MCP OAuth 2.0 (PKCE)**、**按对象类型生成的查询/写入提案 MCP** 与更多外部格式适配器，详见 [`docs/TODO.md`](docs/TODO.md)。

---

## 参与贡献与许可证

欢迎通过 [Issues](https://github.com/opendata-lab/ontofoundry/issues) 提交问题或建议，提 PR 前请遵循 [`AGENTS.md`](AGENTS.md) 约定并确认 `make lint`、`make test` 与 `make build` 通过。

本项目采用 [Apache License 2.0](LICENSE) 开源；内置资源许可位于 Apache Ossie（[`LICENSE`](apps/api/src/ontofoundry_api/adapters/ossie/assets/vendor/apache-ossie/LICENSE) · [`NOTICE`](apps/api/src/ontofoundry_api/adapters/ossie/assets/vendor/apache-ossie/NOTICE)）与 DataAgent 技能共享目录（[`LICENSE`](integrations/dataagent/shared/LICENSE) · [`NOTICE`](integrations/dataagent/shared/NOTICE)）。
