# 实例库实施计划

设计：`docs/design/2026-10-21-instance-store.md`（IS-01～IS-12 已确认）。路线图步骤 3。

## 分块

| 块 | 内容 | 负责 | 依赖 |
|---|---|---|---|
| A 后端主体 | 实例库四张表与迁移；core-1 移除 `material_objects`／`material_links`（Pydantic、JSON Schema、校验）；切换清单（IS-02：删字段、重算哈希、失效旧运行固定草稿与未确认导入）；实例服务（读写、revision 比较更新、历史、软删除）；提案链路改用实例基线（运行上下文、结果解析、有效状态、接受与撤销、待发布与生效 IS-04、放弃会话 IS-10）；共享发布服务中的引用检查（IS-05、IS-08）；读取接口（MCP `search_objects`／`get_object`、REST 实例接口、固定版本过滤 IS-09）；材料用量（IS-07 与 M7）；Ossie 导出移除事实读取 | Codex | 无 |
| B Skill 脚本 | entity-extraction 与共享脚本（`show_element`、`check_part`、`prepare_result`、`check_result`）按实例基线定位实例目标、生成 before/hash；示例与写法包同步；体积预算不放宽 | Codex | A 的契约 |
| C 前端 | 类型同步（含生成的 `core.generated.ts`）；实例页、提案详情、发布面板、文档用量改读实例库；“放弃会话”操作与待发布实例列表；界面文案“事实”改为“实例”（IS-12）；1440×900 截图与视觉测试 | Claude | A 的接口 |

## 验收

- 后端：pytest 全量、ruff、契约导出检查；新增用例覆盖并发覆盖被拒、跨会话、待发布生效与放弃、发布阻止（两条发布通路）、固定版本过滤、切换后旧运行被拒。
- Skill：`integrations/dataagent/tests` 全量与预算。
- 前端：tsc、eslint、vitest、视觉测试，局域网地址联调。
- 真实建模验收（DeepSeek）暂缓。

## 实施结果

2026-10-21，块 A 后端实施。未 commit/push，未修改 `apps/web/` 或 `integrations/dataagent/`。

### 完成内容

- 新增 `20261021_000002_instance_store` 迁移和 `document_instances`、`instance_links`、`instance_evidence`、`instance_history` 四张表；实例生命周期为 staged／active／deleted，revision 比较更新，历史主键保证 `(owner_kind, owner_id, revision)` 唯一。关系引用约束包含工作空间，材料证据建索引。
- core-1 移除两个实例集合，模型、图校验、引用改写、哈希、JSON Schema、原生导出及 Ossie 导出同步。保留英文提案种类 `material_object`／`material_link` 和实例内容模型；两者不属于本体集合。更新共享设计样例与概念文档，独立的实例测试样例放在后端测试夹具中。
- 切换迁移丢弃会话草稿与版本快照中的旧实例，重算草稿、基线、版本内容哈希；本地在途运行标记取消，撤销运行 token、结果认领和 manifest 固定草稿，历史报告保留；待审提案标记 superseded，未确认导入清空转换内容并标记失效。不把旧实例写入新表。
- `services/instance_store.py` 实现实例读写、证据校验、软删除、关系失效、历史、变更序号和会话放弃；材料与人工证据复用 `domain/evidence.py` 的原有校验。证据读取按集合批量查询，实例读取期间集合变化会拒绝返回不一致基线。
- 运行 manifest 和工作包附带独立实例基线；结果解析从基线核对 before/hash，服务端推导 expected instance revision。有效状态、重复候选、待审内容修订、`fact_revision`、接受和撤销改查实例库。决定业务移入 `services/proposal_decisions.py`；混合批次在同一事务更新定义、实例、证据、历史与提案决定，撤销核对接受后的实例 revision。删除提案使关联关系失效，撤销时核对关联关系 revision 后恢复。
- 按 IS-04 判断接受后 active 或 staged，包括已有类型的新属性、属性值类型和关系两端；共享 `publish_draft` 校验活动实例引用及本会话 staged 实例，覆盖会话发布与元素详情保存。预览返回受影响实例与集合变更序号，发布核对序号并激活本会话 staged 实例。描述、显示名、同义词变更不阻止发布。
- REST／MCP 文档实例搜索、详情、邻接改查 active 实例；固定历史版本过滤不兼容实例并返回数量与说明。数据库实例仍按映射只读查询。实例分页游标绑定集合序号。工作空间概览读取实时实例，不再从版本计算实例数量。
- 材料用量合并实例证据与实例历史；已删除实例和历史引用仍阻止删除材料。原有定义、提案、导入、运行清单、版本引用照旧保留。
- 建模运行凭据固定授予 `ontology:read`、`instances:read`、`mappings:read`（SG-14）；未新增运行目标分类或提案种类限制（SG-15）。

