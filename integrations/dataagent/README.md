# DataAgent core-1 发布操作

平台仅引用已有 DataAgent Agent；仓库编辑不会自动同步管理后台。
源码：`skills/ontofoundry-modeling/`；分发包由 `make -C integrations/dataagent zip` 生成，产物 `dist/ontofoundry-modeling.zip` 不提交。

以下只在完整 P2 前后端集成验收后由发布人员执行，不由自动测试启动或重启外部系统：

1. 正常运维备份平台数据库和磁盘材料；停止旧建模运行及结果同步，关闭切换窗口的新写入。
2. 删除运行时旧技能目录，将新 ZIP 解压到 `SKILLS_ROOT_DIR`（或复制源码目录）；不要并存旧目录。
3. 在 DataAgent 管理后台把已有建模 Agent 的技能配置改为 ontofoundry-modeling；同步并发布 [建模提示词](agents/agent_ontofoundry.md) 和 [问数提示词](agents/agent_ontofoundry_qa.md)。平台不创建或修改 Agent。
4. 重启 DataAgent 使其重新索引技能，检查 capabilities 能看到 ontofoundry-modeling。此操作不得放进自动测试。
5. 停止旧应用进程，确认备份后执行 Alembic 升级到 `20261016_000001`；清空旧提案、会话、身份和版本，不转换旧数据；保留用户、工作空间、成员、材料/分块、数据连接、服务令牌/范围、元数据快照及磁盘材料。
6. 同时部署 core-1 前后端，重启应用以清除进程内 read_cache。旧 run grant 因会话删除立即失效，旧回调不能复活会话。服务令牌仍存在，但未发布空间返回空 MCP 目录。
7. 验证从空空间建模、审阅、接受、预览、发布及四工具读取；验证问数通过 DataAgent 自有数据库工具聚合。导入/导出入口在 P4/P5 交付前保持下线。

迁移仅在部署窗口执行；回滚旧内容依赖备份，downgrade 不能恢复已清空的数据。
本工作树无 .env，不连接开发数据库。测试只用测试自建临时 SQLite 或显式 disposable PostgreSQL/MySQL。

## 2026-10-20 名称统一部署

1. 先备份数据库与全部磁盘材料（含 data_dir）。停止正在进行的建模运行，并停止应用写入。
2. 部署新代码，执行 `alembic upgrade head`（含 20261020_000001）。此迁移只删除旧本体内容，不转换任何 JSON。
3. 清理：workspaces.current_version_id 置空；ontology_imports（及历史 imports）、proposal_decision_items、proposal_item_dependencies、proposal_items、proposal_batches、proposal_decision_requests、modeling_session_migrations（存在时）、modeling_sessions、ontology_element_identities、ontology_versions 全部清空。保留 users、workspaces、workspace_members、materials、material_chunks、磁盘材料、data_connections、service_tokens、service_token_scopes、metadata_snapshots。
4. 重启全部应用进程，清除进程内缓存。downgrade 无法恢复已清理内容，恢复必须使用备份。
5. 将 agents/agent_ontofoundry.md 和 agents/agent_ontofoundry_qa.md 同步到已有 DataAgent 的管理后台并发布，不创建 Agent。将 `make -C integrations/dataagent zip` 生成的技能包解压到 SKILLS_ROOT_DIR（包内不含 tests 与 offline_budget），重启 DataAgent。旧输出中的 technical_name 将被严格契约拒绝。
6. 在局域网 HTTP 地址确认新建元素、提案、导入导出可用。Ossie 下载为 .ossie.zip，包内为纯 Ossie JSON 与 ontofoundry-extension.json；原生导入旧文件会报告字段转换。视觉基准由人工重新生成。

## 2026-10-20 建模 token 效率优化（离线实现）

此改动不涉及核心模型、契约或迁移，不重复执行上文清空数据步骤。部署时用 `make -C integrations/dataagent zip` 生成的技能包替换 `SKILLS_ROOT_DIR/ontofoundry-modeling` 整个目录（包内不含 tests 与 offline_budget：测试夹具含验收答案，不能让 Agent 读到），由运维重启 DataAgent；将更新后的 `agents/agent_ontofoundry.md` 系统正文同步到已有 Agent 并发布。建模 Agent 的 max_turns 设为 40（2026-10-21 真实验收：抽取约 29 轮、补齐约 25 轮）。问数需要 DataAgent 配置 `ODW_BACKEND_BASE_URL`（OpenDataWorks 后端 AI 接口根地址）与 `ODW_AGENT_SERVICE_TOKEN`（等于后端 `AGENT_API_SERVICE_TOKEN`）。

