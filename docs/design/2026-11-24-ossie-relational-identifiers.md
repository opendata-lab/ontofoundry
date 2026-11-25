# Ossie 关系标识的等价导入

日期：2026-11-24。状态：已实施（PR 见分支 `feat/ossie-relational-identifiers`；设计评审 Codex，8 条意见全部采纳，记录在 `~/.agents/handoffs/2026-11-24-codex-ossie-relational-identifiers-review/`）。来源：内网大型 Ossie 材料重放（`2026-11-18-large-material-modeling.md` §7），8 个实体因 RT-32 没有标识，进而映射失败、3 条多元关系报错；用户 2026-11-24 决定“同一含义换一种写法导入，导出用平铺写法，不改核心模型”。

## 1. 问题

Ossie 允许用关系做标识（官方 `ontology.md`“Identifying relationships”一节：`License` 由 `acct` 和 `seat_nr` 标识；“Object mappings”一节：`OrderLineItem identify_by: [nr, order]`，映射用嵌套 `referent_mappings` 展开 `order`）。这是 ORM 的参照方案，用来表达“下级对象在上级范围内编号”。

核心模型的标识只能是本对象的属性（§3.2），所以导入现在按 RT-32 整组放弃这类标识，并按 §5.7 拒绝嵌套 `referent_mappings`。后果是连锁的：

1. 对象没有标识；
2. 对象映射失败（“身份成员不是已转换属性”或“嵌套 referent_mappings 未承载”），对象没有数据；
3. 以它为决定角色的多元关系不能构造中间标识（RT-28 error）；
4. 指向它的关系绑定找不到目标身份。

例（虚构）：

```yaml
- concept: warehouse
  identify_by: [code]                     # code → String，OneToOne
- concept: zone
  identify_by: [warehouse, zone_code]     # warehouse → warehouse，ManyToOne
- concept: bin
  identify_by: [zone, bin_code]           # zone → zone，ManyToOne
```

`bin_code` 只在同一库区内唯一，`zone_code` 只在同一仓库内唯一。现在导入后 zone 和 bin 都没有标识。

## 2. 参考

| 来源 | 标识 | 关系 |
|---|---|---|
| Ossie | 一组二元关系，可以指向实体（如上） | 映射用嵌套 `referent_mappings` 逐层展开到值 |
| Palantir Foundry | 单个属性；多列自然键在管道里由多列算出一个主键（create-object-type：“the primary key is the function of either a single column or multiple columns”） | 外键属性对主键（create-link-type：“select properties that represent the foreign key and corresponding primary key”） |
| Fabric IQ | 单个 string 或 integer 属性（how-to-create-entity-types） | 两端各一列对接（how-to-create-relationship-types） |
| 本平台核心 | 一组本对象属性（可复合） | `DirectJoin`：源属性组对目标标识属性组 |

主流产品都不让标识引用关系，“下级属于上级”由外键属性加关系表达。本平台导入多元关系时已经这样做（RT-28：每个实体角色生成“角色·标识”属性，关系按这些属性 `DirectJoin` 到目标标识）。

## 3. 两种写法等价的条件

写法一（关系标识）：`zone identify_by: [warehouse, zone_code]`。

写法二（平铺）：zone 有属性 `warehouse_code`（必填）和 `zone_code`，标识为二者；关系 `warehouse` 按 `warehouse_code` 直接对接 warehouse 的标识 `code`。

同时满足以下三条时，两种写法对**已存在的对象**给出相同的身份：两个 zone 是同一个，当且仅当它们的 (warehouse 标识, zone_code) 相同（无环的多层标识逐层把对象引用替换成上级键元组，身份相等关系不变）：

1. **标识值相同**：标识关系被替换为“上级完整标识”的属性组，逐层递归到值；
2. **值必填**：替换出的属性 `required=true`；
3. **关系对接上级完整标识**：该关系 `data_join = DirectJoin(source=替换出的属性, target=上级标识属性)`，逐对对应。

两种写法**不完全相同**，差在以下三点，均如实记录、不假装等价：

