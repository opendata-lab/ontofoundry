# 工具与脚本给 Agent 的报错格式

日期：2026-10-23。状态：格式已由用户确认（2026-10-23）；技能侧已实现，DataAgent 侧待做。范围：`integrations/dataagent/shared/scripts/` 的全部脚本，以及 DataAgent 运行时返回给模型的拒绝、截断、清理、落盘提示。

## 1. 背景

真实运行中，多数无效轮次来自看不懂或跟不上的报错：读表超限只说“缩小范围”，Agent 换了三种写法才读到；查写法的提示给出裸 `python` 加主机绝对路径，按原样执行会失败；上下文清理把“退出码 1”之后的具体原因一起删掉。Codex 集中审查（2026-10-23）列出约 45 处，High 9 处。

## 2. 参照的做法

- Anthropic《为 Agent 编写有效的工具》：报错要可操作，指出具体哪里错、正确写法是什么，不返回不透明的错误码或堆栈；输出被截断时，告诉 Agent 换什么更省的方式取数。
- Claude Code 自带工具：文件超过读取上限时，提示里给出实际大小、上限，以及用 offset/limit 分段或改用搜索；命令输出过大时落盘，提示里给出保存路径和预览，Agent 按路径再读。
- Manus 上下文工程：被压缩的内容必须可恢复，保留路径或原调用，Agent 知道去哪里找回。

共同点：Agent 看完一条报错，不用猜就能执行下一步。

## 3. 格式

```
错误 [CODE]：<发生了什么，具体原因，带实际值与上限>。<执行或保存状态>。下一步：<可直接复制的完整命令>
```

- 前缀两种：`错误 [CODE]` 表示这次调用失败或被拒绝；`提示 [CODE]` 表示调用成功但有需要知道的事（输出被截断、已折叠落盘、示例省略了依赖）。
- 原因带数字和单位：“输出 9655 字节，超过 8000 字节上限”，不写“过大”“超限”。
- 状态说清做了什么、没做什么：“未回显内容，源文件未改动”“候选文件未生成，最终文件未替换”“已保存到 modeling/checks/01-types.json”。落盘必须写完整相对路径。
- 下一步给完整命令，参数已经填好；能算出来的就算好（例如下一批读表的列范围），不让 Agent 自己拼。有多种走法时最多列 3 条，按推荐排序。
- 同参重试注定失败时直接说明“同参重试无效”（越界、权限、预算耗尽、技能安装缺文件），需要人处理的说明找谁。
- 需要业务决定的才让 Agent 问用户；技术错误不包装成业务问题。

## 4. 路径与命令

- 工作区文件写相对路径（`modeling/parts/01-types.json`），不输出主机绝对路径。
- 技能脚本按它实际所在的位置写：在工作区里用相对路径，不在就用技能目录的实际路径；不生成 `../`（沙箱会拒绝）。技能不依赖某个 Agent 运行时注入的变量。
- 技能目录由运行时告诉模型：参照 Claude Code 与 Agent Skills 约定，加载技能时返回“本技能目录”，SKILL.md 里的脚本写成相对本技能目录的路径（`scripts/init_workflow.py`），由模型拼出完整路径。DataAgent 的 Skill 工具目前只返回 SKILL.md 正文、不返回目录，需在 DataAgent 补上（见 §8）。
- 解释器沿用现有的 `$DATAAGENT_PYTHON_BIN`（DataAgent 沙箱要求），这是已有的运行时约定，本次不改。
- 参数按 shell 规则加引号。

## 5. 截断、折叠与清理

- 截断：说明保留了哪一段、省略了多少、怎样读下一段（给出下一段的完整调用）。
- 折叠落盘：写明保存的是什么（“本次返回的 120 行”，不说“完整结果”除非确实完整）、路径、取回调用。
- 上下文清理：占位写明原调用（工具名与参数，超长截断）和取回方式；没有保存的写“未保存，只读命令可按原调用重读”；有副作用的命令不建议重跑。
- 历史报错压缩只去掉堆栈，保留具体原因和下一步。

## 6. 原因码

原因码用英文大写，跨脚本、跨两套运行时统一，例如：

| 码 | 含义 |
|---|---|
| OUTPUT_TOO_LARGE | 输出超过单次上限 |
| FILE_NOT_FOUND / JSON_INVALID | 文件不存在 / JSON 无法解析（带行列） |
| INVALID_ARGUMENT | 参数不合法（指出哪个参数、收到什么） |
| DUPLICATE_REF | client_ref 重复 |
| PATH_OUT_OF_SCOPE / PARENT_SEGMENT | 路径越界 / 含 `..`（同参重试无效） |
| REPAIR_BUDGET_EXHAUSTED | 修正次数用完（停止修正） |
| CONTEXT_CLEARED / RESULT_FOLDED | 上下文已清理 / 大结果已折叠落盘（提示） |

完整清单随实现维护在脚本的公共模块中，测试检查每条报错都带前缀、原因码和“下一步”或“同参重试无效”。

## 7. 示例

| 场景 | 改前 | 改后 |
|---|---|---|
| 读表超限 | 范围超过 8 KiB；缩小 --start/--end、--pointer 或分批 --tables | 错误 [OUTPUT_TOO_LARGE]：t1 的 240 列共 9655 字节，超过单次 8000 字节上限。未回显内容，源文件未改动。下一步：`"$DATAAGENT_PYTHON_BIN" .claude/skills/ontology-discovery/scripts/read_input.py uploads/tables.json --tables t1:1-120`，再读 `t1:121-240` |
| 合并时重名 | /items/65/client_ref PREPARE_INPUT；期望不重复的 client_ref | 错误 [DUPLICATE_REF]：modeling/parts/04-metrics-rules.json 第 3 项的 client_ref prescription_total_amount 已在 01-types.json 中使用。候选文件未生成，最终文件未替换。下一步：把 04 中的这个名字改成别的（如 prescription_total_amount_metric）后执行 `…check_part.py --work-pack uploads/pack.json 04` |
| 上下文清理 | [Output evicted … re-run the original tool if it is needed again.] | 提示 [CONTEXT_CLEARED]：为控制上下文，已移除这次调用的输出：Bash `read_input.py uploads/tables.json --tables t1,t2`（约 7.2 KB）。未保存；这是只读命令，需要时按原调用重读。 |

## 8. 实施

1. ontograph：脚本公共模块提供 `error(code, reason, state, next)` 与 `notice(...)`，各脚本改用它；命令一律由 `command()` 生成。
2. DataAgent：Skill 工具在返回 SKILL.md 时附上“本技能目录”；运行时同样提供公共函数，先改清理、折叠落盘、越界拒绝、Bash 超时与截断；MCP 上游报错进入模型前脱敏。两套运行时（Claude Code、Pi）共用原因码。
3. 测试：每个脚本的报错路径各一条用例，断言前缀、原因码、相对路径和可执行的下一步。
