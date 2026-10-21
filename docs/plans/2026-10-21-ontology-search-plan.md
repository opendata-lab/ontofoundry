# 本体检索实施计划

设计：`docs/design/2026-10-21-ontology-search.md`。OS-06 已确认用 pgvector。

## 步骤

1. **检索服务拆分**：把 `search_ontology` 的匹配逻辑从 `services/mcp_ontology.py` 移到新的 `services/ontology_search.py`，MCP 层只负责参数、权限与分页；行为不变，现有测试全部通过。
2. **关键词召回与重排**：实现 4.1 的三类匹配、机械规范化、英文标识拆词、4.4 排序和 4.5 `unmatched_terms`。
3. **关系扩展与摘要**：实现 4.3 一层扩展和第 3 节各类型摘要；新增 `expand` 参数，默认 `true`。
4. **向量**：配置项；embedding 客户端（OpenAI 兼容、超时、批量）；数据库镜像换为 `pgvector/pgvector:pg17`（compose.yaml、scripts/offline-compose.yaml、CI 服务）；Alembic 迁移启用 vector 扩展并新增向量缓存表；按 `(模型, 文本哈希)` 读写；检索时余弦计算与阈值；发布成功后后台补算。未配置或失败时降级并在 `retrieval` 中标明。
5. **契约**：MCP 工具输入 Schema 与描述更新；返回结构写入 api-read 契约并导出 JSON Schema；前端如有调用同步类型。
6. **问数方法**：写入 semantic-grounding Skill（见 `docs/design/2026-10-21-semantic-grounding-skills.md`）：先 search_ontology，按 id 调 get_ontology，不读全量；unmatched_terms 中的实体提及交给 resolve_entity。Skill 拆分完成前，先临时改 `agents/agent_ontofoundry_qa.md`，同步到 DataAgent 并发布。
7. **验收集**：虚构采购协同领域的种子本体与至少 20 道题及期望 id，离线脚本输出两种召回方式的前 10 召回率与返回大小。
8. **统一验证**：后端 pytest、ruff、契约检查；用内网 embedding 服务跑一次验收集；新会话中问数 Agent 真实问答一轮（DeepSeek 预算，先确认）。

## 测试

- 长句内嵌名称、同义词、英文标识拆词、描述弱匹配、`kinds` 过滤、分页与游标。
- 关系扩展只扩一层、`via` 正确、直接命中优先于扩展。
- 权限：无映射权限不返回数据集；无实例权限不返回证据。
- 向量：缓存命中不重复调用；服务超时降级；不同空间和版本不串数据；阈值过滤。
- `unmatched_terms` 只含未被定义名覆盖的片段。
