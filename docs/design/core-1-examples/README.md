# core-1 原生格式示例

配合[设计文档](../2026-10-14-core-model-and-format-adapters.md) §3、§4.6 阅读。修订：2026-10-16，第 15 轮。
每份文件都是单文件原生格式，`draft` 才是完整包中 draft.json 的内容：

```json
{
  "format": "ontofoundry",
  "schema_version": "core-1",
  "exported_at": "…",
  "draft": {}
}
```

固定集合：object_types、properties、link_types、rules、metrics、datasets、mappings、material_objects、material_links。
元素 id 为 UUID；sources.id 是映射内的局部来源名（主来源 main），不是元素 UUID。
示例证据引用的材料未附带；完整包才打包原材料。单文件跨环境导入时缺失的材料证据会 dropped，人工证据保留。

这些是**设计样例**。本轮只做 JSON 解析、引用、继承、路径方向及绑定结构的静态核查；目前没有 core-1 可执行官方 schema 或适配器，不能声称已通过核心、Ossie 校验或往返测试。下列是实施时的预期。

## 场景与往返预期

“原生导入成功”均指结构可保存；不承诺缺失材料证据完整。Ossie 导出成功允许报告局部损失，交付文件仍须通过目标官方校验。

| 文件 | 原生导入 | Ossie 导出 | Ossie 再导入预期及主要损失 |
|---|---|---|---|
| [01-basic-sales](01-basic-sales.json) | 成功 | 成功；下单客户数、依赖它的客单价 dropped | 单表过滤和同数据集完成率按列回读；跨客户过滤保留数据集 expression；指标均挂数据集，映射键计数回读为列 count_distinct；规则名称、实例证据按报告损失 |
| [02-many-to-many](02-many-to-many.json) | 成功 | 成功；复合键基对象 count 不可表达则 dropped | 普通关系、映射表及数据集列聚合回读；不把带成绩选课对象合并为纯配对 |
| [03-n-ary-reified](03-n-ary-reified.json) | 成功 | 成功；ManyToOne 自动重化的中间对象 | 不还原多元关系；前三角色决定最后数量，编号属性作为 direct 源端，与参与方完整业务标识逐项对应 |
| [04-composite-key](04-composite-key.json) | 成功 | 成功；复合键 count dropped | 数量×单价计算列和单表 sum 回读；跨数据集条件保留 expression；键顺序显式对齐 |
| [05-self-and-parallel-links](05-self-and-parallel-links.json) | 成功 | 全量导出 **error**：新增买卖双角色 expression 无法保留角色时不交付；结构化定向导出时歧义指标 dropped | 买卖绑定用业务关系＋列组配对，不交换；工位反向1:1指标可导出，LEFT JOIN 风险逐指标报告；该全量文件不执行回读；单独验收可表达结构化项时仍不恢复本体路径 |
| [06-inheritance](06-inheritance.json) | 成功 | 成功；VIP 的语义派生条件可按 RT-67 转换，成员扩展绑定仍按 RT-57 报损失，依赖它的个人数按 RT-61 报 dropped | 父表覆盖、虚拟父、独立对象三种建法；全部 Dataset 一一输出；虚拟父查询并集及继承绑定范围按 RT-65 说明，不承诺无损恢复 |
| [07-instances-and-evidence](07-instances-and-evidence.json) | 成功，缺标识事实保留 | 成功；文档实例、证据不导出 | 布尔属性保留，不还原 Ossie 一元关系；不恢复材料实例 |
| [08-rules](08-rules.json) | 成功 | 成功；属性与对象、关系约束按规则导出，客户等级只留计算绑定 | 客户等级同行计算列回读；其他 Rule 保留表达式，名称、描述不保留 |
| [09-empty](09-empty.json) | 成功 | **error**，不交付 Ossie 文件 | 不执行再导入；此例是负向验收 |
| [10-partial](10-partial.json) | 成功 | 成功；缺映射部分按报告保留定义、丢绑定 | 城市、关系语义仍存在，查询未绑定路径有明确状态，不静默缺项 |
| [11-multi-source-and-unique-link](11-multi-source-and-unique-link.json) | 成功 | 成功；账户可用金额因缺主来源锚点按 RT-61 dropped；业务外键子节点因编码不是客户业务标识可能 dropped，物理连接保留 | 主身份＋附表属性 children＋唯一键星形连接按 RT-52 回读；客户 unique 编码不是物理键；无法唯一定位业务边则 RT-53，不猜 |
| [12-snapshot-and-trends](12-snapshot-and-trends.json) | 成功 | 成功；快照和指标时间字段按 RT-60 报损失 | 指标与属性保留，Dataset 快照声明、simple、expression 的时间字段不能自动恢复，历史键及连接限制按 RT-64 说明 |
| [13-dataset-metrics](13-dataset-metrics.json) | 成功，无对象绑定 | **error**；没有本体元素，不满足 ontology 至少一项，不为导出伪造对象 | 本例不执行完整 Ossie 再导入；列聚合、条件、比率和 expression 的定向适配器验收应另配已有真实业务对象的测试夹具，不反查对象 |

