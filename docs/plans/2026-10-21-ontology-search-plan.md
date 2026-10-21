# 本体检索实施计划

设计：`docs/design/2026-10-21-ontology-search.md`。向量召回延后，本期只留扩展点。

## 步骤

1. **检索服务拆分**：把 `search_ontology` 的匹配逻辑从 `services/mcp_ontology.py` 移到新的 `services/ontology_search.py`，MCP 层只负责参数、权限与分页；行为不变，现有测试全部通过。
2. **关键词召回与重排**：实现 4.1 的三类匹配、机械规范化、英文标识拆词、4.4 排序和 4.5 `unmatched_terms`。
3. **关系扩展与摘要**：实现 4.3 一层扩展和第 3 节各类型摘要；新增 `expand` 参数，默认 `true`。
4. **向量扩展点**：召回来源接口（关键词为唯一实现），返回 `retrieval` 字段固定为关键词召回。不换数据库镜像、不建向量表、不加 embedding 配置；向量召回另行实施。
5. **契约**：MCP 工具输入 Schema 与描述更新；返回结构写入 api-read 契约并导出 JSON Schema；前端如有调用同步类型。
6. **问数方法**：写入 semantic-grounding Skill（见 `docs/design/2026-10-21-semantic-grounding-skills.md`）：先 search_ontology，按 id 调 get_ontology，不读全量；unmatched_terms 由 Skill 识别实体与时间。`resolve_entity` 随路线图步骤 5 上线后再加入方法，此前不得调用。Skill 拆分完成前，先临时改 `agents/agent_ontofoundry_qa.md`，同步到 DataAgent 并发布。
7. **验收集**：虚构采购协同领域的种子本体与至少 20 道题及期望 id，离线脚本输出两种召回方式的前 10 召回率与返回大小。
8. **统一验证**：后端 pytest、ruff、契约检查；跑一次验收集记录关键词召回的前 10 召回率，作为以后接入向量的对比基线；新会话中问数 Agent 真实问答一轮（DeepSeek 预算，先确认）。

## 测试

- 长句内嵌名称、同义词、英文标识拆词、描述弱匹配、`kinds` 过滤、分页与游标。
- 关系扩展只扩一层、`via` 正确、直接命中优先于扩展。
- 权限：无映射权限不返回数据集；无实例权限不返回证据。
- 召回来源接口：可注册额外实现，返回 `retrieval` 正确标明使用的召回方式。
- `unmatched_terms` 只含未被定义名覆盖的片段。

## 实施结果

- 已完成步骤 1–5 的后端部分：关键词检索迁入 `services/ontology_search.py`，REST 与 MCP 复用同一服务、输入读模型与返回读模型；支持 NFKC、去空白、英文小写、英文标识下划线拆词、三类关键词命中、规则排序、一层关系扩展、各类型摘要和保留原文位置的 `unmatched_terms`。
- REST 新增 `POST /api/v1/ontology/workspaces/{workspace_id}/search`，请求字段为 `query`、`kinds`、`expand`、`limit`、`cursor`；使用当前发布版。MCP 继续服从令牌固定版本。返回保留 `workspace_id`、`version_id`、`items`、`total`、`next_cursor`，新增 `retrieval` 与 `unmatched_terms`。类型过滤在扩展排序后执行，未覆盖片段在过滤和分页前统一计算。
- 召回来源为可插拔接口，本期默认仅注册关键词来源；`retrieval` 固定为 `{"keyword": true, "vector": false}`。游标签名绑定空间、版本、查询参数、权限指纹，并记录召回方式，后续页沿用该方式。没有更换数据库镜像、新建向量表、迁移或增加 embedding 配置。
- 摘要只返回允许字段；无映射权限时，召回来源看不到数据集、指标物理列或表达式，也不经数据集映射扩展实体；比率分子分母引用仍为语义信息。检索摘要不附带证据。保留原 `matched_synonyms`、`owner_id`、`owner_kind` 兼容字段。
- 契约已加入 `OntologySearchRead` 并导出 api-read JSON Schema，MCP 输入 Schema 与工具说明同步更新。空查询继续兼容原 MCP 的浏览行为。统一服务对超出单页预算的响应抛出 `ServiceError`，保证两个入口返回相同结构。
- 偏离与范围说明：按本任务明确限制未改前端类型或 DataAgent；未实施步骤 6–8 的技能发布、独立验收脚本、召回率对比和真实 Agent 问答；向量能力按已确认决定延后。未新增本体模型概念或存储字段。
- 测试：新增虚构采购协同领域测试，覆盖长句、同义词、英文拆词、规范化原文映射、描述弱匹配、排序、类型过滤、分页、游标、各类一层扩展、直接命中优先、权限裁剪、固定版本与 REST/MCP 一致性。统一验证结果：在 `apps/api` 执行 `.venv/bin/python -m pytest -q`，1091 通过、17 跳过、0 失败、0 错误，耗时 104.24 秒；跳过项依赖未配置的可丢弃 PostgreSQL/MySQL 环境，另有 3 条现有依赖或模型警告。`.venv/bin/ruff check src tests` 与 `.venv/bin/python -m ontofoundry_api.contracts.export_schema --check` 均通过。未启动、重启或重建外部环境。