平台与技能须同时部署：平台新增临时工作包、材料原行号索引及修正计数侧文件；完整固定上下文、Schema、原材料仍上传并强校验，历史材料上传去重不变。每轮结果须同时保留 `output/ontofoundry-budget-<run_token>.json`，平台校对结果 SHA256，缺失／过期／耗尽走既有失败路径，不新增业务状态。prepare_result.py 每次整批校验，通过才原子写最终文件；首次检查不占修正，后续内容变化自动计数，--repair 显式计数，平台拒收修复继续同一预算。

离线命令（不联网、不生成 dist、不自动重启）：

```bash
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python -m pytest -q integrations/dataagent/skills/ontofoundry-modeling/tests
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python integrations/dataagent/skills/ontofoundry-modeling/scripts/offline_budget.py
```

部署后仍需一次获授权的真实运行，核对≤T4 写入、正常≤8／含修正≤10 轮、完整合法范围和中文缺项说明、Schema fetch/search=0、真实 U/C/O 与缓存代际。不把离线 bytes/3 当作模型 usage。本轮不部署、不访问后台。

## 2026-10-20 建模 harness 配套部署（待执行）

本轮仅离线实现。后续部署整批更新平台、整个技能目录与已有建模 Agent 系统正文；不执行上文历史清库步骤，不新增迁移。

1. 用打包产物替换 `SKILLS_ROOT_DIR/ontofoundry-modeling` 全目录（SKILL、references、正例与运行脚本；不含 tests 与 offline_budget）。源码不创建反例目录；tests 中的错误构造与验收夹具不作为 Agent 阅读材料。
2. 在管理后台只复制 [建模配置](agents/agent_ontofoundry.md) 的“系统提示词：”之后的五行正文（四行候选加简体中文要求）。技能绑定和 max_turns=40 属配置，不粘到正文；核对现有 Agent 已绑定技能与轮数，再发布。此次问数 Agent 查询语义保持原有配置，不因建模优化删减。
3. 运维重启 DataAgent，确认技能被识别；在技能目录执行 `python scripts/show_example.py metric --variant ratio`，应返回 ≤8 KiB 正例，检查未知类型能列出选项。报错中的绝对路径由运行时技能脚本计算，服务端相对命令在技能目录执行。
4. 同版部署平台，核对首轮提示仅有模式、工作包、token、输出路径和用户消息；材料、结果头、Schema、MCP 在工作包。平台拒收须上传新 context 和新工作包，并保留原材料／Schema 索引、pinned draft 和累计次数；MCP 配置重新签发同一固定版本与发起用户的新 token 凭据，不能继续使用旧包或重置两轮预算。旧运行缺少完整索引时明确失败，不用旧包续跑。
5. 本地统一离线检查通过后再安排一次获授权的真实验收。核对思考与回答为简体中文、MCP固定版本和授权、业务口径、完整提案与证据、实际轮数及U/C/O、工具折叠与压缩缓存。未同步表只在方法／交付说明提示需先同步，本次未实现“表未同步”校验或审阅UI。

回退时平台、技能及系统提示成对回退；保留失败诊断，不重置执行计数续跑。离线预算从实际五行系统正文计量，配置文件另列；不把字节代理指标当作真实token结论。

## 关联表与数据集来源（2026-10-20）

- 构建页关联的已登记数据表进入工作包的 `tables`（目录）和 `tables_file`（完整列）；技能用 `scripts/read_input.py <tables_file> --tables t1,t3` 一次读齐。
- 跨表口径按技能提议“基于表达式的数据集 + 单数据集指标”，写法用 `scripts/show_example.py dataset --variant query`。
- 技能与平台需同版部署：旧技能不认识 `tables_file` 和基于表达式的数据集。
- 分步建模：Agent 在工作区 `modeling/` 写 plan.md、entities.json／issues.json、notes.md、parts/01–05 片段和 checks/。脚本 `init_workflow.py`（建骨架、还原上一轮计划）、`check_part.py`（片段快速检查）、`prepare_result.py <目录>`（按文件名合并片段）。等待用户确认时平台保存计划，下一次建模运行以 `prior_plan_file` 交回。

## 2026-10-21 本体检索（问数方法）

平台的 `search_ontology` 改为关键词召回、一层关系扩展和规则重排，返回命中原因与 `unmatched_terms`（见 `docs/design/2026-10-21-ontology-search.md`）。问数提示词的“取定义的顺序”随之更新：原句检索、按 id 读取所需定义、自行识别未匹配片段中的实体名称与时间。部署平台新版本后，把更新后的 [问数提示词](agents/agent_ontofoundry_qa.md) 同步到已有问数 Agent 的管理后台并发布；不涉及技能包和建模 Agent。拆分 Skill 后，这部分方法迁入 semantic-grounding。

