# core-1 P2 后端实施记录

## 基线和范围

- 基线 `5afb43d`，分支 `feat/core1-p2-backend`，包含 P1 `a5fcd6e` 与接口协调提交。
- 依据主设计当前决定 49–51、实施计划 §2/§5.1～5.3/§9.1/§10/§12/§13，以及 2026-10-16 API 契约。
- 文件修改只限后端、DataAgent、脚本、Makefile、本记录及脚本生成 core.generated.ts。前端由另一分支实施。
- 初始存在未跟踪 node_modules 链接，不修改；无 .env。未连接开发数据库，不 commit/push。

## 实施顺序

按 P2-01～P2-14 实施；2026-10-16 完成后端收尾和统一检查，外部发布及未覆盖项见下文。

## 契约变更

无变更。继续以 `2026-10-16-core1-p2-api-contract.md` 为准，未修改核心模型、接口 envelope 或已确认业务语义；schema 与生成 TS 的只读漂移检查均通过，无需重新生成类型。

本次收尾没有把材料跨空间校验放宽，也没有把对象主附来源改为 INNER JOIN、将指标范围套到对象实例集合、强制来源同日或给指定快照日期增加回退。实例读投影和预览结果仍不写入模型。

## 测试退役与迁移台账

仅按具体行为退役，不按文件前缀批量删除：

- `test_p0_v3_contract.py`：旧 v3 schema/转换器已删除，core1_models/schema/architecture 替代。
- `test_p1_native_roundtrip.py`：旧原生 AST 保真退出，外部往返归 P5。
- `test_p1_roles.py`：旧角色结构退出，二元/重化核心例02/03/05替代。
- `test_m7_optional_role_names.py`：旧角色命名保真退出。
- `test_p3_verbalization_retype.py`：旧读法占位符退出。
- `test_p1_legacy_form.py`：旧表单回写退出，element_save/bindings 替代。
- `test_p3_semantic_views.py`：旧树投影退出，core1_instances/bindings 替代。
- `test_p3_semantic_integration.py`：旧语义树写入退出，metric_preview/lifecycle 替代。
- `test_semantic_editing.py`：旧树编辑 API 删除，保存/预览接口替代。
- `test_p1_mcp_roles.py`：旧角色工具退出，core1_mcp 替代。
- `test_p2_mcp_synonyms.py`：旧文档/字段节点退出，core1_mcp 同义词替代。
- `test_t7_mcp_elements.py`：旧工具退出，core1_mcp 替代。
- `test_p2_m4_compact_projection.py`：旧 compact AST 投影退出，core1_mcp 内容预算替代。
- `test_p2_extensions.py`：旧扩展回读退出，适配器报告归 P3/P5。
- `test_ossie_name_description.py`：旧导入/导出下线，后续适配器测试替代。
- `test_p2_concept_context.py`：旧 context 注册表退出，核心 synonyms/description 及改名测试替代。
- `test_t1_v2_model.py`：旧 v1/v2 兼容退出，core1_models/cutover 替代。
- `test_t2_postgres_migration.py`：旧 backfill 退役，core1_cutover 替代。
- `test_t8_switch.py`：旧 full/proposals 双模式退出，proposals-only 接收测试替代。
- `test_m6_session_cleanup.py`：旧仅清非 v3 退出，core1_cutover 全清保留范围替代。
- `test_m6_import_counts.py`：旧导入 API 下线，P4 新合同替代。
- `test_compiler.py`：旧 Ossie compiler 删除；core1 发布不编译外部格式。
- `test_ossie_import.py`：旧 importer 删除，P3 新适配器替代。
- `test_synthetic_ossie_roundtrip.py`：旧 compiler/importer 往返不再运行，原 A/B 源夹具保留给 P3/P5。
- `test_m8_binary_facts_replay.py`：旧真实 v3 回放退出，用虚构 core facts/edges 替代。
- `test_p3_owner_join_replay.py`：旧真实 owner/role 回放退出，direct/mapping_table 查询替代。

有效生命周期、并发、撤销、来源与指标行为保留/迁移为 core-1 测试；auth、static、运行状态、BFF、SDK、诊断等无关测试保留。

## 验证记录

### 收尾修复与判断

- 上一轮记录为 3 failed / 429 passed / 10 skipped；续作起点工作区已包含部分尚未统一验证的修正，不能把旧结果当作当前工作区的复现结果。
- 事实修订的材料问题来自测试辅助函数：原 `seed_batch` 使用恒返回 None 的材料 lookup，会把已上传到当前空间的材料误判为不存在。保留工作区已改用的 `material_lookup(db, settings, workspace_id)`，整理导入，并在事实修订用例中明确断言上传 201、材料可从该空间目录读到。生产材料归属、哈希、行号和引文检查保持有效；测试继续覆盖目标 hash 过期、修订不增 revision、依赖端点改写和接受后证据 UUID 保留。
- 两项实例测试的预期符合契约，不降低断言。保留工作区已具备的每个来源独立 SQL 别名、主表决定集合并 LEFT JOIN 附表、逐 Dataset 取全表最大快照日期的实现；本次未再改实例查询服务的执行语义。断言加强为：A1 金额 100、A2 金额 null、孤儿金额 900 不进入对象集合；默认数量日期 12-31、状态日期 12-30；指定 12-29 得数量 16、状态 null，不借用 12-30 状态；指定主来源无数据的 12-30 返回空集合。以上均在最终全量中通过。
- 指标预览夹具直接构造 `Condition`，不再向 `filters` 赋 dict 后靠整份草稿重新校验补救；移除多余的序列化往返。最终无 Pydantic 序列化警告。
- 清理 E701、导入排序和未使用导入；按要求执行全目录格式检查，统一格式化发现的 37 个文件（含既有文件，仅格式调整），最终 src/tests 共 139 个文件格式一致。

### 环境与执行命令

Python 3.13 虚拟环境沿用 `apps/api/.venv`；生成类型检查使用 Node 22.19.0。两个可丢弃外部数据库配置 `ONTOFOUNDRY_TEST_POSTGRES_URL` / `ONTOFOUNDRY_TEST_MYSQL_CONFIG` 均未提供；没有连接 `127.0.0.1:55441` 或其他非临时数据库，没有启动/重启外部服务。

