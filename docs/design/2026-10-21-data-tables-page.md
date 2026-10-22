# 数据管理「数据表」页：左侧操作区与步骤式同步

日期：2026-10-21。状态：已实施，2026-10-21 按预览反馈补充 DT-04–DT-07。来源：用户 2026-10-21 反馈（数据表页布局与同步操作）。

## 1. 已确认需求

| 编号 | 需求 |
|---|---|
| DT-01 | 页面左侧是操作区：选择数据连接、选择库（schema，含“全部”），搜索表名／注释，显示同步时间，可排序。右侧是已登记数据表列表。 |
| DT-02 | “同步”是一个操作按钮，点开后弹窗，步骤式完成：① 选择数据连接 ② 选择库（可多选）③ 选择表（可全选，也可部分选择；按库分组）④ 同步进度与结果。 |
| DT-03 | 一个连接下有多个 schema 的场景必须支持：浏览时可在库之间切换或看全部；同步时可一次选择多个库。 |
| DT-04 | 「同步数据表」按钮和搜索框与「文档」Tab 一致：放在列表上方的灰底工具栏，主按钮在左，搜索框在右；连接下拉（页面和同步弹窗）只显示连接名。 |
| DT-05 | 每张表可查看表详情：基本信息、字段，以及只读查询的前 100 行数据。 |
| DT-06 | Doris 连接的表清单和表结构按 schema 显式读取，与 opendataworks 一致：`information_schema.tables/columns` 以 `TABLE_SCHEMA` 过滤；字段类型依次取 `COLUMN_TYPE`、`DATA_TYPE`，仍为空时用 `SHOW FULL COLUMNS` 补；`COLUMN_KEY = 'PRI'` 记为主键；隐藏 `information_schema`、`mysql`、`performance_schema`、`sys`、`__internal_schema`。 |
| DT-07 | 同步、表清单、表数据预览和登记表目录只读取连接允许范围内的库（MySQL 为配置的 database，配置了 schemas 时以其为准，Doris 排除系统库）；不能把“存在快照”当成仍获准读取。 |

## 2. 设计

### 2.1 页面布局

- 左侧操作区（固定宽度面板，使用现有布局组件）：
  - 数据连接选择（下拉，只显示连接名）。
  - 库列表：每项显示库名、已登记表数、最近同步时间；顶部“全部库”。选中项决定右侧列表范围。
  - 排序：表名、最近同步时间、列数，升序／降序。
- 列表上方灰底工具栏（与「文档」Tab 相同）：左侧主按钮“同步数据表”和表数，右侧搜索框（按表名或注释过滤已登记表，不触发同步）。
- 右侧：已登记数据表表格——表名、库、列数、状态（已登记／当前不可见或不存在）、最近同步时间、说明；超过 20 行分页。点击表名打开表详情弹窗：「基本信息」（表名、库、类型、状态、字段数、最近同步时间、主键、引用的数据集、说明）、「字段」、「数据」（切到该页签才查询，只读，最多 100 行；二进制值以 0x 十六进制显示）。

### 2.2 同步弹窗（Ant Design Steps）

1. **选择数据连接**：默认带入左侧当前连接。
2. **选择库**：列出连接可见的全部库，可多选；显示每个库已登记表数与最近同步时间。
3. **选择表**：按库分组列出可同步的表（含未登记的），可搜索；支持“全选当前库”“全选全部”与逐个勾选。全选某库等价于该库全量同步（会把库中已消失的表标为不存在）；部分选择只同步所选表。
4. **同步进度与结果**：每个库一个同步任务，显示批次进度、耗时、成功／失败数；失败可重试；完成后列出每张表的结果，关闭弹窗后左侧与列表刷新。

### 2.3 后端

