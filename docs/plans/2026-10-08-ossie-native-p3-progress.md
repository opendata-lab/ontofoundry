# P3 语义模型与映射树实施进度

基线：2026-10-09，P2 提交 `3a2ceef`。仅本 worktree 修改，禁止提交/启动服务/访问演示目录。保留已有问数提示词工作区改动。

核对：P1/P2 已原生承载 semantic_models/datasets/dataset_fields/dataset_relationships/metrics/concept_mappings/mapping_nodes，slot、出现状态、数组顺序、扩展与稳定 ID 已具备，A/B 严格往返 0 差异。缺口是读路径仍借助旧编译/解析器，写表单按连接整组重建、复合连接不可查询，以及缺少语义层只读浏览。

里程碑：M1 直接派生 mapping_view/join_view；M2 实例/MCP/投影/脚本消费切换与复杂映射错误；M3 定向原生写入与提案/编辑；M4 语义层只读页签和指标归属；M5 A/B、SQLite 数据库与咖啡业务端到端回归及全量检查。

当前数字：P2 基线 API 557 passed / 1 skipped，Web 27 files / 129 tests。下一步 M1，未决为 B 可查/只读数量待新视图实际分析。测试使用隔离库，不调用真实智能体或运行演示脚本。

## M1/M2/M3 — 2026-10-09（实现与专项验证进行中）

直接读取原生 concept_mapping 树的 `mapping_view` / `join_view` 已实现；单列投影解析 ANSI_SQL 字段，未用于查询的计算字段/指标不阻断查询；连接支持多列等值并按端点方向执行。实例搜索/详情/双向邻域与会话/版本/提案/MCP 投影通过同一视图读取，不再编译 Ossie 再解析旧映射。复杂映射返回 `COMPLEX_MAPPING_READ_ONLY`。

映射写入已改为定向更新 native dataset/field/concept_mapping/mapping_node/dataset_relationship，连接别名写入模型 vendor 扩展；保留其他模型、字段、指标和子树。平台新节点使用可重复的身份，避免元素保存预演/事务实际写入产生不同 ID。旧 Mapping DTO 仅为表单/提案的输入和派生输出，v3 持久化 mappings 仍为空。演示脚本 data/check 改读映射视图表单，提交原生结构并检查可查询概念数。

专项第一轮发现两处旧测试合同需调整：B 的复杂 component 不再允许叠加简单映射（身份保留测试改用未映射 microservice_component 并保留全部现有简单投影）；保存预演两次生成随机子树 ID 已改为确定性身份。修复后实例/表单/原生视图专项 **14 passed**。新增复合 SQL 与 B/coffee 发布-MCP 验收仍在验证，全量尚未运行。

B 初步覆盖：29 个 EntityType，10 个可查询，11 个复杂只读（2 个多根、9 个 referent），8 个无映射。A/B 读取视图前后原快照与原生导出均 0 差异。

下一步：完成只读语义浏览与大列表分页组件测试、B 等价 SQLite 查询、4 表/3 连接提案发布和 780/269516 问数回归，然后运行全量 API/ruff/Web。未决：真实回放固定快照中的两条反向关系已有 from_columns/to_columns 与演示表外键位置不符，本阶段保留原文件不推断修复；新的建模提案测试显式写入正确的端点连接列并验证方向。尚无最终测试数字。

## M1/M2/M3 专项验收 — 2026-10-09

原生视图、原生映射写入、发布与实例/MCP 专项在 SQLite/隔离 PostgreSQL 持久库上 **9 passed**（72.75s，无跳过）。B 所有 10 个简单概念的搜索及详情可查询；complex component 明确返回只读错误。真实回放概念基础上生成 4 条 mapping create + 3 条 link update 提案，全部接受、预览无错误、发布成功；等价 SQLite 销售表验证 **780 张订单 / 269516 元**，反向 customer/order 及 order/item 连接、商品邻域正常；映射编辑后发布查询采用新列。

新建、编辑、复合连接原生导出通过固定 Ossie 校验，二次导入 ID/数组顺序保持，未编辑 A/B 仍严格逆转换 0 差异。新增列名引用使用 SQL 标识符引用，保留含空格/保留字列的单列解释。新增通用连接绑定覆盖/禁用测试，避免删除共享 dataset_relationship 或让旧连接覆盖新显式连接。全量正在运行，最终数字见 M5。

## M4 — 2026-10-09（已实现）

数据映射页新增语义模型只读页签；模型折叠、数据集每页 10、字段展开后每页 20、连接每页 20、指标每页 10；展示来源、主键/唯一键、说明、原始方言表达式、数据类型、维度、同义词、多列连接以及指标的 0..n 归属概念。归属由映射树/指标数据集引用推导，并标记多候选，未新增持久化字段。新增成员专用干净 `/semantic-models` REST 投影，不返回内部保真字段；完整编辑草稿合同保持。