### 主要文件

- 表与迁移：`apps/api/src/ontofoundry_api/db_models.py`、`alembic/versions/20261021_000002_instance_store.py`。
- 核心与实例：`domain/core.py`、`domain/models.py`、`domain/dependencies.py`、`domain/validation.py`、`domain/evidence.py`、`domain/instance_validation.py`、`domain/instances.py`。
- 提案／发布：`contracts/proposals.py`、`services/proposals.py`、`services/proposal_decisions.py`、`services/instance_proposals.py`、`services/fact_revision.py`、`services/proposal_revision.py`、`services/dataset_proposals.py`、`services/import_completion.py`、`services/workspaces.py`、`services/model_result.py`、`api/agent_conversation.py`、`api/modeling.py`、`api/proposals.py`。
- 实例与读取：`services/instance_store.py`、`services/instance_query.py`、`services/mcp_ontology.py`、`services/ontology_query.py`、`services/material_usage.py`、`services/public_projection.py`、`api/instances.py`、`api/workspaces.py`、`api/auth.py`、`api/mcp.py`。
- 契约与样例：`contracts/instances.py`、`contracts/export_schema.py`、`contracts/ontofoundry.instances.v1.schema.json`、`contracts/ontofoundry.core-1.schema.json`、`contracts/read_models.py`、`contracts/ontofoundry.api-read.v1.schema.json`、`docs/concepts/evidence-and-instances.md`、`docs/design/core-1-examples/*.json`、`apps/api/evals/ontology_search/seed.json`。
- 测试：新增 `apps/api/tests/test_instance_store.py`、独立实例夹具，更新实例修订、提案、发布、导入导出、概览及历史迁移测试。

### 前端块 C 对接清单

管理接口前缀为 `/api/v1/workspaces/{workspace_id}`；只读接口前缀为 `/api/v1/ontology/workspaces/{workspace_id}`。

| 接口或契约 | 变化 |
|---|---|
| core-1 草稿、版本、原生文件／包 | 删除 `material_objects`、`material_links`，不可再经保存草稿提交实例；生成的前端类型须同步。 |
| 版本 `counts` | 删除两个快照实例数量；实例统计来自实时实例读取／工作空间概览。 |
| `GET /sessions/{session_id}/instances` | 新增，仅本会话 staged，返回 `{change_sequence, items}`；每项见下方基线契约。 |
| `GET /sessions/{session_id}/instance-baseline` | 新增，返回 active 与本会话 staged，供审阅、重复实例定位等会话管理使用。 |
| `GET /instances/{kind}/{instance_id}/history?session_id=…` | 新增，kind 为 `material_object`／`material_link`；返回 `{items:[{owner_kind, owner_id, revision, operation, before, after, proposal_item_id, actor, at}]}`。before/after 为 `{element,state,revision,session_id}` 或 null；staged 历史须带所属会话参数。 |
| `POST /sessions/{session_id}/abandon` | 新增，无请求体；前端二次确认后调用；响应 `{session_id,abandoned_at,abandoned_by}`，重复调用返回同一结果。 |
| 会话响应 | 新增 `abandoned_at`、`abandoned_by`；放弃后禁止继续写入、运行和发布。 |
| `POST /sessions/{session_id}/preview` | 新增响应 `instance_change_sequence`、`affected_instances:[{target_kind,target_id,revision,reason}]`；受影响时 `validation.publishable=false`。 |
| `POST /sessions/{session_id}/publish` | 请求新增必需核对值 `expected_instance_change_sequence`，取自预览；原版本、会话 revision、合并哈希核对继续保留。 |
| `POST /element-saves/preview`、`POST /element-saves` | 预览新增 `affected_instances` 和 `instance_change_sequence`；保存可携带 `expected_instance_change_sequence` 核对已预览集合。没有预览的直接保存仍由共享发布检查当前实例引用。 |
| 提案详情、决定 | 新增 `expected_instance_revision`、`accepted_instance_revision`；不把实例 after 拼回草稿。`accepted_revision` 仍是会话 revision。重复候选新增 `revision`，`expected_target_hash` 取自实例基线。 |
| `POST /proposal-items/{proposal_id}/revision` | 请求和返回形态不变，目标和 hash 改取实例基线，仍只修订待审提案，不直接修改实例。 |
| 只读 `GET /objects`、`GET /objects/{ref}`、邻接 | 文档实例改为 `data_mode="live"`；搜索／详情文档条目带 revision/state；新增 `filtered_count`、`warnings`、`instance_change_sequence`。ref 仍为 `doc.{UUID}`；数据库 ref 不变。 |
| MCP `search_objects`／`get_object` | 实时 active 数据；返回过滤数、说明与集合序号，原权限要求保留。 |
| 材料用量 | 计数字段 `material_objects`／`material_links` 保留英文名，来源改为实例证据与历史合并；references 新增“实例证据”“实例历史”。 |

