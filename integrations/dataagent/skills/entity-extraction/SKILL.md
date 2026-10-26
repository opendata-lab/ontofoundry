---
name: entity-extraction
description: 按已有本体约束从文档抽取文档实例、属性值和关系实例，核对身份、引用与原文证据；材料包含具体对象或具体关系陈述时使用，可与 ontology-discovery 在同一运行中组合。
---
# 实例抽取路由

实例抽取以已批准的概念为前提：具体事物要落到批准过的类型上，类型范围先经用户批准，抽取才不返工。

- 要用到的类型缺失时，先按 ontology-discovery 计划步骤列概念并提交计划，获批准前不写定义或实例。
- 类型齐全时读[实例抽取](references/steps/facts.md)，片段写完后读[收尾](references/steps/finish.md)。

脚本在本技能目录的 `scripts/` 下，用 `"$DATAAGENT_PYTHON_BIN"` 运行，stdout≤8 KiB，同回合多条调用，不拼接输出。