复杂概念映射表单显示“复杂映射：暂只读”，不提供简单表覆盖入口；复合关系映射显示全部键对并只读，实例面板显示只读原因。服务端同样拒绝简单 DTO 覆盖复杂原生树。Web 初轮全量 **28 files / 132 tests passed**，lint、tsc -b 通过；新增 3 个组件测试覆盖大列表折叠/分页、原文表达式/同义词/多候选归属及复杂编辑保护。最终复核待 M5 记录。

下一步：全量 API/ruff/Web 最终验证、更新 B 覆盖及验收边界。未决：复杂映射/复合对象键按 P3 只读，跨数据源连接不执行，指标执行属于 P4；没有真实外部 MySQL 测试库，保留原有环境跳过。

### M5 全量首轮与修复 — 2026-10-09

API 全量首轮（隔离 PostgreSQL）结果 **563 passed / 1 failed / 3 errors / 1 skipped**（527.35s）：失败为成员概览把复杂映射从计数/预览中丢弃，已改为按原生概念映射计数并用查询视图标记 queryable/readonly；3 个错误为新测试复用 fixture 在全量收集时未注册，已改为模块内显式 fixture 绑定。专项还发现原生关系改名后，在旧名称新增连接时派生 ID 碰撞；已提供可重复的替代 ID，保留改名节点身份。资产兼容性检查现使用复合连接全部列。

修复后表单/视图/双向 SQL 专项 **16 passed**；概览/新视图/发布专项 **12 passed / 2 skipped**（本次专项未提供 PostgreSQL 环境变量，两个后端变体待最终全量覆盖）。Web 最终复核 **28 files / 132 tests passed**（13.80s），lint、tsc -b 通过。覆盖矩阵生成检查与 git diff --check 通过。最终 API 全量正在重跑；此处不视为 M5 完成。

### M5 评审修复 — 2026-10-10（进行中）

确认平台连接写入未为未映射的物理连接键补充 dataset field。正在统一修复提案/表单与 v2 读时迁移的生成路径，查询改为严格通过字段表达式解析连接键；已有原生导入字段和出现状态不改写。下一步补充远山咖啡 98 订单四表双向邻域验收及最终全量。当前数字仍为评审方复跑 API 537 passed / 32 skipped、Web 132 passed，尚非本轮最终结果。

M5 评审专项首轮（实际 SQLite 源表 + 隔离 PostgreSQL 持久库）：75 passed / 1 failed（101.93s）。四表 3 连接两种提案写法接受、发布、MCP 双向邻域以及远山咖啡 98 张订单均通过；唯一失败为旧迁移测试固定只有 3 个属性字段，现调整为明确验证补充的主键与外键字段集合。迁移只补生成结构所需字段，避免新增无用属性列副本；原始快照、旧哈希与原生导入保持。Web 28 files / 132 passed、lint、tsc -b 已通过，ruff 通过。新增同名字段保留/确定性别名及缺失数据集/物理字段具体诊断测试已通过。下一步最终 API 全量。

数量断言修正后，v3 冻结合同/旧哈希/迁移纯函数与幂等/原生视图专项 **66 passed**（14.15s）。最终全量已启动，显式提供隔离 PostgreSQL 管理入口；业务库 ontofoundry_ossie 未访问，未启动服务。新增字段只在平台连接写入与 v2 迁移生成结构时补充，导入原文不自动修复。测试还补充商品→明细反向邻域与 98 订单未截断断言，等待最终全量结果。

### M5 最终完成 — 2026-10-10

根因确认：平台写入 data_join 时将物理列直接写为 dataset_relationship 的字段引用，却未补充未映射为属性的外键字段；连接查询此前还允许缺失字段回落到同名物理列，存在同名逻辑字段误解风险。

- 提案 link data_join 与映射表单共用原生写入器，按物理列补充缺失字段（name=列名、ANSI_SQL 单列引用），连接保存其逻辑字段名。已有字段和元数据不改写；同名字段表达式不同则复用正确的既有别名或创建确定性的 `__join` 别名。重复保存保持身份与结构不变。
- v2→v3 纯读迁移只在旧数据生成的语义文档中补充主键/连接键字段并解析名称冲突；旧原始快照与旧哈希不变，原生 Ossie 导入不调用补充逻辑，已经发布的 v3 原文不静默改写。
- join_view 严格把 relationship 的字段引用解析为物理列，复合键按全部列执行等值连接。缺失数据集字段报告 `数据集字段不存在：dataset.field`，缺失物理列报告 `关系物理字段不存在：table.column`，REST/MCP 邻域共用诊断。

