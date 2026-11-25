# 建模对话中的 Ossie 导入：实施计划

日期 2026-11-25（重写，含评审修订，见设计 §8）。依据 `docs/design/2026-11-24-ossie-in-conversation-import.md`（2026-11-25 版）。前置：PR #106、#107、#109 合入 main。

分 2 个 PR。文档、示例和测试只用虚构名字（如 `sales.order_df`、`sales.customer_df`）。

## PR 1：导入器（`apps/api/src/ontofoundry_api/adapters/ossie/`）

- `ImportContext` 增加可选的 `session_tables`（本轮 `table_snapshot` 中的表：连接、schema、表名、主键、列）。“导入文件”路径不传，行为不变。
- `mappings.import_datasets`：扩展文件没有连接名、`source` 为 `schema.table` 时，在 `session_tables` 中找同 schema 同表名的表；恰好一张则采用其连接，否则不接连接并报告“缺表”（OC-02）。
- `rules.import_rules`：约束只要求一个属性不为空时，设该属性 `required=true`，不生成规则，报告注明（OC-04）。判断复用 `domain/rule_evaluation.only_says_required`。
- 报告：物理连接因目标唯一键未证明而放弃时，若两端数据集命中会话表，附上两端登记表的主键和列，供智能体判断（OC-03）。
- 测试：唯一命中、没有命中、扩展连接名优先、“导入文件”路径不接；`requires: ["order.code IS NOT NULL"]` 得到必填属性且没有规则；未证明的物理连接报告带两端主键。

## PR 2：运行前导入与技能（`apps/api/src/ontofoundry_api/`、`integrations/dataagent/`）

- `api/agent_conversation.py` 启动运行处：先解析会话表范围（现有 `resolve_session_table_scope`），再对本轮材料中尚未导入过的 Ossie JSON（按会话 + 材料 SHA 判断）执行导入，然后才计算待审上下文（`run_review_context`），使固定草稿包含导入提案。
- 抽出 `services/imports.py` `confirm_import` 中“生成并存储批次”的部分，供两处共用：基线换成本会话草稿；不新建会话；会话已有待审提案时与之合并（复用 `pending_merge`）；来源 `producer.kind = import`。导入记录（`ImportRecord`）照常保存原文、报告和转换结果，并记下会话，用于“只导入一次”。
- 导入失败（不是合法 Ossie、转换错误）：报告写入工作包，运行照常开始，不阻断对话。
- 工作包加 `import_report`（摘要 ≤ 8 KB，明细另存文件）。
- 技能：改写 `skills/ontology-discovery/references/import-completion.md`：本会话有导入提案时读 `import_report`；导入的元素已在草稿中，可以修改，不要重复建；快照列、未证明的物理连接由智能体判断，依据写进提案 `reason`；只补缺口和润色。守住离线字节预算，`plan.md`、`extract.md` 不增字节。
- 测试：带 Ossie 材料发消息后会话出现导入提案、工作包有报告、固定草稿包含导入元素；再发一次消息不重复导入；已有待审提案时合并为一个批次；导入失败时运行照常开始；智能体结果修改导入项后合并成一条新增提案（新增 + 修改 → 新增）。

## 端到端验证

- 本地 Doris 模拟库（`~/.local/odw-doris/arch-gov-sim/`，164 张表）+ 内网同一份 Ossie 材料，本机 DataAgent（:8902）。内网真名只留在本机，不进仓库。
- 对照组：同一材料、同一表范围、同一模型、空草稿，用现行流程跑一次。
- 记录：首次提交前的回合数和时长、读原文次数、提交修正次数、最终提案条数。
- 正确性：41 个数据集的连接；14 条物理连接中智能体写出的对接是否通过检查、是否与表主键一致；快照列判断；入库只有一批；续做后修改仍在。
- 部署后按 `integrations/dataagent/README.md` 同步技能，用局域网 IP 验证一次。

## 评审修订（设计 §8，优先于上文）

- **PR 1**：OC-04 只在约束属于该属性所属对象本身、每个合取项都只要求非空时，按属性 UUID 设必填；否则不生成规则、报告为待补全。测试补：`AND` 两个非空、子类约束继承属性（不转）。证据按 JSON Pointer 从原始字节取行段（单行 JSON 回归测试）。
- **PR 2**：
  - 新表“会话材料导入”（会话、材料 SHA 唯一；报告、批次 ID），Alembic 迁移；不改 `ImportRecord`。
  - 会话有待审提案时不导入，报告提示先处理待审。
  - 未命中会话表的数据集及其依赖不进批次。
  - 导入批次 `source_session_revision` 取本轮修订号、令牌 `import:<记录>`；测试：取消运行后导入批次仍可接受和拒绝。
  - 导入记录、批次、运行占位同一事务；失败局部回滚、清理新文件、带报告继续；DataAgent 投递失败后重试复用已提交的批次和报告。
  - 续做基线加入固定草稿哈希；工作包只放短提示和报告路径；合批后总条数超过 500 报错。
  - 技能：计划阶段看到导入提示即写“补全导入缺口”；改导入项保留原证据。
