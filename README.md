# OntoFoundry

OntoFoundry 是面向企业业务人员的本体工程平台。V0.1 聚焦 Markdown 与数据库映射驱动的 Object、Link、Object Type、Link Type 建模、可视化编辑、实例浏览、版本发布、Apache Ossie JSON 校验，以及面向应用和 Agent 的 REST API / MCP 本体服务。

当前已进入正式代码实现：React + TypeScript 前端、FastAPI 后端，保留 HTML 原型作为历史参考。只维护一份权威设计：

- [平台完整设计](./docs/design/2026-09-01-enterprise-ontology-intelligence-platform-design.md)
- [原型参考与分阶段产品补充](./docs/design/2026-09-01-enterprise-ontology-intelligence-platform-design.md#prototype-supplement)：七张参考图、与现有实现的对应关系，以及基线补齐 → 业务 Skill → 探索与智能体的需求。阶段 A 的实施与验收记录见同一文档第 17.12 节，阶段 B/C/D 仍为后续设计。
- [DataAgent + Pi 集成设计](./docs/design/2026-09-12-dataagent-pi-integration.md)：单运行时边界、AgentEvent 协议、SSE、状态投影、部署与验收。

已迁入的内置建模资产：

- [md2ossie Skill](./integrations/dataagent/skills/md2ossie/SKILL.md)：将 Markdown 转换为 Apache Ossie 0.2.0.dev0 Ontology JSON，并执行离线官方 Schema 校验和 semantic lint。

所有范围变化直接修订该文档，不另建精益版或平行方案。

## 本地运行

需要 Node.js 22.19+、Python 3.13 和 uv。默认仅监听本机，开发身份是 `admin`，不可直接用于生产。

前端与 Pi runtime 由根目录的 npm workspaces 统一安装，`make install` 在仓库根执行 `npm ci`，不再单独进入 `apps/web`。Node 版本下限由 Pi 数据面决定。

```sh
make install
make api-dev
# 另一个终端
make web-dev
```

前端 http://127.0.0.1:5174，API http://127.0.0.1:8000/docs。首次启动创建明确标注的制造供应链示例。平台内部统一使用 PostgreSQL；SQLite 只保留给隔离单元测试，不属于部署技术栈。

先将根目录 `.env.example` 复制到 `apps/api/.env` 再配置。从本版本起需要一个可达的外部 OpenDataWorks DataAgent，并配置六个 `ONTOFOUNDRY_DATAAGENT_*` 接入变量；`make dataagent-up` 启动的仓库内置服务仍使用旧运行时路由，已经不兼容（T11 会将其删除）。PostgreSQL 数据保存在 Compose volume，材料文件位于 `apps/api/.data/files`，均不纳入 Git。

## 已接通的流程

- 本体视图、对象/关系目录、详情和人工编辑；对象五步编辑，关系字段映射。语义图谱只画业务对象和它们之间的关系与继承，属性是对象的字段，由卡片计数和详情面板呈现，不画成节点。
- 建模工作台三栏布局：Markdown 材料、DataAgent 通用对话、候选列表/语义图谱。明确点击“开始建模”后才抽取；回答通过 AgentEvent SSE 增量展示并安全渲染 Markdown。
- 服务端会话与草稿保存、候选接受/忽略、同字段冲突提示、三方结构化合并、工作空间整体发布和历史 JSON 下载。
- Apache Ossie JSON 导入导出：内置模型已按 Ossie 扩展（继承、标识关系、requires/derived_by、verbalizes），本平台导出的文件重新导入得到同一个模型，外部文件导入后仍可编译回合法 Ossie。导入先过官方 Schema，可合并或替换，生成建模草稿并逐条报告仍装不下的构造（一元/n 元关系、指向 Any 的关系、计算列映射），发布仍是单独操作。完整对照见设计文档第 9.1、9.2 节。
- 文档实例详情与 1–3 跳关系；数据库只读预览、实例详情及同连接等值 Join 邻域。数据库行不全量同步。
- 本体视图增加业务/技术阅读与同版本 Ossie JSON；对象、属性、关系和空间约束可编辑，发布前可查看标准定义与结构化 Diff，历史版本按 UUID 对齐比较。
- 数据资产目录保留结构快照，展示表/字段到已发布本体的反向映射、缺失字段和结构漂移。源表可以带入草稿映射编辑器，明确选择标识字段并保存后生效。
- REST 类型与实例服务、MCP 均支持固定已发布 `version_id`；实例搜索、详情与邻域共用查询和授权。服务令牌默认只有本体读取权限，实例需要额外 `instances:read` 及签发人的有效成员身份。数据库事实仍为实时读取，固定模型版本不等于固定源库数据。
- 文档实例在候选接受和发布时检查必填、标识属性、继承属性及值类型；不完整草稿可保存，校验失败不能发布。源库质量问题随只读结果报告，无效标识和非有限数值返回明确错误。

界面按给定参考图的头部、侧栏、三栏工作台、卡片目录、步骤条和表格布局实现。小于 1100px 时整体缩放，不改成另一套移动布局。右侧只保留“本体模型列表 / 语义图谱概览”两个页签。所有值来自 API，没有把原型的模拟结果当作模型输出。

## 配置与部署边界

正式发布只产出 `of-web`、`of-api`、`of-agent-master` 和 `of-agent-worker` 四个业务镜像。不包含独立的 Portal MCP 代理；平台 MCP 由 `of-api` 原生提供，Pi 保留可连接显式配置 MCP server 的通用客户端。

- Agent 后端：`ONTOFOUNDRY_DATAAGENT_BASE_URL`、`ONTOFOUNDRY_DATAAGENT_API_PREFIX`、`ONTOFOUNDRY_DATAAGENT_WEBSITE_ID`、`ONTOFOUNDRY_DATAAGENT_ACCESS_KEY`、`ONTOFOUNDRY_DATAAGENT_AGENT_ID`、`ONTOFOUNDRY_DATAAGENT_REQUEST_TIMEOUT_SECONDS`；任务执行模式沿用 `ONTOFOUNDRY_DATAAGENT_EXECUTION_MODE`。
- 模型供应商：Compose 将 `ONTOFOUNDRY_ANTHROPIC_BASE_URL`、`ONTOFOUNDRY_ANTHROPIC_MODEL`、`ONTOFOUNDRY_ANTHROPIC_API_KEY` 注入 DataAgent。这里的 Anthropic-compatible 是 Pi 使用的模型传输协议，不依赖 Claude Agent SDK。
- 数据库连接密码：配置固定的 Fernet `ONTOFOUNDRY_CONNECTION_KEY` 后才能新增连接。部署时用源库只读账号，不将密码写入本体版本。
- OAuth：配置服务端地址、client ID/secret、回调 URI；启用 `AUTH_MODE=oauth`。生产启用 HTTPS 安全 Cookie、随机 session secret，关闭 demo seed。

构建后可由同一个 API 进程托管前端，无需生产 Vite：

```sh
make build
make serve
```

`make serve` 用 `ONTOFOUNDRY_WEB_DIST=../web/dist` 托管 SPA 与 API。同域 HTTPS 入口由部署环境的反向代理提供。Agent 任务统一进入 DataAgent：平台控制面和 DataAgent 共用同一 PostgreSQL 的 `public` schema 和一张 `alembic_version`，Redis 管理调度协调，Pi Cell 执行模型循环。Agent master 不再内置 MySQL/Doris 查询桥；外部能力通过显式配置的 MCP server 扩展。正式上线前仍需完成真实模型、OAuth、外部 MCP、并发与大文件测试。

暂未完成的设计项：规则执行与物化、业务 Skill、探索问数和智能体应用、通用中间表关系映射、跨源查询、文档/数据库事实的同屏混合浏览。表达式可编辑、保存和发布，当前没有执行引擎。

所有平台表和 DataAgent 表由同一套 Alembic migration 管理，部署配置不使用 API 启动时 `create_all`。升级既有的双 schema 开发库时，migration 会把已知的 `dataagent.da_*` 表移动到 `public`，删除 eval 表和已被 DataAgent/Pi 替代的旧 B0.1 运行表，最后只保留 `public.alembic_version`。这一步会删除废弃运行历史，执行前必须备份并验证恢复能力。

```sh
cd apps/api
ONTOFOUNDRY_DATABASE_URL=postgresql+psycopg://... \
  uv run alembic -c src/ontofoundry_api/alembic.ini upgrade head
```

MCP 当前实现 2026-07-28 的 `server/discover`、`tools/list`、`tools/call`，使用本平台签发的只读 Bearer 令牌；尚未实现 MCP OAuth 动态发现或兼容旧版 `initialize` 客户端。上线前需与实际消费端核对版本。

## 验证

```sh
make test
make lint
make build
```

默认单元测试使用临时 SQLite 和受控模型协议响应；部署与迁移验证必须使用 PostgreSQL。设置 `DATAAGENT_TEST_POSTGRES_URL` 后运行 `dataagent/dataagent-backend/tests/test_postgres_store_integration.py`，用例只删除名称以 `dataagent_test_` 开头的隔离 schema。浏览器验收截图在 `output/playwright/`，实际结果持续记录在设计文档中。
