# 建模失败后在已有成果上继续实施计划

设计见[建模失败后在已有成果上继续](../design/2026-11-13-modeling-resume.md)。一个 PR，涉及平台后端和 DataAgent 共享脚本与技能，不改前端。预计 2 至 3 个工作日。

## 任务

1. **基线摘要**：`services/modeling_input.py` 计算基线（会话基版本 ID 与摘要、会话草稿摘要、材料清单摘要、表范围与结构摘要、实例基线），写入 `run_manifest_json.baseline`；只用已有字段计算，不新增表和列。
2. **保留判断**：`api/agent_conversation.py` 在新消息替换运行清单前，按设计第 3 节第 1 条判断，在现有会话锁和空闲门禁之内；符合时在工作包 `run.resume` 写入上一轮令牌。入库批次按上一轮令牌查询（`submitted_batch`）。
3. **初始化**：`integrations/dataagent/shared/scripts/init_workflow.py` 按设计第 3 节第 2 条的三步顺序处理六类工作文件，续做时打印摘要；新增 `--restart` 选项供技能主动归档后从头开始；同步更新步骤文件中“本轮从空目录开始”的说明。
4. **检查报告留档**：`prepare_result.py`、`check_result.py` 按设计第 3 节第 3 条另存最近一次内容检查报告。
5. **续做步骤与路由**：新增 `shared/references/steps/resume.md`（按 MR-03 选择四种做法，列出判断依据和例子，计划模式先提交计划）；`skills/ontology-discovery/SKILL.md` 和 `skills/entity-extraction/SKILL.md` 在初始化打印续做摘要时先读该步骤；`entity-extraction` 的实例步骤不再无条件重写 `05-facts.json`。
6. **提交成功后归档**：`prepare_result.py` 收到通过回执后把本次提交的片段和范围文件移到 `modeling/submitted/<令牌>/`，失败只记日志。
7. **提示改正**：`services/proposal_submit.py` 的 `REPAIR_BUDGET_EXHAUSTED` 消息按 MR-06 改写。
8. **测试**：
   - 后端：基线相同且未入库时写 `resume`；草稿、材料、表、实例任一变化不写；上一轮已入库不写；会话修订号变化、其他会话发布新版本不影响判断；取消、超时同样可保留。
   - `integrations/dataagent/tests`：把现有“新令牌必归档”测试改为三步条件测试；同令牌重复初始化保留；续做保留六类文件并打印摘要；非续做整体归档；`--restart` 归档；检查报告留档不被预算拒绝覆盖；提交成功后归档、归档失败仍报告入库。
   - 全部修改完成后统一运行后端测试、`make lint` 和 DataAgent 集成测试。
9. **同步**：技能和脚本改动后按 `integrations/dataagent/README.md` 复制到 DataAgent 的 `SKILLS_ROOT_DIR` 并重启。

## 验收

见设计第 4 节。另用一个虚构的大会话手工验证：故意让一个映射引用不存在的列，修正轮次用完后分别发送“继续”和“不要生成指标”，确认 Agent 不重新读材料、按消息分别只修映射或删掉指标后提交成功；记录前后运行的模型轮次和耗时（DataAgent 逐轮用量事件），作为后续优化的基线数据。

## 发布与回退

不改数据库结构。回退时恢复上一版脚本和技能即可；保留在工作区的文件在下一次非续做运行时被整体归档。
