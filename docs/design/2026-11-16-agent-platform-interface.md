# 智能体与平台接口：一条变更管线，技能做薄

日期：2026-11-16。状态：方向已定，待实施。来源：用户 2026-11-16 提出——人工与智能体的工作阶段不同，是否应统一；检查应在接口里，技能做薄；智能体知道 schema 后，示例是否还需要；现有接口不满足高内聚、低耦合。要求不过度设计。评审：Gemini 4 Argon（`~/.agents/handoffs/2026-11-16-gemini-agent-interface-arch*/`、`2026-11-16-gemini-api-design/`）、Codex 两轮（`2026-11-16-codex-agent-interface-review*/`），Claude 核对源码后合并；评审中有误的结论未采用。

## 1. 现状与问题

| | 人工 | 智能体 | 导入 |
|---|---|---|---|
| 写入 | `POST /workspaces/{w}/element-saves`（立即发布）；`PUT /sessions/{s}` 直接覆写草稿；`resolve-merge` | `POST /ontology/workspaces/{w}/runs/{run_token}/proposals` | `POST /modeling/workspaces/{w}/imports/...` |
| 检查 | 图校验、连接列、发布检查 | 技能本地检查 → 提交检查 → 接受时检查 → 发布检查 | 提交、接受、发布 |
| 留痕 | 无（不产生提案） | 提案、决定记录 | 提案、决定记录 |

1. **两套标准。** 接受时规则（AC-02～11）不作用于人工写入，人工可以发布智能体提案接受不了的内容。
2. **技能重写平台逻辑。** 约 790 行本地检查（`check_part`、`check_result`、`column_refs`、`function_refs`）只为节省提交轮次；`materials.py`、物理类型映射、表达式分词是平台逻辑的副本。
3. **接口分散。** 同一工作空间分在 `/workspaces/{w}`、`/ontology/workspaces/{w}`、`/modeling/workspaces/{w}` 三个前缀下；版本、实例、预览跨前缀；`api/modeling.py`（1 148 行）在路由里加锁、三方合并、提交事务，违反“`api/` 只做路由、校验和权限”。路径里的 `run_token` 与运行凭据重复。
4. **修改历史不完整。** 人工写入没有记录；提案行会被原地改写（状态、内容），本身不是历史。

## 2. 决定（用户 2026-11-16）

| 编号 | 决定 |
|---|---|
| AI-01 | **一条写入管线。** 人工保存、智能体提交、导入都转成提案（`items[]`），经同一服务检查和写入。人工保存在服务层转成提案并立即接受；前端编辑器仍提交编辑后的草稿。 |
| AI-02 | **保存不发布。** 所有写入只进草稿；发布按钮旁显示待发布数量。 |
| AI-03 | **虚拟会话。** 会话外的保存写入该用户在本工作空间的个人会话（`GET /sessions/personal`，按需创建、唯一）。它是普通会话：在列表中可见，可对话、建模、审提案。 |
| AI-04 | **接口按会话寻址，不同行为不同端点，不设 mode 参数，不设独立检查端点**；检查在写入端点内完成，失败不写任何东西。 |
| AI-05 | **智能体可以审人工修改。** 运行输入包含本会话未发布的修改与待审提案（before、after、依赖）。 |
| AI-06 | **撤销与退回待审跨批次级联。** 撤销一项时，所有未发布批次中依赖它的项、以及之后对同一元素的修改，按从新到旧一并撤销，结果列出全部被撤销项；退回待审同理（一并回到待审）。可以触及已只读的智能体批次；不触及已发布内容。 |
| AI-07 | **追加式变更记录表。** 提案层和草稿层的每次变化都记一行，含智能体对人工提案的修改。 |
| AI-08 | **提交时合并待审提案。** 有待审提案时智能体可以运行：同一目标的项替换原提案，新项加入，未提及的原样带入，形成新的待审批次，旧批次标为被取代。每个会话始终只有一个待审批次。被智能体改过的人工提案在卡片上标明。 |
| AI-09 | **两级检查。** 提案检查：结构、引用、图校验、条件必须是条件（AC-09）；失败不存，内容不完整可以存并标待补全。接受检查：提案检查加接受时规则（AC-02/03/04/07/10/11）；失败不进草稿。人工保存两级都做，全成或全不成。待补全按接受时实际展开的依赖与原子组计算。 |
| AI-10 | **修正轮次。** 每次运行最多 10 轮不同内容的提交；重复相同失败不计。 |
| AI-11 | **实例与定义同一生命周期。** 接受的文档实例、关系实例（新增、修改、删除）进入草稿，发布后才对外可见。现在新增实例在定义未变时直接生效、修改删除直接改现有记录，改为一律暂存：已有实例保留发布内容，另存本会话的待发布内容，发布时原子生效；需新增存储与迁移。检查不变（提案检查、接受检查、发布检查）。发布说明写明“接受的实例在发布后才对外可见”。 |
| AI-12 | **变更记录分提案层和草稿层。** 两者是不同的东西：提案可以变化而草稿不变（如智能体修订待审提案）。 |

