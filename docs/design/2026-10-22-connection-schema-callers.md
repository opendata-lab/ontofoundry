# 服务级连接的库名调用链修复（v0.2.2）

日期：2026-10-22。基于 v0.2.1，分支 hotfix/0.2.2。

## 已确认决定

| 编号 | 决定 | 来源、分类与影响 |
|---|---|---|
| CS-01 | MySQL/Doris 连接不填库，PostgreSQL 必须填数据库。列表删除数据库列，PostgreSQL 地址显示 host:port/db。 | 用户要求，沿用已有连接规则和字段，不新增模型概念。 |
| CS-02 | 读取单库资产必须带库名；全部库先列库再逐库请求。MySQL/Doris 数据集表来源先选库再选表（PostgreSQL 保留默认 schema），切换连接仅在目标库及表都存在时保留来源。 | 用户要求，执行边界；已有 schema_name 足够表达。 |
| CS-03 | 后端继续拒绝 MySQL/Doris 空库，不回落到驱动默认库。 | v0.2.1 已确认决定；本次不改接口、契约、迁移和版本号。 |
| CS-04 | 用 Vitest 页面/组件渲染和真实 client 请求参数、pytest SQLite ATTACH/mock API 验证。明确区分复现缺陷与未复现路径。 | 用户要求；不连接真实 MySQL/Doris。 |

## 初步核查

数据集位置选择器的加载 effect 和切换连接保留表逻辑均可能在 schema_name 为空时请求 assets。数据表页和同步弹窗通过 loadSchemaAssets 逐库请求，需以测试验证，不能将用户报告直接归因为这两个当前入口。构建页使用 registered-tables 汇总，旧 table-material 接口已禁止创建重复材料，不调用 require_schema。

完整调用清单、测试证据和结果追加到 [数据表设计](2026-10-21-data-tables-page.md) 的 v0.2.2 小节。