12 的原生导入预期为成功；Ossie 导出保留对象与指标并按 RT-60 报告快照时间声明损失，结构化声明不能自动回读。对象指标的导出限制和数据集裸 count 无来源锚点使用 RT-61；expression 也须检查角色、方向和统计范围，无法保留时本项 error。可确定的旧字段名可在同一 Dataset 中生成逻辑字段别名；本体路径或规范化数据集引用按 RT-47 只转换已解析标识符，核心原文、算法和字面量不变，无法合法输出引用时报 error，不能复制 Dataset 或丢表达式。

01 同时新增 median 和复杂表达式；expression 的核心原文与算法保留，导出仅按 RT-47 转换已解析引用。

所有 Ossie 回读指标显式挂数据集，不恢复对象粒度或属性路径（RT-50）。多数据集表达式若未声明统计来源，原文留在待补全条目，选择数据集前阻断该指标提案。

全部 Dataset 按 RT-62 一一对应；Ossie 未同构承载的来源方言和物理元数据按 RT-66 报告，不能由 ANSI_SQL 推断引擎。

## 共同写法

- ObjectType.extends 为单个 UUID 或 null。上下文统一写入 description，没有 instructions 字段。title_property_id 是属性 id，缺值回退标识。
- Dataset 扁平登记 id、name、dialect、schema_name、table_name、description 和 snapshot_date_column，可选 columns 来自元数据快照；样例方言 mysql 和来源名均为虚构，不是从 ANSI_SQL 推断。对象、关系表和数据集指标统一引用 dataset_id，表位置只登记一次。
- DataMapping 的 sources 平铺为 `{id, dataset_id, key_columns}`，主来源 main 决定对象集合，普通附表补充属性；shared_parent 沿用父来源并可增加成员扩展表，membership_source_id 表示扩展表有记录才属于子对象。列绑定写 `{kind: column, source_id, column}`，计算列写 `{kind: expression, expression}`。
- key_columns 为建模者声明的逻辑唯一键，不要求数据库已建 PRIMARY KEY。不做运行时唯一性、基数验证；缺键保留未完成状态。快照选定本数据集日期后可按实体键关联，不能把时点唯一性冒充历史全表唯一，也不自动加跨数据集日期相等。
- DataJoin.kind 区分 direct（两端属性 id）与 mapping_table（dataset_id、列组及两端键引用）；映射表可直接引用某一端已有数据集，不重复登记或填写表名。
- time_field 只属于 simple 和 expression；ratio 不存该字段，分别使用分子、分母定义的时间字段。
- simple、expression 显式存 base_type_id 或 base_dataset_id，恰好一项非空；ratio 不存 base，读取时从同统计对象的 simple 分量推导。simple、ratio 不存 value_kind，读取时推导；expression 仍声明类型。数据集 measure 和 filters.column 使用 `{dataset_id, column}`，列清单为空则待补全；不反查对象。
- 对象指标 Path.links 的每跳为 `{link_type_id, direction}`；正向 N:1、1:1、反向1:1 可用；N:N 或反向 N:1 不作首版指标路径。按声明基数提示风险，不承诺实际数据不会增行。
- 平台交付结构化指标或表达式语义；绑定就绪的结构化指标可以附基础 SQL 参考。agent 负责查询分组、时间选择和类型调整，保留固定口径。MCP 四工具不接受 version_id，版本由服务端决定。