- 新增 `GET /connections/{id}/assets/rows?schema_name=&table_name=`：只读取已同步且未消失的表，标识符来自快照并由 sqlglot 生成 `SELECT * … LIMIT 100`，需要映射和实例查看权限，并校验库范围。
- 复用现有接口：`GET /connections/{id}/schemas`、`GET /connections/{id}/tables?schema_name=`、`GET /connections/{id}/assets?schema_name=`、同步任务创建／查询／重试。
- 多库同步：前端对每个选中库各建一个同步任务（scope=all 或 selected），不新增跨库任务概念。
- 如现有响应缺少“每张表最近同步时间”“每个库的已登记表数与最近同步时间”，在现有资产／库接口的响应里补充这两个派生字段（来自已保存的元数据快照，不新增存储）。契约变化按 AGENTS.md 同步 Pydantic、JSON Schema 与前端类型。

### 2.4 不做

- 不新增数据集概念或跨库同步任务状态；不改变同步语义（全量会标记消失表，部分只同步所选）。
- 搜索与排序只作用于已登记表列表，不访问业务库。

## 3. 界面规范

遵守 `docs/design/2026-10-17-ui-visual-consistency.md`：控件用 Ant Design 5、布局用 `components/layout/`，视觉数值只改 `styles/tokens.css`。“左侧操作区＋右侧列表”和“步骤式弹窗”若为新布局模式，先补该文档第 4 节。

## 4. 实施选择

- 跨库列表由前端逐库请求 assets 后合并：现有省略 schema 的行为是归一化到默认库，其他调用方依赖该语义；保留接口兼容性，无新增存储。
- 每张表的 observed_at 已由同步服务写入快照并经 assets 原样返回，前端补齐该既有字段类型。每库表数由快照表清单计算，最近同步时间使用 assets.observed_at；无需新增后端派生字段、模型概念或迁移。
- schemas 接口按连接 schemas 配置过滤可见库；MySQL 默认只列配置的 database。
- 读取引擎由 `connect_readonly` 记在连接上，`services/metadata_catalog.py` 统一负责库范围、表清单和 Doris 表结构；同步、`/tables` 和单表字段读取都走这里。`/tables` 省略 schema 时归一化为连接默认库。

## 5. Doris 历史快照处理

现场反馈：Doris 连接下 5 个库都显示同一批（主库的）257 张表。本地无 Doris，未能复现根因；DT-06 改为按 schema 显式过滤读取。已写入的错误快照不会因部署新代码或重试而消失：重新全量同步只会把不属于该库的表标为“当前不可见或不存在”。处理步骤：

1. 备份该连接的 `metadata_snapshots`、`metadata_sync_jobs`、`metadata_sync_batches`。
2. 删除该连接的快照（不迁移数据）。
3. 部署新版本后，在同步弹窗中对每个业务库新建全量同步任务（不要重试旧任务，旧任务会复用原清单）。
4. 核对已有数据集引用：引用的表若在正确的库中不存在，会显示来源诊断，按提案或数据集修改流程处理。

## 2026-10-22 修复（v0.2.1）

本节取代 DT-07 和第 4 节中“MySQL 只列配置 database”“省略库名默认使用连接库”的规则。MySQL/Doris 连接代表整个服务；显式选择业务库，空库名报 `SCHEMA_REQUIRED`，配置了 schemas 时仍遵守允许范围。PostgreSQL 仍须填写连接数据库，schema 缺省仍为配置值或 public。不增加核心模型字段。

### 根因与证据边界

**能确定的缺陷**：本轮开始时 `normalize_schema` 虽已去掉 MySQL/Doris 的 database 回落，仍无条件回落到遗留 `config_json.schema_name`。例如连接保存 `schema_name=main`，省略库名的列表、建任务、assets 请求仍读 main，绕过“必须选择库”的规则。后台 `run_job` 没有重新校验持久化任务的库名和当前权限，且把空字符串转成 None；MySQL 方言在 None 时使用 default_schema_name。保存前也未核对观察结果与任务库名是否一致。这些缺口已修复并有回归覆盖。

