# 本体检索：search_ontology 混合召回与关系扩展

日期：2026-10-21。状态：待评审。来源：用户 2026-10-21 与 ChatGPT 讨论中的“Ontology Retriever：统一语义检索”，以及 Codex 核心竞争力方案的“检索和开放消费”。

## 1. 目标

问数 Agent 不再读完整本体，而是按问题检索相关定义，再按 id 读取需要的部分。检索结果始终带空间、版本和元素 id，后续步骤只按 id 引用，不按名称匹配。

现状（`services/mcp_ontology.py` 的 `search_ontology`）：

- 整句必须是名称、英文标识、同义词或描述的子串才命中：查“采购金额”能命中，查“星河电子近三个月的采购金额”返回 0 条。
- 结果按类型和 id 排序，不按相关程度。
- 不带关系；指标只带数据集名称，属性只带所属实体 id，口径和别名要再调 `get_ontology`。

## 2. 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| OS-01 | 继续使用现有 MCP 工具名 `search_ontology`，扩展而不是新增工具；空间与版本由 MCP 令牌绑定（含固定版本），不接受空间名称参数；返回信封保留 `workspace_id`、`version_id`。 | 已确认 |
| OS-02 | 召回：关键词召回 + 向量召回并行，合并后做一层关系扩展，再按规则重排。 | 已确认 |
| OS-03 | 向量来自内网已有、兼容 OpenAI `/v1/embeddings` 的服务；未配置或调用失败时只用关键词召回，检索照常可用，并在返回中注明。 | 已确认 |
| OS-04 | 不返回数值分数或置信度，只返回顺序与命中原因（`match`）。 | 已确认（沿用“分数需标注校准”的判断） |
| OS-05 | 未被任何定义覆盖的查询片段原样放入 `unmatched_terms`，不推测它是筛选值还是时间范围，由 Agent 判断。 | 已确认 |
| OS-06 | 向量存于 pgvector：数据库镜像由 `postgres:17-alpine` 换为 `pgvector/pgvector:pg17`（compose、离线包、CI 同步），迁移中 `CREATE EXTENSION IF NOT EXISTS vector`。列不固定维度，不建 HNSW 索引：先按当前版本可见元素的文本哈希过滤再算余弦，元素数百个时无需索引；规模上来后按模型维度建索引。 | 已确认（2026-10-21） |
| OS-07 | Entity Resolver（实例消歧）另写设计文档，与本文衔接：本文的 `unmatched_terms` 是它的输入之一。 | 已确认 |

## 3. 接口

输入（在现有字段上增加 `expand`，保持向后兼容）：

```json
{"query": "星河电子近三个月的采购金额", "kinds": ["object_type", "property", "link_type", "metric"], "expand": true, "limit": 10}
```

- `kinds` 沿用 core-1 的 `object_type`、`property`、`link_type`、`rule`、`metric`、`dataset`、`value_type`，不另起 `relation_type`。
- `limit`、`cursor` 沿用现有分页。

输出：

```json
{
  "workspace_id": "…", "version_id": "…",
  "retrieval": {"keyword": true, "vector": true},
  "items": [
    {"id": "…", "kind": "metric", "display_name": "采购金额", "name": "purchase_amount",
     "match": {"by": "name_in_query", "text": "采购金额"},
     "summary": "…", "definition": {"kind": "simple", "aggregation": "sum", "measure": "…", "time_field": "…", "filters": []},
     "dataset": {"id": "…", "name": "purchase_orders"}},
    {"id": "…", "kind": "object_type", "display_name": "供应商", "name": "supplier",
     "match": {"by": "expansion", "via": {"id": "…", "relation": "metric_dataset_bound_type"}}},
    {"id": "…", "kind": "property", "display_name": "供应商名称", "name": "supplier_name",
     "owner": {"id": "…", "display_name": "供应商"}, "synonyms": ["供应商全称"],
     "match": {"by": "expansion", "via": {"id": "…", "relation": "title_property"}}}
  ],
  "unmatched_terms": ["星河电子", "近三个月"],
  "total": 3, "next_cursor": null
}
```

各类型附带的摘要（只放检索判断所需的内容，完整定义仍用 `get_ontology(ids=…)`）：

| 类型 | 附带内容 |
|---|---|
| object_type | 描述、同义词、标题属性 id |
| property | 所属实体 id 与名称、值类型、是否业务标识、同义词 |
| link_type | 两端实体 id 与名称、角色名、基数 |
| metric | 种类、聚合方式、度量列、时间字段、筛选条件或表达式；比率指标的分子分母 id；有映射权限时附数据集 id 与名称 |
| rule / dataset / value_type | 保持现有摘要 |