错误码：`INSTANCE_REFERENCES_BLOCK_PUBLISH`（409，附受影响实例）、`INSTANCE_REVISION_CHANGED`（409）、`PROPOSAL_STALE`（409）、`PROPOSAL_UNDO_CONFLICT`（409）、`PREVIEW_OUTDATED`（409，包含实例变化）、`SESSION_ABANDONED`（409）、`INSTANCE_SET_CHANGED`（409，读取期间变化请重读）、`RUN_CONTEXT_INVALIDATED`（409）、`IMPORT_INVALIDATED`（409）；REST 旧游标沿用 `INVALID_CURSOR`（422），MCP 为 `cursor_invalid`。证据沿用 `EVIDENCE_INVALID`、`EVIDENCE_ID_DUPLICATE`、`MANUAL_EVIDENCE_IMMUTABLE` 等原错误码。

### 块 B 实例基线契约

工作包 `proposal_context` 在 `run`、`draft`、`element_hashes` 之外新增：

```json
{
  "instance_baseline": {
    "change_sequence": 12,
    "items": [
      {
        "target_kind": "material_object",
        "target_id": "00000000-0000-4000-8000-000000008601",
        "revision": 3,
        "state": "active",
        "session_id": null,
        "element": {
          "id": "00000000-0000-4000-8000-000000008601",
          "type_id": "00000000-0000-4000-8000-000000001601",
          "values": {"customer_no": "C001"},
          "evidence": []
        },
        "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    ]
  }
}
```

示例 hash 仅说明形状。真实 hash 是 `domain_sha256({"instance": element, "revision": revision})`，复用平台 core canonical 的默认值与 evidence 排序规则；应直接复制固定基线提供的 hash，不能用旧的 `element_sha256(..., collection="material_objects")`。

- `draft`、`element_hashes` 只含本体定义；基线包含 active 与所属会话 staged，不含其他会话 staged 或 deleted。
- 更新／删除实例：按 `target_kind + target_id` 找基线项，before 原样复制 `element`，`expected_target_hash` 原样复制 `hash`；after 沿用当前提案内容形状，不带顶层 id。服务端从基线推导 expected revision，不要求 Agent 自填新字段。
- 新增实例和关系仍用 `client_ref`，关系仍引用 `type_id/source_id/target_id`。实例、关系、定义可以在同一结果中混合，不按运行目标限制种类。
- `show_element`、`check_part`、`prepare_result`、`check_result`、entity-extraction 样例及写法包必须使用这份独立基线；输出头部不新增字段。更新或删除目标不在基线时为 `TARGET_NOT_FOUND`，before 或 hash 不符为 `BEFORE_MISMATCH`／`TARGET_HASH_MISMATCH`。
- 权威导出为 `contracts/ontofoundry.instances.v1.schema.json`；提案文件仍遵循 `ontofoundry.proposals/v1`。预算不放宽。

### 偏离、部署与待续事项

- 未改变 IS-01～IS-12、SG-14／SG-15。工作空间增加集合变更序号，会话增加放弃作者／时间，提案增加实例 revision 字段，均实现已确认的生命周期和并发核对，不进入 core-1。集合序号以整个工作空间为范围，采取保守失效策略。
- 新的直接实例编辑／导出入口不在本期设计范围；写入仍通过接受／撤销提案，放弃只删除 staged。
- 迁移撤销平台本地在途运行及凭据，不在 Alembic 中调用远端 DataAgent HTTP。部署时仍须先停服务／运行投递，停止远端在途任务，备份后迁移，再重启服务以清空进程读取缓存。旧实例不能通过 downgrade 恢复，需备份恢复。
- 块 B：更新脚本、实体抽取样例与生成 Schema，执行完整测试和预算，按集成 README 安装、后台同步并发布。块 C：按上述接口更新前端类型、实例页、提案、发布面板、材料用量及二次确认放弃操作，完成视觉测试与局域网联调。
- 未执行真实 DeepSeek 建模验收，未连接或改动现场数据库／DataAgent 服务。

