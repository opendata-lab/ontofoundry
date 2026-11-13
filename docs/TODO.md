# 待办清单

记录已确认要做、但当前不做的事项。

- 新的待办追加到这里，不另建零散的 TODO 文件。
- 每条写清楚现状、要做什么、来源（含日期）。
- 开工时，中大型变更先按 AGENTS.md 写 `design/` 和 `plans/`，并在这里附链接。
- 做完后移到文末“已完成”，保留结果链接。

已有的专项待办：[Ossie 上游结构跟进](plans/2026-10-20-ossie-upstream-alignment-todo.md)。

## 本体 MCP

已出台专项设计与实施计划：
- 设计：[面向外部智能体（zcode 等）的运行时无关本体语义层设计](design/2026-11-11-runtime-agnostic-semantic-layer-for-agents.md)
- 计划：[运行时无关本体语义层（面向外部 Agent）实施计划](plans/2026-11-11-runtime-agnostic-semantic-layer-plan.md)

来源：2026-10-28 对照 Palantir Ontology MCP 文档（链接见文末“参考”），以及 2026-11-11 针对 zcode 等外部智能体消费本体语义与版本更新的讨论。

### Palantir 中 Agent、MCP、本体的关系（参考）

| 关系 | Palantir 的做法 | 依据 |
|---|---|---|
| 本体与空间 | 一个空间对应一个本体（1:1）；私有空间对应私有本体，共享空间对应跨组织的共享本体。官方明确说“和其他团队合作不是新建第二个本体的理由”，团队之间用项目角色控制权限 | 文档原文 |
| MCP 服务器与本体 | 一个 MCP 服务器就是一个 Developer Console 应用。建应用时选一个本体，SDK 生成后不能再改；在这个本体里挑要暴露的对象类型、动作类型、查询函数，并可限制只读写指定项目里的资源 | 文档原文 |
| Agent 与 MCP 服务器 | 文档写的是“可以组合多个 MCP 服务器”，并列出环境里的所有 Ontology MCP 服务器（MCP Hub） | 文档原文 |
| 一个 Agent 跨多个本体 | 没有专门机制，也没有“一个应用含多个本体”的说法。推断是连多个 MCP 服务器，每个服务器对应一个本体 | 推断，文档未直接写 |
| Agent 作为工具 | 平台内的 Agent（AIP Chatbot，原名 AIP Agent）可以保存成函数，再经 MCP 作为工具暴露给外部 Agent | 文档原文 |

对应到我们：工作空间相当于 Palantir 的“空间加本体”，一个空间一个 MCP 地址（`/api/v1/ontology/workspaces/<id>/mcp`）。已有客户端可继续挂载各空间地址。2026-11-12 已确认新增个人令牌网关，首版支持工作空间目录和跨空间语义查询，见上方专项设计与计划。差别在于 Palantir 的一个 MCP 服务器只暴露手选的资源子集，我们暴露整个空间。

### 1. 工具按对象类型生成

- **现状**：MCP 只有固定的通用工具 `search_ontology`、`get_ontology`、`search_objects`、`resolve_entity`、`get_object`，由参数指定类型。暴露范围是整个工作空间。
- **Palantir**：对象类型通过一个 SQL 工具查询；每个动作类型、查询函数各是一个工具，工具描述可以在本体管理里按“给 Agent 看的描述”单独填写。暴露哪些资源在应用里挑选。
- **要做**：
  - 按对象类型生成工具（名称、描述、参数来自对象类型和属性）；
  - 每个 MCP 地址可以选暴露哪些对象类型；
  - 想清楚和现有通用工具的关系（保留检索类工具，还是全部替换）；
  - 评估对象类型很多时工具列表的 token 成本，以及工具列表变化后的通知。
- **待定**：工具粒度（每类型一个查询工具，还是统一 SQL 工具加类型说明）；我们没有动作类型（决定 #37），首期只有读。

