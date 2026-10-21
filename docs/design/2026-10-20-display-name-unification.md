# 元素英文标识与中文名称统一

日期：2026-10-20。状态：用户已确认，实施依据。本文覆盖此前名称、关系无显示名及内嵌扩展块的决定。

## 已确认决定

| 编号 | 决定 | 确认日期 |
|---|---|---|
| N-01 | ObjectType、Property、LinkType、Rule、Metric 必填 name（ASCII 英文标识），可选 display_name（中文名称）；删除 technical_name 及数据库读取兼容。Dataset 不变。 | 2026-10-20 |
| N-02 | name 沿用原英文标识的作用域、忽略大小写唯一性及引用用途；display_name 不参与唯一性，空时显示 name。 | 2026-10-20 |
| N-03 | 关系新增 display_name；verbalizes 与 source_role_name、target_role_name 保持原语义。 | 2026-10-20 |
| N-04 | 旧本体内容清理、不转换。新增 Alembic 迁移，清空版本、会话、提案、导入与身份登记，保留用户、空间、成员、材料与分块、磁盘材料、连接、服务令牌及范围、元数据快照。 | 2026-10-20 |
| N-05 | Ossie 导出 ZIP：纯 Ossie JSON + ontofoundry-extension.json；官方 vendored schema 校验纯 Ossie 文件。 | 2026-10-20 |
| N-06 | Ossie 单文件导入不填显示名；ZIP 恢复扩展；外部旧 ai_context.ontofoundry 仍读取并报告“旧版扩展块”。 | 2026-10-20 |
| N-07 | 原生单文件及完整包导出新字段，旧外部文件仅在导入边界转换并报告。 | 2026-10-20 |
| N-08 | 契约、MCP、DataAgent、前端与测试同步；界面“名称”为 display_name，“英文标识”为 name。 | 2026-10-20 |

## 来源与概念审查

name 来自 Ossie 的原生标识语义（概念使用 concept，关系及指标使用 name），承担表达式、MCP 和交换路径；[Foundry API](https://www.palantir.com/docs/foundry/api/ontologies-v2-resources/object-types/get-object-type)区分 apiName 与 displayName，作为名称分离的参考。display_name 是平台展示元数据，删除会失去中文名称，现有 description、synonyms 均不能替代主显示名。二者都不是查询执行优化；复用现有两个命名字段的职责，不增加第三种名称。Dataset 不变。

## 模型与界面

name 满足 `^[A-Za-z_][A-Za-z0-9_]*$`，必填。对象、指标在空间内唯一；规则在归属内唯一；属性与关系共享所属对象及继承后的命名空间，忽略大小写。display_name 可省略、null 或空字符串；去除首尾空格并按 NFKC 规范化。名称允许重复。

虚构工作空间“青岚演示”：对象 name=contract、display_name=合同；关系 name=signer、display_name=签约方。规则路径 contract.signer.code、材料 values 的键 code 始终使用英文标识。修改中文名称不重写路径。目录实体和指标列为名称、英文标识；关系列为名称、英文标识、关系含义、基数、标签、描述。编辑名称可空，显示统一回退 name。

## Ossie 映射与扩展文件

| 平台 | Ossie 原生位置 | 平台扩展 |
|---|---|---|
| 对象 name | ontology[].concept | 不写显示名到 concept |
| 属性、关系 name | relationships[].name | 不拼接显示名 |
| 指标 name | semantic_model.metrics[].name | 不拼接显示名 |
| description | 对应 description | 不拼接显示名 |
| display_name | 无 | display_names，键为英文路径 |
| 同义词 | 支持 ai_context 的根、SemanticModel、Dataset、Field、Metric 等使用 ai_context.synonyms | 概念和本体关系等不支持位置使用 synonyms |
| 两端角色名、生成读法标记、标签、必填、标题属性 | 可用原生位置继续按既有映射输出 | link_role_names、generated_link_readings、tags、required、title_properties |
| 未导出内容 | 不写占位符 | unsupported，逐项指向转换报告 |

ZIP 中 `qinglan.ossie.json` 仅含官方 schema 字段；`ontofoundry-extension.json` 使用 version=core-1，display_names 例为 {"contract":"合同","contract.signer":"签约方","metric:contract_count":"合同数"}。没有扩展时 display_name 为空；普通 Ossie 的同义词从其原生 ai_context 读取。根和语义模型上下文没有对应核心元素时报告归属边界，不复制到每个对象。扩展 rules 以归属英文路径、规则种类、数组位置关联匿名表达式，键为归属路径.规则英文标识；display_names 的 rule: 前缀路径保存规则名称，rules 同时保存规则描述。该交换元数据来自平台自创映射，不增加核心语义；删除它会丢失 Ossie 无原生槽位承载的规则标识与名称。扩展不保存实例与证据，完整备份仍用原生完整包。

## 数据清理与部署

先备份数据库及磁盘材料，停止建模运行并停止应用写入，执行迁移，再重启全部应用进程以清除进程内缓存。迁移先置 workspaces.current_version_id=null，按外键顺序清理 ontology_imports、imports（历史表存在时）、proposal_decision_items、proposal_item_dependencies、proposal_items、proposal_batches、proposal_decision_requests、modeling_session_migrations（历史表存在时）、modeling_sessions、ontology_element_identities、ontology_versions。db_models.py 的全部 JSON 列已纳入检查：本体快照、校验、运行上下文、候选、提案前后值/差异/回放响应、导入报告/预览/补全历史均随所在表清空；data_connections.config_json 与 metadata_snapshots.snapshot_json/changes_json 为保留的连接及元数据，不含本体定义。历史会话迁移表同样清空。不会扫描或改写 JSON。downgrade 无法恢复清理内容；恢复须使用备份。

## 风险与验证

清理不可逆，备份与停写是部署前提。旧 Agent 输出会被严格契约拒绝，必须同步提示词和技能。显示名不唯一，匹配与路径必须始终用 name。导出 ZIP 与单文件 MIME、下载名、上传接受类型同步；ZIP 校验成员和大小，避免解包到磁盘。单独 Ossie 文件按设计缺少中文显示名；原生旧字段转换只存在于外部适配边界。测试覆盖新字段校验、命名空间、路径重写、导入匹配、迁移保留集合、原生旧文件转换、Ossie ZIP/纯文件/旧扩展与官方 schema、MCP 和前端回退。视觉基准由人工重建。