最初按计划尝试 `UV_CACHE_DIR=<临时目录> uv run --offline --python 3.13 ...`，uv 在启动时因 macOS `system-configuration` 的 `Attempted to create a NULL object` panic 返回 101，schema/lint/pytest 均未开始执行。随后直接调用现有虚拟环境内相同的 Python/ruff 完成全部检查，没有据此记为测试失败或跳过。

以下 Python/ruff 命令均在 `apps/api` 目录执行，其余命令在仓库根目录执行：

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m ontofoundry_api.contracts.export_schema --check` | 通过，退出码 0；核心与提案 schema 无漂移 |
| `npm run check:core-types --workspace apps/web`（Node 22.19.0） | 通过，生成 TS 与核心 schema 一致 |
| `.venv/bin/ruff check src tests` | 通过，0 lint errors |
| `.venv/bin/ruff format --check src tests` | 通过，139 files already formatted |
| `.venv/bin/python -m pytest -q -rs` | 434 passed、0 failed、0 errors、10 skipped；共 444 项，30.04 秒 |
| `.venv/bin/python -m pytest -q -rs ../../integrations/dataagent/skills/ontofoundry-modeling/tests` | 3 passed、0 failed、0 errors、0 skipped；共 3 项，0.05 秒 |
| `make -C integrations/dataagent zip` | 通过，生成 `integrations/dataagent/dist/ontofoundry-modeling.zip` |
| `unzip -t integrations/dataagent/dist/ontofoundry-modeling.zip` | 通过，ZIP 完整，顶层目录为 `ontofoundry-modeling/` |
| `git diff --check` | 通过 |

完整后端 pytest 留有 2 项依赖弃用提示：Starlette TestClient 的 httpx 适配及 anyio BlockingPortal 别名；不涉及本次 Pydantic filters 警告。

10 项 skipped 的归属与原因：

| 文件/场景 | skipped | 原因 |
|---|---:|---|
| `test_core1_cutover.py` 的 base→head、旧 head→head | 2 | 未提供 disposable PostgreSQL |
| `test_core1_metric_postgres.py` 的真实聚合预览 | 1 | 未提供 disposable PostgreSQL |
| `test_t0_postgres_publish.py` 的发布并发 | 2 | 未提供 disposable PostgreSQL |
| `test_t4_postgres_decisions.py` 的决定并发/幂等 | 4 | 未提供 disposable PostgreSQL |
| `test_stage_a_mysql.py` 的真实 MySQL 行为 | 1 | 未提供 disposable MySQL 配置 |

SQLite 切换清空、保留平台配置及重入测试已通过；这不能替代上表 PostgreSQL 迁移/并发及真实数据库执行验收。所有编辑完成后才执行上述统一测试；之后仅补本进度记录，未再改实现。

## 发布操作与未完成项

本轮没有 commit/push，也没有执行外部发布操作。发布步骤详见 `integrations/dataagent/README.md`，待完整 P2 前后端集成验收后执行：

1. 备份平台库与磁盘材料，停止旧建模运行、回调同步和切换窗口写入。
2. 安装新 `ontofoundry-modeling.zip` 到 DataAgent 的 `SKILLS_ROOT_DIR`，清理旧技能目录；更新已有建模 Agent 的技能配置，同步并发布仓库中的建模/问数提示词，重启 DataAgent 并核对技能索引。仓库提示词改动不代表管理后台已生效。
3. 停止旧应用后执行 `20261016_000001_core1_cutover`，清空旧本体相关记录并保留设计指定的平台配置/材料；同时部署 core-1 前后端，重启应用清 read_cache。此迁移本轮仅在临时 SQLite 测试中执行，未在开发/部署库执行。
4. 完成 DataAgent 建模→提案审阅→发布→MCP 四工具读取和自有数据库工具问数的端到端验收；核对聚合 SQL 日志，验证不会靠 MCP 数据库执行或实例分页求统计。

仍未覆盖/不在本分支范围的事项：

- 上述 9 项 PostgreSQL 和 1 项 MySQL 外部测试，需提供可丢弃配置后重跑；PostgreSQL 全新迁移、旧 head 升级和并发行为尚未验收。
- DataAgent 管理后台同步、技能安装、重启及端到端问数均未执行；ZIP 仅生成并校验，不上传，dist 产物不提交。
- 前端测试/tsc/lint/build、localhost 与局域网 IP HTTP 页面及弹层交互验收由前端/集成分支完成；本分支只执行生成核心类型检查，没有部署服务或修改前端实现。
- 六份 10-08 历史文档的顶部替代标记已在集成分支补上。
- 适配器导入、翻译报告与导出往返属于 P3～P5；P2 旧导入/导出入口继续下线。

## PR #23 评审修正

### 修正计划与边界

以当前主设计 §3.2、§3.6、§3.9、§14.3 和本轮 API 契约为依据，修复 S1–S7、G1–G7、A1；不变更核心模型或持久化表结构。本节兼作评审修正计划，避免超出本任务限定的文档归属新增设计文件。

1. 查询与读投影：统一嵌套证据裁剪；保留 SQLAlchemy 相关子查询；分离快照选日和业务时间归组；展开虚拟父具体目标；按有效绑定补齐 MCP 物理 DTO。
2. 保存与提案：同步确认的受影响项并校验会话；提供只读元素保存影响预检；暂存只阻断结构、证据及适用来源错误；修正名称分组和事实修订依赖闭包。
3. 使用设计示例及临时 SQLite 补实际结果回归；固定 PostgreSQL 并发双方预览，未配置可丢弃库则 skip。全部编辑结束后统一执行 schema、ruff、完整 pytest、技能测试和 ZIP 构建；不连接开发库、不启动服务、不提交。

### 逐项修复与结果回归

| 项目 | 修复与结果断言 |
|---|---|
| S1 | resource_items 统一递归裁剪 evidence，覆盖 ratio 两个分量。test_core1_permissions 使用例13、实际仅 mappings:read 的服务令牌读取 REST 和 MCP；高权限能看到人工说明及真实上传的材料引文，低权限仍得到正确分量 UUID，但全部嵌套 evidence、说明、quote 均消失。 |
| S2 | 以 ResolvedScalar 保留 SQLAlchemy 子查询到外层 SELECT 编译时，避免提前序列化导致相关性丢失；根引用由同一生成器处理。test_core1_instances 基于例06只有 B/P2 有合同、A/P1 无合同，分别执行单独 EXISTS 和本地条件 AND EXISTS，结果严格只有 P2。 |
| S3 | 元素保存后同步目标聚合和全部已确认 affected_items 回会话，校验同步后的完整图后再提交。test_element_save 基于例07将 customer_no 改成 customer_code：发布事实和会话事实均为 C001、新键生效、旧键消失，两份图均合法，后续预览合法；无关会话描述修改保留且未发布。 |
| S4 | 名称碰撞仅检查实际具有名称命名空间的种类及存在的字段；属性与关系共用所属对象命名空间，规则只比较同归属技术名。test_core1_lifecycle 对例07事实及例01映射的两个独立更新断言无 atomic_group_id，接受/撤销一项不会决定或修改另一项。该测试同时发现并修正提案 after Schema 错误剥除 MappingSource.id 的问题，恢复必填本地来源名；核心 Schema 不变。 |
| S5 | 快照选日与业务月份分离：时间字段为快照列时逐周期选末日；按上线日期统计时先选定快照，再归业务月份。test_core1_metric_preview 用例12来源扩展主设计 §3.6 的五行组件数据，simple/expression 均得到总值3、10月1、12月2；无 time_field 的快照指标返回总值10、trend/trend_query=null 和明确 warning。 |
| S6 | 邻接按虚拟目标的具体子类型展开，双向查询取得当前端及目标端有效本地 inherited_link_bindings；物理查询预算按具体查询计数，按实际具体 ref 去重。例06当事人反查负责人测试得到设备、车辆各一项，二者同键字符串1但实际 type_id/ref 不同，负责人边方向均为具体资产→当事人，无 warning。 |
| S7 + A1 | 新增只读 EffectiveBindingRead/MembershipRead/EffectiveLinkRead DTO，并校验生成结果。MCP physical 返回有效来源、字段、每层成员绑定、有效关系、虚拟父具体展开，以及指标/映射表/各来源完整 DatasetRead（含各自快照声明）；继承关系读视图使用本地有效 join，原核心 LinkType 不变。test_core1_mcp 覆盖例06成员与设备/车辆绑定及分段续读、例13 ratio 的数据集/列/分量、例02映射表数据集、例12两来源快照声明；低权限回归确认不会借新 DTO 泄露物理或证据。 |
| G1 | 需要只读保存影响预检：新增 POST W/element-saves/preview，输入候选 ElementSave，返回 current_version_id、session_revision、带 reason 的 AffectedItem[]。服务端从当前编辑基线推导必要引用改写及规范化 hash；Dataset 变更补齐直接指标和间接 ratio 影响，不把不相关编辑纳入范围。test_element_save 验证例07清单/hash、预检零写入、确认后保存、未确认拒绝、hash过期拒绝、版本/revision过期及无关修改拒绝；例13覆盖全部指标影响及服务端 hash。 |
| G2 | 暂存仅校验 JSON 结构、证据和可适用的已知来源列；缺元数据/悬空语义引用/重复名称进入 validation。发布预览合并可编辑草稿结构，完整图错误作为 publishable=false 返回，避免把它误读成合法发布快照而500；接受及发布仍阻断完整图错误。test_modeling 覆盖重复技术名可暂存/重读/预览、接受与发布422 VALIDATION_FAILED、修好后发布成功；已知不存在的物理键列独立返回 JOIN_COLUMN_NOT_FOUND，悬空关系引用仅使 validation 不通过。 |
| G3 | 事实修订迭代扩展原子组、下游和所需 pending 上游到完整闭包，新批次重建依赖并重写重复事实端点；已接受上游已在会话基线，无需重建，失效依赖明确拒绝。test_core1_fact_revision 在例07同时创建重复客户、新退货单和关联：修订重建三项、关联保留两项新依赖，旧三项 superseded；接受后新增退货与邻接都保留并指向原客户。原追加真实材料证据测试继续通过。 |
| G4 | ratio 趋势保留分子/分母 snapshot_date 并汇总实际 dataset_id/period/date，同日期去重。例13扩展快照数据实际执行，断言10月5/7、11月1/2及各周期10-02、11-30，保留总值使用的11-30。 |
| G5 | 后端覆盖检查按唯一 UUID 集合，已有规则允许一个 simple 项覆盖同一 ratio 的两个引用，保留这一行为。结果测试验证只传一个分量时总值及趋势均为1；空分量或重复同一分量仍422。 |
| G6 | 去掉邻接测试的 if rows 空通过；六个场景严格比较全部关系的端点类型、键、关系类型和方向，覆盖反向、映射表、复合键、自关联、平行关系及多来源，并断言无 warning/截断。 |
| G7 | PostgreSQL 并发双方先固定同一版本的预览，再同时提交；独立修改预期一个200、一个409 PREVIEW_OUTDATED，失败方重新预览发布后版本连续到3并保留两项描述修改。冲突场景也复用固定预览。未提供可丢弃库，本轮两项明确 skip，未声称真实并发已验收。 |

### 契约变化与前端配合

已同步 `2026-10-16-core1-p2-api-contract.md` 的 §4.2、§6 和 mock：

- 新接口 `POST /api/v1/workspaces/{workspace_id}/element-saves/preview`，请求 `ElementSave`，响应 `ElementSaveImpact`；新增 M35 请求、响应与确认后保存 mock，列明结构/范围错误和版本/revision过期错误。前端编辑器需要先预检，展示 `affected_items[].reason` 供确认，再将去掉 reason 的三字段 AffectedItem 原样带入保存；不得在浏览器自行计算 expected_target_hash。预检后内容变化须重做预检，保存仍核对全部基线。
- MCPElement 新增 `effective_bindings?: Page<EffectiveBindingRead>` 以及 ratio 的 `components`、推导 `dataset_id/value_kind`；datasets 扩展至指标、映射表与有效具体绑定来源。DTO 包含 `type_id/sources/fields/memberships/links`，membership 保存 `mapping_id/type_id/binding_mode/membership_source_id/derived_by`，有效关系保存 `link_type_id/source_type_id/target_type_id/data_join`。契约补例06 person/device/vehicle/asset 的响应构造、来源快照和权限规则。前端若声明/消费这些读 DTO，需同步对应可选字段。
- 前端 ratio 预览按 UUID 去重 components；同一 simple 可覆盖分子分母。无业务时间字段时保留服务端总值与 warning，不绘制趋势；逐周期快照按响应原样展示。上述为前端配合项，本轮没有改 apps/web。
- 提案 Schema 仅修正 `AfterMappingSource.id` 的必填本地来源名；生成文件在 `apps/api/src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json`。无核心模型字段、核心 JSON Schema 或数据库结构变化，无迁移；无需运行 scripts/generate_core_types.mjs，未改 core.generated.ts。新增预检/读 DTO 属于既有定义的交互及查询投影，删除它们不改变语义模型，但会丢失服务器影响确认能力或有效绑定读取信息。
- integrations 源码及 Agent 提示词未修改；按要求重建技能 ZIP 并校验完整性，未上传、复制技能目录、发布 Agent 或重启 DataAgent。

### 统一验证记录

所有初始修复和结果用例完成后统一执行。第一轮完整 pytest：453 passed、2 failed、10 skipped；失败揭示上述 G2 预览严格快照读取及 S4 嵌套来源 id Schema 问题，修正实现/Schema后保留并加强断言，重新执行完整检查。最终结果如下。

在 `apps/api` 使用的可执行文件与环境（所有 Python 验证均显式移除外部数据库测试配置，未尝试连接外部数据库）：

```sh
export PYTHONPATH=<集成工作区>/apps/api/src
PR23_PYTHON=<后端工作区>/apps/api/.venv/bin/python
PR23_RUFF=<后端工作区>/apps/api/.venv/bin/ruff
```

| 执行命令 | 最终结果 |
|---|---|
| `env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG "$PR23_PYTHON" -m ontofoundry_api.contracts.export_schema --check` | passed，退出码0；核心及提案 Schema 无漂移 |
| `"$PR23_RUFF" check src tests` | passed，0 lint errors |
| `"$PR23_RUFF" format --check src tests` | passed，141 files already formatted |
| `env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG "$PR23_PYTHON" -m pytest -q -rs` | **455 passed、0 failed、0 errors、10 skipped**；共465项，34.41秒 |
| `env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG "$PR23_PYTHON" -m pytest -q -rs ../../integrations/dataagent/skills/ontofoundry-modeling/tests` | **3 passed、0 failed、0 errors、0 skipped**；0.06秒 |
| 仓库根 `make -C integrations/dataagent zip` | passed，生成 dist/ontofoundry-modeling.zip（忽略的构建产物） |
| 仓库根 `unzip -t integrations/dataagent/dist/ontofoundry-modeling.zip` | passed，ZIP 无损坏，顶层为 ontofoundry-modeling/ |
| 仓库根 `git diff --check` | passed；最终文档追加后核对 |

10项 skipped：PostgreSQL切换迁移2、真实指标聚合1、并发发布2、并发提案决定4，MySQL来源行为1。均因未提供可丢弃配置；skip不等于通过，评审A2的真实迁移保留范围验收仍待外部条件。完整测试仅有原有 Starlette/httpx 与 anyio 两项依赖弃用提示。

本轮未连接 127.0.0.1:55441 或任何非临时数据库，未启动服务、commit或push；未触碰其他人的 apps/web 修改。最终测试通过后只追加本记录并检查 diff，未再改实现。

## PR #23 第二轮评审修正

### 修正计划与边界

本节依据 API 契约 §4.2、§4.6 记录本轮设计与实施计划；遵照本任务路径限制，不新增设计文档，不改变核心语义模型或数据库结构。仅处理 N1、N2、N3、N4、N6、N7 的后端部分。

1. 元素保存：从目标聚合单独推导必要引用改写，候选依赖只能保持原值或等于必要改写；预检与事务内保存共用范围推导、三方合并、完整图校验及会话同步计算，严格核对确认集合。
2. 查询：字符串字面量交给 SQLAlchemy 绑定；虚拟父精确定位明确要求具体类型，返回 422。
3. 读契约：独立导出四种接口 DTO 的 JSON Schema，纳入 export_schema --check，并列出前端所需字段。
4. 补结果回归与双方言纯编译回归；全部编辑结束后统一运行指定四项检查，移除 PostgreSQL/MySQL 外部测试配置，不启动服务、不连接外部数据库、不 commit/push。

### 改动、回归与验证结果

| 项目 | 实现文件 | 回归测试与结果断言 |
|---|---|---|
| N1 | `apps/api/src/ontofoundry_api/services/element_save.py`、`api/modeling.py` | `test_element_save.py`：例13六项指标确认，省略全部、部分、重复、额外 UUID、错误 kind 均 422 且版本/会话不变；完整清单顺序无关且成功发布。未暂存/已暂存两种 Dataset 修改均覆盖；旧会话还必须确认最新发布版新增的第七项指标。既有 hash 过期回归仍要求 409 VERSION_CHANGED。 |
| N2 | 同上 | `test_element_save.py`：例07对象描述夹带关系描述在预检和保存均为 ELEMENT_SCOPE_INVALID；必要事实键改名可以显式提交，但夹带 C001→C999 被拒，恢复原值后成功。服务端只应用目标聚合，合并后从最新版本推导必要外部改写，确认不赋予额外编辑权限。 |
| N3 | 同上 | `test_element_save.py`：改名后第二次只改描述，预检无需重复确认且保存成功；旧会话遇到最新改名，预检列出事实键同步，确认后发布/会话两图合法，无关草稿保留且未发布。补基线后新增事实也随改名改写的回归。共用计算在副本上完成三方合并、发布图校验、必要确认集合与会话同步校验，预检不写入。 |
| N4 | `apps/api/src/ontofoundry_api/services/instance_plan.py` | `test_core1_instances.py`：PostgreSQL/MySQL 的 LIKE '1%' 字面量进入 SQLAlchemy 参数，实例键参数仍保留；模拟驱动百分号格式处理成功；字面量内联编译正确转义，另覆盖与取模操作组合。纯编译不连接数据库，既有 EXISTS 相关查询结果测试保留。 |
| N6 | 同上 | `test_core1_instances.py`：虚拟父传不存在 TypedKey 的直接定位和邻接均为 422 INVALID_OBJECT_REF，提示具体类型，且在数据源解析之前失败。契约 §4.6 明确具体类型定位要求。 |
| N7 | `apps/api/src/ontofoundry_api/contracts/read_models.py`、`export_schema.py`、`services/physical_projection.py`、`api/modeling.py` | `test_read_contracts.py`：独立读 Schema 产物与模型一致，故意漂移能被 --check 拒绝；13份例子的有效绑定/成员/关系实际投影通过对应 Schema 校验；实际六项保存影响通过 Schema，缺 hash 被拒。 |

接口读 Schema 路径：`apps/api/src/ontofoundry_api/contracts/ontofoundry.api-read.v1.schema.json`，与核心及提案 Schema 分开，三者都纳入 `export_schema --check`。权威 DTO 在 `contracts/read_models.py`，原 API 和物理投影均改为引用它们，无核心语义字段/数据库结构变化。

| DTO | 前端需同步的字段 |
|---|---|
| MembershipRead | type_id、mapping_id、binding_mode、membership_source_id（可 null）、derived_by |
| EffectiveLinkRead | link_type_id、source_type_id、target_type_id、data_join（可 null） |
| EffectiveBindingRead | type_id、sources、fields、memberships、links（默认 []） |
| ElementSaveImpact | current_version_id（可 null）、session_revision（可 null）、affected_items；每项 target_kind、target_id、expected_target_hash、reason |

前端同事负责以上类型及 `MCPElement.effective_bindings?: Page<EffectiveBindingRead>`；本任务未编辑 apps/web 或前端进度文档。

### 本轮统一检查结果

全部实现、Schema、测试及契约编辑完成后统一执行指定检查。第一轮为 482 passed、10 skipped；复核发现旧会话必须覆盖最新版本新增依赖，补充对应实现及两个结果测试后，重新执行全部四项检查，最终结果如下。

工作目录 `apps/api`，Python/ruff 均使用相邻后端工作区已有虚拟环境；每项检查显式移除外部数据库测试配置，并设置本 worktree 的 `PYTHONPATH`：

```sh
export PYTHONPATH="$PWD/src"
PR23_PYTHON=../../../backend/apps/api/.venv/bin/python
PR23_RUFF=../../../backend/apps/api/.venv/bin/ruff

