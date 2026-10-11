# 演示案例：咖啡渠道销售

同一个业务空间演示两种建模方式，再通过 MCP 交给智能体问数，全程真实模型、真实数据库：

- **自上而下**：业务文档 + 目标范围 → 业务对象、属性、关系、规则，以及**文档中的业务事实（文档实例）**，全部带原文证据。
  文档没给出的值（例如客户编号）不编造，标记为「待补全」，不阻止发布；只被提到、没写字段的对象提示从数据表补全。
- **自下而上**：在构建页「业务数据」选表 → 系统读取字段、主键、样例值、外键生成结构说明 →
  智能体复用已有对象，提出**数据映射**和关系的**字段连接**，发布后即可按映射实时查询。

| 项目 | 内容 |
| --- | --- |
| 业务 | 精品咖啡渠道分销：客户（渠道企业）下订单，订单包含订单明细，明细对应商品；售后退货 |
| 文档 | [`01-渠道销售业务说明.md`](materials/01-渠道销售业务说明.md)（预备，v1）、[`02-售后退货规则.md`](materials/02-售后退货规则.md) + [`03-2026年1月退货登记.md`](materials/03-2026年1月退货登记.md)（现场自上而下） |
| 数据 | MySQL `demo_analytics`：8 个客户、6 个商品、780 张订单、1,574 条明细；只读账号 `of_readonly` |
| 起点 | v1 = 文档建模结果（4 个对象及属性、3 条关系、规则），**尚无映射**；两个备用会话提案待处理 |
| 现场演示 | [演示手册](演示手册.md)，约 20 分钟 |
| 场景二 | [导入真实手工 Ossie 模型](../ossie-import/演示手册.md)，单独演示 |

## 环境与地址

| 服务 | 地址 | 启动 |
| --- | --- | --- |
| OntoFoundry（演示用生产构建） | http://127.0.0.1:8000 | `make build && make serve` |
| DataAgent 后端 | http://127.0.0.1:8900 | `opendataworks/dataagent/dataagent-backend`：`SKILLS_ROOT_DIR="$PWD/../.claude/skills" .venv-py313/bin/python main.py` |
| DataAgent 前端 | http://localhost:3001 | `opendataworks/dataagent/dataagent-frontend`：`npm run dev` |
| PostgreSQL（平台库） | 127.0.0.1:55441 | `docker start of-local-pg` |
| MySQL（业务库）、Redis | 3306 / 6379 | 已有容器 `data-portal-mysql`、`odw-local-redis` |

## 从零准备（幂等，可重跑）

```sh
cd docs/demo/coffee-channel-sales/scripts
python3 prepare_demo.py model     # 新建空间、上传业务说明、真实 DataAgent 建模（约 5 分钟）
python3 prepare_demo.py publish   # 接受全部提案，发布 v1
python3 prepare_demo.py connect   # 只读数据连接「销售业务库」
python3 prepare_demo.py standby   # 两个备用会话：售后退货（自上而下）、销售业务库映射（自下而上），提案待处理
python3 prepare_demo.py token     # 问数令牌，生成 generated/mcp-config.json（不入库）
python3 prepare_demo.py ossie     # 场景二的两个空空间
python3 dataagent_agent.py        # 导入 MCP、创建/更新问数助手；需在 v2/v3 发布后跑，五个问题全对才发布
./reset_demo.sh snapshot          # 保存演示起点
```

重建前清掉旧空间：`cd apps/api && uv run --python 3.13 python ../../docs/demo/coffee-channel-sales/scripts/purge_workspace.py coffee-channel-sales`。
兜底：自下而上现场和备用都失败时，`prepare_demo.py data` 用脚本直接配置映射（依赖建模结果的属性技术名，用前核对）。

彩排后恢复到演示起点（平台库快照在 `generated/platform-db.sql`，由 `reset_demo.sh snapshot` 生成）：

```sh
pkill -f 'uvicorn ontofoundry_api'               # 先停 OntoFoundry
docs/demo/coffee-channel-sales/scripts/reset_demo.sh restore
make serve                                        # 再启动
```

DataAgent 上预先问好的对话「客户销售额排名」不受恢复影响。

MySQL 只读账号（一次性）：

```sql
CREATE USER 'of_readonly'@'%' IDENTIFIED BY 'of_readonly_demo';
GRANT SELECT, SHOW VIEW ON demo_analytics.* TO 'of_readonly'@'%';
```

## 已核实的问数答案

| 问题 | 答案 | 依据 |
| --- | --- | --- |
| 星海贸易在哪个城市？什么时候签约的？ | 上海，2025-10-02 | `customers` |
| 经典手冲壶是什么品类？标准单价多少？ | 咖啡器具，168 元 | `products` |
| 一共有多少张订单？订单总金额是多少？ | 780 张，269,516 元 | `orders` 全量 |
| 销售额最高的客户是谁？ | 远山咖啡，38,348 元（98 张订单） | `orders` ⋈ `customers` |
| 哪个城市销售额最高？ | 北京（远山咖啡），38,348 元 | 同上 |
| 销量最高的商品？ | 冷萃咖啡液，580 件；销售额最高是经典手冲壶 86,016 元 | `order_items` |
| 1 月有哪些退货？退款合计多少？ | 3 单：星海贸易 120、远山咖啡 168、木棉生活 88，合计 376 元 | 文档实例（退货登记） |
