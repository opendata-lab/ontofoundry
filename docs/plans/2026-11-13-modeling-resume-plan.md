# 建模失败后续做修正实施计划

设计见[建模失败后续做修正](../design/2026-11-13-modeling-resume.md)。一个 PR，涉及平台后端、DataAgent 共享脚本与技能、构建页提示。预计 2 至 3 个工作日。

## 任务

1. **基线摘要**：`services/modeling_input.py` 计算基线（发布版本 ID 与摘要、会话草稿摘要、材料清单摘要、表范围与结构摘要、实例基线），写入 `run_manifest_json.baseline`；摘要只用已有字段计算，不新增表和列。
2. **续做判断**：`api/agent_conversation.py` 在新消息替换运行清单前，按设计第 4 节第 1 条判断；符合时在工作包 `run.resume` 写入上一轮令牌。入库批次按上一轮令牌查询（`submitted_batch`）。
3. **初始化**：`integrations/dataagent/shared/scripts/init_workflow.py` 按设计第 4 节第 2 条保留或整体归档 `parts`、`checks`、`plan`、`notes`，续做时打印提示；同步更新共享步骤文件中“本轮从空目录开始”的说明。
4. **技能路由**：`skills/ontology-discovery/SKILL.md` 增加续做入口；`shared/references/steps/finish.md` 写明续做时按上次检查报告只改报错片段、计划模式先提交修正计划；提交成功后片段移出活动目录。
5. **提示改正**：`services/proposal_submit.py` 的 `REPAIR_BUDGET_EXHAUSTED` 消息按 MR-04 改写。
6. **构建页**：结果为失败且未提交时，在结果区显示设计第 3 节的提示文案。界面改动按 AGENTS.md 截图对比并运行 `npm run test:visual`。
7. **测试**：后端（基线相同且未入库时写 `resume`；草稿、材料、表、实例任一变化不写；上一轮已入库不写；会话修订号变化不影响判断）；`integrations/dataagent/tests`（把现有“新令牌必归档”测试改为条件测试：续做保留四类文件、非续做整体归档、片段缺失时提示并归档；提交成功后片段移出）；前端提示显示条件。全部修改完成后统一运行后端测试、`make lint`、DataAgent 集成测试和前端测试。
8. **同步**：技能和脚本改动后按 `integrations/dataagent/README.md` 复制到 DataAgent 的 `SKILLS_ROOT_DIR` 并重启。

## 验收

见设计第 5 节。另用一个虚构的大会话手工验证一次：故意让一个映射引用不存在的列，修正轮次用完后发送“继续”，确认新运行不重新读材料、只修该映射后提交成功，并记录前后两次运行的模型轮次和耗时（DataAgent 逐轮用量事件），作为后续优化的基线数据。

## 发布与回退

不改数据库结构。回退时恢复上一版脚本和技能即可；已保留在工作区的片段在下一次非续做运行时被整体归档。
