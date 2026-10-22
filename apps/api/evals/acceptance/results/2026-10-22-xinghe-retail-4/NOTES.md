# 真实验收四：星河零售建模与问数（2026-10-22）

虚构星河零售：材料 `material.md` + 本地 MySQL `xinghe_retail` 六张表（refunds 故意先不同步）。平台 main，DataAgent 三技能（ontology-discovery、entity-extraction、semantic-grounding），DeepSeek 低峰时段。

| 步骤 | 目录 | 结果 | 轮数 / 关键数据 |
|---|---|---|---|
| 计划 | `1-plan` | 列出 6 个实体（门店、会员、商品、订单、订单明细、退款），退款标“表未同步”，等待确认 | 12 轮（预期 3–4，读了较多脚本与示例） |
| 抽取 | `2-extract` | 回复“可以，商品改名为‘商品 SKU’，其余照旧。”后生成 64 条提案 | 40 轮，7 次工具报错（/tmp 路径、check_part/prepare_result 参数、02 片段缺 data_join.kind） |
| 发布 | `3-publish` | 直接接受时 refunds 被拦（SOURCE_NOT_REGISTERED，符合设计）；同步 refunds 后 64 条全部接受并发布版本 1 | — |
| 问数 1 | `4-qa-1-token-missing-scopes` | 两题均错：MCP 令牌创建时传了空 scopes，缺映射与实例权限，Agent 改查无关演示表（答 662.40）；云桥店无法解析 | 测试配置失误 |
| 问数 2 | `5-qa-2-sql-channel-down` | 语义全对（指标绑定、过滤、resolve_entity 命中星河云桥店 S03），但 SQL 通道未配置无法出数 | 重启 DataAgent 时丢失 ODW_BACKEND_BASE_URL／服务令牌 |
| 问数 3 | `6-qa-3-final` | **两题全对**：1–3 月 257.20／174.60／237.10，合计 668.90；云桥店 317.10（5 笔） | 查询 xinghe_retail；云桥店先经 resolve_entity 解析 |

过程中的修正（均已进入 main）：

- 抽取的 6 个实体都没设标题属性，按名称解析必然失败 → 人工为门店、会员、商品设标题属性并发布；技能补“有名称属性时设标题”（457a4c7）。
- MCP 鉴权改为部署时配置的固定令牌（v0.2.4／v0.2.5），删除服务令牌。
- DataAgent 重启改用固定启动脚本，保留 SQL 通道环境变量。

标准答案：1 月 257.20、2 月 174.60、3 月 237.10、合计 668.90；星河云桥店（S03）317.10。

花费（DeepSeek 余额）：计划 + 抽取 + 问数 1 共 1.56 元（10.47 → 8.91）；之后的问数 2、问数 3 与同时段计划轮验证合计约 0.6 元（8.91 → 8.25，余额更新有延迟，未逐次拆分）。

每个目录的 `conversation.json` 为完整对话与工具记录（本机路径已替换为 `~`），`run.log` 为运行状态。