### 验证结果

- `cd apps/api && .venv/bin/ruff check src tests evals`：通过。
- `cd apps/api && .venv/bin/python -m ontofoundry_api.contracts.export_schema --check`：通过；`git diff --check` 通过。
- `cd apps/api && .venv/bin/pytest -q`：1109 passed、18 skipped、0 failed、0 errors、3 warnings（117.31 秒）。跳过项需要可丢弃 PostgreSQL；警告为现有 Starlette/httpx 与 TranslationIssue 字段命名提示。
- `apps/api/.venv/bin/pytest -q integrations/dataagent/tests`：297 passed、16 failed（46.20 秒）。按任务要求未修改该目录。失败为旧固定草稿仍携带两个实例集合，以及实例更新／删除未从实例基线定位目标；涉及 `test_extract_kit.py` 1 项、`test_incremental_kit.py` 5 项、`test_workflow.py` 10 项（实例 update/delete、reuse-fact、人工证据示例）。这些属于块 B 的脚本、夹具和样例契约切换；未放宽预算。
- 没有提供 `ONTOFOUNDRY_TEST_POSTGRES_URL`，PostgreSQL 真实迁移链与并发测试按既有门禁跳过；SQLite 实际升级、切换与事务回归已执行。未做现场重启、远端运行取消或真实 DeepSeek 验收。


## 块 B 实施结果

2026-10-21，块 B Skill 脚本实施。编辑仅限 `integrations/dataagent/` 与本计划；未修改 `apps/`，未 commit/push。

- 共享脚本统一按种类与 UUID 定位固定目标：定义取 `draft`／`element_hashes`，实例取独立 `instance_baseline` 的 `element`／`hash`；不重算实例哈希，不新增提案头字段。`show_element` 返回完整实例、基线哈希和直接引用者；`check_part`、`prepare_result`、`check_result` 使用同一定位逻辑，统一报告 `TARGET_NOT_FOUND`、`BEFORE_MISMATCH`、`TARGET_HASH_MISMATCH`。排除 deleted 和其他会话 staged；通用 `init_workflow`、`read_input` 无需改变。
- entity-extraction 方法、入口、共享语义说明和写法包同步实例基线规则，对外称“实例”，英文协议名不变。新增 `examples/instance-baseline.json` 演示定义更新、实例更新和关系实例删除混合结果；已有实例片段仍可省略 before/hash，由组装脚本补齐。
- `generate_output_schemas.py` 从平台提案导出生成两个抽取输出 Schema，并核对权威 `ontofoundry.instances.v1.schema.json` 与提案实例内容、证据定义一致，漂移时拒绝生成。两个生成文件已重新生成，当前内容与原文件一致，提案仍为 `ontofoundry.proposals/v1`。
- 夹具移除草稿实例集合，单独固定实例基线与真实 revision 哈希，更新平台解析测试上下文。新增更新／删除、active／本会话 staged、目标缺失、before／revision 哈希不符、种类定位、不可见目标、权威 Schema、混合结果及三个 ZIP 解压后完整脚本链回归，预算上限保持原值。
- 验证结果：
  - `PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/pytest -q integrations/dataagent`：342 passed，0 failed／0 errors／0 skipped；包括三个 ZIP 的隔离完整脚本链。
  - `apps/api/.venv/bin/python integrations/dataagent/scripts/offline_budget.py`：退出码 0，首读、工作包、示例、方法与全部路线通过；所有预算上限未改。抽取路线 35,972／36,000 B、增量路线 44,748／50,000 B、定义与实例组合路线 34,454／36,000 B；entity-extraction 入口 3,333／4,000 B、实例方法 2,331／2,500 B。抽取路线剩余 28 B，后续改文案需持续检查预算。
  - `make -C integrations/dataagent zip`：退出码 0，生成三个独立技能 ZIP 和统一插件 ZIP，产物位于已忽略的 `integrations/dataagent/dist/`。
  - `git diff --check -- integrations/dataagent docs/plans/2026-10-21-instance-store-plan.md`：通过。
- 部署与未完成项：未安装到外部 DataAgent 的 `SKILLS_ROOT_DIR`、未重启或同步后台发布；按集成 README 由管理员部署。未做真实 DeepSeek 建模验收。上线需与块 A 实例基线契约成套部署，旧在途上下文不能作为新实例基线使用。
