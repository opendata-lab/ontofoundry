# 业务数据源连接池与统一只读取数接口（2026-11-06）

状态：草案，已经 Gemini 评审（handoff `2026-11-06-gemini-source-pool-review`），Claude 核对后修订（§6）。用户要求（2026-11-06）：业务数据源需要连接池；调用方只通过接口要数据，连接复用由后端统一处理。与 [会话数据表范围与 AI 可读读取](2026-11-06-table-scope-and-ai-ready-reads.md) §3.4 的 `sample_table` 相关，但独立实施。

## 1. 现状

- 平台自身数据库有连接池：`database.py:12-14` 全局一个 engine，SQLAlchemy 默认池（5 个、溢出 10）加 `pool_pre_ping`。
- 业务数据源（MySQL、Doris、PostgreSQL）没有池：`services/readonly.py:12-60` 的 `connect_readonly` 每次调用新建 engine、建一条连接、设只读和超时、执行、回滚、`engine.dispose()`。每次都重新 TCP 握手和认证。
- 13 处调用，8 个文件：连接测试与库表发现（`api/connections.py:120,152,180,205`）、库表列表（`api/assets.py:42`）、元数据同步（`services/metadata_sync.py:241,258`，15 秒超时，用 SQLAlchemy Inspector）、数据集校验（`services/dataset_validation.py:40,74`）、表预览（`services/table_preview.py:38`）、实例查询（`services/instance_plan.py:532`、`services/instance_neighborhood.py:34`）、指标查询（`services/metric_query.py:430`）。
- `api/connections.py:152` 测试的是未保存的候选配置。
- 超时：PostgreSQL 通过连接参数 `options=-c statement_timeout=…` 设定（建连时固定）；MySQL 用 `SET SESSION MAX_EXECUTION_TIME`；Doris 用 `SET query_timeout`。只读：PostgreSQL `SET TRANSACTION READ ONLY`，MySQL `SET SESSION TRANSACTION READ ONLY`。
- 部署是单个 uvicorn 进程（`apps/api/Dockerfile:43`）；同步任务在后台执行。

问题：取数频繁的场景（建模运行按需取样、问数、实例浏览）每次都建连，延迟高、业务库连接抖动；调用方各自拼连接和超时，规则分散。

## 2. 方案

### 2.1 一个模块负责连接：`services/source_access.py`

- **池**：每个数据连接一个 engine，按 `(connection_id, 配置指纹)` 缓存。指纹覆盖驱动、主机、端口、库、用户名和密钥版本；配置或密钥变化即换新 engine，旧 engine 关闭。
- **池参数**（默认，可配置）：`pool_size=2`、`max_overflow=2`、`pool_timeout=5` 秒（取不到连接报“数据源繁忙，请稍后重试”）、`pool_recycle=300` 秒、`pool_pre_ping=True`。
- **每次借出都重设会话**：只读、本次超时（不同调用超时不同，不能固定在建连参数里；PostgreSQL 改为每次 `SET statement_timeout`），归还时回滚。会话级设置因此不跨调用泄漏。
- **空闲回收**：后台定时关闭超过 10 分钟没用过的 engine，避免长期占着业务库连接。
- **失效**：数据连接修改、删除时立即关闭对应 engine；应用关闭时全部关闭。
- **不入池**：连接测试的未保存候选配置，用一次性连接（沿用现行为）。
- **并发**：engine 缓存的创建与替换加锁；连接本身由 SQLAlchemy 池管理。

### 2.2 调用方只要数据

调用方不再拿连接，按用途调用：

| 接口 | 返回 | 用于 |
|---|---|---|
| `fetch_rows(connection, statement, *, timeout_ms, max_rows)` | 列名和行（值已做预览转换），截断标记 | 表预览、实例查询、指标查询、数据集校验、`sample_table` |
| `inspect_catalog(connection, schema, tables=None, *, timeout_ms)` | 库、表、列、主外键结构 | 元数据同步、库表发现 |
| `check_connection(config)` | 是否可连、服务端版本 | 连接测试（不入池） |

- `statement` 必须是 sqlglot 表达式或已通过白名单检查的 SQL，模块内再按数据源方言生成；调用方不拼字符串。
- 错误统一转换为现有 `ServiceError`（`QUERY_TIMEOUT`、`QUERY_FAILED`），新增 `SOURCE_BUSY`（池满）。
- `connect_readonly` 保留为模块内部实现，迁移完成后不再对外导出。

### 2.3 观测

每个 engine 记录借出次数、等待超时次数、当前占用；日志不打印密码和完整连接串。

