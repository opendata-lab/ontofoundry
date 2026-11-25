# 建模对话中的 Ossie 导入：实施计划

日期 2026-11-25。依据 `docs/design/2026-11-24-ossie-in-conversation-import.md`（§3、§4、§8、§9、§10）。前置：PR #106、#107、#109 合入 main；PR #105（`expand_tables.py` 的 `snapshot_date_column`）合入 main。

分 4 个 PR，按顺序提交，每个 PR 自带测试。文档、示例和测试只用虚构名字（如 `sales.order_df`、`sales.customer_df`）。

## PR 1：导入器接到登记表（`apps/api/src/ontofoundry_api/adapters/ossie/`）

- `ImportContext` 增加两项：`table_scope`（本会话关联的登记表，`t#` → 连接、schema、表名、主键、列）和 `snapshots`（`t#` → 快照列）。“导入文件”路径不传 `table_scope`，行为不变（§10 #6）。
- `mappings.import_datasets`：扩展文件没有连接名、`source` 为 `schema.table` 时，在 `table_scope` 中找同 schema 同表名的表。恰好一张：采用其连接，数据集记下 `t#`；不在会话范围但工作空间里恰好一张：报告“请把表加入会话”；多张：报告歧义；没有：报告缺表（§4.2）。登记列覆盖材料列时，材料独有的列列入报告（§8 #1）。
- 快照：数据集命中的 `t#` 在 `snapshots` 中时设 `snapshot_date_column`；列不在登记列或类型不是日期、日期时间、字符串、整数时报告并不设（§8 #5）。
- 物理连接：目标数据集命中登记表且设了快照列时，用“登记主键去掉快照列”作为单独的证明输入交给 `bind_relationship`，不写入 `DatasetInfo.keys`，不恢复属性唯一性（§8 #3）。生成前逐项核对两端绑定、键序、基数，核心校验不过就报告。
- 不在范围内的数据集及其依赖闭包（映射、关系对接、指标）不进结果，逐项报告（§8 #1）。
- 测试：唯一命中、会话外、歧义、缺表；快照列合法与非法；`(customer_no, ds)` 去掉 `ds` 证明成功；`(tenant_id, customer_no, ds)` 只连 `customer_no` 不证明；列序接反不证明；依赖闭包被剔除；“导入文件”路径不自动接连接。

## PR 2：平台转换接口（`apps/api/src/ontofoundry_api/`）

- 新路由，按运行凭据访问，地址写进本轮 `platform_check_file`（新增 `ossie_url` 字段）。校验：签名凭据、空间与会话匹配、运行仍在进行、用户仍有编辑权限（§8 #6）。
- 请求：`material_id`、`sha256`、`mode`（`inspect` 或 `convert`）、`snapshots`（`t#=列`）。平台从材料存储读原件，不接收原文；只支持单个 JSON 材料（§8 #4）。
- `inspect`：返回概念清单、命中的 `t#`、各表主键和候选快照列（日期、日期时间、字符串、整数类型的列）、预计提案条数及 500 条剩余容量（§8 #8、§10 #1）。
- `convert`：调用导入器 → 对照本轮固定草稿生成提案 `items`（草稿已有元素为 `update`，用真实 UUID；新元素为 `create`，用稳定 `client_ref`，§10 #7）→ 跑提交端同源检查（候选图校验、`_no_required_rules`、表范围检查），不能通过的项连同依赖剔除并写入报告（§10 #4）→ 证据定位到已登记材料的原始行（§8 #7）→ 按实体分组返回。
- 返回体：分组后的 `items`、报告摘要（≤ 8 KB：摘要、待补全、阻断、缺表、歧义、键差异、容量）和报告明细。错误码区分 `NOT_OSSIE`、`UNSUPPORTED_FORMAT`、平台错误（§10 #7）。
- 不建会话、不建提案、不改草稿；不写审计以外的记录。
- 测试：凭据过期、运行已结束、权限撤回均拒绝；`inspect` 不改任何状态；`convert` 的输出能被现有提交入口原样接受；只要求非空的规则被剔除并报告；草稿已有对象输出为 `update`。

## PR 3：技能脚本与文字（`integrations/dataagent/`）

- 新脚本 `shared/scripts/import_ossie.py`：
  - `--inspect [--material <id>]`：调用接口，报告写 `modeling/checks/ossie-inspect.md`，不写片段，计划模式可运行。
  - `--snapshot t3=ds,… [--material <id>] [--force]`：在计划获批后（沿用 `plan_not_approved()`）调用 `convert`。按实体写 `modeling/parts/00-ossie-entity-<对象>.json`，数据集、指标、关系、规则各自成组写 `00-ossie-<类别>-<归属>.json`；文件名含归属，避免同名冲突（§10 #5）。报告摘要写 `modeling/checks/ossie-report.md`，明细写 `modeling/tmp/ossie-report-detail.json`。
  - 清单 `modeling/tmp/ossie-manifest.json` 记录每个文件的哈希。重跑时：未改过的文件直接重写；改过或删除的文件不覆盖，列入输出；`--force` 先按旧清单删除全部旧文件再写（§9、§10 #5）。
  - 退出码：0 成功；`NOT_OSSIE` 提示回到普通阅读；其他错误提示停下向用户说明（§10 #7）。
- `init_workflow.py`：本轮材料中有 Ossie JSON（顶层含 `ontology`）时打印 `import_ossie.py --inspect` 命令和一句指引；续做摘要对 `00-ossie-*` 只打印文件数和改过的文件（§10 #3、#8）。
- `expand_tables.py`：读取 `00-ossie-*` 已占用的对象、数据集（连接、schema、表）和 `client_ref`，跳过已覆盖的；指向导入对象的关系引用其 `client_ref`（§10 #5）。
- 新参考页 `skills/ontology-discovery/references/reading-ossie-import.md`：报告各段的含义，智能体接下来做什么（补待补全、润色显示名和描述；改英文标识或删除元素要同步改引用方）。`import-completion.md` 不改（§10 #8）。
- 守住离线字节预算（`offline_budget.py`），`plan.md`、`extract.md` 不增字节。
- 测试：脚本对假接口的 `inspect`、`convert`、重跑保护、`--force`、计划未批准时拒绝写片段；`init_workflow.py` 的识别与汇总；`expand_tables.py` 跳过已占用对象和数据集；离线预算。

## PR 4：本体标识与表主键差异报告（`docs/TODO.md` 第 7 项）

- `convert` 报告列出对象标识映射到的列与命中登记表主键（去掉快照列）的差异，只报告，不改标识。
- 测试：组件式“标识只有名称、主键含环境和区域”的虚构例子出现在报告中。

## 端到端验证

- 本地 Doris 模拟库（`~/.local/odw-doris/arch-gov-sim/`，164 张表）+ 内网同一份 Ossie 材料，在本机 DataAgent（:8902）跑一轮建模；内网真名只留在本机，不进仓库。
- 记录：回合数、总时长、提案条数、能证明的物理连接数（预计 5/14）、报告中的待补全项；与设计 §1 的内网基线对比。
- 计划模式和直接建模各跑一次；中途取消后续做一次，确认不重读材料、润色不被覆盖。
- 部署后按 `integrations/dataagent/README.md` 同步技能，用局域网 IP 验证一次。
