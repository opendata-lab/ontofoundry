# 增量／小改动写法

先执行 `show_element.py --work-pack <工作包> <英文标识或id>...`，按输出复制完整定义和 UUID；不读 context_file 全文、脚本源码或 Schema。先取修改目标、引用实体及相关属性／关系／数据集／指标；同名不证明同义，核对定义后复用。按 id、kind:英文标识或 property:实体.属性、link_type:源实体.关系精确查询，区分大小写。无英文标识的映射／实例用 id。不存在或有歧义返回非零和候选精确写法；超过 8 KiB 时按返回的 --page N --sha256 参数分次读取并依序拼接 text，再解析原 JSON，不能把分页摘要当成完整定义。引用者只列直接引用的 id/英文标识（包含规则路径、映射字段与继承），不代表可安全删除。

同一工具回合分别执行 `show_example.py --incremental-guide`、`--values`、`--part update`；改名称／说明或删除再读 `--part edit`。两份都是裸 items 数组，用独立的虚构澄页图书馆借阅 v1 context 验证，并非本轮业务答案；示例 UUID、物理列、SQL、证据须换成本轮查询和输入的确定值。display_name 只写名称，不把说明写进名称；例如“借阅读者”，临时读者可不登记写 description。

- update：target_id 写已有 UUID，after 复制查询 definition 后去掉顶层 id，保留所有未改字段、人工证据及证据 UUID，再修改目标字段（不是局部 patch）。片段不写 before／expected_target_hash，prepare_result 对定义从 draft/element_hashes 填入，对实例按 target_kind+target_id 从 instance_baseline 原样复制 element/hash；后者含 revision，不用旧集合哈希。目标不在基线为 TARGET_NOT_FOUND，旧值／哈希不符为 BEFORE_MISMATCH／TARGET_HASH_MISMATCH。Dataset 补列必须保留原来源；新列只来自同步后的表结构。
- 既有引用用 UUID 字符串，例如 type_id、dataset_id、owner_type_id、owner_id；不写 {"client_ref":"旧标识"}。本批 create 才定义 client_ref，并用 {"client_ref":"新标识"} 引用。映射 fields 的键是属性英文标识，source_id 是本映射的局部字面量。
- update 片段共七项：原 claims Dataset 补列；给已有 claim 实体 create 映射；create 事件 query Dataset；赔偿金额 simple 引用已有赔偿 Dataset；两个 simple 与 ratio 引用本批新事件 Dataset／指标。押金与赔偿各保留日期，UNION ALL 避免多条赔偿重复累计押金；ratio 分量同 Dataset。
- edit 片段：属性及已有押金指标只改名称／说明并保留引用与证据；create 规则的 owner_id 用已有属性 UUID；delete 只写 operation、target_kind、target_id，after 可省略或 null。先查引用者，再显式更新／删除依赖，最终图检查通过才交付；不自动级联，也不删除无关规则。

写 modeling/parts/01-update.json（编辑可用 02-edit.json），即执行 `check_part.py --work-pack <工作包> modeling/parts/01-update.json`；按 SKILL 的④合并、⑤修正、⑥交付。检查器处理引用闭合与候选图；增量只写变化，不重复创建实体。edit 中删册数非负规则仅演示用户明确要求取消该规则，不是赔偿补齐的步骤。
