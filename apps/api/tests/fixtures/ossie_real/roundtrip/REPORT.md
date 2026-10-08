# 真实 Ossie 往返审计（2026-10-07）

A、B 均通过官方固定版本 Schema 和语义 lint，第二次完整导出与第一次完全一致；均仍存在真丢失，不能宣称无损。

原文件只读；副本 SHA-256 与原文件一致。主测试将测试工作空间的 slug/description 对齐原文件名称/描述；另有独立测试验证默认目标空间会重写这两个字段。

差异按同名概念/关系/数据集对齐。缺失子树以一个差异记录保存完整 before，包含全部角色、基数、规则、读法与描述；数量不是叶子字段损失数。逻辑数据集被移除/重建记为 (a)，即使部分物理表列仍相同；可证明等价的单列引用展开单独记为 (b)。平台新增说明及 OntoFoundry 扩展记为 (b)。

## 导入与导出摘要

| 文件 | 概念 | 属性 | 导入实体关系 | 原/导出关系总数 | 导入映射 | skipped | notes | (a)/(b) 记录 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 21 | 22 | 18 | 46/40 | 0 | 6 | 3 | 14/7 |
| B | 29 | 65 | 23 | 96/88 | 11 | 46 | 94 | 128/84 |

## 修复与剩余限制

- Ossie mappings.py 支持 ANSI 双引号单列标识符，反转义后保存物理列名，导出时按 ANSI 标识符规则引用。B 的 arch_rule 映射及 9 个非键属性映射恢复，映射数量由 10 增至 11。拒绝计算表达式，避免误判为列。
- importer.py 明示不保存的 ai_context、dataset/字段元数据、映射描述和指标；mappings.py 明示无法承载的 14 条 dataset 连接。报告修复不等于数据保真修复。
- 未扩改内部模型：仍缺少多角色关系、完整逻辑语义模型（datasets/fields/metrics/连接/多根/referent mappings/计算 SQL）、源文档上下文和元数据承载位置。
- 建议单独设计模型迁移：增加有序角色集合与通用关系；保存独立的源本体元数据及完整逻辑语义模型；定义编辑、合并和发布时的同步与校验规则。
- 默认工作空间的 name/description 不由导入设置，发布采用目标空间元数据；主往返测试显式对齐，独立测试记录这种限制。

## 验证

- `cd apps/api && uv run --python 3.13 pytest -q`：367 passed、9 skipped、0 failures、0 errors；2 个依赖弃用警告。跳过项要求未配置的外部 PostgreSQL/MySQL。
- `cd apps/api && uv run --python 3.13 ruff check src tests`：All checks passed。
- 新测试 13 项全部通过；第二次导出的整个 JSON（含 rule UUID、扩展及映射）相同。
- 官方 ontology/core Schema 均与 Apache 固定提交 88e0011148283302c9a04cd0287e00e0b9d87354 逐字节一致。
- 已运行 API 的 GET /openapi.json、GET /api/v1/workspaces 均 200。只有会创建会话并 commit 的 POST /imports/ossie，无只读预检端点，未提交文件到运行中数据库；两份文件的接口报告在临时 SQLite 中验证。见 [只读 API 与 Schema 验证记录](live-preflight.json)。

## A：逐项差异

[完整导入报告、校验结果和全部 before/after](account-model-v2.report.json) · [第一次导出](account-model-v2.export.json) · [第二次导出](account-model-v2.second-export.json)

| 分类 | 语义 JSON 路径 | 原因 |
|---|---|---|
| (b) | `$.ai_context.instructions` | 生成的平台扩展或说明，不替换原业务构造 |
| (b) | `$.ai_context.ontofoundry` | 生成的平台扩展或说明，不替换原业务构造 |
| (a) | `$.ai_context.synonyms[0]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[1]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[2]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[3]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[4]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[5]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[6]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[7]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology` | 同名构造仅排序不同 |
| (a) | `$.ontology[concept=custodian_institution].relationships[name=has_member_collateral_account]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology[concept=dedicated_fund_account].relationships` | 同名构造仅排序不同 |
| (a) | `$.ontology[concept=dedicated_settlement_account].relationships[name=manages_settle_sub_account]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=exchange_guarantee_fund_account].relationships[name=has_guarantee_fund_sub_ledger]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology[concept=exchange_member].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=financial_futures_exchange].relationships` | 同名构造仅排序不同 |
| (a) | `$.ontology[concept=member_collateral_account].relationships[name=collateral_pledged_to]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology[concept=party].relationships` | 同名构造仅排序不同 |
| (a) | `$.ontology[concept=settlement_member].relationships[name=reports_collateral_to_exchange]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=trading_member].relationships[name=reports_collateral_to_settlement_member]` | 内容丢失、改变或新增语义 |

## B：逐项差异

[完整导入报告、校验结果和全部 before/after](architecture-governance.report.json) · [第一次导出](architecture-governance.export.json) · [第二次导出](architecture-governance.second-export.json)