## 场景说明

### 01：基本销售与完成率

订单 → 客户是多对一；订单表同时作为该关系的映射表。客户 customer_no 绑定 main.customer_id，属性名和列名可不同。订单 order_no 是标题属性，业务说明统一在 description 中。

订单金额用 sum，订单数用 count（measure=null），已完成订单数固定过滤 status。华东订单金额经过客户关系；下单客户数的 base 仍是订单，Ossie 表达式只引用客户时粒度不能表达，报告 dropped，不能擅改为所有客户数。

新增完成率：分子已完成订单数，分母全部订单数。分子的“已完成”不能移到公共 WHERE：一单完成、一单取消应为 0.5。客单价与完成率都按总计的分子、分母重算，不相加各组比率。

一季度有效金额使用 `ge 2026-01-01T00:00:00` 与 `lt 2026-04-01T00:00:00`，再加 not_in。3 月 31 日 23:59:59.500 属于季度，4 月 1 日零点不属于。这是事件指标的半开区间，不声明快照时间语义；D2 的快照例子见 12。

### 02、03：中间对象

纯学生、课程配对用多对多 mapping_table；带成绩的选课记录建对象，学生、课程编号作为复合标识。实际若有重修，通常还须学期、尝试次数，不能把本例键当成通用答案。

03 是供货 ManyToOne 自动重化的例子：角色依次为供应商、零件、项目、数量，前三角色编号组成标识，最后数量不参与。生成编号属性直接作为角色关系 direct 源端，目标为参与对象完整标识，列绑定已明确证明保存相同业务编号，无须另加一致性 Rule；供货日期是额外业务属性，不参与该元组标识。数量自身>0和祖先>=0约束按变量绑定实例化为两条属性 Rule。若无基数则数量也须入键；同元组是一个关系链接，需要重复业务事件时另建带事件编号的对象。

缺决定角色标识时不生成该角色编号，整组键待补全；ManyToOne 最后角色无标识不阻止前面完整键。外键只对应物理键时编号绑定待补全，角色原映射保留。其他元组约束先确认现有 Rule 可表达，否则整项原文待补全。仓库运往的键是起点加终点仓库编码，排班的键是医生编号加日期。

### 04：复合键与计算列

明细 key_columns 为 order_id、line_no；指向明细的映射表 target_columns 按同样顺序。标识属性各自 unique=false，组合唯一；关系不参与标识。

新增 line_amount 属性绑定 `main.qty * main.unit_price`，sum 此属性得到明细销售额。平台只查同行列引用，不执行、不调整物理类型；无需先建数据库金额视图。

### 05：自关联、平行关系与反向1:1

员工的 manager 指向员工；买方和卖方各有关系 id，指标路径能区分；基础 SQL 参考按路径前缀和方向分配别名。

员工 → 工位为1:1；新增“未使用工位数”以工位为 base，reverse 走员工使用工位关系，并检查员工标识 is_null。换成员工为 base 会丢掉空工位，不等价。结构化定向导出时保留该指标并说明 LEFT JOIN 依赖，自关联回原 dataset、买卖两条路径等无法表达角色的结构化指标仍 dropped。新增同条件 expression 反例：买方华东、卖方华南、金额100，角色保留结果100，若两个地区都落 companies.region 则结果0；无法保留时本项 error，全量文件要求该指标时不交付。

### 06：继承的三种建法

建法①：当事人绑定 parties 数据集，包含所有个人、机构和 VIP 当事人实例。个人和机构的 shared_parent 映射各加一个扩展数据集，membership_source_id 指向 extension；只有扩展表里有记录的父实例才属于子类。身份证号、统一社会信用代码来自扩展表，姓名、电话、当事人编号和联络关系都从父表取。VIP 当事人在 ObjectType.derived_by 中用 simple 分支引用父属性 level 的 id，条件为 eq VIP，特有说明来自父来源；列绑定与成员条件分别保存，物理列改名不影响条件。

