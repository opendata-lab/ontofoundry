# 实体解析离线评测

用平台的 `services/entity_resolution.py` 原样解析 20 个提及，候选来自 `instances.json`（虚构青岚采购的 8 家供应商，名称刻意重叠），本体复用 `../ontology_search/seed.json`。不连数据库、不经 HTTP、不调用模型。

```bash
cd apps/api
.venv/bin/python evals/entity_resolution/run.py [--output /tmp/entity-resolution.json]
```

题型：编号精确、全称精确、简称唯一、简称多家（应返回 AMBIGUOUS 由人追问）、全角与空格、不存在，以及两类已知缺口：叫法不同（非连续子串、行业简称）、需要上下文（结合城市或门店位置）。缺口题按理想答案标注，用来衡量今后上下文消歧的收益；`instances.json` 的 city 只供标注参考，解析器不读取。

基线（2026-10-22）：已实现题型 14/14，叫法不同 0/3，需要上下文 0/3，总体 70%。