四表三连接验收使用实际 SQLite 销售源表及 SQLite/自动创建并清理的 PostgreSQL 持久库，两种提案形态（native update、智能体二元端点 create）均完整接受→预览无错误→发布→MCP 查询/邻域→导出校验→映射编辑再发布。外键 customer_id/order_id/product_id 明确不属于属性映射；新关系引用的每个键都有 dataset field。订单 1→远山咖啡客户、远山咖啡→98 个订单（98 条边，无警告、不截断）、订单→明细、明细→订单及商品、商品→明细均通过。订单 **780 张 / 269516 元**保持，映射修改列后查询采用新列。新增 6 个参数化回归变体，并扩展既有四表验收的全部方向和 98 订单断言。

最终验证：

- API 全量：`uv run --python 3.13 pytest -q`，提供隔离 PostgreSQL 测试入口，**574 passed / 1 skipped / 2 warnings**，446.31s。唯一跳过为未配置真实 MySQL 集成环境；警告为现有 Starlette/httpx/anyio 弃用提示。
- `ruff check src tests`：通过。
- Web：`npx vitest run` **28 files / 132 passed**（8.24s）；`npm run lint`、`npx tsc -b` 均通过。
- A/B 原生往返仍 **0 差异**（原生数组顺序、字段出现状态、表达式文本保留），覆盖矩阵检查与 `git diff --check` 通过。
- B 覆盖维持 29 个 EntityType：10 可查、11 复杂只读（2 多根、9 referent）、8 无映射；复杂映射/跨连接执行维持 P3 边界，指标查询属于 P4。

无本轮未决阻断。业务库 ontofoundry_ossie / API 8010 未访问，未调用真实 DataAgent；结果来自隔离持久库与实际 SQL 表的确定性回放。仅本 worktree 修改；未提交、未启动/重启服务、未 make build、未访问演示目录。已有问数提示词工作区修改保留。

### M6 真实 owner 方向修复 — 2026-10-10（进行中）

已复制 bottomup-raw-result.json / bottomup-replay.json 至 real_runs，真实 11 条提案的 data_join.source_column 属于 owner，反向兼容端点曾导致写入错误表。上一轮手工测试按旧端点构造连接，未覆盖该写法。现统一 v3 输入 DTO 为 owner_columns/role_columns，旧 source/target 拼写同样按 owner/附加角色解释；SQL join_view 仍使用内部端点方向，v2 原始快照读迁移保持旧版本端点合同。正在同步提案、表单投影、前端转换和提示词，增加已知表结构的写入校验及真实原始批次回放。上轮全量 574 passed / 1 skipped、Web 132，不作为本轮最终数字。

M6 初步专项：真实 bottom-up 11 条原始提案（旧 owner 拼写与显式 owner_columns 两种输入）、手写 forward/reverse、已知资产/连接元数据拒绝、接受/草稿保存/元素保存原子性 **12 passed / 2 skipped**（26.28s；该轮未启用隔离 PostgreSQL）。真实 after 快照通过回滚 7 个 before 并移除本批 4 条 mapping create 的生成结构，还原 pinned_draft，其 sha256 **完全等于原始 source_draft_sha256 和 base_version_sha256**，不修改运行头或 expected_target_hash。原材料全文未提供，证据复用既有回放方法重建原 quote 行，并进行真实 lookup/quote 校验。另修复派生 data_join 污染原生提案 expected hash 导致已有连接 update 误报 stale，原生 canonical 算法不变。

Web 全量 **28 files / 135 passed**（12.48s），新增 3 个 owner/role 到二元端点 UI 的往返与复合键测试；lint、tsc -b 通过，ruff 通过。合同说明已加入覆盖矩阵生成源，生成校验保持通过。隔离 PostgreSQL 扩展专项进行中；下一步最终 API 全量与 M6 完成记录。

M6 隔离 PostgreSQL 扩展专项 **53 passed**（216.95s，无跳过）：真实原始 11 条提案（保留 header、before、expected_target_hash）与显式 owner 新写法均接受/发布/导出合法，订单→客户、远山咖啡→98 个订单、订单↔明细、明细↔商品无警告；手写 forward/reverse 以及已有提案/元素保存回归通过，A/B 0 差异。补充旧端点反排列的两个真实批次负例，在接受前返回 JOIN_COLUMN_NOT_FOUND 并保持 11 项 pending 与 revision/draft 不变。最终 API 全量已启动；无须修改业务库或运行 API 8010。

消费者复核：本 worktree 原 P3 范围内的 prepare_demo.py data 阶段也改为按 owner/附加角色选表并发送明确 owner_columns/role_columns，去掉旧端点翻转；未运行脚本、未调用服务、未触及外部演示目录。脚本 AST 语法检查通过。两个真实批次错误方向负例 **2 passed**（3.02s）。