影响例子：VIP 从只含 P-001 改为还含 P-002，实例数从1变2，所有以 VIP 为统计对象的指标及依赖它们的 ratio 都须在提案中列出。新增或删除薪酬关系绑定也可能影响依赖 EXISTS 的员工成员范围；仅搬迁到相同逻辑范围的父表则说明换绑，不擅自声称业务口径已变。

具体数据例子：父表有 P-001 张三（VIP）、P-002 某机构和 P-003 待分类当事人；个人扩展表只有 P-001，机构扩展表只有 P-002。查当事人得到三人各一次，查个人只得到 P-001，查 VIP 也只得到 P-001。扩展表里不能另有父表没有的 P-004；这应先补全父表覆盖，或改用建法②或③。父查询不需要合并扩展表来补实例。

建法②：资产是无 DataMapping 的虚拟父对象，设备和车辆各有自己的数据集，分别绑定继承的资产名称、负责人编号及负责人关系；关系保持同一个 id，数据绑定写入具体子对象的 inherited_link_bindings。设备有 D-001、车辆有 V-001 时，查询资产列出这两个具体类型实例的并集；MCP 明示“无自己的表，实例来自以下子对象”。一个实例只属于一个具体子对象，虚拟父不直接存实例。

建法③：供应商与渠道商是两个独立对象，即使都有编号和名称也不建立 extends，查询范围各自独立。示例还保留合同与张三的材料事实，合同关系可指向兼容的个人子类型，继承的标题属性用于显示姓名。

### 07、08：证据与规则

07 展示多证据和缺标识事实；事实不存 name，读取按标题、完整标识、可见 quote 开头、UUID 回退；0 和 false 有值，搜索覆盖只读显示文本和属性。单文件中没有原材料，不能验证 quote 的真实性或保证跨环境证据无损。

08 规则称为“受限 SQL 表达式 + 本体路径”。客户等级仅保留属性业务说明和同行 CASE 计算绑定，删除重复的 derivation Rule；不要求每个计算属性再存一份公式。其他规则说明业务约束，不自动执行；改名按 id 依赖更新表达式。

08 还展示金额值类型约束实例化：订单金额>=0，退款使用正金额，保留祖先退款金额>=0及自身>0。原有订单金额>0规则独立保留，不被复制规则覆盖；description 注明值类型来源，不表示以后自动联动。

### 09—11：空模型、半成品和多来源

09 原生合法但不能导出 Ossie。10 没有城市映射和关系 JOIN，查询相应路径应返回 unbound 状态；未填 Dataset.schema_name 时由服务端来源配置解析默认 database/schema；MCP 只返回方言和 database，不返回 connection_alias。

11 主表 accounts 与附表 account_amounts 分别声明 account_id、acct_id 匹配，不依赖数据库真实 PK。available_amount 明确来自附表 amounts；只在附表出现的账户不会自动生成实例。account.customer_code 直接关联 customer.code（unique），客户物理主键仍为 customer_id。Ossie unique_keys 与物理连接可表达此结构，但业务子节点若不能直接表达完整目标身份，必须报告损失；不能把客户编码猜成客户编号。

11 的金额指标虽是空属性路径，实际绑定仍来自附表，不能据此认定已有 accounts 主来源锚点。本例直接替换只能得到 SUM(account_amounts.available_amount)，按 RT-61 dropped，不交付这个缺少主范围的聚合。反例：主表仅 A1、A2，附表为 (A1,100)、(A3,900)，A3 不能创造账户；正确金额是100，直接聚合附表的1000错误。此项验收同时检查报告定位到该指标，不用描述文字代替范围限定。

换绑例子：普通附表不改变账户实例数，但把可用金额从100换绑到200仍可能改变求和指标，须列出潜在影响；不能只因为改的是普通附表就认定口径不变。

### 12：数据集快照与趋势

[12-snapshot-and-trends.json](12-snapshot-and-trends.json)给出组件与仓库对象。组件数量、组件状态和仓库三个 Dataset 各自声明 snapshot_date_column，映射只引用 dataset id 和选定日期后的实体键；历史物理行通常以实体编号和日期共同唯一，但不能据此强制不同数据集的日期相等。数量指标的时间字段是快照日期；各数据集已经声明快照，按周期取最后一个有数据的日期，指标不另存快照开关。覆盖率是属性，1m 和 3m 也是分别解释窗口的属性，没有给它们建求和指标。

