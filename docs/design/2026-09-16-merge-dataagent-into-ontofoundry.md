# 把 DataAgent 后端并入 OntoFoundry

**日期:** 2026-09-16
**目标:** 两个 Python 服务合成一个,保留 TS 运行时不动。

## 现状

| | ontofoundry_api | dataagent-backend |
| --- | --- | --- |
| 位置 | `apps/api/src/ontofoundry_api` | `dataagent/dataagent-backend` |
| 代码量 | 约 7,200 行 | 约 16,400 行(不含测试) |
| 数据访问 | SQLAlchemy ORM | 裸 `psycopg` + 手写 SQL |
| 连接 | `create_engine(..., pool_pre_ping=True)`,**有池** | `psycopg.connect()` 每次新建,**无池** |
| 进程入口 | `create_app()` | `main.py`、`sandbox_runner_main.py`、`sandbox_task_main.py` |
| 通信 | `DataAgentClient` 经 HTTP 调用对方,11 个方法 | 被调方 |

已经统一的部分(本次不需要处理):

- **数据库**:两边都是 `postgresql://ontofoundry@.../ontofoundry`,`dataagent_database_schema = "public"`,同库同 schema。
- **迁移**:只有一套 alembic(`dataagent/dataagent-backend/alembic.ini`)。`20260913_000001` baseline 同时建 11 张 OntoFoundry 表和 15 张 `da_*` 表。
- **建表机制**:`Base.metadata.create_all()` 由 `auto_create_schema` 守着,默认 `False`,compose 未设置,部署环境不会执行。schema 归 alembic 唯一所有。

**沙箱不受影响。** agent 实际执行发生在 TS 运行时(Pi Cell)里,Python 侧只负责 spawn。合并 Python 进程不改变模型生成代码的执行边界,因此这不是一次安全模型变更。

## 问题

- 一个逻辑产品跑两个 Python 服务,同一个库,彼此用 HTTP 互调。部署、配置、依赖各两份。
- `DataAgentClient` 的 11 个方法全是进程间序列化开销,而两端共享同一个数据库。
- DataAgent 侧无连接池,是此前 N+1 代价高昂的根因(`list_documents` 曾 255 连接 / 532ms)。合并后若继续裸连,单进程的连接数只会更难约束。
- OntoFoundry 页面无法呈现 DataAgent 的真实状态(见 `7b9a683`:协议、模型名都只能写死或省略),因为跨服务取数代价过高。

## 方案

### 1. 单进程,双路由挂载

DataAgent 的 FastAPI 路由挂进 `create_app()`,保留原有 URL 前缀(`/api/v1/dataagent/...`、`/api/v1/nl2sql/...`),使前端与 TS 运行时无需改动。`main.py` 退化为薄入口或删除。

`sandbox_runner_main.py` 与 `sandbox_task_main.py` **保持独立入口**。它们是被 spawn 的子进程,不属于 API 服务,合并进 web 进程没有意义。

### 2. 数据访问统一到 SQLAlchemy

五个裸 psycopg 消费者迁移到共享 engine:

- `core/database.py`(连接工厂,迁移后删除)
- `core/skill_admin_store.py`
- `core/topic_task_store.py`
- `core/runtime_registry_store.py`
- `core/agent_profile_service.py`

**不改写为 ORM 模型**,仅把连接来源换成共享 engine、SQL 经 `session.execute(text(...))` 执行。理由:这些 store 的 SQL 已被大量测试锁定,改写查询语义会把一次基础设施合并变成一次行为重构。ORM 化可以后续单独做。

副作用:DataAgent 侧自动获得连接池。

### 3. 事件循环与线程池隔离

合并后 agent 长任务(SSE 流、可达 30 分钟的 run)与本体编辑请求共享同一个事件循环与默认线程池。

- 交互式端点继续走 FastAPI 默认线程池。
- agent 执行与流式端点使用**独立的 `anyio` 限流器或专用 executor**,使长任务无法占满交互式请求的线程。
- `a040ff9` 建立的约束(路由 handler 不得 `async def` 却不 await)扩展覆盖合并进来的路由模块。

### 4. 配置合并

`dataagent/dataagent-backend/config.py` 的字段并入 `Settings`。`database_url` 与 `dataagent_database_url` 指向同一个库,合并为一项;保留 `DATAAGENT_DATABASE_URL` 作为过渡期别名。

## 取舍

- **不做 ORM 化**:见上。基础设施合并与查询重写分开,失败时可独立回退。
- **不合并沙箱入口**:它们是子进程,不是服务。
- **保留 URL 前缀**:避免同时改动前端与 TS 运行时,合并本身已经足够大。
- 另一种方案是保持两个服务、只共享数据库连接配置。成本最低,但不解决部署两份、HTTP 互调、页面看不到真实状态的问题。

## 风险

- 合并后单进程故障域变大:DataAgent 的崩溃会带走本体编辑 API。缓解手段是第 3 点的隔离,以及合并前补齐两侧的健康检查。
- 依赖集合并可能出现版本冲突(两侧各有 requirements)。需在合并前做一次依赖求解。
- 约 16,400 行代码换连接层,测试覆盖是唯一保障。合并前必须确认 DataAgent 侧 450 个测试全绿,且 `test_postgres_store_integration.py` 能对真实库跑通——它目前被跳过。
