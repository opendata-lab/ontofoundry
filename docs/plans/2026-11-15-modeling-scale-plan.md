# 表多时降低建模成本实施计划

设计见[表多时降低建模成本、补上语义质量](../design/2026-11-15-modeling-scale.md)。一个 PR，涉及平台后端一处和 DataAgent 共享脚本与技能，不改前端和本体模型。预计 2 至 3 个工作日。

## 任务

1. **初始化列出表**（MS-05）：`shared/scripts/init_workflow.py` 改读工作包指向的表结构文件，每表一行；外键优先用表结构里的 `foreign_keys`，没有时按“列名等于另一张表的单列主键”给候选；取值候选按注释“：甲/乙/丙”识别。修复读取不存在的 `pack["tables"]`。
2. **展开脚本**（MS-01、MS-03）：新增 `shared/scripts/expand_tables.py`，按设计第 3 节第 2 条生成 01、03 中的机械部分；扩展 `shared/references/examples/protocol/entities.json`；`build_packages.py` 打包新脚本。
3. **平台补列**（MS-02）：在提案提交的校验之前，按运行清单表快照给缺列的表数据集补列；落点为 `services/table_submission.py` 的 `prepare_table_submission`（已按快照定位每个表数据集）。本地检查不读数据集列，不需补列。
4. **覆盖检查**（MS-04）：`check_part.py` 增加材料覆盖和语义清单对照，只提醒。
5. **技能文本**（MS-04、MS-06）：`ontology-discovery` 的 `plan.md`、`extract.md`，共享 `extract-kit/guide.md`（关联表写法、三条语义要点）、`03.json`（表数据集不写列）；`quick-reference.md` 同步。运行 `integrations/dataagent/scripts/offline_budget.py`。
6. **测试**：
   - `integrations/dataagent/tests`：表目录打印；展开结果与星河 conservative 夹具在 01、03 上语义等价；手写条目放 01b、03b；值类型只按确认清单生成；重名前缀；覆盖检查只在检查 04 时列出未引用的口径行和未兑现的计划、不影响退出码。
   - 后端：表数据集不带列可提交并补齐；映射引用不存在的列仍报错；自填的列仍被同步的表结构取代。
   - 全部修改完成后统一运行后端测试、`make lint` 和 DataAgent 集成测试。
7. **同步**：按 `integrations/dataagent/README.md` 打包并复制到 DataAgent 的 `SKILLS_ROOT_DIR`，重启。

## 验收

按设计第 4 节，在隔离的 DataAgent（:8902）上跑星河（全量＋增量）和青禾（全量）各 2 次，用 `apps/api/evals/acceptance/tool_stats.py` 统计，按 `qinghe-scale/README.md` 的质量参照逐项核对，结果存档到 `apps/api/evals/acceptance/results/`。预计费用 ¥1–1.5。

## 发布与回退

技能与平台可分开回退：平台补列向后兼容（带列的提案照旧）；技能回退到上一版即恢复手写。