- **上级对象是否一定存在（参照完整性）。** 写法一里标识成员是一条必须存在的关联，官方 `OrderLineItem` 示例还显式写了 `requires: ["OrderLineItem.order"]`。核心模型的关系没有“必填”字段，`required` 只保证外键值不为空，`DirectJoin` 只记录逐列相等，都不能证明目标对象存在。数据中可能出现 `(warehouse_code=W9, zone_code=Z1)` 而没有仓库 W9 的“孤儿”库区：按对象查询能查到它，沿关系查不到仓库。导入报告在 RT-32 converted 中写明这一差距；原文的 `requires`（如有）照常按规则导入，不能转换时按 RT-31 待补全。是否给核心关系增加“必填”属于模型变化，本设计不做，见 §7。
- **上级标识变化后是否自动跟随。** 写法一自动跟随；写法二要改下级属性。核心校验只保证关系目标仍是**某个**唯一键（`domain/validation.py` `_join`、`_unique_key`），若上级把标识从 `code` 换成 `warehouse_id` 而 `code` 仍是唯一属性，旧关系照样通过，不会提示“已偏离上级的首选标识”。这是编辑时的已知局限。
- **往返。** 见 RI-05。

## 4. 已确认决定
## 4. 已确认决定

| 编号 | 决定 | 来源与理由 |
|---|---|---|
| RI-01 | **`identify_by` 中的关系成员按 §3 展开。** 适用条件全部满足才展开，否则按 RI-02：(a) 关系是二元 ManyToOne，或 OneToOne 且展开后只有一个属性（该属性设 `unique=true`，保留反向唯一）；(b) 关系声明在本对象上（声明在祖先上的关系，其 `DirectJoin` 源端必须是祖先的属性，不能用子类生成的属性）；(c) 先按 RT-68 判断本对象的标识会被采用，即没有继承来的不同父标识，被 RT-68 放弃的标识不展开；(d) 目标对象已有完整有效标识，目标标识本身含关系时先展开，按依赖顺序处理，成环者放弃；(e) 展开后对接列数不超过 `DirectJoin` 上限 16。每个关系成员生成一组属性，名称为 `<关系名>_<上级标识属性名>`（冲突按现有规则消歧），`value_kind`、`value_type_id` 取自上级标识属性，`required=true`，显示名为空（扩展文件有则用）。`DirectJoin` 按属性 id 逐对对应上级标识，不依赖排序。展开后整个对象只剩一个标识属性时，按现有 RT-33 设 `unique=true`。一个对象的生成属性、标识和关系对接在候选草稿上整组校验、整组提交，失败则全部不留，按 RI-02 报告。报告 `converted`（RT-32），列出生成的属性和 §3 的参照完整性差距。 | 用户 2026-11-24。同 RT-28 多元关系的做法，不加核心概念。删掉的后果：材料中“在上级范围内编号”的对象全部没有标识，映射、关系、多元关系连锁失败。 |
| RI-02 | **条件不满足仍整组放弃。** 关系是多对多、目标没有完整标识（含依赖成环）、成员缺失或重复时，按现状 RT-32 / RT-30 dropped，不裁剪为较小键。 | 保持 §5.2 “整组翻译或整组放弃”。 |
| RI-03 | **嵌套 `referent_mappings` 只在对应 RI-01 展开的标识关系时承载，按原始成员逐层核对。** 每一层先解析成员名（可带对象前缀），检查每个标识成员恰好出现一次，`expression` 与嵌套二选一，没有多余成员；最后核对所有叶子都是同一数据集的直接列，再把叶子绑定到对应的生成属性。任何一项不满足，整个对象映射 dropped（RT-43），不猜列。按固定版规范，实体型的 referent 用嵌套写法（`OrderLineItem` 示例中 `CustOrder` 只有单一标识也嵌套）。材料常见的简写，即对实体型 referent 直接写 `expression`，作为**兼容行为**接受，限于目标的原始标识只有一个值类型成员，报告注明是兼容写法。关系绑定中目标端的嵌套引用按同样规则展开。 | 嵌套映射就是“生成属性对应哪一列”的逐项证据；不从列名猜，不按属性名合并字典以免同名成员互相覆盖。 |
| RI-04 | **标识关系的对接以 RI-01 为准，link mapping 逐项核验。** 该关系已由 RI-01 设好 `DirectJoin`。映射里对同一关系的 link mapping，要逐个上级标识成员核对：根身份与本对象主身份一致、来自同一数据集、每个成员对应的列与生成属性的绑定列相同。逐项一致报 `converted`，否则报 RT-53 dropped，不覆盖。不按列集合比较，以免两列互换也被判为一致。 | 关系对接由标识语义决定，与物理 relationships 无关。 |
| RI-05 | **导出用平铺写法，不还原，往返条件写明。** 生成属性按普通属性导出，`identify_by` 列属性，这部分总能回读。关系的 `DirectJoin` 按现有导出规则（RT-52）只在两端都有数据映射、能写出物理连接且目标业务键已声明唯一时输出；否则导出后回读只剩普通关系、没有对接，按现有 RT-53 报损失。只有本体没有数据映射时同样如此；若要无映射也保留对接，需要扩展文件，本期不做。不把平铺写法还原成关系标识。 | 还原需要把所有引用生成属性的映射、规则、指标改写成嵌套路径，生成属性的显示名、同义词无处安放，换来的只是写法不同（§3）。 |
| RI-06 | **材料中的建模缺陷不替用户修。** 父类没有标识而子类各自定义等，按现有规则报告。本体标识与登记表主键不一致（如本体用 `rule_key` 标识，表主键为 `domain, label, key`），**现有导入不报告**：`mappings.identity` 直接优先采用数据集声明的主键作为来源键。这类差异的报告列入 `docs/TODO.md`，不在本期。 | 用户 2026-11-24：目标是正确的模型，不将错就错，也不擅改。 |

