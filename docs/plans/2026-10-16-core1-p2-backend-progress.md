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

最初按计划尝试 `UV_CACHE_DIR=/private/tmp/core1-p2-uv uv run --offline --python 3.13 ...`，uv 在启动时因 macOS `system-configuration` 的 `Attempted to create a NULL object` panic 返回 101，schema/lint/pytest 均未开始执行。随后直接调用现有虚拟环境内相同的 Python/ruff 完成全部检查，没有据此记为测试失败或跳过。

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
