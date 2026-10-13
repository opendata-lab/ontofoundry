# OntoFoundry

OntoFoundry 是企业本体建模与发布平台。它将业务文档、数据库结构和人工编辑组织为可审阅的建模草稿，帮助团队定义业务对象、属性、关系及数据映射，再通过版本化的 REST API 和 MCP 服务供应用与 Agent 使用。

前端使用 React 和 TypeScript，后端使用 FastAPI，平台数据存储在 PostgreSQL。AI 建模通过外部 OpenDataWorks DataAgent 接入；未配置 DataAgent 时，仍可使用人工编辑、Ossie 导入导出、版本发布和查询服务。

## 功能

- **本体建模**：定义对象、值类型、属性、关系、继承、约束和 Action，支持目录、详情及图谱查看。
- **AI 辅助建模**：从 Markdown 材料或数据库结构生成变更提案，经用户审阅接受后写入草稿。
- **语义模型与数据映射**：查看和编辑语义模型、数据集、字段、关系、指标及本体映射，展示数据资产结构和映射状态。
- **版本发布**：预览草稿与当前版本的变化，处理合并冲突，发布后保留可查询、可比较的历史版本。
- **Apache Ossie 导入导出**：使用固定版本的官方 Schema 校验，支持原生构造及平台扩展的往返转换。
- **实例与服务**：浏览文档实例，按已发布映射只读查询数据库实例及关系邻域，通过 REST API 和 MCP 读取本体与业务数据。

规则与 Action 的定义可以编辑和发布，通用规则执行与物化、跨数据源查询仍未实现。模型版本固定不会冻结源数据库中的实时数据。

## 快速开始

### 使用 Docker Compose

需要 Docker 和 Docker Compose。以下配置用于本地体验：

```sh
git clone https://github.com/opendata-lab/ontofoundry.git
cd ontofoundry
cp .env.example apps/api/.env
make compose-up
```

启动后访问：

| 服务 | 地址 |
| --- | --- |
| Web 应用 | http://127.0.0.1:8080 |
| API 文档 | http://127.0.0.1:8900/docs |
| 健康检查 | http://127.0.0.1:8900/healthz |

后端容器启动时自动执行 Alembic 数据库迁移。首次启动会创建制造供应链示例，开发身份为 `admin`。停止应用使用 `make compose-down`，数据库保存在 Compose volume 中。

### 从源码运行

需要 Node.js **22.19+**、Python **3.13**、uv 和可用的 PostgreSQL。安装与前端构建均从仓库根目录执行，npm 依赖由 workspaces 统一管理。

```sh
cp .env.example apps/api/.env
make install

# 使用仓库提供的本地 PostgreSQL，也可在 apps/api/.env 配置已有数据库。
docker compose up -d postgres

# 首次运行和升级时执行数据库迁移。
(cd apps/api && uv run --python 3.13 alembic -c src/ontofoundry_api/alembic.ini upgrade head)

make api-dev
```

另开一个终端：

```sh
make web-dev
```

访问 http://127.0.0.1:5174，API 文档位于 http://127.0.0.1:8000/docs。Vite 将 `/api` 等请求代理到本地 API。

如需由同一个 API 进程托管前端，先停止 `make api-dev`，然后执行：

```sh
make build
make serve
```

此时应用和 API 共用 http://127.0.0.1:8000。

## 配置

配置模板见 [`.env.example`](.env.example)，完整定义见 [`config.py`](apps/api/src/ontofoundry_api/config.py)。源码启动时读取 `apps/api/.env`，其中相对路径以 `apps/api` 为基准。

| 变量 | 用途 |
| --- | --- |
| `ONTOFOUNDRY_DATABASE_URL` | 平台 PostgreSQL 连接地址 |
| `ONTOFOUNDRY_DATA_DIR` | 上传材料的本地存储目录 |
| `ONTOFOUNDRY_CONNECTION_KEY` | 加密业务数据库连接凭据的固定 Fernet 密钥，新增数据连接前必须配置 |
| `ONTOFOUNDRY_SEED_DEMO` | 是否初始化示例，正式部署设为 `false` |
| `ONTOFOUNDRY_AUTH_MODE` | 本地开发使用 `dev`，正式部署使用 `oauth` |
| `ONTOFOUNDRY_SESSION_SECRET` | 会话签名密钥 |
| `ONTOFOUNDRY_COOKIE_SECURE` | 是否只通过 HTTPS 发送会话 Cookie |
| `ONTOFOUNDRY_PUBLIC_BASE_URL` | 外部 Agent 访问本平台 MCP 时使用的可达地址 |

可用以下命令生成连接加密密钥，并将输出填入 `apps/api/.env`：

```sh
(cd apps/api && uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
```

业务数据库使用只读账号。连接密钥应固定保存并单独备份，更换它会影响已有连接凭据的解密。

### 接入 DataAgent

[`integrations/dataagent/`](integrations/dataagent/README.md) 提供建模和问数 Agent 定义、`md2ossie` Skill 及安装说明。该目录需要保留在版本控制中，DataAgent 服务本身由外部环境部署。

启用 AI 建模需要配置：

```dotenv
ONTOFOUNDRY_DATAAGENT_BASE_URL=http://your-dataagent-host:port
ONTOFOUNDRY_DATAAGENT_API_PREFIX=/api/v1/nl2sql
ONTOFOUNDRY_DATAAGENT_WEBSITE_ID=ontofoundry
ONTOFOUNDRY_DATAAGENT_ACCESS_KEY=your-server-access-key
ONTOFOUNDRY_DATAAGENT_AGENT_ID=your-created-agent-id
ONTOFOUNDRY_DATAAGENT_REQUEST_TIMEOUT_SECONDS=30
```

