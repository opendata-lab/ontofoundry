# 提案检查只有一处：实施计划

设计：`docs/design/2026-11-04-single-proposal-check.md`（SC-01～SC-10）。依据：Codex 评审（2026-11-04，8 条均已核实并入）。不兼容 0.2.6 技能，平台与技能同时升到 0.3.0。

## 进度（2026-11-04）

- 已完成：阶段 2（提交即入库、删除 `/proposal-check` 与结果下载、`store_batch` 不再试应用、导入确认显式试应用、提交后停止保留批次、任务登记补写批次任务 ID）；阶段 5 的 `submit_url`（写在现有凭据文件里，工作包键仍叫 `platform_check_file`）；阶段 6 中合并脚本改为提交、`finish.md`、`README.md`、迁移说明。
- 2026-11-05 完成阶段 4：平台按被拒提交计修正轮次（内容相同重交不计），任务登记时保留计数；技能删除本地计数文件。起因：端到端测试中本地格式修正占用了轮次，第 4 次提交未到平台即被拦下。
- 2026-11-05 完成阶段 1 的“一次返回全部错误”：`parse_result` 的两轮逐条检查收集全部出错条目，提交接口逐条返回，整批只计一轮修正；另修复 MySQL 查询数据集被拒、拒收原因丢失诊断详情、绑定就绪只看实际读取的列。
- 未完成：阶段 1 的提交时严格检查来源列与锁外探测（端到端运行中入库后来源诊断为空，优先级降低）；阶段 3（结果契约去掉头部和哈希）；阶段 5 的工作包键改名；阶段 6 中 `check_result.py` 精简与示例更新；版本号升到 0.3.0。
- 已知遗留：`modeling_runs` 中“提交状态未知”的对账（任务 ID 未写入即释放）仍会使固定上下文失效，即使本轮已有批次；需与阶段 2.3 一起处理。

## 阶段 1：检查函数（SC-01、SC-02、SC-06）

1. 新建 `services/proposal_evaluation.py`：
   - `evaluate_batch(db, settings, session, context, raw) -> Evaluation(errors, warnings, items)`；
   - 顺序：补全（阶段 3）→ `parse_result` → `trial_apply(draft=context.draft, baseline=context.instance_baseline)` → 来源列检查 → `AlignmentContext` 警告；
   - `ServiceError`、`ProposalContractError` 转成 `errors`，不再只取第一条。
2. `contracts/proposals.py` 的 `parse_result`：
   - 逐条检查改为收集错误：`fail()` 记入列表，跳过当前条目，继续下一条；
   - 整批级错误（JSON、Schema、固定上下文失效）仍立即抛出；
   - 有错误时最后抛出 `ProposalContractErrors(list)`。
3. `trial_apply`：
   - 逐条规则（目标存在与哈希、Pydantic 校验、实例 revision、证据）收集错误后统一抛出；
   - 整图规则（`group_items`、`OntologyDraft.model_validate`、`check_identities`）保持整批失败，报一条。
4. 来源列检查（SC-02）：
   - 从 `services/dataset_proposals.proposal_diagnostics` 抽出 `source_column_diagnostics(db, settings, workspace_id, candidate)`，放进 `services/join_validation.py`，对整个候选图检查一次；
   - 覆盖：映射来源与字段（含继承链来源）、`inherited_link_bindings`、关系 `data_join`、数据集 `snapshot_date_column`、指标的度量、时间、过滤和表达式列；
   - 表未同步、来源无效仍为错误（现状）；列不存在为错误；只有连接不可达或探测超时为警告 `SOURCE_COLUMNS_UNCHECKED`；
   - 未绑连接的数据集跳过，不报（SC-03）；
   - 列来源分两步：`collect_columns(db, settings, workspace_id, datasets)` 在锁外运行，表数据集读元数据快照，查询数据集 `check_dataset(probe=True)`，每个数据集只探一次，整批总时长上限 20 秒；`source_column_diagnostics(candidate, columns)` 是纯函数，锁内运行；
   - `validate_join_columns` 改用同一份列来源，“取不到列”不在此处失败；
   - `proposal_diagnostics` 改为调用它，只用于审阅页显示；
   - 回归用例：查询数据集无声明列、映射表关系引用不存在的输出列，提交应报错。
