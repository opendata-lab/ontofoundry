# 提案检查只有一处：对话内提交即入库

日期：2026-11-04。状态：方向经用户同意（2026-11-04）；Codex 评审（2026-11-04）8 条已并入。不兼容 0.2.6 技能（SC-09）。补充 `2026-10-26-checks-before-output.md`：CO-01（检查串在产出之前）、CO-02（最多两轮修正）不变；该文 §4“入库不会再因为内容被拒”不成立，由本文 SC-04、SC-05 处理。

## 1. 背景

对话内的平台检查（`/proposal-check`）和入库（`_consume_proposals`）调用的是同一个函数 `parse_agent`，规则没有复制两份。但模型在对话里检查通过，入库或审阅时还要修，原因是同一套规则在不同环节用了不同的宽严和不同的状态：

| 环节 | 现状 | 后果 |
|---|---|---|
| 来源列 | 对话 `probe=False`；数据集没有列清单时 `validate_source_columns` 直接跳过（`join_validation.py:21`） | 入库后审阅页的 `proposal_diagnostics` 按实时元数据报 `COLUMN_NOT_FOUND`、`DATASET_SOURCE_BLOCKED` |
| 入库改写内容 | `trial_apply` 用元数据补全数据集列、改写引用，覆盖 `item.after`；`store_batch` 又跑一遍 `trial_apply`（`proposals.py:53`） | 存进库的不是 Agent 检查过的那份 |
| 检查与入库之间状态变化 | `parse_result` 用固定草稿，`trial_apply` 读实时草稿、实例和元数据 | 检查后别的会话改了实例或同步了元数据，入库 `failed_permanent`，Agent 已结束，无法修 |
| 报错数量 | `parse_result` 遇到第一个问题就抛出；`proposal_checks.check_result` 只返回这一条 | Agent 一次只能改一个问题 |
| 修正预算 | 运行环境里的计数文件，候选内容一变就计一轮，在平台检查之前就扣（`check_result.py:413-453`） | 本地格式修正用掉两轮预算，平台报的问题来不及改 |

例：Agent 新建数据集 `fiction_orders`（已绑连接 `虚构采购库`），映射里用列 `supplier_nm`，元数据快照里该表没有列清单。对话检查通过；入库后元数据同步完成，审阅页显示“列 supplier_nm 不存在”，只能人工改。

另外，技能脚本带了不少平台内部细节（2026-11-04 评审，已核实）：

- 从 MCP 地址截掉 `/mcp` 再拼出检查地址（`prepare_result.py:263-281`）；
- 把平台已有的数据抄进结果再交回平台比对：结果头部 7 个字段、`before`、`expected_target_hash`、`material_sha256`（`prepare_result.py:41-74, 112-136`）；
- 修正计数放在 Agent 可写的文件里；
- 平台写死运行环境里的结果文件路径并在运行结束后下载（`model_result.py:220`）。

调用方式本身不改：由技能脚本直接调平台接口，不改成 Agent 调 MCP 工具。理由：结果有一两百条，由模型写进工具调用既费 token 又可能截断；MCP 接口限 256 KB（`api/mcp.py:85`）；改 MCP 工具要管理员在 DataAgent 后台刷新工具列表，问数 Agent 也会看到写入工具；本轮专用凭据已经和 MCP 共用同一授权（`mcp_principal`）。

## 2. 已确认决定