## 3. 接口

工作空间内统一前缀 `/api/v1/workspaces/{w}`（下表省略）。`/api/v1/ontology/…` 前缀整体取消，MCP 也一并调整（用户 2026-11-16）：跨空间网关 `/api/v1/ontology/mcp` → `/api/v1/mcp`；可访问空间目录 `/api/v1/ontology/workspaces` → `/api/v1/mcp/workspaces`；单空间 `/api/v1/ontology/workspaces/{w}/mcp` → `/api/v1/workspaces/{w}/mcp`。

| 分组 | 端点 | 归属模块 |
|---|---|---|
| 会话 | `GET/POST /sessions`、`GET /sessions/personal`、`GET /sessions/{s}`、`PATCH /sessions/{s}`（只改标题、材料、表范围、模式）、`POST /sessions/{s}/abandon`、`/validate`、`/publish-preview`、`/resolve-merge`、`/publish` | `api/sessions.py` → `services/sessions.py` |
| 会话变更 | `POST /sessions/{s}/element-saves/preview`（保存前的影响确认清单）、`POST /sessions/{s}/element-saves`（人工保存，带 revision 与幂等键）、`POST /sessions/{s}/proposals`（只接受运行凭据，智能体提交；导入在服务层直接调用同一服务）、`GET /sessions/{s}/change-events?target_id=`（元素修改记录）、`GET /sessions/{s}/proposal-batches[/{b}]`、`POST /sessions/{s}/proposal-decisions`（接受、拒绝、恢复、退回待审）、`PATCH /sessions/{s}/proposals/{p}/after`、`PUT …/dataset`、`POST …/fact-revision` | `api/proposals.py` → `services/changes.py`（`check_proposal`、`check_accept`、`propose`、`accept`、`undo`） |
| 对话 | `/sessions/{s}/agent-conversation`（消息、事件、取消、交互） | 不变 |
| MCP | `POST /api/v1/mcp`、`GET /api/v1/mcp/workspaces`（不在工作空间前缀下）、`POST /mcp`（单空间） | `api/ontology_gateway.py`、`api/mcp.py` |
| 发布版本与本体 | `GET /versions`、`/version`（可不带参数取当前版本）、`/versions/{v}`、`/versions/{v}/presentation`、`/version-comparison`、`/types…`、`/type-graph/neighborhood`、`/catalog`、`POST /search`、`/entities/resolve`、`GET /exports/{adapter}…` | `api/ontology.py`、`api/exports.py` |
| 实例 | `GET /objects…`、`/instances…`、`/sessions/{s}/instances`、`/sessions/{s}/instance-baseline`、`POST /instance-neighborhood` | `api/instances.py` |
| 数据 | `/connections…`、`/registered-tables`、`POST /datasets/validate`、`/datasets/preview`、`/mapping-preview`、`/metrics/preview` | `api/connections.py`、`assets.py`、`datasets.py`、`metrics.py` |
| 材料与导入 | `/materials…`、`/imports/{adapter}…` | `api/materials.py`、`imports.py` |
| 工作空间 | `GET/PATCH ""`、`/overview`、`/capabilities`、`/members…`、`/users/search`、`/feedback`、`/settings/dataagent-health` | `api/workspaces.py`（并入 `settings.py`） |

