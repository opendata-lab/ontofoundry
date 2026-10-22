# 2026-10-22 计划步骤精简后回归（main ee82ac1）

计划步骤从 2000 余字节压到约 1300 字节、计划路线从 18.6K 压到 14.8K 后，重跑 5 个公开场景。DeepSeek 余额 7.10 → 6.15 元。

| 场景 | 准确率 | 召回 | 例子归位 | 轮数 | 输出 token | 用时(s) | 精简前轮数 |
|---|---|---|---|---|---|---|---|
| wind_inspection | 1.0 | 7/7 | 9/11 | 10 | 14725 | 161 | 11 |
| contract_approval | 1.0 | 6/6 | 10/10 | 16 | 10993 | 151 | 9 |
| clinic_booking | 1.0 | 7/7 | 9/9 | 11 | 9731 | 131 | 14 |
| adv_property_repair | 1.0（离线补评） | 7/7 | 6/6 | 12 | 10050 | 131 | 10 |
| adv_training_courses | 1.0 | 6/6 | 10/10 | 11 | 13563 | 171 | 10 |

## adv_property_repair 自动评分为 0 的原因

Agent 识别的 7 个概念全部正确，但把概念清单写到了 `modeling/parts/entities.json`；平台只从 `modeling/entities.json` 读取计划，于是保存的计划里没有清单（`plan.json` 只有 plan.md），自动评分为 0。若用户此时回复“确认”，抽取轮也拿不到清单。

原因是初始化输出只写了“片段写 modeling/parts/”，没写概念清单的位置，plan.md 模板也只写“见 entities.json”。已修正：初始化输出单列“概念清单写 modeling/entities.json（与 plan.md 同级，不放 parts/）”，模板和计划步骤都写完整路径。

`entities-misplaced.json` 是从 DataAgent 工作区取回的原文件，`score-offline.json` 是对它的离线打分。

## 结论

- 概念识别没有因精简退化：5 个场景全对。
- 轮数与 token 没有明显下降（contract_approval 反而多了 7 轮），精简的收益主要在读入字节，不在轮数。
- wind_inspection 例子归位 9/11，比基线少 2 个。