| 分类 | 语义 JSON 路径 | 原因 |
|---|---|---|
| (b) | `$.ai_context.instructions` | 生成的平台扩展或说明，不替换原业务构造 |
| (b) | `$.ai_context.ontofoundry` | 生成的平台扩展或说明，不替换原业务构造 |
| (a) | `$.ai_context.synonyms[0]` | 内容丢失、改变或新增语义 |
| (a) | `$.ai_context.synonyms[1]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=api_interface].identify_by` | 集合成员不变，仅排序不同 |
| (a) | `$.ontology[concept=api_interface].relationships[name=call_observation]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology[concept=arch_issue].identify_by` | 集合成员不变，仅排序不同 |
| (b) | `$.ontology[concept=arch_issue].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=arch_rule].relationships` | 同名构造仅排序不同 |
| (a) | `$.ontology[concept=component].relationships[name=call_observation]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=component].relationships[name=config_reference_observation]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=component].relationships[name=database_access_observation]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=component].relationships[name=direct_kafka_producer_observation]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=component].relationships[name=kafka_consumer_observation]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=component].relationships[name=msc_kafka_producer_observation]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology[concept=component].relationships[name=table_call_observation]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology[concept=database_instance].identify_by` | 集合成员不变，仅排序不同 |
| (b) | `$.ontology[concept=database_instance].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=global_cfc_config].identify_by` | 集合成员不变，仅排序不同 |
| (b) | `$.ontology[concept=global_cfc_config].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=graded_assurance_microservice_component].extends` | 集合成员不变，仅排序不同 |
| (b) | `$.ontology[concept=host].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=kafka_cluster].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=kafka_topic].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=maven_third_party_library].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=private_cfc_config].identify_by` | 集合成员不变，仅排序不同 |
| (b) | `$.ontology[concept=private_cfc_config].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=redis_db].identify_by` | 集合成员不变，仅排序不同 |
| (b) | `$.ontology[concept=redis_db].relationships` | 同名构造仅排序不同 |
| (b) | `$.ontology[concept=system].relationships` | 同名构造仅排序不同 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=api_interface]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_issue]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children` | 同名构造仅排序不同 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=description].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=description].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=domain].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=improvement].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=issue_site_template].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=issue_site_template].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=label].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=level].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=negative].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=positive].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].children[relationship=title].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].link_mappings[0].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=arch_rule].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=architecture_type].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=architecture_type].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=belongs_to_department]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=belongs_to_system]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=business_importance_label].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=business_importance_label].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=component_name].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=component_name].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=component_name_cn].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=component_name_cn].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=component_type].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=component_type].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=is_core]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=located_in]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=runs_in]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=system_level].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].children[relationship=system_level].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[0].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[1]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[2]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[3]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[4]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[5]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[6]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[7]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[8]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[9]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[10]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[11]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[12]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[13]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[14]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[15]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[16]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[17]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[18]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[19]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[20]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[21]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[22]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[23]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].link_mappings[24]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=component].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=database_instance]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=database_schema]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=department].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=deployment_cluster].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=environment].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=global_cfc_config]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=host].link_mappings[0].children[relationship=host_type].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=host].link_mappings[0].children[relationship=host_type].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=host].link_mappings[0].children[relationship=system_uuid].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=host].link_mappings[0].children[relationship=system_uuid].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=host].link_mappings[0].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=host].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_cluster].link_mappings[0].children[relationship=kafka_name].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_cluster].link_mappings[0].children[relationship=kafka_name].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_cluster].link_mappings[0].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_cluster].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_topic].link_mappings[0].children[relationship=cluster]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_topic].link_mappings[0].children[relationship=partition_count].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_topic].link_mappings[0].children[relationship=partition_count].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_topic].link_mappings[0].children[relationship=replica_count].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_topic].link_mappings[0].children[relationship=replica_count].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_topic].link_mappings[0].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=kafka_topic].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=maven_third_party_library]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=private_cfc_config]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=redis_db]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=redis_instance].link_mappings[0].children[relationship=redis_name].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=redis_instance].link_mappings[0].children[relationship=redis_name].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=redis_instance].link_mappings[0].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=redis_instance].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=second_party_library]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children` | 同名构造仅排序不同 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=display_name].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=display_name].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=system_id].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=system_id].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=system_level].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=system_level].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=system_name].object_mapping.concept` | 保留关系的目标概念已由本体 role 定义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].children[relationship=system_name].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].link_mappings[0].object_mapping.expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=system].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=table_asset]` | 内容丢失、改变或新增语义 |
| (b) | `$.ontology_mappings[name=architecture_governance_mapping].concept_mappings[concept=zone].object_mappings[0].expression` | dataset 别名/逻辑字段展开为同一物理表列 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.ai_context` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=api_interface_daily]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_issue_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=description].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=description].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=domain].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=domain].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=improvement].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=improvement].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=issue_site_template].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=issue_site_template].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=label].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=label].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=level].ai_context` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=level].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=level].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=negative].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=negative].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=positive].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=positive].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=rule_key]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=title].datatype` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].fields[name=title].description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=arch_rule].primary_key` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_call_rollup_1m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_call_rollup_1y]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_call_rollup_3m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_call_rollup_6m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_config_reference_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_dependency_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_deployment_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_package_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_redis_usage_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=component_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=database_access_rollup_1m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=database_access_rollup_1y]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=database_access_rollup_3m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=database_access_rollup_6m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=database_schema_catalog_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=department]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=deployment_cluster]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=environment]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=global_cfc_config_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=host]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=host_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=interface_call_rollup_1m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=interface_call_rollup_1y]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=interface_call_rollup_3m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=interface_call_rollup_6m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_cluster]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_consumer_rollup_1m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_consumer_rollup_1y]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_consumer_rollup_3m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_consumer_rollup_6m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_producer_rollup_1m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_producer_rollup_1y]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_producer_rollup_3m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_producer_rollup_6m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_topic]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=kafka_topic_catalog]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=private_cfc_config_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=redis_catalog_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=redis_instance]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=system]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=system_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=table_call_rollup_1m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=table_call_rollup_1y]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=table_call_rollup_3m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=table_call_rollup_6m]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=table_catalog_snapshot]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.datasets[name=zone]` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.description` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.metrics` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.name` | 内容丢失、改变或新增语义 |
| (a) | `$.ontology_mappings[name=architecture_governance_mapping].semantic_model.relationships` | 内容丢失、改变或新增语义 |

结论：A 不可无损往返，B 不可无损往返。
