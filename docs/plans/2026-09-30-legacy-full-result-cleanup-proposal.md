# 旧“完整结果替换草稿”路径的清理提案

**日期：** 2026-09-30  
**状态：** 提案，未执行（实施设计 T8 要求单独提出，不在切换任务中删除）

Proposal-first 已成为新建模运行的默认合同。以下代码与字段只为兼容切换前已开始的运行、旧会话与旧客户端而保留。

## 前置条件

全部满足后才开始清理：

1. 生产环境 `GET /api/v1/workspaces/{id}/proposal-metrics` 中 `legacy_active_runs` 在所有空间持续为 0，并至少经过一个稳定发布周期。
2. 同一周期内 `batch_failure_rate` 与 `stale_rate` 处于可接受范围，决策统计显示提案流程在被实际使用。
3. 数据库统计：`modeling_sessions.candidates_json` 非空的会话数，以及仍为 schema v1 的会话草稿数量，均已评估；有数据的空间已通知其成员。
4. 已完成 PostgreSQL 与材料存储的备份和恢复演练。

## 清理范围

| 对象 | 位置 | 处理 |
|---|---|---|
| 完整结果消费 | `services/model_result.py` 中 `RESULT_SCHEMA_VERSION` 分支、`review_conventions` 修复轮 | 删除；无清单或 `result_contract != proposals` 的结果改为明确失败 |
| 旧提示词 | `services/dataagent.build_turn_prompt` 的完整快照分支、`model_review.build_repair_request` | 删除 |
| `modeling_result_contract = "full"` | `config.py` | 删除取值与开关 |
| 候选 | `candidates_json` 列、`POST /sessions/{id}/candidates`、前端 `Candidate` 类型 | 独立 Alembic 迁移删除列；删除接口与类型 |
| 运行中禁止编辑 | `api/modeling.blocks_edits` 的旧合同分支 | 删除 |
| 旧发布/预览请求形态 | `SessionPublish.revision`、`MergeResolution.revision/current_version_id`、字符串形式的 resolution | 删除；只接受 `expected_*` 与 `{choice, value}` |
| `version_sha256` 别名 | REST/MCP 响应 | 公告弃用一个周期后删除，只保留 `version_content_sha256` 与 `normalized_snapshot_sha256` |

不在清理范围：v1 快照的读取规范化（历史版本永久保留）、Ossie 扩展 v1/v2 的导入兼容。

## 步骤

1. 发布一个只加弃用日志与告警的版本，观察一个周期。
2. 删除代码路径（单独 PR），保留列。
3. 独立 Alembic 迁移删除 `candidates_json`，downgrade 恢复为可空空列。
4. 更新 README、主设计与实施设计的兼容说明。
