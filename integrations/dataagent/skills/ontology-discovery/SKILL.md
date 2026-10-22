---
name: ontology-discovery
description: 从文档、表结构发现实体类型、属性、关系、数据集、映射、指标、规则，判断新增还是复用已有定义，提出供审阅的增量提案。
---
# 建模路由

先定范围：概念经用户确认后，再按清单展开属性、关系、实例。

先运行 `"$DATAAGENT_PYTHON_BIN" .claude/skills/ontology-discovery/scripts/init_workflow.py --work-pack <工作包>`（有 prior_plan_file 加 `--prior-plan <prior_plan_file>`），照抄它打印的路径、模板和命令，不必列目录或读源码。

再只读当前一个步骤文件：
- 会新增概念，无 prior_plan_file：[计划](references/steps/plan.md)，列概念写待确认后结束，不写提案。
- 不加材料的整体优化，无 prior_plan_file：[优化](references/steps/optimize.md)。
- 有 prior_plan_file 且前轮是概念清单：[抽取](references/steps/extract.md)。
- 不新增概念的小改动，或前轮是问题清单：[增量](references/steps/incremental.md)。

写完片段读[收尾](references/steps/finish.md)。