env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG "$PR23_PYTHON" -m ontofoundry_api.contracts.export_schema --check
env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG "$PR23_RUFF" check src tests
env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG "$PR23_RUFF" format --check src tests
env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG "$PR23_PYTHON" -m pytest -q
```

| 检查 | 最终结果 |
|---|---|
| `python -m ontofoundry_api.contracts.export_schema --check` | 退出码 0；核心、提案和接口读 Schema 均无漂移 |
| `ruff check src tests` | 退出码 0；All checks passed |
| `ruff format --check src tests` | 退出码 0；143 files already formatted |
| `pytest -q` | 退出码 0；**484 passed、0 failed、0 errors、10 skipped**，共 494 项，35.68 秒；2 项既有依赖弃用提示 |
| `git diff --check` | 退出码 0；最终文档记录后复核 |

10 项跳过原因与上一轮相同：PostgreSQL 切换迁移 2、真实指标聚合 1、并发发布 2、并发提案决定 4，MySQL 来源行为 1；均未提供外部可丢弃库配置。A2 的 PostgreSQL 带数据迁移/保留范围与真实并发验收仍待外部条件，不能把 skip 视为通过。

本轮未启动服务、未连接外部数据库、未 commit/push；只改本任务允许的后端和两份文档路径，未编辑 apps/web 或前端进度文档。最终检查完成后仅补本验证记录并检查 diff，未再修改实现。

### A2 PostgreSQL 迁移验收

新增 `test_core1_cutover.py::test_postgres_populated_cutover_preserves_platform_rows`，沿用环境变量 opt-in 和独立库 CREATE/DROP 方式。先升级到旧 head `20261009_000001`，通过 SQL 向全部 17 张业务表写入虚构数据，再升级到 head `20261016_000001`；随后重复 `upgrade head`，验证数据、结构和 revision 均不变。PostgreSQL 17 验收仅使用获准的一次性数据库端口 55460；测试库在 finally 中删除。

| 范围 | 表与断言 |
|---|---|
| 保留（9 张） | `users`、`workspaces`、`workspace_members`、`materials`、`material_chunks`、`data_connections`、`service_tokens`、`service_token_scopes`、`metadata_snapshots`。比较迁移前后行数及所有字段，覆盖归档材料、分块正文、连接配置和密文、令牌 hash/多个 scope、元数据 JSON 与时间。工作空间仅允许 `current_version_id` 从已写入的旧版本 id 置空，其他字段完全不变。 |
| 清空（8 张） | `ontology_versions`、`ontology_element_identities`、`modeling_sessions`、`proposal_batches`、`proposal_items`、`proposal_item_dependencies`、`proposal_decision_requests`、`proposal_decision_items`。迁移前逐表断言非空，迁移后逐表断言零行；覆盖版本/草稿、导入候选及材料清单、两条关联提案、依赖和决定记录的外键链。 |
| 结构与重入 | 表集合不变，`ontology_versions.ossie_json` 删除，`proposal_items.atomic_group_id` 新增为可空 `VARCHAR(36)`；其余两表列集合不变。两次升级后 revision 均为 head，第二次全库行快照与第一次完全相同。 |

依据主设计 §8 和已确认决定第 5 项，切换清空测试本体内容，保留平台配置；本次不修改迁移脚本。旧 head 已由前序 `20261009_000001` 删除 `modeling_session_migrations`（以及可能存在的 `proposal_item_migrations`），因此不人为重建退役表；当前旧 head 也没有独立导入记录表，导入候选/清单在旧会话及提案中覆盖。切换本身不新增业务表，只新增上述列。

同时修正 `test_t4_postgres_decisions.py::test_a_three_level_group_is_accepted_atomically_under_a_race`：`order_no` 只按新建 `purchase_order` 的 owner 统计为 1，并核对本次提案生成的属性 id、对象 id 和关系 id/两端；保留竞争结果严格为一方 200、一方 409，增加 revision 只增长 1 的断言。

全部编辑结束后统一执行以下检查（工作目录 `apps/api`；设置本 worktree 的 `PYTHONPATH="$PWD/src"`；Python/ruff 使用 `../../../backend/apps/api/.venv/bin/`）。所有命令均移除 MySQL 测试配置；仅定向 PostgreSQL 命令设置获准的数据库变量，全量命令移除两个外部数据库测试变量。

| 命令 | 结果 |
|---|---|
| `ruff check src tests` | 退出码 0；All checks passed |
| `ruff format --check src tests` | 退出码 0；143 files already formatted |
| `pytest -q -rs tests/test_core1_cutover.py tests/test_t4_postgres_decisions.py tests/test_t0_postgres_publish.py tests/test_core1_metric_postgres.py`（设置 `ONTOFOUNDRY_TEST_POSTGRES_URL`） | 退出码 0；**11 passed、0 failed、0 errors、0 skipped**，共 11 项，9.04 秒 |
| `pytest -q`（不设置外部数据库测试变量） | 退出码 0；**484 passed、0 failed、0 errors、11 skipped**，共 495 项，38.68 秒 |

定向 PostgreSQL 检查包含切换迁移 4 项（SQLite 带数据 1、PostgreSQL 空库/旧 head 2、新增 PostgreSQL 带数据 1）、并发/幂等提案决定 4 项、并发发布 2 项、真实指标聚合 1 项；全部执行通过。未配置数据库的全量检查按预期跳过 PostgreSQL 切换迁移 3、提案决定 4、并发发布 2、指标聚合 1，以及 MySQL 来源行为 1；这些 skip 不算通过，其中全部 PostgreSQL 项目已在本次定向检查真实执行。两次 pytest 均只有既有 Starlette/httpx 与 anyio 的 2 项依赖弃用提示。

验收结论：迁移实际保留/清空范围与主设计 §8 一致，未发现差异；版本指针置空是清除旧本体引用的预期行为。没有修改迁移脚本或迁移语义。最终只补本节验证结果并检查 diff；未启动应用服务，未 commit/push，保留已有第二轮评审修正。

## PR #23 第三轮评审修正

本轮限定后端实现、回归测试和 API 契约说明，不改前端，不新增模型字段或迁移。

实施计划：R1 对已有成员跨聚合移入、移出进行对称检查，保留删除语义；R2 对照旧图推导最终引用，识别客户端已完成的精确改写；R3 同步合并目标所需但会话缺失的上游依赖闭包，将补入项纳入既有 hash 确认；R4 复用表达式的驱动安全标识符渲染；R6 分阶段检查确认集合和 hash。全部实现和测试编辑完成后，统一执行 Schema、ruff 和两轮全量 pytest。真实数据库只使用任务指定的一次性 PostgreSQL 和 MySQL 配置。

### 改动与回归覆盖

| 评审项 | 修正 | 回归断言 |
|---|---|---|
| R1 | 对当前会话和历史发布基线分别做已有成员跨聚合的对称检查；成员仍存在于候选图时，移入或移出均拒绝。真正删除成员仍允许。 | 例01 的 Property、Rule、Mapping 分别覆盖移入/移出，以及未暂存/已暂存两种候选；预检和保存均为 `422 ELEMENT_SCOPE_INVALID`，版本和会话不变。单独删除客户 region 属性和绑定保存成功。 |
| R2 | 按旧图 UUID 推导最终绑定/事实值字典，先识别客户端已提交的精确最终改写，避免名称交换后再解释一次旧键。所有转换在副本上执行。 | 例01 交换 customer_no/name：未改写候选与已改写候选的保存计算完全相同；两种请求实际保存后，发布图和会话图按属性 UUID 核对绑定不变；输入不变。例07 核对事实值按属性 UUID 保持，以及精确最终改写再次处理的结果不变。 |
| R3 | 从合法合并图按稳定 UUID 计算目标所需的缺失上游依赖闭包，仅补缺失元素，不覆盖已有会话草稿。补入项加入必要确认清单，沿用会话优先、最新发布版回退的 hash 基线。 | 例13 旧会话仅改 ratio 说明、最新版本换新分子保存成功；进一步覆盖新分子/分母依赖新 Dataset 的两层闭包。例01 覆盖映射换新 Dataset。核对确认集合/hash、缺项 422、过期 hash 409、失败原子性、两侧完整图合法以及无关草稿保留。 |
| R4 | `MetricCompiler.identifier()` 复用 expression 的驱动安全渲染，统一列、表、schema 中 `%` 的转义，不处理已生成的参数占位符。 | PostgreSQL/MySQL 各覆盖 SUM/COUNT DISTINCT、普通时间/快照、总值/趋势；列名、表名和 schema 均含 `%`，绑定值也含 `%`，核对占位符保留及驱动格式化；PostgreSQL 另走 psycopg 参数转换。两种数据库的真实 ratio 聚合新增 `%` 列名/表名变体，期望值均为 0.8，PostgreSQL 同时核对趋势。 |
| R6 | 两阶段验证：完整核对 `(kind, UUID)` 集合、重复、缺失、多余，然后比较全部 hash。 | 同一真实必要清单混入过期 hash 与重复/缺项/多余/错误种类，排列错误项与有效项顺序，统一返回 422；只有 hash 错误时各排列统一返回 409。均核对版本、会话未改变。 |

API 契约同步补充上述聚合边界、一次改写、上游补入和错误码优先级；没有改变请求/响应字段或模型 Schema。

首轮全量结果为 517 passed、6 failed、0 errors、0 skipped。六项失败均是新增 R1 测试将创建响应的带时区时间戳与 SQLite 重读后的不带时区时间戳直接比较，实际拒绝行为正确；已改为比较操作前后的读取响应。随后补齐历史基线对暂存跨聚合移动的检查及六项回归，再统一执行最终检查。

### 最终检查结果

全部代码和测试编辑完成后，工作目录为 `apps/api`，Python/ruff 使用指定的相邻后端虚拟环境；命令如下（没有启动应用服务）：

```sh
export PYTHONPATH="$PWD/src"
PR23_PYTHON=../../../backend/apps/api/.venv/bin/python
PR23_RUFF=../../../backend/apps/api/.venv/bin/ruff

