# AGENTS.md

`CLAUDE.md` 只引用本文件。模型、接口和契约以 `docs/design/` 中当前生效的设计文档及其“已确认决定”表为准，概念说明在 `docs/concepts/`。

## 产品原则

- 核心模型只表达业务语义。SQL 写法、类型转换、精度、日期不齐、空周期显示、选哪张表更快等执行细节交给查询 Agent，不进入模型。
- 以 Apache Ossie 为语义基准，尽量无损承载；做不到的集中记录在设计文档的例外表里。
- 新增字段、状态或模式前先说明它来自哪里（Ossie、Fabric IQ、Palantir Foundry，还是自创）、是语义还是执行优化、删掉会失去什么、已有结构能否表达。不加只为弥补另一个概念而存在的概念。
- 能从已有定义推导出的关联、统计和展示信息不存进模型。

## 协作约定

- 业务或产品取舍交给用户决定，提问时给出具体数据例子（改前改后的结果）和推荐选项。
- 中大型改动先写设计和计划：`docs/design/YYYY-MM-DD-<topic>.md`、`docs/plans/YYYY-MM-DD-<topic>-plan.md`；模型概念变化时同步更新 `docs/concepts/`。
- 代码注释和提交信息用英文；文档和界面文案用中文。文档、示例和测试只用虚构的工作空间名和业务表名。
- 一个任务的全部编辑完成后再统一跑测试，不要每改一处就跑。
- 只在用户明确要求时 commit 或 push。不提交 `.claude/`、`docs/design/prototypes/`、评审报告和 `integrations/dataagent/dist/`；文档不链接原型。

## 代码约定

- 后端（`apps/api/src/ontofoundry_api/`）：`api/` 只做路由、校验和权限检查，业务在 `services/`，`domain/` 不依赖数据库会话和 HTTP。业务错误抛 `services/errors.py` 的 `ServiceError` 子类（英文 `code`、中文 `message`），服务层不抛 `HTTPException`。
- 契约变化时同时更新 `contracts/` 的 JSON Schema、Pydantic 模型和前端类型。
- 业务数据源只读；SQL 经 sqlglot 解析和白名单检查后执行。
- 表结构变化必须新增 Alembic 迁移；设计决定不迁移数据时，不临时加迁移分支。
- 前端（`apps/web/src/`）：控件用 Ant Design 5，布局用 Tailwind CSS v4，`styles/tokens.css` 是唯一的设计变量来源；不再新增手写控件和零散 CSS 文件，旧页面改到哪里替换到哪里。接口调用统一走 `api/client.ts`。
- 生成 id 用 `lib/id.ts` 的 `newId()`，不直接用 `crypto.randomUUID`：现场部署通过局域网 IP 的 HTTP 访问，是非安全上下文。前端或部署改动要用局域网 IP 验证一次。

## DataAgent 集成

- 平台只引用 DataAgent 上已有的 Agent，不创建或修改它。Agent 提示词以 `integrations/dataagent/agents/*.md` 为准，改动后要同步到 DataAgent 管理后台并发布。
- 技能源码在 `integrations/dataagent/skills/`，改动后按 `integrations/dataagent/README.md` 复制到 DataAgent 的 `SKILLS_ROOT_DIR` 并重启。