**不能据此断言现场最初五份 257 张表的产生原因已查明**：当前前端明确传非空 schema，后端也一路保留。未取得现场请求、任务/快照、Doris 版本和 catalog 的对应证据。连接 URL 带 database 本身不能证明它覆盖了显式 schema；本机 SQLAlchemy 的 MySQL 方言在显式 schema 下发出 `SHOW FULL TABLES FROM <指定库>`、`DESCRIBE <指定库>.<表>`，get_columns/get_pk_constraint/get_table_comment/get_foreign_keys 共用带 schema 的 SHOW CREATE TABLE 反射。原始现场故障仍待其运行证据定案。

最小复现（SQLite ATTACH、从 HEAD 抽取原 normalize_schema 与修复实现比较）：连接的 database/schema_name 均为 fiction_alpha；alpha 仅有 fiction_alpha_only，beta 仅有 fiction_beta_only。请求 schema=None 时，HEAD 归一化为 fiction_alpha 并返回 fiction_alpha_only，修复实现返回空名并由入口拒绝；显式请求 fiction_beta 时，HEAD 和修复实现都保持 fiction_beta，读取结果为 fiction_beta_only。这同时证明默认回落缺陷存在，以及不能把显式库名被覆盖当成已复现结论。

**前次改读 information_schema 后仍看到旧表的确定原因**：`run_job` 的重试复用 inventory_json 和成功批次，不重新列库中表；新建全量任务虽重新列该库，仍把旧快照中已不在源清单的表保留为 missing，assets 继续展示它们。回归注入两个库各一份相同错误表，重新全量后错误表仍在 assets 中、状态为 missing，registered-tables 则过滤它。这说明读取修复不会自动清除历史错误记录，不能只重试旧任务来验证修复。