以下均为虚构数据，供后续实现验收。它们是物理来源行，不是 material_objects；本轮没有访问业务数据库。

| 组件编号 | 快照日期 | 数量 |
|---|---|---|
| A | 2026-11-30 | 8 |
| B | 2026-11-30 | 6 |
| A | 2026-12-29 | 9 |
| B | 2026-12-29 | 7 |
| A | 2026-12-31 | 10 |

| 问题 | agent 应采用的语义及结果 |
|---|---|
| 11 月、12 月的组件数量趋势 | 数量数据集 11 月统一取 11-30，结果 14；12 月统一取 12-31，结果 10。不能对整个月求和，也不能给 B 另取 12-29 得到 17 |
| 当前组件数量，假设最新数据就是这些行 | 数量数据集的所有行统一使用 12-31，结果 10；回答说明使用的日期及缺失实例没有延续 |
| 明确查询 12-29 | 只用 12-29，结果 16，不改取 12-31 |
| 12 月按组件分组的期末数量 | 日期仍统一为 12-31，A 为 10，B 当日无数据，不能在 B 分组里退回 12-29 |
| 仓库来源最后有数据的是 12-30 | 仓库独立当前值使用 12-30；不能因组件用 12-31 就声称仓库也有 12-31 数据 |

再给状态数据集两行 `A,12-29,维修`、`A,12-30,正常`，其当前日期为 12-30；数量数据集仍取 12-31，仓库若最后更新到 12-30 也独立取 12-30。两者更新日期不齐如何关联由 agent 按问题处理并说明，核心不要求同日，不规定退回共同日期，也不由数量主来源决定状态附表的日期。

给 agent 的提示是不要把多天历史记录仅按实体编号连接而交叉配对，应理解各数据集时点后再安排查询；同日连接只是可选执行方式。若 1 月整月没有数据，如何展示空周期也由 agent 处理，核心不规定补零、延续旧值或省略该月。共享父表的成员条件也不改变数据集日期：若 12-31 只有普通客户、VIP 最后出现在 12-29，当前 VIP 查询仍使用该数据集的 12-31，不能为这个子类单独取 12-29。

范围例子：把组件来源从全周期行改为声明快照后取末日，会改变数量结果，相关对象指标、数据集指标及其 ratio 须列入影响；不能归为仅 SQL 参考变化。

### 01 中的补充指标

订单金额中位数使用 simple + median，SQL 方言由 agent 调整。拼接订单号和状态的去重计数使用 expression，保留分隔符与 NULL 行为；含 OR、ELSE 0 的有效金额也使用 expression。导入遇到这些形式不再丢指标。

### 13：汇总表上的数据集指标

“代码行日统计”直接登记 repo、stat_date、commit_count 三列，不建业务对象。每行是一个仓库一天的统计，提交数为 SUM(commit_count)，COUNT(*) 只是统计行数。此表记录事件汇总，提交数按整个范围求和，不声明存量快照。

| 仓库 | 日期 | commit_count |
|---|---|---|
| core | 2026-10-01 | 3 |
| core | 2026-10-02 | 5 |
| web | 2026-10-02 | 2 |

预期提交数为 10、核心仓库提交数为 8、核心仓库提交占比为 0.8、有提交仓库数为 2、统计行数为 3。有提交仓库数 10-01 为 1、10-02 为 2，全周期按 repo 去重为 2，不能相加为 3。simple 和 expression 的 time_field 指向 stat_date；ratio 不存 time_field，使用两个分量的时间字段。复杂表达式保持 OR 和 ELSE 0。没有本体引用时指标弹窗省略关联本体项，对象弹窗始终没有指标入口。

12 另外加入显式挂 component_daily 的“数量表期末合计”，使用列度量，时间字段是该数据集的快照日期列；与对象指标相同地按数据集末日取数，不能因为该表有组件绑定而自动改挂组件。

本例直接在日汇总数据集上建指标。汇总表登记成数据集，直接在其上建数据集指标；查询时用不用汇总表由 agent 决定，并保留指标口径和可用粒度。

