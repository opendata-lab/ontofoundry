# core-1 P1 后端实施记录

## 基线和范围

- 基线：`9375ed3`，分支 `feat/core1-p1-core-model`；依赖 P0 `7d99a09`。
- 依据：`2026-10-14-core-model-and-format-adapters.md` 当前 §3、决定 49–51，及同日实施计划 P1-01～06。
- 本轮完成 P1 未接入运行的后端基础件：图校验、绑定解析、表达式、依赖、哈希、生成契约及回归。沿用已确认设计，不新增持久化模型概念，不切换生产读写、不清库。
- 前端页面交由 Claude；本轮前端文件仅限生成契约所需的脚本、依赖、类型与共享夹具。
- 未跟踪的原型目录不编辑、不提交；不 commit/push。已停止端口 5176、5177、5178、5190 的遗留 Vite 服务。

## 实施顺序

1. 完成继承/绑定投影和图校验，区分结构错误与待补全状态。
2. 分开实现本体、同行绑定、数据集指标表达式，保存内部 UUID 引用和原文本位置，支持按引用重建。
3. 实现引用索引、变更影响和候选图校验；本体变化不产生指标依赖。
4. 实现 core-1 独立哈希、schema/TS 生成和漂移检查；修正示例 06/12 已登记列缺口。
5. 全部编辑后统一执行后端和契约检查；记录覆盖、失败、跳过及未做事项。

## 已完成实现

- `graph.py` 补双向有效关系、有效规则和标题属性继承；标识仍按属性 UUID 字节序。
- `bindings.py` 解析有效主附来源、字段与继承关系绑定，虚拟来源只列首个有绑定的后代，避免重复展开它的 shared_parent 子类；输出 bound/unbound/virtual/missing_key 静态状态。跨连接、权限和采集时效留给 P2 服务投影。
- `validation.py` 检查九集合 UUID、证据 UUID 归属、名称、继承环/遮蔽/标识、标题、字段和关系键、指标和事实引用；未知元数据/空键保留为未完成，不扫描外部业务数据。
- `expressions.py` 区分本体路径、同行来源列和指标数据集列；记录 UUID、方向、原文位置并附到内部 AST。支持 CASE、反向、自关联、平行关系与成员 EXISTS；禁止集合作标量、查询作用域和窗口。本体/同行使用已知标量函数集合；指标语义保存不套用数值预览白名单。内部占位符会避开用户原文，不能借同名占位符绕过列检查。
- `dependencies.py` 覆盖表达式、条件、字段键、继承关系 UUID 字典键、事实值键和端点；基于旧图引用在候选图重建路径，支持交换技术名；Dataset/列/位置/快照及分量变更传播至 ratio，本体变化不触发指标修订。
- `core_canonical.py` 独立规范化九集合、证据、来源、列和集合标签；保留键列、JOIN 列组、路径、条件与 between 的次序，保留事实 null/0/false 和表达式原文。`core.py` 额外拒绝 NaN/Infinity，避免不可生成稳定 JSON 的存储值。
- 生成 Draft 2020-12 schema 与判别联合 TS，均有只读 `--check`；固定 `json-schema-to-typescript@15.0.4` 并更新 lock。Python/TS 夹具直接读取 13 份设计 JSON，不复制业务数据。
- 修正 06 的 devices/vehicles 列清单及 12 的 snapshot_date 缺口，同时保留缺口负例。
- 全量 ruff 发现基线另有两处问题：`model_result.py` 将相同异常范围的忽略处理改为 `suppress`；`test_proposal_undo.py` 使用显式同名导入保留 pytest 夹具重导出。未移除夹具。

## 验证记录

执行环境：Python 3.13；Node 22.19.0（仓库要求 >=22.19.0）。本机默认 Node 20 不满足 engines；首次用工具附带的 Node 24 运行时，既有 `agentConversation.test.ts` 的 Blob.text 测试失败，切回 Node 22 后其定向及全量测试通过，没有修改该产品代码或测试。

- P1 首轮回归中发现两处新增测试对夹具的假设错误（规则归属可能是属性、示例 01 的指标均在 orders），已修正为真实归属解析和明确构造跨数据集负例。
- 收紧标量函数时发现 sqlglot 把 AND/OR 也归为 Func，已明确放行布尔/算术运算节点，并重验全部表达式、继承和依赖用例。
- P1 定向：149 passed，0 failed；之后补充虚拟来源展开和未知物理类型两项用例，纳入最终全量后端测试。
- 前端：36 files、210 tests passed，0 failed，0 skipped（Node 22）。仅新增共享夹具/类型回归，无页面重写。
- `ruff check src tests` 通过；核心 schema 和 TS check 均通过。
- 前端 `lint` 通过（0 errors，保留既有 ReviewOverlays 的 1 个 Fast Refresh warning）。
- `npm run build --workspace apps/web` 通过，包含 `tsc -b`；当前入口 JS 985.99 kB（gzip 315.62 kB），CSS 161.79 kB（gzip 28.19 kB）。保留既有大 chunk 提示；本轮未测变更前包体积，不能声称差值为零。
- `npm ls json-schema-to-typescript --workspace apps/web` 确认为 15.0.4。
- 局域网非 HTTPS 静态验收：临时 Vite preview 在 5181 开放，局域网 IP 的入口和主 JS 请求均 HTTP 200；验证后关闭。页面交互和逐像素比对未重复，因本轮只有生成类型和测试夹具变化。
- 最终全量后端：`cd apps/api && uv run --python 3.13 pytest -q -rs`，884 passed、0 failed、0 errors、61 skipped，耗时 127.71 秒。60 项缺 disposable PostgreSQL，1 项缺 disposable MySQL 配置；不把 skip 记作通过。保留 FastAPI/Starlette 的 2 项既有弃用提示。
- 全量之后的最终审阅补充了合法单数据集 `FILTER` / `WITHIN GROUP` 保存与跨数据集过滤拒绝，调整仅限未接入运行的表达式模块；四个 `test_core1_*.py` 全部重跑：154 passed、0 failed、0 errors、0 skipped，耗时 0.75 秒。此后未再改实现；最后一次 ruff 全目录通过。未为这三个新用例虚报重新跑过全量。
- `git diff --check` 通过。5176、5177、5178、5190 及临时 5181 端口均无监听。

## 阶段边界和后续

P1 模块未接入现有生产读写；本轮无数据库迁移、数据清空、发布、DataAgent 管理台同步、commit、push 或 PR。P2 应在同一完整集成分支同步切换后端生命周期、提案、来源/实例/指标预览、MCP、DataAgent 及 Claude 负责的前端；在这些切换完成前不部署半切换系统。P0 的新交互确认和 P2～P5 检查项不在本轮虚报完成。