| 链路 | 核查结果与代码位置（apps/api/src/ontofoundry_api/ 下，前端仅阅读） |
|---|---|
| 列库 / 选库 | `services/metadata_catalog.py:visible_schemas/schema_allowed` 过滤系统库与 schemas 白名单。`apps/web/src/components/TableSyncDialog.tsx` 用每个选中库 s 请求 tables 和 refreshAssets；`apps/web/src/lib/metadataSync.ts` 按库请求 assets，`api/client.ts:query` 保留非空 schema_name。 |
| 列表 | `api/connections.py:tables` 归一化并校验库名后调用 list_tables；MySQL inspector 的表与视图列表都传 schema。 |
| 建任务 / 后台 | `services/metadata_sync.py:create_job` 把显式 schema 写入任务；run_job 重新校验并直接传 job.schema_name，重试不更换任务库。 |
| 读字段 | read_table 的 has_table/get_columns/get_pk_constraint/get_table_comment/get_foreign_keys/get_view_names 都显式带 schema；Doris 的 tables/columns 查询同时以 TABLE_SCHEMA、TABLE_NAME 过滤，类型补查限定并转义库与表名。 |
| Doris catalog / 前缀 | 按 TABLE_SCHEMA 精确匹配，不裁剪前缀。测试覆盖带冒号前缀与不带前缀的隔离；没有真实 Doris，无法验证现场版本的 catalog 可见范围或列库返回值与 TABLE_SCHEMA 格式差异。字符串不匹配会导致空清单，当前没有证据支持它导致复制主库表。官方 [3.x 系统表说明](https://doris.apache.org/docs/3.x/admin-manual/system-tables/overview/) 明确每个 catalog 的 information_schema 只含该 catalog 的元数据，[SHOW DATABASES](https://doris.apache.org/docs/2.0/sql-manual/sql-reference/Show-Statements/SHOW-DATABASES) 默认列当前 catalog；当前连接没有 catalog 选择机制，因此不能声明支持跨 catalog 同步，也不把 catalog 名擅自当成库名前缀。 |
| 保存 | save_observation 先验证 table.schema 等于 job.schema_name，再按 `(connection_id, schema_name)` 读写快照。全量消失标记也带任务库名。 |
| 展示 | assets 校验显式库名及允许范围后按同一复合主键读取；registered-tables 用快照库名输出身份。登记目录不再把未指定库的数据集显示为所有同名表的引用。 |

### 修复与测试

- MySQL/Doris 的连接 URL 不选择 database，归一化也不从 database/schema_name 猜库；导入上下文和数据集来源采用一致规则。
- 请求入口、后台任务、源读取、快照保存各检查相应的库边界；不同库的同名表不合并、不做跨库表名去重。
- 新增 `tests/test_metadata_schema_isolation.py`：SQLite ATTACH 两个业务库，每库含字段/主键不同的同名表、独有表和视图，覆盖 MySQL inspector 与 Doris information_schema 两条路径，从 API 列表、选择同步、全量同步直至 assets/registered-tables 和持久化快照。另覆盖省略库、遗留配置/任务、后台权限变更、观察结果错库、删除和消失表隔离、前缀精确匹配、Doris 类型补查、MySQL 方言 SQL、连接 URL 及迁移。
- 既有同步测试显式使用 SQLite 的 main 库，数据集和导入测试夹具为 MySQL 显式填写库名，权限测试改为 schemas 白名单，不放松产品约束。
- 首轮完整验证：1079 passed、1 failed、17 skipped。失败是旧导入测试输入省略了 MySQL 库名，审阅夹具补库后导致同文件二次导入产生差异；已在测试输入显式指定虚构库名。ruff 的导入排序及测试变量遮蔽问题也已修正。
- 最终完整验证：**1085 passed、0 failed、0 errors、17 skipped、3 warnings，104.32 秒**；ruff **All checks passed**。新增多库/边界用例覆盖 MySQL 与 Doris 两条读取路径（真实服务验证不计入这些测试）。警告为既有 TestClient 依赖弃用和 Pydantic 字段命名提示。

```sh
cd /Users/guoruping/project/bigdata/ontograph-hotfix/apps/api
PYTHONPATH=src /Users/guoruping/project/bigdata/ontograph/apps/api/.venv/bin/pytest -q -p no:cacheprovider
/Users/guoruping/project/bigdata/ontograph/apps/api/.venv/bin/ruff check src tests
```

最终 pytest 日志为 `/private/tmp/ontofoundry-021-pytest-final.log`。没有修改 apps/web、main 分支或主目录源码，没有 commit/push；并行工作产生的其他文件改动保留。

### 真实 MySQL 只读验证

脚本仅保留在 `/private/tmp/ontofoundry-021-readonly-mysql.py`，不加入仓库测试；密码从用户指定 .env 的 MYSQL_PASSWORD 读取且不打印。使用本分支 kind=mysql、临时 SQLite 平台库和虚构工作空间，列所有业务库，从非空库中选择最多三个分别建全量任务，断言每库保存的名称清单等于其源清单且所有观察结果的 schema 等于任务库名，逐库打印 source/saved。源库只设置只读会话及读取元数据，不执行源 DDL/DML。

```sh
cd /Users/guoruping/project/bigdata/ontograph-hotfix/apps/api
PYTHONPATH=src /Users/guoruping/project/bigdata/ontograph/apps/api/.venv/bin/python /private/tmp/ontofoundry-021-readonly-mysql.py
```

执行已确认加载 `ontograph-hotfix/apps/api/src/ontofoundry_api/__init__.py`，连接 127.0.0.1:3306 时沙箱返回 `PermissionError: [Errno 1] Operation not permitted`，PyMySQL 为 2003，服务层为 QUERY_FAILED。**真实验证未通过环境预检，未获得各库表清单，不能声明真实 MySQL 或 Doris 验证通过**。详细错误保留在 `/private/tmp/ontofoundry-021-readonly-mysql.log`；需在允许本机 TCP 的终端运行上面命令完成验收。

### 上线注意

先停止旧 API/后台任务并备份平台数据库，再执行 `20261022_000001` 迁移：会清空所有连接（包括 PostgreSQL）的 metadata_snapshots、metadata_sync_jobs、metadata_sync_batches，并清空 MySQL/Doris 连接配置中的 database。业务源库、工作空间和本体/数据集定义不变。**所有已同步表都需要重新同步**；现有数据集在此之前显示表未同步。不要重试旧任务，按实际库新建全量任务，核对同名表的字段与主键。该迁移不可恢复已删除快照，回滚需使用备份。现场重新出现异常时，应保留同一请求、任务 schema、源清单和快照的对应证据，再定位运行路径。

## 2026-10-22 调用方修复（v0.2.2）

依据：[服务级连接调用链设计](2026-10-22-connection-schema-callers.md)。不修改版本号、核心模型、接口契约或数据库结构。

### 复现范围与修复

使用空 database 的 MySQL/Doris 连接，Vitest 渲染真实页面/组件，保留真实 api/client.ts，以 mock HTTP 对缺少 schema_name 的单库接口返回 SCHEMA_REQUIRED；pytest 使用 SQLite ATTACH 两个虚构业务库和 Doris information_schema 模拟，禁止连接真实服务。

| 路径 | 触发操作与修复前行为 | 修复 |
|---|---|---|
| components/elements/DatasetLocationFields.tsx:37 的 assets effect（修复前 :35） | 新建基于表的数据集选择连接但未选库；或编辑 schema_name=null 的遗留数据集。直接 GET assets，无 schema_name，返回“请选择库”。 | MySQL/Doris 未选库不请求资产，表选择禁用；选库后显式传 schema_name。PostgreSQL 保留默认 schema。清空库时清空表和列。 |
| 同文件 :53 的 changeConnection（修复前 :49） | 遗留数据集有 table_name 而无 schema_name，切换连接。Promise.all 同时列库、用空库查资产；报错被 catch 吞掉并重置来源。 | 未选库直接重置；已有库先确认目标连接可见该库，再带该库查表。检查期间不提前写入目标连接，防止 effect 向无权限库发请求。 |
| components/DataConnections.tsx:51、:112、:202 | 列表有数据库列及“整个服务”；表单从 PostgreSQL 切换引擎时隐藏的旧数据库仍被 Form 保留。 | 删除该列；PostgreSQL 地址附 /db；隐藏字段 preserve=false，提交时 MySQL/Doris 的 database 显式清空，PG 必填。 |

当前分支数据表页和同步对话框本来已逐库传参。新增回归须在修复前后均验证它们，不能据此声称复现了用户现场这两个入口的同一错误；现场运行资源版本与请求参数尚未取得。表详情“影响”在本实现体现为基本信息中的引用数据集及数据集引用页，无独立表影响接口。

### 前端全部连接相关调用清单

下表文件路径相对于 apps/web/src。api/client.ts 的 catalogApi 统一经 workspaceRequest 构造连接 URL，测试断言最终 fetch URL，而非仅断言 mock 方法实参。

| 调用方 | 接口/传参及空库行为 |
|---|---|
| components/DataConnections.tsx:43、:56、:60、:132 | catalogApi.connections；workspaceRequest POST /connections、PATCH /connections/{id}、POST /test。连接级入口不要求 schema；MySQL/Doris 不带固定数据库，PG 必填。 |
| hooks/useConnectionNames.ts:11 | catalogApi.connections，只读连接显示名，无单库读取。 |
| lib/metadataSync.ts:8–9 → TableSyncPanel.tsx:42、TableSyncDialog.tsx:43 | schemas 后遍历每个库请求 assets({schema_name: schema})；“全部库”只是前端合并，不发空库资产请求。无可见库时不请求 assets。 |
| components/TableSyncPanel.tsx:34、:47 | connections；删除用 deleteTable(table.schema, table.name)；打开详情携带该行库名。 |
| components/TableSyncDialog.tsx:36、:44、:62、:74、:93、:103 | connections；每库 syncJobs(g.schema)；选中的每库 tables({schema_name:s})、refreshAssets({schema_name:s})；syncJob/retrySync 用 job_id，后台读取持久化的 job.schema_name。 |
| components/TableDetailDialog.tsx:25 | tableRows({table_name, schema_name:schema})；结构和引用数据集来自已选库资产快照，不再请求源库。其唯一调用方 TableSyncPanel 保证传行库名。 |
| components/elements/DatasetLocationFields.tsx:22、:28、:37、:50、:53 | connections、schemas；本轮修复两个 assets 调用，MySQL/Doris 均在明确库名后请求，PostgreSQL 允许后端归一化默认 schema；目标连接没有原库时不请求该库资产。用于新建和编辑数据集的共用选表控件。 |
| pages/InstancesPage.tsx:136、components/elements/ElementInstances.tsx:167 | mappingPreview，映射引用的数据集含其自身 schema_name；经 dataset_sources 解析，不调用 metadata 的 require_schema。 |
| api/client.ts:251 的 tableMaterial | 无前端使用者；保留旧客户端方法，后端固定拒绝重复材料，错误码 DATASET_ASSOCIATION_REQUIRED，不读取表、不调用 require_schema。 |
| components/TableMaterialPicker.tsx:32（构建页）、api/client.ts:377–380 的 datasetApi | registeredTables 不要求库，后端汇总登记快照；关联结果逐表保留 connection_id/schema_name/table_name。datasetApi.validate/preview 请求体携带数据集选中的 schema_name。 |
| 其他 workspaceRequest | settings、modeling、提案等不是连接单库入口；reviseDataset 和 element-saves 保留数据集 schema_name，不另猜默认库。 |

### 后端全部归一化/库名检查入口

路径相对于 apps/api/src/ontofoundry_api。MySQL/Doris 空库在下表检查点均保持拒绝；PostgreSQL 的 normalize_schema 仍回落配置值或 public。

| 调用方 | 上游入口与检查 |
|---|---|
| api/connections.py:190 的 tables | GET /connections/{id}/tables（含 table 参数详情）→ normalize_schema → require_schema → list_tables；空库 422，显式库同时传列表和字段读取。 |
| api/assets.py:113 的 assets | GET /assets → normalize_schema → require_schema → 复合主键快照；空库 422。 |
| services/metadata_sync.py:147 的 create_job | POST /assets/sync-jobs 与兼容 /assets/refresh → normalize_schema → require_schema；空库不创建任务。 |
| services/metadata_sync.py:171 的 latest_jobs | GET /assets/sync-jobs → normalize_schema → require_schema；前端逐库读历史。 |
| services/metadata_sync.py:238 的 run_job | 创建或重试后台任务 → require_schema(job.schema_name)；空库遗留任务失败，禁止打开源库。GET 单任务不要求另传库。 |
| services/metadata_sync.py:307 的 remove_table | DELETE /assets/tables → normalize_schema → require_schema；删除只作用于目标库快照。 |
| services/table_preview.py:24 的 preview_table | GET /assets/rows → normalize_schema → require_schema，再从已登记表生成限定库名的只读 SQL。 |
| services/metadata_catalog.py:53 的 list_tables | require_source_schema；上游为 tables 接口、read_structure、后台全量同步发现表。 |
| services/metadata_sync.py:114 的 read_table | require_source_schema；上游为 tables 单表详情、read_structure、后台批次。 |
| services/metadata_catalog.py:65 的 read_doris_table | require_source_schema；上游为 read_table 的 Doris 分支，空库不能落到默认库。 |
| services/imports.py:111 的 import_context | normalize_schema(c,None) 生成导入候选连接的 default_schema；MySQL/Doris 为 None，不调用 require_schema，不访问源库。 |
| services/dataset_sources.py:32 的 resolve_dataset | normalize_schema(connection,dataset.schema_name)，供数据集校验/预览、映射/实例和资产引用解析；未指定库的表来源由 registered_tables 返回 SOURCE_NOT_REGISTERED，不是 SCHEMA_REQUIRED。 |
| services/dataset_sources.py:137 的 registered_table_catalog | normalize_schema 仅用于将数据集引用匹配到确切登记表；汇总所有合法快照，不调用 require_schema，不需要单库参数。 |

### 验证记录

- 修复前证据：用 git archive HEAD 建立 `/private/tmp/ontofoundry-022-before` 隔离副本，只复制新增回归测试，执行 `npx vitest run src/components/ConnectionSchemaFlow.test.tsx src/pages/ConnectionsPage.test.tsx`。最终 **6 failed、9 passed（15 项）**：MySQL/Doris 新建数据集未选库各一项、遗留数据集切换连接一项、连接地址/列一项、隐藏旧库值切换两种引擎各一项。数据表/同步完整流程两种引擎、PG 默认 schema 和构建关联表均通过。日志 `/private/tmp/ontofoundry-022-before-vitest-final.log`。修复后这 15 项均包含在下列全量通过结果中。
- Vitest 保留真实 client，mock HTTP 拒绝 MySQL/Doris 空库；断言 URL 的 schema_name、数据集 validate/preview 的请求体，以及跨库同名表关联的三元身份。测试中等待 Ant Design Checkbox.Group 注册完毕，消除过早点击造成的测试时序失败。
- pytest 新增完整 API 流程：POST 不含 database 的 MySQL/Doris 连接 → 连通测试 → 列库/列表 → 选择表同步 → 双库不同字段及样例行 → 数据集校验/预览/新建保存/改库保存 → registered-tables 引用及构建会话 linked_tables；旧表材料入口保持 DATASET_ASSOCIATION_REQUIRED。补测 PG 缺库/空白库拒绝、有效库创建，以及 refresh/delete 空库拒绝。仅使用 SQLite ATTACH 和模拟 Doris 系统表。
- 后端指定命令最终 **1089 passed、17 skipped、0 failed、0 errors、3 warnings，130.38 秒**。日志 `/private/tmp/ontofoundry-022-pytest.log`。警告为现有 Starlette/TestClient 依赖弃用及 Pydantic 字段名提示。更新后的测试文件 ruff 通过。
- 前端指定命令最终：build 通过（现有大 chunk 提示）；Vitest **50 个文件、233 passed、0 failed、0 skipped，22.57 秒**；`npx eslint src` 通过。日志分别为 `/private/tmp/ontofoundry-022-build-final.log`、`/private/tmp/ontofoundry-022-vitest-final.log`、`/private/tmp/ontofoundry-022-eslint-final.log`。
- 环境处理：原 apps/web/node_modules 是指向主目录的只读符号链接，Vite/tsc 写缓存时返回 EPERM；验证期间使用工作目录内的缓存目录及原依赖链接，未安装或改动主目录依赖，结束后恢复原符号链接。
- **视觉及局域网验收未完成**：已执行 `npm run test:visual`，Vite 监听 127.0.0.1:5199 返回 EPERM，测试未开始；直接启动 Chromium 也被沙箱终止。`npx vite --host 172.20.10.3 --port 5199 --strictPort` 同样返回 EPERM。尝试现有浏览器的离线真实组件页面，工具安全策略拒绝 file://（只允许 HTTP/HTTPS），随后停止该路径并恢复视口。无 1440×900 前后截图可供比较，容器层级、对齐线、字号档位、状态和表格密度尚未经截图验收；旧 connections.png 基准待在可启动浏览器的环境审核更新。日志 `/private/tmp/ontofoundry-022-visual.log`、`/private/tmp/ontofoundry-022-lan.log`。新增数据集编辑视觉用例在可运行环境生成测试截图附件。
- 真实 MySQL/Doris 未访问；没有修改版本号，没有 commit/push。

```sh
cd apps/api
PYTHONPATH=src /Users/guoruping/project/bigdata/ontograph/apps/api/.venv/bin/pytest -q -p no:cacheprovider
cd ../web
npm run build
npx vitest run
npx eslint src
npm run test:visual
```