M6 最终全量首轮：**589 passed / 1 failed / 1 skipped**（774.56s）。唯一失败为检入的提案 JSON Schema 尚未同步 owner_columns/role_columns，新运行模型与静态 schema 不一致；真实回放、字段拒绝、所有业务与 PostgreSQL 用例均通过。已使用官方 export_schema 工具重新生成瞬时提案合同 schema（未更改冻结 v3 领域 schema/canonical），正在确认 schema 一致性并补跑最后一轮全量。尚不标记 M6 完成。

Schema 同步后的单项一致性测试 **1 passed**（0.16s），`ruff check src tests` 再次通过。最终全量正在重跑，输出保存在 worktree 内忽略目录 `apps/api/.pytest_cache/m6-final.log`，便于中断后恢复结果；未改冻结 v3 schema 或原生哈希算法。

### M6 最终完成 — 2026-10-10

根因确认：真实智能体把旧 data_join.source_column 按 Ossie owner（隐含首角色）填写，P3 写入器却按旧 source_type_id 的兼容端点解释；reverse 关系把 orders.customer_id 错配到了 customers，把 order_items.order_id 错配到了 orders。M5 的手工连接按旧端点构造，因此未覆盖真实写法。

- 明确 v3 平台写入合同为 `owner_columns` / `role_columns`，分别对应 owner_ref / roles[0] 的物理表列，有序非空等长数组支持复合键。旧 source_column/target_column 拼写继续兼容，统一解释为 owner/附加角色。建模提示词、提案 JSON Schema、表单投影、前端输入/输出和本 worktree 演示准备脚本同步。SQL 查询仍使用内部端点视图，reverse 时只在明确的转换边界交换列。历史 v1/v2 已存快照仍按旧端点合同纯读迁移，不重解释、不改旧哈希。
- 接受、草稿保存、元素保存统一调用连接列校验：优先已知数据资产快照，否则读取可用连接元数据。物理列缺失返回 422 `JOIN_COLUMN_NOT_FOUND`，包含 owner/role 侧、表与具体缺失列，草稿 revision、决定记录与 pending 状态不推进。未知/离线表结构不伪造存在性；查询仍保留明确的缺失字段诊断。
- 保留 M5 的补充 dataset field 路径，只有平台连接写入和旧快照迁移生成结构时补缺失物理键；已有字段、导入原文及原生表达式不改写。瞬时连接 DTO 不再注入原生 proposal_snapshot 的 link_type 目标，避免已有原生提案被派生 data_join 错误标记 stale；冻结 v3 领域模型与 canonical 不变。

真实回放文件逐字节复制到 `apps/api/tests/fixtures/real_runs/`，原始结果 32942 bytes、回放快照 137477 bytes，与用户提供文件完全相同。还原 pinned draft 的 SHA256 与原始运行头相同，不修改 header、before、expected_target_hash；旧拼写与显式角色拼写解析后的 after、fingerprint、依赖及目标哈希等价。使用原始 11 条提案完整解析→生成批次→全部接受→预览无错误→发布→导出合法，覆盖 SQLite 和隔离 PostgreSQL 持久库、实际 SQLite 四表源数据。

双向邻域验收：订单 1→远山咖啡；远山咖啡→**98 张订单 / 98 条边**；订单↔明细；明细↔商品全部通过，均无 warnings、不截断。生成连接按物理列解析为 customers.id = orders.customer_id、orders.id = order_items.order_id、order_items.product_id = products.id。保留 forward/reverse 手写两种输入形态；两个真实反向错列负例在接受前拒绝，11 项仍 pending、revision/草稿不变。新增 API **16 个参数化回归变体**，前端新增 **3 个转换测试**。

最终验证：

- API 全量：`uv run --python 3.13 pytest -q`，启用自动创建/清理的隔离 PostgreSQL 测试库，**590 passed / 1 skipped / 2 warnings**，521.68s（8m41s），退出码 0。唯一跳过为未配置真实 MySQL 集成环境；警告为已有依赖弃用提示。
- `ruff check src tests`：通过；提案生成 schema 与运行模型一致性测试通过。
- Web：`npx vitest run` **28 files / 135 passed**（12.48s），`npm run lint`、`npx tsc -b` 均通过。
- A/B 原生往返仍 **0 差异**；覆盖矩阵生成检查与 `git diff --check` 通过。

无本轮未决阻断。未在业务 API 8010 或 ontofoundry_ossie 上重放，未调用真实 DataAgent；原始运行证据的材料全文未提供，证据回放沿用既有方法还原 quote 行并执行实际 lookup/quote 校验。已发布的错误 v3 快照不静默改写，应在部署新代码后重新接受正确输入或重新保存连接。复杂映射、跨连接执行维持 P3 只读边界。仅本 worktree 修改；未提交、未启动/重启服务、未 make build，未触及外部演示目录；已有问数提示词工作区修改保留。
