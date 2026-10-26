# 星河零售离线夹具（全部业务名称虚构）

来自 2026-10-21 抽取轮评审的离线样品，作为确定性测试输入固化，不是实际模型运行记录。material.md 保留原文与行号；approved-plan.json 是已批准概念清单的离线重建，用户的修改意见“商品改名为商品 SKU，其余照旧”由测试和预算单独给出。context.json 使用虚构离线运行与空候选图。

- tables.json 只有五张已知表；refunds 不含物理列。conservative/ 为 63 项候选，退款只到语义、基于表数据集与有材料依据的语义规则；没有退款映射、依赖它的 SQL 或指标。delivery.md 记录未交付项与补齐提示。退款属性英文标识是语义命名，不声明为物理列。
- tables-supplemented.json 是显式补齐后的结构；supplemented/ 为 69 项完整预期，五个业务指标共七个 Metric（包含同数据集 ratio 分量）。不能把这个文件当作初次抽取已知输入。
- events-seed.sql 仅保留用于复算的虚构订单／退款行，以 SQLite 内存库验证 UNION ALL 不重复累计销售；不连接实际数据库。
- 测试还会将 conservative 的服务端候选图作为已接受草稿，以既有 UUID 生成真正的增量批次：更新一个退款 Dataset，新增映射、事件来源与四个指标，共七项。该增量结果与 supplemented 的逻辑图逐项相等。

写法覆盖是字段路径、类型及判别值覆盖，加单／复合标识、同源比率等明确断言。作者核对过契约；这不是盲测，也不能证明 Agent 会在给定轮次内遵循路线或真实来源探测成功。

增量固定输入：v1-context.json 是接受 conservative/ 后的完整草稿，包含固定元素 UUID、逐元素 hash、虚构 v1 版本与本轮头；v1-refs.json 用于测试逻辑图的 UUID 归一。v1-increment.json 将原七项补齐答案保存在本离线夹具中，不能通过 show_example 读取。写法包与非协议正例改用独立图书馆领域及 v1；测试比较字段形状（包括已有 UUID 字符串与新 client_ref），再用本夹具的确定业务内容、show_element 读取结果校验零售增量，与 supplemented/ 独立预期图逐项比较，SQLite 从最终图复算。不将图书馆的业务文字或 UUID 用作零售答案；离线通过不能替代换包后的真实验收。
