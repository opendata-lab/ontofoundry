---
name: ontology-discovery
description: 从文档、表结构发现实体类型、属性、关系、数据集、映射、指标、规则，判断新增还是复用已有定义，提出供审阅的增量提案。
---
# 建模路由

先定范围再写提案：概念经用户确认后，属性、关系、实例只按清单展开。

先运行 `"$DATAAGENT_PYTHON_BIN" .claude/skills/ontology-discovery/scripts/init_workflow.py --work-pack <工作包>`（有 prior_plan_file 加 `--prior-plan <prior_plan_file>`）。它打印本轮路径和命令，照抄，不必 --help、读源码或列目录。

再只读当前一个步骤文件：
- 会新增概念或要整体优化，且没有 prior_plan_file：[计划](references/steps/plan.md)，列概念写待确认后结束，不写提案。
- 有 prior_plan_file（已确认范围）：[抽取](references/steps/extract.md)。
- 不新增概念（改名、补指标或映射、已有概念的实例）：[增量](references/steps/incremental.md)。

写完片段读[收尾](references/steps/finish.md)。同回合多条调用，不拼接输出。
