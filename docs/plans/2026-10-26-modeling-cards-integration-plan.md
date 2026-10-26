# 建模接入问题卡片与计划卡片：实施计划

设计：[会话模式](../design/2026-10-25-session-modes.md) SM-03。卡片本身由 DataAgent 提供，需求见 opendataworks 仓库 `docs/design/2026-10-25-dataagent-plan-and-question-cards-design.md`。

## 1. 现状

- 建模有新概念时分两轮：
  - 第一轮写概念清单（`modeling/entities.json`）和待确认文件 `output/ontofoundry-needs-input-<run_token>.json`，然后结束；
  - 平台看到待确认文件，把会话标成 `awaiting_reply`，并把计划存进 `run_manifest_json.prior_plan`；
  - 用户随便回一句话就算确认。第二轮平台把计划上传成 `prior_plan_file`，技能用 `init_workflow.py --prior-plan` 恢复后再抽取。
- 整体优化同样分两轮：问题清单加待选择文件。
- 输入框没有计划开关，构建页右侧栏只显示提案。

## 2. 改后

一次运行完成，确认发生在运行中间：

1. 建模模式下，输入框的“计划”开关默认打开，消息带 `settings.permission_mode = "plan"`。BFF 只接受 `plan` 和 `default` 两个值，转给 DataAgent 的 `deliver-message`。
2. 计划模式下，技能先只读调研，把概念清单（或优化的问题清单）写成 Markdown，调用 `ExitPlanMode` 提交：
   - 用户点“是，开始执行”：同一个运行接着写 `modeling/plan.md`、`entities.json` 并抽取，最后产出提案；
   - 用户点“先调整计划”：修改意见回到模型，模型改完再次提交。
3. 拿不准的取舍用 `AskUserQuestion` 提问，每题标一个推荐项。超时按推荐项继续。
4. 开关关闭时不提交计划，技能直接按自己判断的范围抽取，在回答里说明范围。
5. 展开计划时，构建页在右侧栏显示全文：顶部是计划标题和下载、复制、关闭按钮。关闭后回到提案。

删除：
- 待确认文件和它的模板；
- `awaiting_reply` 状态；
- `prior_plan`、`prior_plan_file`、`init_workflow.py --prior-plan`；
- 构建页“请在对话中回复”的提示。

没有结果文件的运行一律按“没有产出提案”失败。不兼容旧会话：停在 `awaiting_reply` 的旧会话，下一条消息按新流程重新开始。

## 3. 任务

### T1 BFF

- `ConversationMessageRequest` 增加 `settings`，只取 `permission_mode`。日常模式不传；建模模式不传时按 `default`。
- `DataAgentClient.deliver` 增加 `permission_mode`。
- 删除 `prior_plan` 读取和上传、`needs_input_file`、待确认文件下载与 `parse_questions`、`saved_plan`，以及 `UNSETTLED_RESULT_STATES` 里的 `awaiting_reply`。
- 本轮提示去掉“待确认：…”一行。

### T2 构建页

- 建模模式给对话组件设 `composerConfig.planMode = {enabled: true, default: true}`；日常模式不显示开关。
- 监听 `dataagent-plan-open`，调用 `preventDefault()` 后在右侧栏显示 `PlanPanel`：
  - 标题是计划标题，正文用 `body`；
  - 下载、复制（局域网 HTTP 下要有回退）、关闭三个按钮。
- 删除 `awaiting_reply` 提示。

### T3 技能

- `SKILL.md` 的路由改为：
  - 会新增概念：计划步骤。计划模式下提交计划，获批准后在同一运行里接着读抽取步骤；
  - 整体优化：同理，获批准后接着读增量步骤；
  - 不新增概念的小改动：直接读增量步骤。
- `plan.md`、`optimize.md`：只读调研；清单写进 `ExitPlanMode` 的计划，获批准后再写 `modeling/` 工作文件；拿不准的点用 `AskUserQuestion`。
- `extract.md`、`facts.md`、`incremental.md`：去掉 `prior_plan_file` 和“前轮”的说法。
- `init_workflow.py`：去掉 `--prior-plan` 和待确认模板，保留概念清单和问题清单两个模板。
- 删除 `needs-input*.json` 模板，同步 `catalog.json`、测试、`offline_budget.py` 和提示快照。

### T4 Agent 与部署

- `agents/agent_ontofoundry.md`：说明计划模式的用法；部署说明里写明，在 DataAgent 建模 Agent 的高级设置中，“计划等待超时后”保持“继续等待用户确认”：计划不自动批准（2026-10-26 用户确认）。
- 新会话验收（技能和提示改动后，真实运行要用新会话）。

### T5 评测

- `evals/concept_scope/run.py` 改为：消息带 `permission_mode = plan`；任务停在 `waiting_permission` 时，从计划卡片记录取计划并打分；带 `--extract` 时通过 `/interactions` 批准，等待同一运行产出提案。

### T6 验证

- 后端 `pytest`、前端 `vitest`、`npm run build`、`npm run test:visual`，技能 `integrations/dataagent/tests`。
- 构建页在 1440×900 下截图，检查右侧计划栏。
- 真实模型验收一次（先征得用户同意）：新会话、建模模式，经历提问、计划、调整、批准，最后产出提案。