| 编号 | 决定 | 状态 |
|---|---|---|
| SC-01 | 检查只有一个函数 `evaluate_batch`：输入结果文件和运行固定上下文，输出全部错误、警告和规范化后的提案。提交接口和审阅页的来源诊断都调用它；审阅页的列检查改为调用同一个列检查函数，不再单独写规则。 | 用户同意方向（2026-11-04） |
| SC-02 | 对话检查按接受时的严格程度检查来源列。表未同步、来源不在允许范围仍为错误（现状，`SOURCE_NOT_REGISTERED`）。已绑连接的数据集取到列（表数据集用元数据快照，查询数据集用只读 LIMIT 0 探测）后，映射来源、字段、继承的关系绑定、关系的 `data_join`、指标引用的列不存在为错误；只有连接不可达或探测超时取不到列时为警告“来源列未核对”。 | 用户同意方向（2026-11-04） |
| SC-03 | 未绑连接的数据集保持现状：对话检查和入库都放过，由审阅人在提案中选择连接，接受时仍要求已绑定。对话检查不为此报错或警告。 | 已确认（用户 2026-11-04：人工可修，不需要再做） |
| SC-04 | 入库不改写。检查返回规范化后的提案，入库的就是这一份；`store_batch` 不再调用 `trial_apply`。 | 用户同意方向（2026-11-04） |
| SC-05 | 提交即入库。合并脚本把结果交给平台的提交接口，平台在同一事务里检查并保存批次（按 `run_token` 幂等）；不通过则不保存，全部错误返回给 Agent 当场修正。运行结束后平台不再下载结果文件、不再重新检查，只看本轮是否已有批次。 | 用户同意方向（2026-11-04） |
| SC-06 | 一次返回全部可独立判断的错误（逐条提案、逐组）。修正预算由平台计数：同一轮运行中，提交未通过后再提交不同内容计一轮，最多两轮（CO-02）；本地检查不计。 | 用户同意方向（2026-11-04） |
| SC-07 | 平台在运行凭据文件里直接给出提交地址 `submit_url`，脚本不再从 MCP 地址拼接。 | 用户同意方向（2026-11-04） |
| SC-08 | 结果只写 `items`。头部字段、`before`、`expected_target_hash`、`material_sha256` 从结果契约中删除，由平台按本轮固定上下文补全。 | 用户同意方向（2026-11-04） |
| SC-10 | 提交成功后本轮结果即定：之后任务失败或被停止，只改运行状态，不改已入库的批次和 `result_state`。 | 已确认（用户 2026-11-04） |
| SC-09 | 不兼容旧技能：删除 `/proposal-check` 接口和运行结束后下载结果文件入库的路径；平台与技能同时升级到 0.3.0。 | 已确认（用户 2026-11-04：不需要兼容） |

来源：全部是运行协议和检查实现，不进入本体模型，不新增概念。SC-05 删除“结果文件下载 + 入库重检”一条路径，删掉它失去的是“Agent 绕过合并脚本直接写结果文件也能入库”，这本来就算异常（CO-01）。SC-08 删除的是重复数据，不删除乐观并发检查：平台仍按固定上下文的哈希比对当前状态。

## 3. 检查函数（SC-01、SC-02、SC-06）

```
evaluate_batch(db, settings, session, context, raw) -> Evaluation
  errors:   [{code, message, client_ref?, pointer?}]   # 有任何一条即不通过
  warnings: [{code, message, client_ref?, pointer?}]   # 来源列未核对、相似定义、物理差异
  items:    规范化后的 ParsedItem 列表
```

- 顺序：补全（SC-08）→ `parse_result` → `trial_apply`（`allow_unbound` 照旧，SC-03；`validate_join_columns` 改用同一份列来源，区分“取不到列”和“来源无效”，前者不在此处失败）→ 来源列检查（SC-02）→ 对齐提示（`AlignmentContext`，只出警告）。
- 收集错误：`parse_result` 的逐条检查改为记下错误继续检查下一条，最后统一抛出；整批级错误（JSON 无效、Schema 无效、固定上下文失效）仍只返回一条。`trial_apply` 按整批原子判定（`2026-10-26-serial-atomic-modeling.md`），整图规则失败时只能报一条；能逐条判断的规则（目标状态、Pydantic 校验、证据、来源列）改为逐条收集，附 `client_ref`。
- 来源列检查函数合并 `proposal_diagnostics` 和 `validate_source_columns` 的覆盖范围（映射来源与字段、继承链上的来源、`inherited_link_bindings`、关系 `data_join`、指标），放在 `services/join_validation.py`，对整个候选图检查一次：提交时用于判定，审阅页读批次时用于显示实时状态（元数据可能在入库后变化）。