鉴权：人工端点只接受登录；`POST /sessions/{s}/proposals` 只接受运行凭据，校验凭据中的工作空间、会话与用户编辑权限，保留“当前运行 → 同内容回执 → 活动状态 → 轮次与待审规则”的顺序，运行结束后仍可重取回执（迁自现有提交端点）。

MCP 不留转发：建模运行从运行输入取地址，交付页同步修改；所有服务端生成的地址同步改：空间目录返回的 `mcp_endpoint`（`api/ontology.py`）、DataAgent 问数的 MCP 登记模板（`integrations/dataagent/plugin.json` 的 `url_template`、`迁移说明.md`，并在 DataAgent 后台重新登记）、导出预览的 `download_url`（读取磁盘缓存后按当前路由重建）；外部客户端（`plugins/ontofoundry/` 由用户填写完整地址）需更新配置，发布说明写明“MCP 地址改为 /api/v1/mcp”，并同步插件与根 README。

直接删除（不留转发）：`runs/{run_token}/proposals`（技能只读 `submit_url`，平台改发新地址即可；发布说明注明升级时不要有进行中的建模）、工作空间级 `element-saves`、前端未用的 `/ontology`、`/published-snapshot`、`/proposal-metrics`、`/assets/refresh`、废弃的 `/connections/{c}/table-material`（同时删前端引用）。以后可选：`PUT/DELETE /sessions/{s}/elements/{kind}/{id}` 取代 `element-saves`。

## 4. 规则

1. **虚拟会话的读取与保存。** 会话外进入编辑时，先取个人会话的草稿、id 和 revision；保存必须带 revision，成功返回更新后的会话，不返回新版本。例：窗口甲保存后，旧窗口乙保存报“草稿已更新”。
2. **人工保存转提案。** 只基于锁定的会话草稿计算，不再在保存时合并最新发布版（否则会把其他会话发布的内容当成本会话的人工修改）；校验范围、证据和确认后，比较保存前后图，生成实际增删改；保留编辑器给的 UUID，人工证据作者由服务端核定；自动重写（如改英文名引起的表达式重写）也记为变更。同一元素再次保存，且中间没有其他已接受的修改时，更新同一条提案（保留首次修改前的值）；中间有其他修改（如智能体改过）则新建一条，保持撤销链按顺序可逆；改回原值则不再算未发布修改。检查、写提案、写草稿在一个事务里。参考导入直接构造提案的实现（`services/import_proposals.py`）。
3. **所有定义写入走管线。** `PATCH /sessions/{s}` 不再写定义；`resolve-merge` 中的人工选择经同一检查并留痕。
4. **发布关闭旧提案。** 发布前对最终合并结果中受影响的定义复用接受检查（另一会话先发布可能使合并结果不完整）；发布在同一事务里记录本会话的发布边界；边界前的提案只读，不能撤销、恢复、退回或修订。解决合并冲突只移动基线，不算发布。
5. **失败不留痕迹。** 提交失败不存提案、不改草稿；表结构收据先在内存参与检查，通过后才落盘（现在会在检查前写文件，`services/table_submission.py`）；只记修正轮次。
6. **幂等。** 人工保存带请求幂等键：同键同内容返回原结果，同键不同内容报错。智能体沿用现有运行回执。
7. **唯一待审批次的收敛。** 运行输入（`proposal_context`、工作包）包含未发布修改与待审提案。提交、恢复、退回待审都把结果并入会话唯一的待审批次（没有则新建）：同一目标的项替换原项，待审新增项沿用原 `target_id`（不按新批次重新生成），同一元素跨批次的连续修改折叠为“首次修改前 → 最新”一条；旧批次中的待审项标为被取代（提案状态、批次读取契约与计数同步增加该状态），已接受、已拒绝项保留以供撤销。合并后重算依赖与原子组，再做两级检查。导入补全走同一合并。
8. **个人会话唯一。** 按（工作空间，用户）唯一，并发创建在锁内去重；会话外新建元素保存后带个人会话 id 导航。

