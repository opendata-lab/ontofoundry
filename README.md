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
| Web 应用 | http://127.0.0.1:8010 |
| API 文档 | http://127.0.0.1:8910/docs |
| 健康检查 | http://127.0.0.1:8910/healthz |

后端容器启动时自动执行 Alembic 数据库迁移。`apps/api/.env` 中 `ONTOFOUNDRY_SEED_DEMO=true` 时，首次启动会创建“星港销售”示例并通过开发身份 `admin` 登录；部署到内网时设为 `false`，从空空间开始。停止应用使用 `make compose-down`，数据库和上传材料分别保存在 Compose volume 中，重建容器不会丢失。需要清空全部数据并重新开始时运行 `make compose-reset`，它会删除这两个 volume。

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
| `ONTOFOUNDRY_SEED_DEMO` | 是否初始化示例，正式部署设为 `false` |
| `ONTOFOUNDRY_AUTH_MODE` | `dev` 不登录；`login` 启用本地账号与可选 SSO，生产环境必须使用 `login` |
| `ONTOFOUNDRY_AUTH_CONFIG` | `login` 模式必填，外置 Python 配置文件路径；`dev` 模式不读取 |
| `ONTOFOUNDRY_SESSION_SECRET` | 会话签名密钥 |
| `ONTOFOUNDRY_COOKIE_SECURE` | 是否只通过 HTTPS 发送会话 Cookie |
| `ONTOFOUNDRY_PUBLIC_BASE_URL` | 外部 Agent 访问本平台 MCP 时使用的可达地址 |

数据连接只需填写业务数据库的地址、账号和密码，密码按原样保存在平台数据库中。业务数据库请使用只读账号。

### 平台登录

Compose 默认使用 `login`（`apps/api/.env` 中显式设置的 `dev` 仍优先），只读挂载
[`deploy/docker/ontofoundry/`](deploy/docker/ontofoundry/) 并指定基础配置入口。
源码运行时，将 `ONTOFOUNDRY_AUTH_MODE` 改为 `login`，保留模板中的配置路径即可。
默认本地账号为 `admin`／`admin123`，启动日志会提醒修改默认密码。

现场配置方法：

1. 将 `ontofoundry_config_docker.py.example` 复制为同目录的 `ontofoundry_config_docker.py`，修改 `LOCAL_USERS` 中的用户名、明文密码。基础配置不要直接修改，升级会覆盖它。
2. 需要 SSO 时，将 `custom_sso_user_info.py.example` 复制为 `custom_sso_user_info.py`，按实际返回结构映射用户信息，然后启用覆盖文件中的 `OAUTH_PROVIDERS` 和 `OAUTH_USER_INFO`。只支持一个授权码认证服务；`name` 为 1～64 位字母、数字、下划线或连字符，不能为 `local`。
3. `remote_app` 填写 `client_id`、`client_secret`、`authorize_url`、`access_token_url`、以 `/` 结尾的 `api_base_url` 和回调地址 `https://<平台域名>/api/v1/auth/callback/<name>`；`client_kwargs.scope` 缺省为 `openid profile`。将 `LOCAL_USERS` 设为空列表可关闭本地登录，但必须保留一种登录方式。
4. 限制覆盖文件和钩子文件的权限，只允许后端运行用户读取；它们已被 Git 忽略，包含的密码和客户端密钥按同等要求保管。修改后重启后端，配置不可读、导入失败或格式非法都会阻止启动。

钩子必须是同步的 `oauth_user_info(provider, token_response, oauth_remotes)`，与 DataAgent
同契约，现有钩子文件可直接复用。客户端 `oauth_remotes[provider]` 已绑定基址、Bearer
访问令牌和单次请求 15 秒超时；钩子在线程中运行，不应记录令牌。返回字典必须有稳定的非空
`sub`，名称依次取 `display_name`、`preferred_username`、`name`、`email`、`sub`；可含
`email`，`role` 被忽略。异常、超时或非法返回仅使本次登录失败。
用户按用户名识别且不区分大小写：本地登录取 `LOCAL_USERS[].username`，SSO 取钩子的可选
`username`（1～120 字符，无控制字符），缺省取 `sub`。同名的本地与 SSO 登录共享用户及空间身份。
新用户自动创建；平台管理员也可在首次登录前预建用户、分配空间。

`ADMIN_USERS = ["admin"]` 指定平台管理员用户名（基础配置默认值），拥有全部空间的阅读、编辑和管理权限；
空列表会在启动时警告，且没有人能进入用户管理。开发模式的 `dev` 用户始终是平台管理员。
**用户名冲突风险**：认证服务返回的用户名决定用户身份；若钩子返回本地 `admin`，就会获得其空间身份，
若该用户名也在 `ADMIN_USERS` 中，还会成为平台管理员。接入 SSO 前必须确认用户名可信、不会与本地账号冲突，
或将本地账号改成 SSO 中不存在的名字（例如 `ontofoundry-admin`）。

**本次升级**：已有用户去掉认证前缀（`dev:admin` 改为 `dev`），重名会阻止迁移并列出冲突用户名。
已有空间全部设为公开，所有登录用户可阅读映射、材料、会话及实例（含业务库查询）；不希望共享的空间请在升级后改为私有。
新空间默认私有。回退前备份 `users` 表；降级只能为当前配置中的本地用户恢复 `local:` 前缀，无法还原其他认证服务前缀。