Agent ID 使用 DataAgent 创建接口实际返回的值。模型供应商、Skill、任务调度和沙箱由 DataAgent 配置与管理。按[接入指南](integrations/dataagent/README.md)完成安装后，可在空间设置页检查连通性。

### 正式部署

仓库提供的 Compose 是本地部署参考。正式部署需为后端显式注入生产配置；Compose 当前只映射其中的数据库、DataAgent 和连接密钥变量，不能仅靠修改 `apps/api/.env` 启用所有生产设置。

生产配置要求：

- `ONTOFOUNDRY_ENVIRONMENT=production`，`ONTOFOUNDRY_AUTH_MODE=oauth`，并填写模板中的 OAuth 地址及客户端配置。
- 使用至少 32 字符的随机会话密钥，设置 `ONTOFOUNDRY_COOKIE_SECURE=true`、`ONTOFOUNDRY_SEED_DEMO=false`，由 HTTPS 入口提供访问。
- 升级前备份 PostgreSQL、上传材料和连接加密密钥，按 Alembic 迁移链升级数据库。

## API 与 MCP

REST API 的路由、请求和响应可在运行实例的 `/docs` 中查看。查询本体和实例时可指定已发布的 `version_id`。

每个空间的 MCP 地址为：

```text
POST /api/v1/ontology/workspaces/{workspace_id}/mcp
```

使用平台签发的 Bearer 服务令牌访问。令牌默认只读本体；映射和实例读取还需相应权限及有效的空间成员身份。当前实现包含 `server/discover`、`tools/list`、`tools/call`，以及旧版客户端的 `initialize` 兼容协商；尚未提供 MCP OAuth 动态发现。

## 开发与验证

```sh
make test       # API 和前端测试
make lint       # Python 和前端静态检查
make build      # TypeScript 检查与前端构建
```

默认 API 测试使用隔离 SQLite，外部 DataAgent 请求由受控响应替代。验证 PostgreSQL 事务、迁移和并发行为时，提供可创建临时数据库的 PostgreSQL 账号：

```sh
cd apps/api
ONTOFOUNDRY_TEST_POSTGRES_URL='postgresql+psycopg://user:password@127.0.0.1:5432/test_db' \
  uv run --python 3.13 pytest -q
```

真实 DataAgent 端到端测试需另外配置服务、Agent 与材料，不能由单元测试替代。

## 离线安装包

本地生成包含前后端镜像、PostgreSQL 镜像及安装脚本的离线部署包：

```sh
./scripts/create-offline-package.sh
```

默认输出到 `dist/offline/`。也可直接下载 [latest 离线安装包](https://github.com/opendata-lab/ontofoundry/releases/tag/latest)，包含安装文件和 SHA-256 校验和。

GitHub Actions 在 main 更新、版本标签和手动运行时生成安装包。main 的测试和构建通过后，更新 `latest` Release 及 `of-backend:latest`、`of-frontend:latest` 镜像标签；`latest` 随 main 更新，需要固定版本时使用 `v*` Release 或镜像版本/SHA 标签。

新包上传成功后清理旧的同名 Actions artifact，仅保留最新一份。正式版本的包及校验和附到对应 GitHub Release，Release 附件不随 artifact 轮换删除。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `apps/api/` | FastAPI 服务、领域模型、数据库迁移和 API 测试 |
| `apps/web/` | React 应用、前端测试和本地 Conversation SDK 依赖包 |
| `integrations/dataagent/` | 外部 DataAgent 的 Agent 定义、Skill 和接入说明 |
| `docs/` | 产品设计、接口合同、示例演示和文档图片 |
| `scripts/` | 离线部署打包和 Ossie 覆盖矩阵生成脚本 |
| `prototype/` | 已归档的 HTML 设计原型，供历史参考，正式应用不依赖它 |
| `output/` | 本地截图和验收产物，不再新增提交；历史已跟踪图片保留供文档引用 |

`.env`、数据库、上传材料、构建输出和集成包 ZIP 不提交到 Git。文档需要长期引用的公开图片应放入 `docs/assets/`。

## 文档与参与贡献

- [产品与架构设计](docs/design/2026-09-01-enterprise-ontology-intelligence-platform-design.md)
- [提案、草稿与版本发布合同](docs/design/2026-09-26-proposal-first-ontology-lifecycle-implementation-design.md)
- [Ossie 字段覆盖矩阵](docs/design/2026-10-08-ossie-coverage-matrix.md)
- [DataAgent 接入指南](integrations/dataagent/README.md)
- [渠道销售示例](docs/demo/coffee-channel-sales/README.md)

问题和功能建议通过 [GitHub Issues](https://github.com/opendata-lab/ontofoundry/issues) 提交。Bug 报告请包含复现步骤、预期与实际行为，以及去除凭据和私有业务数据的日志。提交 Pull Request 时说明变更范围与验证结果；涉及接口、映射或发布行为的修改应同步更新相关文档和测试。

## 许可证

OntoFoundry 采用 [Apache License 2.0](LICENSE)。允许商业使用、修改和分发，具体授权与义务以许可证正文为准。

第三方依赖和内置资源保留各自的许可证。Apache Ossie 及 `md2ossie` 的 `LICENSE`、`NOTICE` 和来源说明位于各自目录。
