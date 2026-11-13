# 外部智能体接入步骤一试点记录

日期：2026-11-13。对应[实施计划](2026-11-11-runtime-agnostic-semantic-layer-plan.md)步骤一。环境：本机隔离运行，SQLite，仓库自带虚构演示空间“星港销售”（第 1 版），自定义固定令牌（`ONTOFOUNDRY_MCP_TOKEN`）接单空间入口 `/api/v1/ontology/workspaces/<id>/mcp`。

## 结果

| 计划项 | 结果 |
|---|---|
| 1. 协议 | `initialize` 协商到 `2025-06-18`，`tools/list` 返回 `search_ontology`、`get_ontology`、`search_objects`、`resolve_entity`、`get_object`。 |
| 1. Claude Code 接入 | `claude -p --strict-mcp-config --mcp-config <文件> --plugin-dir plugins/ontofoundry`（Claude Code 2.1.323）：MCP 状态 `connected`，Skill `ontofoundry:ontology-grounding` 加载。 |
| 2. 外部 Skill 与插件 | 已建 `plugins/ontofoundry/`（清单、`.mcp.json`、`skills/ontology-grounding/SKILL.md`、README）和根目录 `.claude-plugin/marketplace.json`；`claude plugin validate` 对插件和插件目录均通过（目录展示类提示如图标、隐私链接不影响加载）。 |
| 3. 只配 MCP 的路径 | 问“销售额怎么定义，按客户统计的 SQL”：先调用 Skill，原句检索，只读取 5 个相关元素（含 `physical`），回答给出空间、版本、物理表和参考 SQL；本体中客户没有数据绑定、`buyer` 关系没有关联字段，智能体说明缺项并追问，没有编造 JOIN。6 轮，约 22 秒。 |
| 3. 挂查询工具的路径 | 未做：本机没有可用的查询平台。留到现场或步骤二联调。 |
| 4. Codex（2026-11-13 补充，codex-cli 0.166.0） | Skill 复制到临时项目的 `.agents/skills/` 后被自动发现并读取；MCP 用 `-c mcp_servers.ontofoundry.url=…` 和 `bearer_token_env_var` 接入，未改动本机 `config.toml`。同一问题下调用 `search_ontology`（原句）和 `get_ontology`（4 个元素），回答给出空间、版本和定义，同样说明客户关联缺失、不猜 JOIN。 |
| 4. 三种客户端安装 | Claude Code 只验证了 `--plugin-dir` 加载，未在真实配置中执行 `/plugin marketplace add`（会改动本机用户配置）。ZCode、opencode 未验证，需要装有客户端的人按 README 操作；ZCode 是否读取 `.claude-plugin/marketplace.json`、ZCode 中令牌如何提供仍是待验证项。 |

## 发现与对步骤二的影响

- **服务说明**：单空间入口 `initialize` 返回的 `instructions` 写着“数据库聚合由 DataAgent 自有查询工具执行”，对外部客户端不准确。网关入口应使用自己的说明（定义来自 OntoFoundry，取数用客户端自己的查询工具）。
- **空间名称**：单空间入口没有空间名称，智能体只能从库名推断是哪个空间。网关的 `list_spaces` 提供名称和版本，Skill 第 1 节已按网关编写。
- **演示数据**：演示空间的客户、订单没有数据绑定，适合验证“缺定义不臆造”，但不足以验证按维度取数。联调前补一个指标、维度、数据集绑定齐全的虚构空间。
- **插件配置**：`.mcp.json` 已按设计使用 `${user_config.ontofoundry_mcp_url}` 和 `${user_config.ontofoundry_token}`（敏感项），步骤二只需把地址指向网关、令牌换成个人令牌，插件文件不用再改结构。

## 待人工完成

1. 在装有 Claude Code 的机器上：`/plugin marketplace add <仓库或本地目录>`，安装 `ontofoundry`，按提示填写地址和令牌。
2. ZCode：添加插件目录（GitHub 或本地目录），确认是否识别 `.claude-plugin/marketplace.json`，以及令牌的填写方式。
3. opencode：按 README 指向 Skill 目录并写入 `opencode.json` 的 MCP 配置。

结果补回本记录；ZCode 两项不通过时先改设计第 8 节，再进入步骤二。
