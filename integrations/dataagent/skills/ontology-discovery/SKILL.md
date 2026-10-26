---
name: ontology-discovery
description: 从文档、表结构发现实体类型、属性、关系、数据集、映射、指标、规则，判断新增还是复用已有定义，提出供审阅的增量提案。
---
# 建模路由

先定范围：新概念经用户批准后，再按清单展开属性、关系、实例。

先用 `"$DATAAGENT_PYTHON_BIN"` 运行本技能目录下的 `scripts/init_workflow.py --work-pack <工作包>`，照抄它打印的路径、模板和命令，不必列目录或读源码。

再只读当前一个步骤文件：
- 会新增概念：[计划](references/steps/plan.md)，获批准后同一运行接着读[抽取](references/steps/extract.md)。
- 不加材料的整体优化：[优化](references/steps/optimize.md)，获批准后接着读[增量](references/steps/incremental.md)。
- 不新增概念的小改动：[增量](references/steps/incremental.md)。

写完片段读[收尾](references/steps/finish.md)。
