# 本体检索离线验收集

虚构领域为“青岚采购协同”，工作空间 UUID 为 `72100000-0000-4000-8000-000000009000`。所有主体、工作空间和 `fictional_qinglan_*` 业务表均为虚构，不需要创建数据库或物理表。

在 `apps/api` 目录运行：

```bash
.venv/bin/python evals/ontology_search/run.py
.venv/bin/python evals/ontology_search/run.py --output /tmp/ontology-search-baseline.json
```

可用 `--seed 路径 --questions 路径` 指定其他快照与题目。默认路径相对于脚本自身，不依赖启动目录；Python 环境需已安装本仓库 API 包。脚本只调用平台的 core-1 发布校验与 `services/ontology_search.py` 的 `retrieve`，不经 HTTP，不连接数据库，不读取业务数据，不调用大模型或 embedding 服务。

## 种子与题目

`seed.json` 是原生 core-1 草稿快照，可直接交给 `OntologyDraft` 和平台发布校验。包含供应商、采购订单、采购订单明细、物料、收货、付款 6 个实体，业务标识与标题属性、同义词、直接关联、数据集及完整列映射，还有简单、比率、表达式指标、业务编码值域和约束规则。工作空间名称只在说明中记录，避免给 core-1 加入不存在的字段。

`questions.json` 有 30 题，6 类各 5 题：名称内嵌长句、同义词、英文标识、只有描述能命中、需要关系扩展才能带出、叫法不同。每题有固定题号、`query`、题型 `type`、人工标注的 `expected_ids` 和理由 `reason`。关系扩展题另外标注 `expansion_expected_ids`，这些元素须由一层扩展带出，关闭扩展时应缺失。其余结果并不因此被视为错误，本验收集衡量召回，不衡量精确率。

“叫法不同”是刻意保留的语义缺口，例如“花了多少钱”期望命中“采购金额”，种子未登记这个同义词。当前关键词预期漏召，题目仍进入总体统计，但不进入 pytest 的回归阈值。后续接入向量时保留这些问题和种子，勿通过补同义词消除对比样本。

## 统计口径与输出

一次运行在相同数据、全部可见类型、有映射读取权限（`mappings=True`）下比较两种配置：

- `keyword_only`：关键词召回和规则重排，`expand=False`。
- `keyword_expanded`：关键词召回、一层关系扩展和规则重排，`expand=True`，作为当前回归基线。

这两个配置均为关键词来源，返回 `retrieval={"keyword": true, "vector": false}`，没有用空实现或模拟结果代替向量召回。将来可通过 `evaluate(..., sources=...)` 注入实际召回来源，默认运行方式仍不会访问网络。

每题取服务有序结果的前 10 条，不翻页：

- `all_expected_in_top10`：前 10 是否包含全部期望 id。
- `recall_at_10`：前 10 命中的期望 id 数 / 该题期望 id 数。
- `response_bytes`：离线返回投影 `{items: 前10条, total: 总条数, retrieval, unmatched_terms}` 经 `json.dumps(ensure_ascii=False, separators=(",", ":"))` 编码后的 UTF-8 字节数。包括完整元素摘要和命中原因；不含 REST/MCP 的空间、版本、签名游标或双份传输封装，不能当作实际网络包大小。

终端输出逐题结果、缺失 id，以及总体、回归集和按题型汇总的召回率与平均返回字节数。JSON 文件还保留逐题完整投影，可检查排序、`match.by`、`via` 和 `unmatched_terms`。汇总的 `recall_at_10` 是逐题召回率的算术平均；`micro_recall_at_10` 是所有题命中期望总数 / 期望总数，`all_expected_rate` 是全中题比例。所有数值均为 0–1，终端显示百分数。

## 回归阈值

2026-10-21 首次运行本集实测后，将开启扩展、排除“叫法不同”的 25 题总体及每类平均前 10 召回率阈值设为 **1.0（100%）**，不人为放宽已达成的效果。具体测量记录见 `docs/plans/2026-10-21-ontology-search-plan.md` 的“实施结果”。pytest 同时检查题型标注的真实性、扩展关闭后的缺失、返回大小计算与可序列化结果；语义缺口不要求未来继续漏召。

全部编辑完成后统一验证：

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests evals
```