5. `validate_source_columns` 的覆盖并入上一步的纯函数；草稿保存仍调用它（行为不变，内部复用）。

## 阶段 2：提交即入库（SC-04、SC-05、SC-09、SC-10）

1. 新接口 `api/proposal_submit.py`：`POST /api/v1/ontology/workspaces/{workspace_id}/runs/{run_token}/proposals`
   - 锁外：解析结果、`collect_columns`；
   - 锁内（`lock_session`）依次：`run_token` 是当前运行、固定上下文未失效 → 已有本轮批次（相同 `result_sha256` 返回原批次，不同 `RUN_ALREADY_SUBMITTED`）→ `has_pending` → `evaluate_batch` → 有错误计修正轮次返回 → 无错误 `store_batch`、`result_state="done"`、提交；
   - 修正轮次在出错时也要提交事务（只写 `run_manifest_json`）。
2. 运行凭据（`api/auth.py:140-152`）：提交接口单独校验，条件为 `dataagent_run_token` 一致且（任务活动中，或本轮已有批次——只允许返回原回执）。MCP 读工具的凭据条件不变。
3. 任务登记（`api/agent_conversation.py:538-601`）：
   - 允许任务 ID 写入前就提交；登记时若本轮已有批次，补写批次的 `dataagent_task_id`；
   - `run_manifest_json` 的写入改为在会话锁内合并字段，不整体覆盖。其他写 `run_manifest_json` 的地方（`modeling_runs.py:104-110` 等）同样改为合并。
4. 任务状态投影（`services/modeling_runs.py:95-115`）：本轮已有批次时，失败或停止只写 `task_status`、`task_detail`，不写 `result_state`、不置 `invalidated`（SC-10）。
5. 契约 `contracts/proposal_submit.py` 和 `ontofoundry.proposal-submit.v1.schema.json`：`{passed, errors[], warnings[], reviewable_count, batch_id, repair_used, repair_limit}`，`errors`、`warnings` 条目为 `{code, message, client_ref?, pointer?}`。
6. `services/proposals.store_batch`：删除其中的 `trial_apply`，直接保存传入的规范化提案（SC-04）。
7. 导入确认（`services/imports.py:389-396`）：在调用 `store_batch` 前显式 `trial_apply`，用其规范化提案；补导入回归用例（已绑连接但来源无效的数据集应在导入确认时报错）。
8. `services/model_result.py`：
   - `reconcile_run`：本轮已有批次 → `done`；没有 → `failed_permanent`，原因“本轮没有提交通过检查的结果”；
   - 删除 `_consume_proposals`、结果文件下载、`exhaust_retriable_result`；
   - 保留 `workflow_diagnostics`（读取 `modeling/parts/*` 作为失败诊断）。
9. `services/modeling_runs.py`：删除对 `exhaust_retriable_result` 的导入和调用（`:16`、`:343`）及下载重试循环；`failed_retriable` 状态如无其他用途一并删除（先 grep 确认）。
10. 删除 `api/proposal_checks.py`、`services/proposal_checks.py`、`contracts/proposal_checks.py`、`ontofoundry.proposal-check.v1.schema.json`，从 `main.py` 去掉路由。

## 阶段 3：结果契约瘦身（SC-08）

1. `contracts/proposals.py`：
   - `result_schema()` 删除头部字段（`schema_version`、`workspace_id`、`session_id`、`run_token`、`base_version_id`、`base_version_sha256`、`source_session_revision`、`source_draft_sha256`）及条目的 `before`、`expected_target_hash`、证据的 `material_sha256`；
   - `parse_result` 从 `context` 取头部值，从 `context.draft` 和 `context.instance_baseline` 补 `before` 与 `expected_target_hash`，从 `material_lookup` 补 `material_sha256`；
   - 契约文件改为 `ontofoundry.proposals.v2.schema.json`，`SCHEMA_VERSION = "ontofoundry.proposals/v2"`。