权限沿用现状：无映射权限时不返回数据集与物理列，无实例权限时不返回证据。

## 4. 召回与排序

### 4.1 关键词召回

对每个元素准备“检索名”：显示名、英文标识、同义词；另有描述作为弱匹配。

1. **定义名出现在查询中**（主要路径）：检索名规范化后是查询的子串，如“采购金额”出现在“星河电子近三个月的采购金额”里。
2. **查询出现在定义名中**（兼容现状）：查询是检索名的子串，如查“采购”命中“采购订单”“采购金额”。
3. **描述命中**：查询中被 1、2 覆盖之外的片段（两个字以上）出现在描述中。

规范化只做机械处理：Unicode NFKC、去空白、英文小写。英文标识另按下划线拆词，如 `purchase_amount` 可被 “purchase amount” 命中。

### 4.2 向量召回

- 元素文本 = 类型中文名 + 显示名 + 英文标识 + 同义词 + 描述（property 加所属实体名，link_type 加两端实体名）。
- 以 `(模型, 文本 SHA-256)` 为键缓存向量，跨版本复用；文本不变的元素发布新版本时不重算。
- 查询时：查询文本算一次向量，与当前版本可见元素计算余弦，取前 N（默认 20）且高于阈值（默认 0.5，可配置）的元素。
- 发布成功后在后台为新版本补算缺失向量；检索时发现缺失也会补算（批量一次调用），超时（默认 3 秒）则本次只用关键词召回。

### 4.3 关系扩展（一层，`expand=true`）

| 命中元素 | 扩展出 |
|---|---|
| metric | 数据集绑定到的实体（经映射）；比率指标的分子、分母 |
| object_type | 标题属性；以它为一端的关系 |
| property | 所属实体 |
| link_type | 两端实体 |

扩展项只扩一层，不再扩展；同一元素同时被直接命中时按直接命中计。每个扩展项写明 `via`（来自哪个元素、何种关系）。

### 4.4 规则重排

按以下顺序排列，同级内按命中文本长度降序、再按 id：

1. 定义名出现在查询中，或查询完全等于检索名；
2. 查询出现在定义名中；
3. 向量召回（按相似度降序，但相似度不对外返回）；
4. 描述命中；
5. 关系扩展。

`kinds` 过滤在排序后执行，扩展项同样受其约束。

### 4.5 unmatched_terms

从查询中移除所有被 4.1 第 1 类命中覆盖的片段，剩余部分按标点和空白切分，去掉单字虚词（的、和、与、及、在、了），其余原样返回。

## 5. 存储

新增一张表（Alembic 迁移），不改本体模型：

| 字段 | 说明 |
|---|---|
| model | embedding 模型名 |
| text_sha256 | 元素文本的哈希 |
| dimensions | 维度 |
| vector | pgvector `vector`（不固定维度） |
| created_at | 生成时间 |

主键 `(model, text_sha256)`。不存元素 id、版本和空间：同样的文本在任何空间和版本得到同样的向量，空间和版本的过滤发生在“当前版本有哪些可见元素”这一步，不会跨空间、跨版本串数据。

配置：`ONTOFOUNDRY_EMBEDDING_BASE_URL`、`ONTOFOUNDRY_EMBEDDING_API_KEY`、`ONTOFOUNDRY_EMBEDDING_MODEL`、`ONTOFOUNDRY_EMBEDDING_TIMEOUT_MS`、`ONTOFOUNDRY_EMBEDDING_MIN_SIMILARITY`。

## 6. 验收

- 一组虚构领域（采购协同）的业务问题，每题标注期望命中的元素 id，至少 20 题，覆盖：名称内嵌在长句中、同义词、只有描述能命中、叫法不同（如“货款”对“采购金额”，同义词未写）、需要关系扩展才能带出实体。
- 分别统计“只用关键词”和“关键词 + 向量”的前 10 召回率，以及返回大小。
- 问数 Agent 用新工具完成一轮真实问答，对比改动前的工具调用次数和读取的定义量。

## 7. 不做

- 不新增本体概念、置信度或分数字段；不把向量写进版本快照。
- 不对实例数据做向量化；实例消歧见 Entity Resolver 设计。
- 不引入 ES、独立向量库或中文分词依赖。
- 已有数据卷升级：同为 PostgreSQL 17，换镜像不需导出导入；现场若使用外部数据库，需由管理员先安装 pgvector 扩展，否则迁移失败并提示。
