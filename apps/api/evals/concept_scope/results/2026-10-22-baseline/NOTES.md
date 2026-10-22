# 概念范围评测 · 第一份基线（2026-10-22 22:05）

版本：main `22e5997` 起的三技能（ontology-discovery、entity-extraction、semantic-grounding），建模 Agent 提示词版本 10。DeepSeek 低峰时段，本地平台 + DataAgent。只跑计划轮，不回复确认。诊所场景另同步 `eval_clinic` 八张空表（含汇总表 daily_visit_stats）。

| 场景 | 准确率 | 召回率 | 实例当概念 | 例子归位 | 轮数 | 用时 | 输出 token | 工具报错 |
|---|---|---|---|---|---|---|---|---|
| wind_inspection | 1.0 | 7/7 | 0 | 11/11 | 11 | 111 秒 | 7805 | 1 |
| contract_approval | 1.0 | 6/6 | 0 | 10/10 | 9 | 111 秒 | 8026 | 1 |
| clinic_booking | 1.0 | 7/7 | 0 | 9/9 | 14 | 161 秒 | 13485 | 1 |

结论：当前难度下概念范围全对，汇总统计表没有被当成概念，具名实例全部作为例子归位。题目偏基础，按用户决定（EV-08）在技能继续提升后提高难度，并另建不公开的留出场景。

工具报错（各 1 次，均不影响结果）：

- clinic_booking：用 shell 写 JSON 时内容含“许医生/唐医生”，DataAgent 沙箱把 `/唐医生` 当成工作区外绝对路径拦截。
- contract_approval：计划轮调用了 `show_example.py` 且类型名不存在；计划步骤本不需要写法示例。
- wind_inspection：开局列 `output/` 目录，目录尚不存在。

花费：0.31 元（DeepSeek 余额 8.19 → 7.88，三个场景合计）。

文件：`summary.json`；各场景 `score.json`（逐项判定）、`plan.json`（Agent 的概念清单原件）、`conversation.json`（完整对话，本机路径已替换为 `~`）、`answer.md`；`run-output.json` 为运行脚本当时的输出。
