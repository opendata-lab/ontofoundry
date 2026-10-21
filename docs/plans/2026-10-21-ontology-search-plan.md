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
- 步骤 1–5 阶段范围说明：按该阶段任务明确限制未改前端类型或 DataAgent；当时未实施步骤 6–8 的技能发布、独立验收脚本、召回率对比和真实 Agent 问答；步骤 7 的后续完成情况见下文，向量能力按已确认决定延后。未新增本体模型概念或存储字段。
- 测试：新增虚构采购协同领域测试，覆盖长句、同义词、英文拆词、规范化原文映射、描述弱匹配、排序、类型过滤、分页、游标、各类一层扩展、直接命中优先、权限裁剪、固定版本与 REST/MCP 一致性。统一验证结果：在 `apps/api` 执行 `.venv/bin/python -m pytest -q`，1091 通过、17 跳过、0 失败、0 错误，耗时 104.24 秒；跳过项依赖未配置的可丢弃 PostgreSQL/MySQL 环境，另有 3 条现有依赖或模型警告。`.venv/bin/ruff check src tests` 与 `.venv/bin/python -m ontofoundry_api.contracts.export_schema --check` 均通过。未启动、重启或重建外部环境。

### 步骤 7：离线验收集（2026-10-21）

- 已新增 `apps/api/evals/ontology_search/{seed.json,questions.json,run.py,README.md}` 和 `apps/api/tests/test_ontology_search_eval.py`。种子为虚构“青岚采购协同”工作空间的原生 core-1 快照：6 个实体（供应商、采购订单、采购订单明细、物料、收货、付款）、25 个属性、5 个关系、6 个数据集、6 个映射、7 个指标（5 个简单、1 个比率、1 个表达式）、1 个值类型和 1 条约束规则；通过现有 JSON Schema、跨元素语义及发布校验。未增加本体模型字段或修改契约。
- 验收共 30 题，名称内嵌长句、同义词、英文标识、只有描述能命中、需要关系扩展才能带出、叫法不同，各 5 题。人工期望共 43 个元素引用；关系扩展题另标注必须经扩展带出的 id，测试验证关闭扩展时这些 id 不在前 10、开启后以 `expansion` 及正确的直接来源带出。描述题测试验证实际命中原因为 `description`。
- 运行命令（`apps/api`）：`.venv/bin/python evals/ontology_search/run.py --output /tmp/ontology-search-baseline.json`。脚本直接调用现有 `retrieve`，不经网络、数据库或大模型；同一题集对比 `expand=False` 与 `expand=True`。二者均为关键词来源，`retrieval={"keyword":true,"vector":false}`；这是扩展开关的消融对比，向量召回仍延后，没有虚构第二种召回来源。
- 下表“召回率”采用逐题前 10 召回率的算术平均；每题为“命中期望数 / 期望数”。字节数为包含前 10 条完整摘要的 `{items,total,retrieval,unmatched_terms}` 紧凑 JSON 的 UTF-8 大小，不含 REST/MCP 信封、签名游标与双份传输封装。统计口径及完整逐题 JSON 输出方法见验收目录 README。

| 范围 / 题型 | 题数 | 纯关键词前 10 召回率 | 关键词 + 一层扩展前 10 召回率 | 纯关键词平均返回（字节） | 开启扩展平均返回（字节） |
|---|---:|---:|---:|---:|---:|
| 总体 | 30 | 73.06% | 83.33% | 986.83 | 2010.00 |
| 回归集（除叫法不同） | 25 | 87.67% | 100.00% | 1163.88 | 2391.68 |
| 名称内嵌长句 | 5 | 100.00% | 100.00% | 959.40 | 3598.80 |
| 同义词 | 5 | 100.00% | 100.00% | 547.20 | 1639.60 |
| 英文标识 | 5 | 100.00% | 100.00% | 3022.60 | 3959.40 |
| 只有描述能命中 | 5 | 100.00% | 100.00% | 670.40 | 1250.80 |
| 需要关系扩展才能带出 | 5 | 38.33% | 100.00% | 619.80 | 1509.80 |
| 叫法不同 | 5 | 0.00% | 0.00% | 101.60 | 101.60 |

- 补充口径：纯关键词全中 20/30 题，开启扩展全中 25/30 题；按期望元素总数加权的总体召回率（micro）分别为 29/43 = 67.44% 和 38/43 = 88.37%。5 道叫法不同题均为刻意保留的未登记别名，如“花了多少钱”→采购金额，留给以后在相同题集上对比向量收益。
- pytest 回归阈值设为 **1.0（100%）**：来源为本次真实服务实测，开启扩展时排除叫法不同后的 25 题及其 5 类各自均为 100%。不降低已达成基线；叫法不同仍计入总体报告，不进入阈值，也不要求未来继续漏召。
- 本次未发现明显不该漏召的题目漏召，未修改检索服务。未改前端、DataAgent 或其他集成，未 commit/push；未启动、重启或重建外部环境。步骤 6 的技能发布和步骤 8 的真实 Agent 问答仍不在本任务范围内。
- 全部代码与验收集编辑完成后统一验证（`apps/api`）：`.venv/bin/python -m pytest -q` 为 **1100 通过、17 跳过、0 失败、0 错误**，耗时 104.64 秒；新增验收测试计 9 个用例。17 项跳过依赖未配置的可丢弃 PostgreSQL/MySQL 环境，另有 3 条现有依赖或模型警告。`.venv/bin/ruff check src tests evals` 全部通过。
