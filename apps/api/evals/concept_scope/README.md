# 概念范围评测

评测建模计划轮识别的概念是否准确。考生是 DataAgent 中的建模 Agent（DeepSeek + ontology-discovery 等技能）：它只拿到 `materials/` 与关联表；`gold.json` 只在本地打分用，不上传。设计与基线记录见 `docs/design/2026-10-22-modeling-eval.md`。

## 场景

| 目录 | 内容 | 关联表 |
|---|---|---|
| `wind_inspection` | 虚构风电场巡检运维说明 | 无 |
| `contract_approval` | 虚构合同审批管理办法 | 无 |
| `clinic_booking` | 虚构社区诊所预约与处方说明 | `tables.sql`（含一张汇总统计表） |
| `adv_property_repair`（进阶） | 虚构物业报修：同名异称、角色、纯关联表与带属性关联、只在表中出现的概念、背景段 | `tables.sql` |
| `adv_training_courses`（进阶） | 虚构职业培训：课程与开班两层概念、同名异称、角色词、背景段 | 无 |

gold.json 的 `level` 区分 basic／advanced，运行时可用 `--level` 只跑一类。`heldout/` 下是不公开的留出场景，由另一模型编写，技能作者不阅读，只看汇总分数；用 `--set heldout` 运行。

`gold.json`：`concepts` 为必须识别的概念，`accepted` 是可接受的中英文叫法，`instances` 是材料中的具名实例（列成概念算错，出现在该概念的 examples 中算归位）；`not_concepts` 为属性、指标、汇总统计表，列成概念算错。不设“两可”项。

## 打分

`score.py` 只按登记叫法精确匹配（NFKC、小写、去空格下划线连字符）。输出准确率、召回率、F1、漏掉的概念、各类错误数、例子归位数。“未登记，待人工判定”的条目由人判断，确认后把叫法补进 `gold.json` 并在设计文档记录。

## 运行（消耗模型费用，低峰时段、经同意后执行）

带表场景先在只读 MySQL 上执行 `scenarios/clinic_booking/tables.sql`（只建表），给评测账号授予该库只读权限。

```bash
cd apps/api
set -a; . <API 环境文件>; set +a
EVAL_MYSQL_USER=<只读账号> EVAL_MYSQL_PASSWORD=<密码> \
.venv/bin/python evals/concept_scope/run.py --api http://<IP>:8000 --origin http://<IP>:5199 --output-dir evals/concept_scope/results/<日期-说明>
```

`--score-only <workspace_id>:<session_id> --scenario <目录>` 可对已有会话重新打分，不再消耗模型。

## 结果存档

每次运行存到 `results/<日期-说明>/`：`meta.json`（时间、代码提交、API）、`summary.json`（各场景分数），每个场景目录下 `score.json`（含逐项判定）、`plan.json`（Agent 写的概念清单原件）、`conversation.json`（完整对话与工具记录）、`answer.md`（最终回答）。另写 `NOTES.md` 记录花费、技能版本和人工判定，并在设计文档的基线表加一行。结果目录提交进仓库，作为对外讲解效果的依据。
