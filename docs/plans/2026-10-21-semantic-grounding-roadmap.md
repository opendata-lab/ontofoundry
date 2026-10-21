# 语义锚定路线图

日期：2026-10-21。用户确认的顺序。各步的设计见对应文档，中大型步骤另写实施计划。

| 步骤 | 内容 | 设计 | 依赖 |
|---|---|---|---|
| 1 | 本体检索：关键词召回 + 一层关系扩展 + 规则重排，召回来源可插拔（向量召回后续接入）；MCP 与 REST 两个入口 | `docs/design/2026-10-21-ontology-search.md`，计划 `docs/plans/2026-10-21-ontology-search-plan.md` | 无 |
| 2 | P0 补缺并拆 Skill：ontology-discovery 补表分类方法、外键与同名字段作为证据、表结构证据；拆为 ontology-discovery、entity-extraction、semantic-grounding 三个 Skill，打插件包 | `docs/design/2026-10-21-semantic-grounding-skills.md`；表结构证据另写设计 | 步骤 1（semantic-grounding 使用检索） |
| 3 | 实例库分离：实例、关系实例、证据、历史独立存储，不迁移已有实例 | `docs/design/2026-10-21-instance-store.md` | entity-extraction 上量之前完成 |
| 4 | P1 双通道融合：用检索找已有相似定义并在审阅中展示对齐理由；业务声明与物理观察的差异提示 | 另写设计 | 步骤 1、2 |
| 5 | P2：Entity Resolver；表结构变化影响预览与局部重建；semantic-grounding 上线问数 | `docs/design/2026-10-21-entity-resolver.md`；影响预览另写设计 | 步骤 1、3 |

## 前置条件（Codex 评审）

- 步骤 3 上线前完成实例契约与事务闭环：实例基线进入运行上下文、本地与服务端校验、接受与撤销的实例 revision 校验、共享发布服务中的 IS-05、生效判定（IS-04）、切换清单（IS-02）。
- 实例抽取启用前完成：运行凭据固定加上实例与映射读取（SG-14）、共享资源完整打包（SG-12）、显式放弃会话与 staged 管理（IS-10）。
- 各步只启用已上线的工具：`resolve_entity` 随步骤 5 进入 Skill 方法。

## 约束

- 已有文档抽取与提案流程保留；提案格式即统一候选输出协议，不另建候选模型。
- 不接入 opendataworks Portal MCP 与其血缘（SG-09）。
- 步骤 2、5 改动 Skill 后，在新会话中做真实验收；DeepSeek 运行前先征得用户同意。
- 向量召回（pgvector + 内网 embedding 服务）在路线图之后单独排期，以步骤 1 的关键词召回率为基线评估收益。

## 实施状态（2026-10-22）

| 步骤 | 状态 | 提交 |
|---|---|---|
| 1 本体检索 | 完成：关键词召回 + 一层扩展 + 规则重排，MCP 与 REST；30 题验收集基线（前 10 召回率 83%，除“叫法不同”外 100%） | eaea849、734bd10 |
| 2 P0 补缺并拆 Skill | 完成：表结构收据、表分类方法、三个 Skill 与插件包 | 47631a3、c8e898b |
| 3 实例库分离 | 完成：四张表、实例基线、待发布与放弃会话、两条发布通路检查、固定运行权限、前端实例视图 | 9430210 |
| 4 P1 对齐审阅 | 完成：可能已有的定义、必填与可空列差异 | af4f5c3 |
| 5 P2 | 完成：Entity Resolver（MCP 与 REST）、表结构变化影响预览与发起局部建模 | b2e462e、a0aa2c3 |

未执行：真实 DeepSeek 建模与问数验收（用户要求暂缓）；向量召回（单独排期）。

## 上线清单

1. 停止平台服务与在途建模运行，备份平台数据库与材料目录。
2. 部署新镜像，执行 Alembic 迁移（`20261021_000001` 材料来源、`20261021_000002` 实例库；后者丢弃旧事实并失效旧运行），重启服务。
3. DataAgent：`make -C integrations/dataagent zip`，用插件包中的 `install.sh` 安装三个技能，重启 DataAgent。
4. 管理后台：OntoFoundry MCP 服务刷新工具列表（新增 `resolve_entity`）；建模 Agent 挂载 ontology-discovery 与 entity-extraction，问数 Agent 挂载 semantic-grounding，并同步 `agents/*.md` 的系统正文后发布。
5. 在新会话中做一次建模与一次问数的真实验收（需用户同意 DeepSeek 预算）。

