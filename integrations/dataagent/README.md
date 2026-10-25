# DataAgent 三个语义技能发布

平台仅引用已有 DataAgent Agent；仓库编辑不会自动同步管理后台。本目录源码与发布产物如下：

```text
shared/                       唯一共享源码：references、scripts、依赖与许可
skills/ontology-discovery/    路由入口 SKILL.md、步骤 references/steps/（plan、extract、incremental）、发现定义的方法、生成的 output-schema.json
skills/entity-extraction/     路由入口 SKILL.md、步骤 references/steps/facts.md、实例方法、生成的 output-schema.json
skills/semantic-grounding/    问数语义方法与结构化理解 Schema
agents/                       两个已有 Agent 的后台配置说明与系统正文
scripts/offline_budget.py     仅离线预算，不进入安装包
tests/                        回归测试和虚构验收夹具，不进入安装包
generate_output_schemas.py    从平台 JSON Schema 裁剪两个抽取契约
build_packages.py             组装包，复制共享资源
plugin.json、install.sh、迁移说明.md
```

`shared/references/` 包含 core-model、principles、quick-reference、examples（含 protocol）、extract-kit、steps/finish.md（合并修正输出，两个建模技能共用）；`shared/scripts/` 包含 init_workflow、read_input、show_element、show_example、check_part、runpaths、check_result、prepare_result。源码只存一份，构建时复制到三个包，每个安装目录均可独立运行。各技能的专属方法与 output-schema.json 保留在各自源码目录。不要直接安装未组装的 skills 源码。

## 入口与步骤（2026-10-22）

每个技能的 SKILL.md 只做路由（≤1100 字节），细节按步骤放在 references/steps/，Agent 每轮只读当前步骤。建模先运行 init_workflow.py，它打印本轮全部路径和可复制命令；prepare_result.py 与 check_part.py 都接受 --work-pack 和片段简称，参数写错时打印本轮正确写法。计划步骤只确认概念：具名的具体事物是实例，只作为“材料中的例子”列出；有新概念必须先确认范围，确认前不写提案。决定见 docs/design/2026-10-22-skill-routing-and-scope.md。

## 离线校验与打包

从仓库根目录统一运行：

```bash
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python -m pytest -q integrations/dataagent
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python integrations/dataagent/scripts/offline_budget.py
make -C integrations/dataagent zip
```

make 打包前自动运行 generate_output_schemas.py，源为 `apps/api/src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json`，只读不修改 apps。实例内容以 `ontofoundry.instances.v1.schema.json` 为准，生成器核对它与提案中实例元素定义一致，契约漂移时拒绝生成。两个抽取技能按 target_kind 裁剪，保留所有可达定义和其余约束，禁止手工维护；semantic-grounding Schema 对应设计 §5。最终组合结果仍按工作包的完整平台 Schema 校验，不按技能子集拒收其他提案。

产物（dist 已忽略，不提交）：

- `dist/ontology-discovery.zip`
- `dist/entity-extraction.zip`
- `dist/semantic-grounding.zip`
- `dist/ontofoundry-dataagent-plugin.zip`：顶层 ontofoundry-dataagent，包含三个已组装技能、plugin.json、install.sh、agents/ 与迁移说明。

隔离测试分别解压三个 ZIP，在临时目录运行 show_example 的 01–05、check_part 与 prepare_result，运行不借用仓库脚本或旧目录。预算保留原上限，组合抽取路线计入两个技能入口；预算和 tests 不打包。

## 发布步骤

1. 按 [迁移说明](迁移说明.md) 核对平台能力、停止旧运行并备份技能与后台 Agent 配置。本次拆分不清库、不执行历史 core-1 数据迁移。
2. 解压统一插件包，执行 `SKILLS_ROOT_DIR=<技能根目录> sh install.sh`；或在后台分别上传三个独立技能 ZIP。脚本只复制技能并校验目录结构；DataAgent 暂不支持整包原生加载。
3. 管理员按 plugin.json 完成 OntoFoundry MCP 登记与授权。当前登记五个已上线工具（四个读取工具与 resolve_entity），问数统计依赖 DataAgent 自有 mysql.query／doris.query。业务数据源只读，不接入 Portal MCP。建模使用工作包提供的运行级 MCP 凭据。
4. 已有 [建模 Agent](agents/agent_ontofoundry.md) 挂载 ontology-discovery、entity-extraction，max_turns=40，动态选择和组合；已有 [问数 Agent](agents/agent_ontofoundry_qa.md) 挂载 semantic-grounding。同步“系统提示词：”后的正文并发布。问数正文已瘦身，检索顺序和查询语义在技能里，必须成套部署。
5. 停用并备份移走旧 ontofoundry-modeling，由运维重启 DataAgent，检查三技能 capabilities。自动测试和安装脚本不操作后台、不重启外部系统。
6. 获授权后在新会话做真实建模与问数验收，DeepSeek 预算先确认。检查证据、完整结果、歧义追问、授权边界、真实 U/C/O 及压缩缓存；离线 bytes/3 不是实际 usage。

工作包 `proposal_context.instance_baseline` 固定 active 与本会话 staged 实例（不含其他会话 staged／deleted）；`draft` 和 `element_hashes` 只含定义。更新／删除按 target_kind+target_id 定位，before 复制 element，expected_target_hash 复制含 revision 的 hash；不存在或不一致分别报 TARGET_NOT_FOUND、BEFORE_MISMATCH、TARGET_HASH_MISMATCH。输出仍为 ontofoundry.proposals/v1，不增加头字段。

实例抽取沿用 material_object／material_link 契约，界面说明称“文档实例”“关系实例”。同运行定义与实例片段共享 modeling/ 和 execution，由 prepare_result.py 合为一个结果文件，最多两轮修正，平台拒收后保留累计计数。平台只引用已有 Agent，不新建、不修改其配置。

当前未调用实体消歧服务；专门实例抽取入口、问数结构化结果自动入运行记录与真实模型验收仍需后续联验。详见 [迁移说明](迁移说明.md) 与仓库 `docs/design/2026-10-21-semantic-grounding-skills.md`。更新 shared、skills 或 agents 后都须重新打包，并由管理员复制至 SKILLS_ROOT_DIR、同步后台并发布。

## 2026-10-22 实体解析

平台新增 MCP 工具 `resolve_entity`。部署平台新版本后，在 DataAgent 管理后台为已登记的 OntoFoundry MCP 服务刷新工具列表；用 `make -C integrations/dataagent zip` 重新生成并安装 semantic-grounding 与 entity-extraction 技能包，重启 DataAgent。


## 2026-10-23 平台提案预检

`prepare_result.py` 本地检查通过后，读取工作包 `mcp_config_file` 中本轮 MCP 地址与 Authorization，调用同空间、同运行的只读 `proposal-check`。契约错误与不可接受组直接进入工具输出；未通过时保留候选和报告，不替换最终结果。平台不可达或配置缺失时输出 `提示 [PLATFORM_CHECK_SKIPPED]`，明确没有完成平台检查；本地通过的结果仍可保存，入库继续使用相同平台规则。最终文件保存不表示提案已接受或本体已发布。

部署时需先升级平台、执行迁移，再重新打包技能并按上述步骤复制到 `SKILLS_ROOT_DIR`、重启 DataAgent；本次未修改 Agent 提示词。仓库验证不替代后台安装和真实运行验收。