"$PR23_PYTHON" -m ontofoundry_api.contracts.export_schema --check
"$PR23_RUFF" check src tests
"$PR23_RUFF" format --check src tests

ONTOFOUNDRY_TEST_POSTGRES_URL='postgresql+psycopg://of:of@127.0.0.1:55460/of_test' \
ONTOFOUNDRY_TEST_MYSQL_CONFIG="$PWD/../../../accept/mysql-p2.json" \
"$PR23_PYTHON" -m pytest -q -rs

env -u ONTOFOUNDRY_TEST_POSTGRES_URL -u ONTOFOUNDRY_TEST_MYSQL_CONFIG \
"$PR23_PYTHON" -m pytest -q
```

| 检查 | 最终结果 |
|---|---|
| Schema `--check` | 退出码 0；核心、提案和接口读 Schema 无漂移 |
| `ruff check src tests` | 退出码 0；All checks passed |
| `ruff format --check src tests` | 退出码 0；143 files already formatted |
| R1 成员边界定向回归 | 退出码 0；12 passed、0 failed、0 errors、0 skipped（其余 31 项未选）；11.87 秒 |
| 配置两个一次性数据库的 `pytest -q -rs` | 退出码 0；**529 passed、0 failed、0 errors、0 skipped**；240.61 秒 |
| 不设置数据库变量的 `pytest -q` | 退出码 0；**516 passed、0 failed、0 errors、13 skipped**；54.26 秒 |
| `git diff --check` | 退出码 0；补完最终记录后复核 |

未设置数据库变量时跳过 PostgreSQL 切换迁移 3、并发提案决定 4、并发发布 2、真实指标聚合 2，以及 MySQL 真实指标聚合 2；这 13 项均已在带配置的全量检查中实际通过。pytest 仅有既有 Starlette/httpx 和 anyio 的 2 项依赖弃用提示。相较原有 495 项，本轮新增 34 项回归。

数据库连通性先以 `SELECT 1` 核对；真实执行只使用指定的 PostgreSQL 55460 和 MySQL 配置文件中的 33070 端口，未连接其他本机数据库端口。测试按既有一次性库/唯一表机制清理资源，无需环境恢复。没有 commit/push。本人只编辑允许的后端与两份文档；同事并行产生的前端和前端进度文档修改保持原样，已有未跟踪 node_modules 保留。最终测试结束后仅补本节验证记录并检查 diff，未再修改实现。

## PR #23 第四轮评审修正

- F2：事实精确最终改写改用类型严格的深比较，区分 true/1、false/0、整数/浮点数，覆盖旧引用与最终引用的名称交换及提案共用校验路径。
- F3：会话同步按目标继承链补齐全部属性、普通关系、规则及有效映射，再遍历其显式依赖；已有草稿保留，不补无关子类、指标和事实。所有补入项进入同一预检/保存确认计算，hash 沿用当前会话优先、缺失时最新发布版的规则。补例 06 有绑定父、成员扩展、虚拟父本地继承绑定、多层父链和已有父草稿回归。
- A1：API 契约明确映射/事实键的精确最终形式优先及先改名再改绑定的两次保存边界，增加歧义解释及第二次换绑的说明性测试。

验证在 `apps/api` 执行，`PYTHONPATH="$PWD/src"`，python/ruff 使用 `../../../backend/apps/api/.venv/bin/`，并设置指定 PostgreSQL URL 与 `ONTOFOUNDRY_TEST_MYSQL_CONFIG="$PWD/../../../accept/mysql-p2.json"`：

| 命令 | 最终结果 |
|---|---|
| `python -m ontofoundry_api.contracts.export_schema --check` | 退出码 0 |
| `ruff check src tests` | 退出码 0 |
| `ruff format --check src tests` | 退出码 0，143 个文件已格式化 |
| `python -m pytest -q -rs` | 540 passed、0 failed、0 errors、0 skipped；55.47 秒 |
| `python -m pytest -q ../../integrations/dataagent/skills/ontofoundry-modeling/tests` | 3 passed、0 failed、0 errors、0 skipped |
| 仓库根 `git diff --check` | 退出码 0 |

相较前轮增加 11 项回归。首轮新增例 06 断言误将集合内容按列表顺序比较，已改为按 UUID 比较完整定义，最终全量通过；仅余既有 Starlette/httpx、anyio 两项依赖弃用提示。数据库先以 SELECT 1 核对，只连接指定 PostgreSQL 55460 与配置文件中的 MySQL 33070，无需环境恢复。不启动应用服务，不 commit/push。

## PR #23 第五轮评审修正

- N1：补例 06 共享父来源的 `note → note2` 保存回归，以及改名后改列绑定的发布图、会话图有效绑定和 bound 状态断言。
- N2：递归类型严格比较复用于保存范围、会话同步/发布确认集合、提案批次完整性。覆盖 true/1、false/0、1/1.0、0/0.0 的原始/最终候选、已有最终草稿、确认及 hash、空确认拒绝、额外事实类型改动拒绝；提案缺事实在接收阶段拒绝，完整原子组应用后校验通过。
- N3：闭包遍历遇到对象即补有效映射并递归来源 Dataset。新增简单派生/表达式 × 单跳/多跳 × 已有/缺失映射回归，核对预检保存一致、补入清单/hash、错误请求原子性、既有对象/映射/Dataset 草稿保留；使用虚构 SQLite 数据实际执行两侧派生查询，确认都返回 P1。

全部编辑完成后统一执行指定检查，结果见本节后续记录。只连接指定一次性 PostgreSQL 55460 和 MySQL 配置的 33070 端口；不启动应用服务，不 commit/push。

最终验证在 `apps/api` 执行，环境和命令如下（数据库先以 SELECT 1 验证连通）：

```sh
export PYTHONPATH="$PWD/src"
export ONTOFOUNDRY_TEST_POSTGRES_URL='postgresql+psycopg://of:of@127.0.0.1:55460/of_test'
export ONTOFOUNDRY_TEST_MYSQL_CONFIG="$PWD/../../../accept/mysql-p2.json"
../../../backend/apps/api/.venv/bin/python -m ontofoundry_api.contracts.export_schema --check
../../../backend/apps/api/.venv/bin/ruff check src tests
../../../backend/apps/api/.venv/bin/ruff format --check src tests
../../../backend/apps/api/.venv/bin/python -m pytest -q -rs
../../../backend/apps/api/.venv/bin/python -m pytest -q ../../integrations/dataagent/skills/ontofoundry-modeling/tests
```

| 检查 | 最终结果 |
|---|---|
| Schema `--check` | 退出码 0 |
| `ruff check src tests` | 退出码 0 |
| `ruff format --check src tests` | 退出码 0，144 个文件已格式化 |
| `pytest -q -rs` | **563 passed、0 failed、0 errors、0 skipped**；97.17 秒 |
| 建模技能测试 | 3 passed、0 failed、0 errors、0 skipped |
| 根目录 `git diff --check`、`git diff --check origin/main` | 退出码 0 |

相较前轮增加 23 项回归，既有断言未放宽。首轮全量为 555 passed、8 failed：新增导航测试误把继承入边端点当作无关对象；按现有双向关系继承语义改为精确核对完整对象集合后，最终全量通过，两侧实际查询仍严格断言只返回 P1。仅有既有 Starlette/httpx、anyio 两项弃用提示，无需恢复环境。最终测试后仅补文档结果并检查 diff，没有改实现。

## PR #23 第六轮评审修正

- N4：三方合并的三个快速分支统一复用严格深比较，区分布尔、整数和浮点数；保留 MISSING 与 null 的区别，合并保留双方的列表去重也使用严格比较。补充标量/嵌套列表/字典快速分支与冲突、缺失值、元素保存及提案批次完整性回归；缺少事实的提案仍在接收阶段拒绝，完整批次应用后与另一会话说明合并保持事实类型。例 07 覆盖属性类型与事实值同时修改、另一会话先发布无关说明的实际预览/发布，断言最终图合法、事实类型和值及预览 hash 与持久化一致。
- N5：数据库 ref 解码后明确检查类型 ID 是字符串和合法 UUID；公共实例查询先校验类型存在，再解析绑定和访问来源。非法 UUID 返回 422 INVALID_OBJECT_REF，已删除类型返回 404 NOT_FOUND，详情、REST 邻接与直接数据库邻接共用该保护。补充不依赖数据库的解析/服务边界测试，以及进程内 HTTP 状态码与错误码回归。
- 本轮没有新增建议项，不修改模型或接口契约，不放宽既有断言。全部实现和测试编辑完成后统一运行指定检查，结果在下方记录；不启动应用服务、不 commit/push。

在 `apps/api` 执行，`PYTHONPATH="$PWD/src"`，使用指定相邻虚拟环境，并设置两个一次性数据库变量：

```sh
export PYTHONPATH="$PWD/src"
export ONTOFOUNDRY_TEST_POSTGRES_URL='postgresql+psycopg://of:of@127.0.0.1:55460/of_test'
export ONTOFOUNDRY_TEST_MYSQL_CONFIG="$PWD/../../../accept/mysql-p2.json"
../../../backend/apps/api/.venv/bin/python -m ontofoundry_api.contracts.export_schema --check
../../../backend/apps/api/.venv/bin/ruff check src tests
../../../backend/apps/api/.venv/bin/ruff format --check src tests
../../../backend/apps/api/.venv/bin/python -m pytest -q -rs
../../../backend/apps/api/.venv/bin/python -m pytest -q ../../integrations/dataagent/skills/ontofoundry-modeling/tests
```

| 检查 | 最终结果 |
|---|---|
| Schema `--check` | 退出码 0 |
| `ruff check src tests` | 退出码 0 |
| `ruff format --check src tests` | 退出码 0，146 个文件已格式化 |
| `pytest -q -rs` | **654 passed、0 failed、0 errors、0 skipped**；97.79 秒 |
| 建模技能测试 | **3 passed、0 failed、0 errors、0 skipped**；0.06 秒 |

新增 91 项回归，另扩展已有 4 组提案批次回归的合并结果断言，既有断言未放宽。数据库先通过 SELECT 1 核对，只使用指定 PostgreSQL 55460 与 MySQL 配置中的 33070；无需环境恢复。后端仅有既有 Starlette/httpx、anyio 两项弃用提示。最终测试后只补文档结果并检查 diff，未改实现。

仓库根 `git diff --check` 最终退出码 0。


## PR #23 第七轮评审修正

- N6：TypedKey 数值解析统一将 decimal 转换错误和超大整数的 float 有限性检查溢出转换为 422 `INVALID_OBJECT_REF`，并显式拒绝非有限 decimal。公共精确查询和邻接关联查询在绑定/来源访问前校验键；详情、REST 邻接、直接数据库邻接及 ref 生成复用相同保护。补报告两条复现、NaN/sNaN/正负 Infinity、合法高精度数值及进程内 HTTP 响应回归。
- N7：事实提案修订捕获 `EvidenceError`，保留原 code 和中文消息，转换为 422 `ServiceError`。补不依赖数据库的不存在材料、错误哈希、越界行号、引文不符及跨元素证据 UUID 回归，核对原提案/草稿/revision 不变且不存批次、不提交；进程内 HTTP 回归验证无效证据不改变批次和会话，随后有效修订仍迁移完整依赖并可接受。
- 未调整模型或接口契约，未放宽已有断言；全量检查包含既有提案缺项拒绝、完整批次解析/应用及严格类型合并回归。只使用指定 PostgreSQL 55460 与 MySQL 配置中的 33070；不启动应用服务、不访问局域网、不 commit/push，保留已有未跟踪 node_modules。

N7 测试补齐提案材料证据持久化格式中的 `locator.heading: null`，使请求模型序列化后仍与原证据内容一致，五个参数均真正进入 `reconcile_draft_evidence` 并触发预期 `EvidenceError`。逐项核对 422、原 code、精确中文消息和异常链，确认草稿、提案、revision 不变且不存批次、不提交。保留全部五个场景；同元素 UUID 重复由请求模型提前拒绝，因此 UUID 场景使用跨元素证据，并在测试注释中说明。

全部实现和测试编辑完成后，在 `apps/api` 统一执行以下检查；格式首检指出新增消息断言需要排版，格式化该测试后复查通过，再运行全量测试：

```sh
export PYTHONPATH="$PWD/src"
export ONTOFOUNDRY_TEST_POSTGRES_URL='postgresql+psycopg://of:of@127.0.0.1:55460/of_test'
export ONTOFOUNDRY_TEST_MYSQL_CONFIG="$PWD/../../../accept/mysql-p2.json"
../../../backend/apps/api/.venv/bin/python -m ontofoundry_api.contracts.export_schema --check
../../../backend/apps/api/.venv/bin/ruff check src tests
../../../backend/apps/api/.venv/bin/ruff format --check src tests
../../../backend/apps/api/.venv/bin/python -m pytest -q -rs
```

| 检查 | 最终结果 |
|---|---|
| Schema `--check` | 退出码 0 |
| `ruff check src tests` | 退出码 0 |
| `ruff format --check src tests` | 退出码 0，146 个文件已格式化 |
| `pytest -q -rs` | **726 passed、0 failed、0 errors、0 skipped**；69.67 秒 |
| 仓库根 `git diff --check` | 退出码 0 |

数据库先通过 `SELECT 1` 验证，只连接指定 PostgreSQL 55460 和配置中的 MySQL 33070，无需环境恢复。仅余既有 Starlette/httpx、anyio 两项弃用提示。最终测试后只更新本节检查结果并检查 diff，未修改实现、模型或接口契约，未启动应用服务、commit 或 push。