## 4. 提交接口（SC-04、SC-05、SC-07、SC-10）

- 新接口 `POST /api/v1/ontology/workspaces/{workspace_id}/runs/{run_token}/proposals`，凭据为本轮运行凭据，请求体为结果文件内容。
- 处理分两段，探测业务库不占锁：
  1. 锁外：`evaluate_batch` 的探测部分（查询数据集 LIMIT 0），每个数据集只探一次，整批探测总时长上限 20 秒，超出的数据集记警告；
  2. 锁内（`lock_session`）：
     - 核对 `run_token` 是会话当前运行（`dataagent_run_token`）、固定上下文未失效；
     - 本轮已有批次：`result_sha256` 相同返回该批次，不同返回 `RUN_ALREADY_SUBMITTED`（先于待审检查，丢失响应后重试能拿到原结果）；
     - 没有待审提案；
     - `evaluate_batch` 其余部分（用锁外的探测结果，不再连业务库），有错误时计修正轮次并返回，不写库；
     - 无错误时 `store_batch` 保存规范化提案，写 `result_state="done"`，提交。
- 运行凭据有效条件：会话当前 `run_token` 一致，且任务处于活动状态或本轮已有批次（只读回执）。任务 ID 尚未写入（投递响应慢）时也可提交，批次的 `dataagent_task_id` 在任务登记时补上。
- 返回 `{passed, errors, warnings, reviewable_count, batch_id, repair_used, repair_limit}`。
- 修正计数存在 `session.run_manifest_json`；会话上对 `run_manifest_json` 的所有写入改为在会话锁内合并字段，不再整体覆盖（避免任务登记时冲掉计数）。
- 任务状态投影（`modeling_runs`）：本轮已有批次时，任务失败或停止只更新 `task_status`、`task_detail`，不改 `result_state`，不使批次失效（SC-10）。
- `reconcile_run`：本轮已有批次 → `done`；没有 → `failed_permanent`，原因“本轮没有提交通过检查的结果”。删除 `_consume_proposals`、结果文件下载和下载重试。
- 删除 `/proposal-check` 接口、`ontofoundry.proposal-check.v1` 契约（SC-09）。
- 导入确认（`services/imports.py`）原来靠 `store_batch` 里的 `trial_apply` 做来源、标识和证据检查；`store_batch` 不再检查后，导入确认显式调用 `trial_apply` 并把规范化提案交给 `store_batch`。

## 5. 技能侧（SC-06、SC-07、SC-08）

- `prepare_result.py`：合并分片 → 本地检查（JSON、Schema、`client_ref` 闭合）→ 调 `submit_url` → 输出平台返回的全部错误和警告，错误映射回 `parts/0X.json` 的条目；通过后写结果文件留档。
- 删除：从 MCP 地址拼接检查地址；`fill_material_hashes`；`before` 和 `expected_target_hash` 注入；计数文件；`check_result.py` 中的头部、`before`、哈希比对。
- `context.json` 本次不改：Agent 仍要靠它查看已有定义（`show_element.py`）。去掉其中的 `element_hashes` 放到下一步。
- 删除 `fixed_context["execution"]`（计数改由平台返回）和工作包里的 `mcp_config_file` 检查用途；`platform_check_file` 改名为 `submit_file`，内容为 `{submit_url, headers}`。
- 技能包和平台同时升到 0.3.0（SC-09），按 `integrations/dataagent/README.md` 重新安装技能并重启 DataAgent。

## 6. 入库还会失败的情况

只剩运行没有提交通过的结果（Agent 放弃、超时、平台不可达、用户停止）和运行期间会话被放弃。检查和保存在同一事务里，中间不会再有状态变化。