提案区分语义和范围保持的物理换绑，与可能改变属性、关系含义或成员、实例、时间范围的修改。派生条件、成员扩展来源、主来源和快照声明等后者，须沿引用、继承、成员派生及 ratio 分量列出受影响指标和原因。不能确认等价的换绑列潜在影响，不扫描数据库证明等价。

## 最低验收分支

| 改坏或边界输入 | 预期 |
|---|---|
| 多个父 UUID、继承环 | 原生 schema 拒绝多父形状；Ossie 多父仅留文件首个并 RT-34，额外父类和受影响引用原文保留，派生条件或关系只是需审阅的非等价业务建议，不自动生成关系；继承环拒绝 |
| 父对象有绑定，子对象却 independent 独立存储 | 拒绝此绑定组合；改虚拟父或两个独立对象，不能漏掉父表以外的子实例 |
| 虚拟父的具体子对象绑定继承属性、关系 | 允许；关系沿用原 id，不复制定义，查询父对象列出具体子实例并集 |
| 成员扩展表有记录、父表没有对应实例 | 不属于合法子实例；建模者须保证父覆盖，平台不扫描数据验证 |
| dataset_id 不存在，或在 sources、关系中重复写表位置 | 拒绝不符合 core-1 结构的绑定；位置从 Dataset 读取 |
| 一个 Dataset 被多个对象或关系复用，另有未引用 Dataset | Ossie 一一登记和输出，不按对象复制，也不丢未引用数据集，按 RT-62 验收 |
| 两个快照 Dataset 最后数据日不同或整周期无数据 | 每个数据集独立选日期，agent 处理关联和展示，不加核心默认规则 |
| 未知 source_id、计算列引用别的对象、聚合或窗口 | 拒绝该绑定；允许的类型差异由 agent 处理 |
| direct 指向非 unique 且非完整标识的属性组 | 拒绝；不要求列为数据库主键 |
| 以客户为 base 反向走 N:1 求订单金额 | 路径拒绝；反向1:1 正例不能一同拒绝 |
| SUM 文本、count 带 measure、比率两边不同对象或不同数据集 | 核心校验拒绝 |
| ratio 携带 time_field | 拒绝；ratio 只用两个分量各自的时间字段，允许二者不同；更改分量时间后展示各自新口径 |
| 导入文件未包含已有元素，或条目转换失败 | 导入只新增和修改，从不生成 delete 提案；转换失败保留原文等待用户选择或点击 AI 补全；要删除就在会话里手动操作，或让 agent 提删除提案并走正常审阅 |
| 新建数据集提交数的数值预览 | 平台按当前表单完整定义在已登记连接只读执行，返回 10；按月另跑趋势，白名单失败或缺绑定显示“无法预览”及原因，不经过 DataAgent 或实例分页 |
| simple/expression 两个 base 都填或都空、ratio 输入 base、数据集指标引用本体路径 | 拒绝；不得由对象绑定推测或补造 base |
| 数据集列清单空或引用未知列 | 清单空时待补全，不臆造；已知清单无该列时修订引用，不生成就绪 SQL |
| 删除引用对象/属性/关系、改基数使路径失效，或删除数据集 | 列出受影响指标，提案归同一依赖组并检查最终图 |
| 本体改名或仅改绑定 | 改名依 id 重生成显示；范围和含义保持的换绑只改 SQL 参考；可能改属性、关系含义或成员、时间范围的变更须沿引用、继承、派生和 ratio 列出影响指标 |
| 给 not_in 包含 null、between 只有一个值 | 核心校验拒绝 |
| 映射表列数、顺序与目标键不对应 | 列数拒绝，导入必须按 to_columns 重排；不能只验长度 |
| 自导出同数据集过滤 CASE、固定 CAST-NULLIF、列去重计数 | 必须按 §5.6 回读为数据集指标，不恢复对象 count 或路径；不以任意 SQL 不支持为由丢掉自家固定形式 |
| 拼接复合键 COUNT DISTINCT | 转为 expression，原文保存并按 RT-56 报 converted，不改成元组去重 |
| 分子过滤放到公共 WHERE、比率先 INNER JOIN 删分母行 | 执行合同错误；一单完成一单取消的完成率应为 0.5 |
| 多层派生、分支并集、成员表同时限定 | 年龄>=18再限东区且成员表含 P1/P2 仅 P1；年龄<18与西区两个分支得 P2/P3，不作 AND；关系 EXISTS 保留方向和角色 |
| 值约束传播与编号连接 | 祖先约束按来源去重，字符串不替换，多元值角色也生成；复合编号 direct 按项对应；决定角色缺标识不裁剪键，最后角色缺标识分开报告 |
| 交易买方华东、卖方华南、金额100的 expression | 保留角色得100，若都降为 companies.region 得0，必须本项 error，不交付必需指标缺项文件；同角色重复引用不误报 |
| 映射不同 UUID 但对象技术名相同 | 对象 id 重写后按 type_id 对应已有唯一映射并沿用 id；UUID 已锁定他对象映射则候选图报告冲突，不硬并 |
| 多作用域同名 Dataset、同业务号事实、同 quote 证据 | Dataset UUID5 用外部作用域加原名，重名按源定位消歧；事实、链接及证据只按 UUID，不静默合并或换归属 |
| 通用解析错误、原生缺材料、补齐依赖 | rule_id 可空，定位只用可取得信息；缺材料 dropped，解析及版本 error；补齐后依赖阻断实时解除，历史报告不改，确认仍核对同产物哈希 |
| 四工具版本参数、连接别名、权限及游标 | 不接受 version_id，不返回 connection_alias；建模版本由服务端固定，问数用当前发布版本；物理信息按权限裁剪，版本变化使旧游标失效 |
| 重复唯一键、映射表重复配对 | 平台不运行基数校验，MCP 提示风险；不把声明当防重证明 |

