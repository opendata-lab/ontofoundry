# 业务动作定义实施计划

设计：[业务动作定义](../design/2026-11-27-action-types.md)。分三个 PR 依次交付，每个 PR 改完再统一跑测试。

- **PR A，整理种类清单（第 0 步）**：只整理确实等价的清单，不改变现有行为。
- **PR B，平台（第 1–6 步）**：做到动作一旦能发布，就能读回、能正确导出。用固定的提案文件验收，不依赖建模 Agent。
- **PR C，技能和插件（第 7 步）**：基于 PR B 稳定的契约，更新 DataAgent 技能和外部插件，并做安装后的端到端冒烟。

0. **整理元素种类清单（PR A）**：后端、技能脚本和前端里有十多份各自硬编码的种类清单。
   - 与 `domain/models.COLLECTIONS` 确实等价的，改成复用。
   - 有意只列一部分的（例如材料用量同时计入定义和文档实例，`import_matching` 的改名分组），保留原样，加断言写明它覆盖哪些种类、排除哪些以及原因。
   - 注意循环导入：`models` 已经导入图索引，所以图索引不能在模块顶层反向导入 `models`。
   - 这一步不改变任何现有行为，测试全部保持通过。
1. **模型与契约**：`domain/core.py` 增加 `Action`、`ActionParameter`、`ActionEffect` 和 `CoreDraft.actions`；更新 `contracts/` 的 JSON Schema 和前端类型；在 `docs/concepts/` 增加动作概念说明，并更新 README 的对比表。把 `action` 加进 `COLLECTIONS`、`ElementKind`、图索引和身份登记。规范化器登记 `actions`（按 `id` 排序）、`parameters` 和 `effects`（保持原顺序）；空的 `actions` 不输出。测试三种情况：缺省与显式空集合的哈希一致、旧快照哈希不变、非空动作能计算各类哈希。
2. **校验与依赖**：按设计 §3.2 实现命名（`casefold`）、引用、效果作用范围和继承规则。把动作的引用路径接入 `walk_references` 和 `reference_index`，覆盖同批 `client_ref`、导入重映射和删除检查。
3. **提案、差异与合并**：提案支持 `target_kind: action` 的 create、update、delete；`parameters`、`effects` 保持原顺序。补正例和反例。
4. **读取与 MCP**：`authorized_snapshot` 清空动作证据；HTTP 版本展示和元素详情返回动作；`search_ontology`、`get_ontology` 的 `inputSchema` 和检索候选加入 `action`。对象类型结果附带沿祖先链推导的动作摘要，HTTP 和 MCP 共用同一个函数。
5. **Ossie 与原生包**：只有全局动作、没有对象类型的模型，Ossie 导出照旧报错，原生包能往返；两种情况分别测。读写 `ontofoundry-extension.json` 的 `actions`，测试往返；只要一个引用解析失败，就整条不导入并报告。纯 Ossie 的损失由导出方报告，并登记到核心设计 §7 例外表。原生完整包单独测试 UUID、引用、证据的往返。
6. **前端**：对象详情的动作区、全局动作列表、提案工作台的“动作”分类、“仅定义”标签。按 AGENTS.md 在 1440×900 下截图对比，并运行 `npm run test:visual`。
7. **建模技能**：`ontology-discovery` 增加动作抽取说明和一个例子，不超出字节预算。`generate_output_schemas.py` 的 `TARGETS` 加 `action`，重新生成 Schema。冒烟用重新打包、安装到本地 DataAgent 的技能来跑。

验证（PR B 用固定提案文件，PR C 用安装后的技能）：
- 后端和前端全量测试、类型检查、构建。
- 端到端冒烟：在本地用一份含“派单”制度的虚构材料建模，接受提案、发布，再经 MCP `get_ontology` 读到动作和参数；导出 ZIP 后重新导入，动作仍在。