### 2. 修改本体结构的 MCP 服务

- **现状**：建模的写入只走提案。Agent 产出结果文件，平台检查后入库，人工审阅后接受。MCP 只读。
- **Palantir**：结构修改由另一个 Palantir MCP 提供，70 多个工具，能改对象类型、关系类型、动作类型，但不能写业务数据；与面向使用者的 Ontology MCP 分开。
- **要做**：
  - 设计一个面向建模者的 MCP 服务（与只读的本体 MCP 分开），提供对象类型、属性、关系、值类型、规则、指标、数据集的增改工具；
  - 写入仍落成待审提案，并复用试应用的检查（[串行化与原子化](design/2026-10-26-serial-atomic-modeling.md)），不绕过审阅；
  - 和现在“运行结束交结果文件”的方式怎么并存或替代，需要先设计。

### 3. MCP 支持 OAuth

- **现状**：外部访问只用部署时配置的固定令牌（[固定 MCP 令牌](design/2026-10-22-fixed-mcp-token.md)），只读，按空间里最早加入的管理员做成员检查，所有调用方共用一个身份。
- **Palantir**：MCP 复用应用的 OAuth 2.0 配置，“没有单独的鉴权系统”。
  - 授权码方式代表用户，令牌按用户权限收窄，支持 PKCE（公开客户端必须使用）；
  - 客户端凭据方式用于服务对服务；
  - 申请 `offline_access` 才有刷新令牌，刷新令牌每用一次就轮换；
  - 令牌权限取三者交集：用户权限、应用上配置的限制、申请的操作范围（如 `api:use-ontologies-read`）。
  - 文档没有提到 MCP 授权规范里的受保护资源元数据和动态客户端注册。
- **要做**：
  - 平台作为 OAuth 2.0 授权方（或接入现有统一认证），支持授权码加 PKCE、客户端凭据和刷新令牌；
  - 令牌权限取用户权限、工作空间和操作范围的交集；
  - 评估是否实现 MCP 授权规范的受保护资源元数据，让 MCP 客户端自动发现授权地址；
  - DataAgent 侧代用户调用时如何传递用户身份（与 DataAgent 服务化架构的凭据设计一起考虑）；
  - 固定令牌是否保留为内网部署的简易方式。

## 已完成

（暂无）

## 参考

- [Ontology MCP 概览](https://palantir.com/docs/foundry/ontology-mcp/overview/)
- [Ontology MCP 鉴权与授权](https://palantir.com/docs/foundry/ontology-mcp/authentication-and-authorization/)
- [Ontology MCP 入门](https://palantir.com/docs/foundry/ontology-mcp/getting-started/)
- [Ontology MCP 示例架构](https://www.palantir.com/docs/foundry/ontology-mcp/sample-architecture)
- [MCP 工具与 Agent 配置](https://palantir.com/docs/foundry/ontology-mcp/mcp-tools-and-agent-configuration/)
- [Ontology MCP 示例工作流](https://palantir.com/docs/foundry/ontology-mcp/example-mcp-workflows/)
- [创建 Developer Console 应用](https://palantir.com/docs/foundry/developer-console/create-application/)
- [应用限制](https://palantir.com/docs/foundry/developer-console/application-restrictions/)
- [编写 Foundry OAuth2 客户端](https://palantir.com/docs/foundry/platform-security-third-party/writing-oauth2-clients/)
- [本体概览（本体与空间 1:1）](https://palantir.com/docs/foundry/ontologies/ontologies-overview/)
- [共享本体](https://palantir.com/docs/foundry/ontologies/shared-ontologies/)
- [组织与空间](https://palantir.com/docs/foundry/security/orgs-and-spaces/)
- [AIP Chatbot Studio 工具](https://palantir.com/docs/foundry/chatbot-studio/tools/)
- [Palantir MCP 概览](https://www.palantir.com/docs/foundry/palantir-mcp/overview)