## 5. 例子（改前 → 改后）

材料（续 §1）的对象映射：

```yaml
- concept: bin
  object_mappings:
    - referent_mappings:
        - relationship: zone
          referent_mappings:
            - relationship: zone.warehouse
              expression: bins.warehouse_code
            - relationship: zone.zone_code
              expression: bins.zone_code
        - relationship: bin_code
          expression: bins.bin_code
```

| | 改前 | 改后 |
|---|---|---|
| zone 属性 / 标识 | zone_code / 无 | warehouse_code（必填）、zone_code / 二者 |
| bin 属性 / 标识 | bin_code / 无 | zone_warehouse_code、zone_zone_code（必填）、bin_code / 三者 |
| 关系 zone.warehouse | 无绑定 | `DirectJoin(warehouse_code → warehouse.code)` |
| 关系 bin.zone | 无绑定 | `DirectJoin(zone_warehouse_code, zone_zone_code → zone.warehouse_code, zone.zone_code)` |
| bin 映射 | dropped（嵌套 referent_mappings 未承载） | 三个标识属性分别绑定 `bins.warehouse_code`、`bins.zone_code`、`bins.bin_code` |
| 报告 | RT-32 dropped ×2，映射 dropped | RT-32 converted ×2，列出生成属性 |

第 2 层的生成属性名是 `zone_` + zone 的标识属性名：zone 的 `warehouse_code` 本身就是 RI-01 生成的，所以 bin 上叫 `zone_warehouse_code`。

## 6. 影响范围

- 只改导入器：`importer.identifiers`（按依赖顺序展开）、`mappings.identity` 和 `bind_relationship`（嵌套引用展开）。核心模型、校验、契约、界面、导出不改。
- 多元关系（RT-28）无需改动：决定角色的目标有了标识，中间标识自然可构造。
- 与 `docs/TODO.md`“多元关系改用多键关联”（用户 2026-11-15）的关系：那条决定针对多元关系中间对象的**角色编号属性**，它们只为对接参与方而生成，外键指向物理键时无法绑定，按 AC-04 不能接受。RI-01 生成的属性不同：它们是本对象**业务标识的一部分**，核心标识只能由属性组成，不能省掉；有嵌套映射时逐项绑定到列，满足 AC-04；没有映射的对象 AC-04 不检查，日后补映射时按业务标识绑定。
- 主设计同步：§5.2 `identify_by` 行、§5.7 “不支持的映射”、能力表“`identify_by` 含关系成员”行、RT-32 行、补全表 RT-32 行。

## 7. 不做

- 不让核心标识引用关系（用户 2026-11-24 否决：复杂度高，Palantir、Fabric IQ 都没有）。
- 不在导出时还原关系标识（RI-05）。
- 不给核心关系增加“必填”字段（§3 参照完整性差距）。它是模型概念变化，Palantir、Fabric IQ 也不在本体里保证外键目标存在；如需要另行设计。
- 不用登记表主键推断标识或补全缺失的嵌套映射。