**旧 OAuth 部署迁移**：将模式从 `oauth` 改为 `login`，删除全部 `ONTOFOUNDRY_OAUTH_*`
环境变量（包括 `.env` 中的空值），改用 `ONTOFOUNDRY_AUTH_CONFIG`。旧字段对应如下：

| 旧变量后缀（前缀均为 `ONTOFOUNDRY_OAUTH_`） | 外置配置 |
| --- | --- |
| `PROVIDER` | `OAUTH_PROVIDERS[0]["name"]` |
| `AUTHORIZE_URL`、`TOKEN_URL` | `remote_app.authorize_url`、`remote_app.access_token_url` |
| `CLIENT_ID`、`CLIENT_SECRET` | `remote_app.client_id`、`remote_app.client_secret` |
| `REDIRECT_URI` | `remote_app.redirect_uri`，路径增加 `/<name>` |
| `USER_INFO_URL` | 在钩子中请求该地址；也可拆成 `api_base_url` 和相对路径 |

认证名称必须保持原 `PROVIDER`（默认 `internal`），钩子返回的 `sub` 必须与旧实现从 `sub`
或 `id` 解析出的标识相同，否则会创建新用户，无法保留原空间成员身份。会话密钥与 Cookie
配置继续用环境变量。本次不改数据库结构；回退时恢复旧镜像和原 OAuth 环境变量。

### 接入 DataAgent

[`integrations/dataagent/`](integrations/dataagent/README.md) 提供建模和问数 Agent 定义、`ontofoundry-modeling` Skill 及安装说明。该目录需要保留在版本控制中，DataAgent 服务本身由外部环境部署。

启用 AI 建模需要配置：

```dotenv
ONTOFOUNDRY_DATAAGENT_BASE_URL=http://your-dataagent-host:port
ONTOFOUNDRY_DATAAGENT_API_PREFIX=/api/v1/nl2sql
ONTOFOUNDRY_DATAAGENT_WEBSITE_ID=ontofoundry
ONTOFOUNDRY_DATAAGENT_ACCESS_KEY=          # 可选，DataAgent 站点开启服务端接入时才需要
ONTOFOUNDRY_DATAAGENT_AGENT_ID=your-created-agent-id
ONTOFOUNDRY_DATAAGENT_REQUEST_TIMEOUT_SECONDS=30
```

Agent ID 使用 DataAgent 创建接口实际返回的值。模型供应商、Skill、任务调度和沙箱由 DataAgent 配置与管理。按[接入指南](integrations/dataagent/README.md)完成安装后，可在空间设置页检查连通性。

### 正式部署

仓库提供的 Compose 是本地部署参考，已映射认证模式、会话密钥、安全 Cookie、运行环境和示例开关；正式部署需在 `apps/api/.env` 中显式配置这些值，并提供 HTTPS 入口。外置认证路径由 Compose 固定为挂载目录内的基础配置。

生产配置要求：

- `ONTOFOUNDRY_ENVIRONMENT=production`，`ONTOFOUNDRY_AUTH_MODE=login`，按上节配置本地账号和可选 SSO。
- 使用至少 32 字符的随机会话密钥，设置 `ONTOFOUNDRY_COOKIE_SECURE=true`、`ONTOFOUNDRY_SEED_DEMO=false`，由 HTTPS 入口提供访问。
- 升级前备份 PostgreSQL、上传材料和连接加密密钥，按 Alembic 迁移链升级数据库。

## API 与 MCP

REST API 的路由、请求和响应可在运行实例的 `/docs` 中查看。查询本体和实例时可指定已发布的 `version_id`。

每个空间的 MCP 地址为：

```text
POST /api/v1/ontology/workspaces/{workspace_id}/mcp
```

使用固定令牌访问：平台环境变量 `ONTOFOUNDRY_MCP_TOKEN`（至少 24 个字符，默认 `ontofoundry-mcp-default-token`，正式环境请改为自定义值），调用方填 `Authorization: Bearer <同一个值>`。该令牌只读，可读定义、数据绑定和实例，按所访问空间的管理员身份做成员检查；显式设为空时外部无法访问 MCP。建模运行由平台自动签发临时凭据，不需要配置。当前实现包含 `server/discover`、`tools/list`、`tools/call`，以及旧版客户端的 `initialize` 兼容协商；尚未提供 MCP OAuth 动态发现。

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

默认输出到 `dist/offline/`。也可下载 [latest 安装包](https://github.com/opendata-lab/ontofoundry/releases/tag/latest)，或从 [Releases](https://github.com/opendata-lab/ontofoundry/releases) 选择固定版本。`latest` 是 main 的最新构建。

下载安装包及对应的 `.sha256` 文件后，先校验，再解压安装：

```sh
shasum -a 256 -c ontofoundry-offline-latest.tar.gz.sha256
tar -xzf ontofoundry-offline-latest.tar.gz
cd offline
cp .env.example .env
# 填写 .env 中的连接加密密钥后执行。
./install.sh
```

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

第三方依赖和内置资源保留各自的许可证。Apache Ossie 的 [LICENSE](apps/api/src/ontofoundry_api/adapters/ossie/assets/vendor/apache-ossie/LICENSE) 和 [NOTICE](apps/api/src/ontofoundry_api/adapters/ossie/assets/vendor/apache-ossie/NOTICE) 位于内置资源目录；`ontofoundry-modeling` 的 [LICENSE](integrations/dataagent/skills/ontofoundry-modeling/LICENSE) 和 [NOTICE](integrations/dataagent/skills/ontofoundry-modeling/NOTICE) 位于技能源码目录。