## 3. 不做

- 跨进程共享池（当前单进程）；以后多进程时每进程各自一个池，池参数按进程数折算。
- 查询结果缓存。
- 写操作（业务数据源只读）。

## 4. 风险与取舍

- 长连接被业务库 `wait_timeout` 或防火墙断开：`pool_pre_ping` 加 `pool_recycle` 处理。
- 同步任务长时间占用连接，挤占交互查询：同步与交互是否分池或限定同步占用，待评审定。
- 借出时的会话重设遗漏会导致只读或超时失效：集中在一个函数，并有测试覆盖三种方言。
- 池参数过大给业务库加压：默认值小，每个数据连接最多 4 条。

## 5. 删掉会失去什么

- 不做连接池：每次取数都重新建连，按需取样和问数的延迟与业务库连接抖动随调用次数增长。
- 不做统一接口：超时、只读和方言规则散落在 13 处调用里，后续改动容易漏。

## 6. 评审后修订（2026-11-06）

Gemini 评审 10 条，Claude 逐条核对代码，均成立；据此修订 §2：

1. **接口分两层**。`fetch_rows` 太窄：实例查询在构建计划时就要用连接（`services/dataset_sources.py:82` 反射表结构，`services/instance_plan.py:305` 查快照日期最大值），用 SQLAlchemy Core 语句和自定义编译节点，需要原始 Python 值做主键类型判断；指标预览要绑定参数（`services/metric_query.py:430-436`）；数据集校验要读游标的列类型码并检查重名列（`services/dataset_validation.py:40-46`）。改为：
   - 模块内部的 `source_session(connection, *, timeout_ms)`：从池借出、重设会话、归还，供服务层复杂调用方（实例、同步）使用；
   - 对外按用途的函数：`fetch_rows(connection, statement, *, params=None, timeout_ms, max_rows, raw_values=False)`（接受 sqlglot 表达式或 SQLAlchemy Core 语句）、`probe_columns(connection, statement, *, timeout_ms)`（列名与类型码，供数据集校验）、`list_schemas`、`list_tables`、`inspect_table`（替代一个大而全的 `inspect_catalog`）、`check_connection(record)`（不入池，无返回值）。
   - API 路由、MCP 工具和新功能只用对外函数，不碰连接。表数据集的关系改由已同步结构构造，不再实时反射（减少一次往返，计划构建不依赖连接）。
2. **指纹**：没有密钥版本字段，密码按原文存在 `secret_encrypted`（`db_models.py:182-185`，注释说明是有意的内网做法）。指纹用驱动、主机、端口、库、用户名加密码的 sha256，日志和指标里只出现连接 ID。
3. **超时**：MySQL/Doris 的 socket `read_timeout` 是建连参数（`services/readonly.py:21-27`），`MAX_EXECUTION_TIME` 只管 SELECT，不管 Inspector 的 SHOW。借出时按本次超时更新驱动连接的读超时；PostgreSQL 建连时设 `default_transaction_read_only=on`，借出时 `SET SESSION statement_timeout`。
4. **归还**：现在 `rollback` 不在 `finally` 里（`services/readonly.py:58-59`），调用方抛异常会跳过回滚。改为 `finally` 回滚，回滚失败则 `invalidate` 这条连接。
5. **连接测试不入池且不影响现有池**：新建（`api/connections.py:120`）、修改前测试（`:152`，候选记录带着现有 ID）、库表发现（`:180`）都走一次性连接；修改和删除在提交成功后才关闭旧池。
6. **同步不挤占交互**：同步锁按 `(连接, 库)`（`services/metadata_sync.py:218-221`），多个库同时同步可能占满池。同步逐表借还连接（不跨平台库提交持有），每个数据连接的同步借出用信号量限制为 1，至少留 2 条给交互查询。
7. **池满单独报错**：池等待超时抛 `sqlalchemy.exc.TimeoutError`，现有按文字判断“timeout”会误报为 `QUERY_TIMEOUT`（504）；先单独捕获，报 `SOURCE_BUSY`（503）。
8. **空闲回收**：每个池记录借出中数量和最后使用时间，只回收借出为 0 且空闲超过 10 分钟的；关闭放在缓存锁外。
9. **MCP 阻塞事件循环（现有问题）**：`api/mcp.py:76` 的 `rpc` 是 async，却同步调用 `invoke`（`:184`），`resolve_entity` 查业务库时会卡住整个进程的事件循环；`sample_table` 加入后更明显。改为在线程池里执行 `invoke`，与连接池同一 PR。