2. `services/proposals.proposal_header` 删除；调用方 `api/agent_conversation.py:53, 513` 与 `proposal_instructions(header=...)` 参数一并删除，提示词里不再出现结果头部。`proposal_context` 的 `run` 只留 `run_token`、`workspace_id`。
3. 前端类型：`apps/web/src/api/types.ts` 中无结果头部类型，确认后不改；提交接口不被前端调用。

## 阶段 4：平台计修正轮次（SC-06）

1. `session.run_manifest_json` 增加 `repair_used`、`last_failed_sha256`。
2. 提交未通过：若 `result_sha256` 与 `last_failed_sha256` 不同且已有过一次未通过，`repair_used += 1`；`repair_used > 2` 时返回 `REPAIR_BUDGET_EXHAUSTED`，不再检查。
3. 删除 `modeling_input.execution_input` 和 `fixed_context["execution"]`。

## 阶段 5：运行凭据文件（SC-07）

1. `api/agent_conversation.py`：上传 `ontofoundry-submit-{run_token}.json`，内容 `{submit_url, headers: {Authorization, Content-Type}}`；工作包键 `platform_check_file` 改为 `submit_file`。
2. MCP 配置文件照旧，只给 Agent 读工具用。

## 阶段 6：技能（integrations/dataagent）

1. `shared/scripts/prepare_result.py`：
   - 删除 `fill_material_hashes`、`material_hashes`、`before`/`expected_target_hash` 注入、`platform_check` 中的 URL 拼接；
   - 结果只写 `{"items": [...]}`；
   - 调 `submit_file` 的 `submit_url`；输出平台全部 `errors`、`warnings`，错误按 `origins` 映射回 `parts/0X.json#i`；输出 `repair_used/repair_limit`；
   - 通过后写结果文件留档。
2. `shared/scripts/check_result.py`：删除计数文件、头部比对、`before` 与哈希比对，只留 JSON、Schema、`client_ref` 与 `depends_on` 闭合、`mapping_local_errors`。
3. `check_part.py`：随 `check_result.py` 调整。
4. `generate_output_schemas.py`、各技能 `output-schema.json`：按 v2 契约重新生成。
5. `shared/references/steps/finish.md`、`shared/references/examples/*.json`、`agents/agent_ontofoundry.md`：删除头部、`before`、哈希的写法，说明修正计数由平台返回。
6. `plugin.json`、`README.md`：版本 0.3.0，`minimum_platform_version` 0.3.0，删除 `proposal-check` 说明，补“提交即入库”。

## 阶段 7：文档

1. `docs/design/2026-10-26-checks-before-output.md` §4 加一行指向本设计。
2. `docs/design/2026-10-23-proposal-checks-in-conversation.md` 状态行：§3 平台检查接口被 SC-05、SC-09 取代。
3. `docs/concepts/` 无模型概念变化，不改。

## 测试（全部编辑完成后统一跑）

- 后端：`test_proposal_checks.py` 改写为 `test_proposal_submit.py`（通过即入库；丢失响应后重试返回原批次而不是 `PENDING_PROPOSALS`；内容不同拒绝；修正计数及任务登记不冲掉计数；任务 ID 写入前提交；提交后停止任务，批次保留；全部错误一次返回；来源列错误与警告、探测总时长上限）；`test_agent_conversation_bff.py`（登记与合并写入）；导入确认用例；`test_model_result.py`（无批次失败、不再下载）；`test_t1_proposal_contract.py`、`test_t3_proposal_results.py`（v2 契约、平台补全 `before` 和哈希）；`test_t4_proposal_decisions.py`、`test_proposal_alignment.py`（回归）。
- 技能：`test_platform_check.py` 改为提交接口；`test_check_result.py`、`test_workflow.py`、`test_stepwise_workflow.py`、`test_packages.py`。
- 命令：`make -C apps/api test`（或仓库现有命令）与 `make -C integrations/dataagent test`。

## 风险

- 查询数据集在提交时探测业务库：在锁外进行，每个 5 秒、整批 20 秒上限，只读连接、sqlglot 白名单（现状）；超时只出警告。脚本调用提交接口的超时从 15 秒改为 60 秒。
- `parse_result` 改为收集错误后，后续条目可能引用了出错条目，产生连带错误；连带错误只报引用不存在，不重复报原因。
