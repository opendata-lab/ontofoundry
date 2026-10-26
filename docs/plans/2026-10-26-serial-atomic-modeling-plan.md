# 建模串行化与原子化：实施计划

设计：[2026-10-26-serial-atomic-modeling.md](../design/2026-10-26-serial-atomic-modeling.md)。依据：codex 评估报告（2026-10-26）。

## 阶段 1：低风险修复

1. 合并脚本：
   - `prepare_result.py`：缺少检查配置时报错，不写最终结果；
   - 删除 `--drop-unacceptable` 和 `drop_unacceptable`；
   - 删除 `check_result.py --publish`；
   - 同步 `finish.md` 和 `README.md`。
2. 发起新一轮前做占用检查：运行已结束但结果还没处理（结果未领取，或处于 processing、failed_retriable）时，拒绝新一轮，返回 409。错误码沿用现有风格，提示文案为“上一轮结果还在处理，请稍候”。
3. 对话快照（`agent_conversation.snapshot`）：
   - 不再调用 `reconcile_run`，不再用平台结果改写运行状态；
   - 提交状态未知时的对账（`_reconcile_stale_submission`）和任务替换，移到建模运行服务。
4. 事件流改用增量 UTF-8 解码，避免中文在网络分块处变成乱码。

## 阶段 2：共享试应用

1. 新建 `services/proposal_apply.py`，分三层：
   - 解析适配：Agent 原始 JSON、导入变更、已存批次加上修改；
   - 试应用：在当前草稿和实例基线上完整校验，输出规范化候选内容、依赖关系和共同决定组，以及实例写入计划，不持久化；
   - 事务内应用：把所选提案及其依赖闭包写入草稿和实例。
2. 把以下规则并进试应用：
   - `parse_result` 和 `group_items` 中的整图规则（改为整批，不再逐组放行）；
   - 数据集来源的静态校验：从 `enforce_dataset` 中拆出，不含实时探测；
   - 证据归属和同一批内的证据 id 复用（`instance_store._save_evidence` 的规则前移）；
   - `check_identities`；
   - 实例 revision 和目标状态。
3. 改为调用试应用的地方：
   - 运行检查接口：`proposal_checks.check_result`；
   - 结果入库：`model_result._consume_proposals` 和 `services/proposals.store_batch`；
   - 接受：`proposal_decisions`，按依赖闭包，同一事务；
   - 修订：`proposal_revision.revise_proposal`、`dataset_proposals.revise_dataset`、`fact_revision.revise_fact`（在当前批次内修订）；
   - 导入：`imports.confirm_import`，以及 `import_completion.complete_import`（在当前批次内更新）。

## 阶段 3：串行门禁

1. 新建会话占用判断 `services/session_gate.py`：会话是否被占用、是否有待审提案。
2. 门禁接入以下入口：发起运行、保存草稿、保存元素、合并、发布、导入覆盖、接受、拒绝、恢复、撤销，以及提案、数据集、实例事实的修订。
3. 拒绝时，连同依赖它的待审提案和同组提案一起拒绝（后端完成，前端只负责展示）。
4. 新一轮开始后，旧批次只读。

## 阶段 4：删除旧状态

1. 删除：
   - `unacceptable`、`superseded` 的写入路径，`stale`、`conflict` 的推导；
   - `store_failed_batch`；
   - 前端相关的页签、文案和类型。
2. 新增 Alembic 迁移清理旧数据：
   - 状态为 unacceptable 的待审提案和失败批次直接删除（不兼容旧数据）；
   - superseded 的提案标为已拒绝。
3. 契约变更时，同步更新 JSON Schema、Pydantic 模型和前端类型。

## 阶段 5：测试与验证

- 新增和保留以下用例：
  - 英文标识互换、复合标识（共同决定组）；
  - 提案编辑后与已有定义重名，保存时被拒；
  - 拒绝时连带拒绝依赖它的提案；
  - 待审期间禁止编辑草稿、禁止发起新一轮；
  - 结果处理期间发起新一轮返回 409；
  - 取消后迟到的结果不入库；
  - 同一批内复用证据 id 在检查阶段被拦下；
  - 导入补全在当前批次内更新；
  - 检查通过的批次接受全部成功。
- 全部改完后统一运行：
  - 后端 `pytest -q`；
  - 技能测试 `pytest -q integrations/dataagent/tests`；
  - 前端 `npm test -- --run`、`npm run build`、`npm run test:visual`；
  - 构建页在 1440×900 下截图对比。