## 5. 变更记录表（AI-07）

```
change_events（只追加，不改不删）
  id, workspace_id, session_id, at
  actor_id, actor_kind        human | agent | import；智能体时 actor_id 为发起运行的用户，另记 run_token
  subject                     proposal | draft | version
  action                      proposal: created | revised | superseded | accepted | rejected | restored | back_to_pending
                              draft:    added | updated | removed
                              version:  published（会话级，target 为空）
  target_kind, target_id
  proposal_id, batch_id, version_id
  before, after               提案层：当时的提议内容与状态；草稿层：草稿中元素的前后内容
  cause_id                    触发本条的记录（级联撤销、接受带出的草稿变化）
```

只由变更服务写入，与变更在同一事务；测试保证没有更新、删除路径。一次操作可在两层各产生记录，例：接受订单 → 提案 accepted ＋ 草稿 added；撤销订单级联金额 → 两条提案 rejected ＋ 两条草稿 removed，后者 `cause_id` 指向撤销。元素“修改记录”视图只读这张表。合并冲突的处理不是发布，其中的人工选择按提案层与草稿层记录。提案、版本、决定请求表保留各自用途（当前审阅状态、发布快照、重试识别），不作为历史。

## 6. 技能变薄与示例

| 处置 | 文件 | 由谁接手 |
|---|---|---|
| 删除 | `check_part.py`、`check_result.py`、`column_refs.py`、`function_refs.py`＋函数清单生成（约 790 行） | 提交时检查（AI-09），失败返回全部错误，最多 10 轮 |
| 删除 | `materials.py` | 平台按行号补引文 |
| 删除副本 | 物理类型映射、`tests/test_platform_copies.py` | 平台在表结构文件里给出每列的值类型 |
| 精简 | `prepare_result.py`（518 → 约 150 行） | 合并片段、提交、把平台错误定位回片段 |
| 以后 | `show_element.py` | 运行中经 MCP 读本轮草稿 |

配套：平台先在生成证据 id 前按行号回填缺省 `quote`、在表结构文件中为每列给出 `value_kind`，然后才删技能里的副本；`atomic_write` 与集合常量迁入 `runpaths.py`，去掉 `expand_tables.py`、`runpaths.py` 对 `check_part.py`、`materials.py` 的调用；`show_element.py` 改从 `runpaths.py` 取常量；`test_platform_copies.py` 只删物理类型断言，分词断言保留到 `show_element.py` 下线。

示例只留 `extract-kit/`：补齐 `05.json`（一个文档实例、一个关系实例），少见写法合为一个变体文件，删除 `examples/` 下按类型、按操作的小示例和 `catalog.json`，同步精简 `show_example.py` 与 `services/modeling_input.py` 的示例清单；平台报错直接给出期望字段形状；保留的示例在测试中通过提交检查。

## 7. 实施顺序

1. **接口整理，不改行为：** 统一前缀与 MCP 地址（含所有服务端生成的地址）；智能体提交迁到 `POST /sessions/{s}/proposals`，保持现有鉴权、回执、检查与轮次；`publish-preview`、`fact-revision` 等改名；按资源归属模块，锁与三方合并原样下沉服务层；删除确无生产调用的端点（`/ontology`、`/published-snapshot` 路由删、内部快照函数保留，`/proposal-metrics`、`/assets/refresh`、`table-material`）；同步 `client.ts`、文档与契约测试。
2. **写入管线：** `services/changes.py` 两级检查；`element-saves[/preview]` 迁入会话并删除工作空间级入口、`PUT` 收窄为 `PATCH`；人工保存转提案、虚拟会话、保存不发布、待发布数量；实例同一生命周期（AI-11，含存储迁移）；`PATCH` 与 `resolve-merge` 收口；发布边界；变更记录表与元素修改记录视图；撤销与退回待审跨批次级联；提交时合并待审提案；10 轮。
3. **技能变薄与示例精简。**
4. **AC-07**（`2026-11-15-accept-completeness.md`）。
5. **DeepSeek 验证**（同上文档第 10 节），比较轮次、修正次数和输出 token；验证完成前不发版。