实施期每个支持的 RT 编号有最小定向回归；完整自动 diff 分类器可后补。该矩阵是验收目标，不是当前测试通过声明。

## 对象指标完整范围的定向导出验收

以下是适配器实施时的隔离夹具，补充示例 06 的成员条件验收；这些物理行不写入 material_objects。父来源 parties 的键为 party_no，并添加 decimal 属性 amount 直接绑定父来源同名列；父对象以 party_no 为单属性标识。各子类共享父来源，沿用父标识。为每种子类各建三个 simple：count（无 measure）、sum(amount)、固定过滤 amount>=200 的 sum(amount)，以及 ratio＝无过滤 sum / count，两个分量以同一子类为统计对象。

| party_no | level | region | amount |
|---|---|---|---|
| P1 | VIP | 东区 | 100 |
| P2 | 普通 | 东区 | 200 |
| P3 | VIP | 西区 | 300 |
| P4 | 普通 | 西区 | 400 |

| 定向夹具 | 成员定义与预期成员 | count / sum / 固定过滤 sum / ratio |
|---|---|---|
| 简单派生 | VIP：level='VIP'；P1、P3 | 2 / 400 / 300 / 200 |
| 分支并集 | 精选：level='VIP' 或 region='东区'，两条 derived_by 分支；P1、P2、P3 | 3 / 600 / 500 / 200；P1 同时满足两分支只算一次 |
| 多层派生 | 高额精选 extends 精选，本层 amount>=200；P2、P3 | 2 / 500 / 500 / 250；不能漏掉祖先范围而混入 P4 |
| 多层加成员扩展 | 高额精选另有成员扩展表，唯一键记录 P3、P4；交集仅 P3 | 1 / 300 / 300 / 300；扩展表中的 P4 不能绕过祖先条件 |

对能够等价输出的条目，必须核对聚合本身包含完整条件，例如简单 VIP 的 count 为 `COUNT(DISTINCT CASE WHEN parties.level='VIP' THEN parties.party_no END)`，sum 为 `SUM(CASE WHEN parties.level='VIP' THEN parties.amount END)`。分支并集必须在同一范围中用 OR，不能把重叠分支聚合相加。另配 ratio＝固定过滤 sum / 无过滤 count，上表四个夹具分别应为150、500/3、250、300。多层条件按 `(level='VIP' OR region='东区') AND amount>=200` 合并；固定过滤与完整成员条件在各自分量内同时生效，ratio 的 count 分母不能借用分子的过滤。回读可以成为数据集 expression，不要求恢复子类 base；结果与上述期望一致才算范围等价。不能只验证 derived_by 回读或 SQL 通过 schema。

成员扩展存在性或任一层范围若不能用目标表达式完整表示，simple 与 ratio 按 RT-61 dropped；不能仅输出普通 LEFT JOIN 后标 converted。每个夹具另配同算法对象 expression，范围不可表达时该项 error，核心原文保留；不得静默输出父全集的 count=4、sum=1000、ratio=250。ratio 任一分量失败，该 ratio 也 dropped，不生成悬空分量引用。示例 11 的 A3 反例按前文固定验收 dropped。

路径到达子类另验：独立订单 O1、O2、O3 金额分别为10、20、30，分别关联 P1、P2、P3；多对一关系目标是上述 VIP 子类，主来源 orders。以订单为统计对象，用该路径的 party_no 非空作固定过滤，simple count=2、sum(订单金额)=40、ratio=sum/count=20。P2 在父来源有行但不属 VIP，不得匹配为目标；VIP 条件须保留在路径匹配或等价聚合条件中。若连同父来源的完整范围无法表达，simple/ratio dropped、同算法 expression error。单独导出 VIP 声明不能让该指标通过。

## 继承标识与非法输入验收

以下是完整的虚构 Ossie 输入。Person 用 person_no 标识，Employee 继承 Person 却另选 employee_no；两个编号均为 String、OneToOne。

```json
{
  "version": "0.2.0.dev0",
  "name": "ExampleInheritedIdentity",
  "ontology": [
    {
      "concept": "Person",
      "type": "EntityType",
      "identify_by": ["person_no"],
      "relationships": [
        {
          "name": "person_no",
          "verbalizes": ["{Person}的编号为{String}"],
          "roles": [{"concept": "String"}],
          "multiplicity": "OneToOne"
        }
      ]
    },
    {
      "concept": "Employee",
      "type": "EntityType",
      "extends": ["Person"],
      "identify_by": ["employee_no"],
      "relationships": [
        {
          "name": "employee_no",
          "verbalizes": ["{Employee}的员工编号为{String}"],
          "roles": [{"concept": "String"}],
          "multiplicity": "OneToOne"
        }
      ]
    }
  ]
}
```

预期 Person.person_no 为 identifier=true、unique=true；Employee 沿用该完整标识，Employee.employee_no 为 identifier=false、unique=true。不得生成 (person_no,employee_no) 组合键，不得把 Employee 的原首选标识报为完整转换；原首选标识按 RT-68 dropped，逐项报告并保留原文与定位。另配只以 employee_no 表达 Employee 身份且无法等价得到 person_no 的映射，预期该映射待补全，不因属性仍在就标就绪。父无标识的对照输入允许子类自建标识；子类仅重述父完整标识的对照输入不误报损失。

非法输入分开验收：多元关系声明 OneToOne 时报告输入 error 与原定位，不生成中间对象、转换 Rule 或 AI 补全任务；把上面 Employee.extends 改为 ["String"] 同样输入 error。二者不计为未承载的合法 Ossie 能力。

## 条件 COUNT 与事实审阅验收

两行都满足 flag='Y'，amount 分别为 NULL、10。`COUNT(CASE WHEN flag='Y' THEN amount END)` 与 `COUNT(amount)` 都为1，导入保留 expression，不能变为结果2的 count 加 flag 过滤。SUM、AVG、MEDIAN、MIN、MAX 的单 WHEN、缺省或 NULL ELSE 才按 §5.6 拆为 measure 与 filters；COUNT DISTINCT CASE 单独验收其忽略 NULL 和列去重语义。

不同文档分别抽出客户 C001，形成 F1、F2 两个新建提案，电话、证据、邻接各自不同。同类型同完整业务标识触发提示，不能自动合并或阻断。分别验收：两条都接受时 search_objects 返回两个 UUID，数量为2，get_object 各自保留属性、证据、邻接；只接受一条时只返回这一条；将 F2 改为更新 F1 追加证据时保留 F1 UUID，并按人工确认内容更新。父查询或多条继承展开路径只对同一 UUID 去重；不同 UUID 的同编号事实仍分别返回。另做业务实体统计时，完整业务标识去重结果为1，不能把统计结果写回检索分页。
