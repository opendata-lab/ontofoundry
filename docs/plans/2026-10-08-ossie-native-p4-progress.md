# P4 指标查询进度

> **已被 core-1 主设计取代。** 本文记录 2026-10-08 方案及当时的进展，保留作历史参考；现行模型与实施以 [core-1 主设计](../design/2026-10-14-core-model-and-format-adapters.md) 为准。

基线：P3 提交 9f07335；仅 feat/ossie-native worktree 修改，不提交、不操作服务、不访问外部演示目录或业务数据库。

## M1 合同与安全规划 — 2026-10-11（进行中）

已核对 P4 方案及 B 原生指标、字段与时间说明。通过 `uv add sqlglot` 安装 30.22.0，pyproject/uv.lock 同步。执行模型只读派生，不修改原生表达式、上下文或默认值。

设计：仅显式引用一个同语义模型 dataset 的聚合指标可执行；指标及 field.expression 使用精确 AST 类白名单，拒绝用户语句、子查询、未知/限定函数和跨作用域引用。字段按目标方言优先、否则 ANSI_SQL 转译。group_by/filters 只接受当前数据集逻辑字段；过滤值参数绑定。表只取 dataset.source 的标准限定表名。默认 limit=100、最大 1000，多取 1 行确定截断。默认语句超时 15s，使用 `ONTOFOUNDRY_METRIC_QUERY_TIMEOUT_SECONDS` 配置，复用连接管理的只读事务。

时间参数仅读取 metric/dataset custom_extensions（vendor_name=ONTOFOUNDRY，data 为 JSON 对象字符串）：`time_semantics: snapshot|rolling|event`、`time_field`（逻辑字段名），metric 显式值覆盖 dataset 值。同作用域重复键冲突拒绝。没有参数但存在 snapshot_date 时保守视为 snapshot。snapshot/rolling 必须对时间字段唯一等值过滤，或给 as_of（不可同时提供时间过滤）；as_of 在该数据集全局选不晚于目标日的最大快照日期，再与其他过滤相交，不跨日期累加。生成器可构造受控 MAX 快照子查询；用户输入/原生表达式不允许子查询。event 才允许范围和跨日分组；不自动把 ai_context.instructions 解释为执行参数，不默设环境 PROD。已有 A/B 原文不补扩展。

里程碑：M1 AST 编译/目录与单测；M2 MCP/只读执行及时间语义；M3 隔离 PostgreSQL B 指标验收；M4 全量 API/ruff/Web、A/B 0 差异。当前测试数字待首轮专项；下一步实现编译器与服务。

## M1 / M2 实现检查点 — 2026-10-11

已实现 metric_query 服务与 MCP 注册，目录返回标准 name/派生中文 display_name/同义词、涉及数据集、可执行性与原因、可分组/过滤字段及时间要求；中文显示名只从平台显示名/首个同义词派生，不写回原生。字段表达式同样过白名单，未使用的复杂字段不阻断指标；禁止聚合外游离列及嵌套聚合。仅支持明确引用单个数据集的聚合指标，COUNT(*) 无数据集引用时只解释。跨数据集返回当前数据集之间的直接 dataset_relationships，不执行连接。

过滤绑定通过 SQLGlot AST 生成驱动参数模板，执行使用 exec_driver_sql；原生字符串里的冒号、百分号不作为用户参数或拼接 SQL。默认只读连接超时不变（旧路径 10s），指标显式传入配置的 15s；PG statement_timeout/MySQL MAX_EXECUTION_TIME/Doris query_timeout 同步。目录沿用映射读取授权，执行沿用实例读取授权，无新权限模型。MCP 交付页只补工具名，不做指标 UI。

两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。

Web 首轮 **134 passed / 1 failed**，ElementInspector 的异步 dialog 等待超时（同时运行 API 专项）；尚未修改该组件，待 API 专项结束后独立复跑。ruff 与 git diff --check 已通过。下一步 PostgreSQL/无损专项完整通过后，按 M4 全量验证。

## M3 PostgreSQL 验收 — 2026-10-11（完成）

隔离 PostgreSQL 专项最终 **7 passed**（84.30s），使用现有 pg_client 自动创建/强制清理 `of_t0_*` 独立库，源表同样在该库。未访问 ontofoundry / ontofoundry_ossie。导入 B 原文件，用真实只读连接与加密配置执行 MCP：

| --- | --- | --- |

两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。

时间 event 参数只追加到指标 ONTOFOUNDRY custom_extensions；跨日期错误率为 540/1400，导出再导入稳定。查询不修改 published snapshot；原生无损比较沿用 P1–P3 reverse_export_edits 可逆平台扩展合同，逐字段原文等价。首轮未逆除新增的可逆平台扩展导致 3 个测试断言失败，现已统一与既有无损测试方法，未修改导入/导出实现。另完成参数冲突、dataset 时间参数/metric 覆盖、最大 limit 以及常见聚合组合复核。

Web 重新运行完整命令链：**28 files / 135 passed**（23.36s），npm run lint、npx tsc -b 均通过；ElementInspector 原测试无需改动，首轮异步等待问题未再复现。全量 API 待 M4；API 首轮候选专项（包含已修复断言的旧进程）为 84 passed / 3 failed，不作为最终结果。下一步最终全量，日志保存忽略目录 .pytest_cache。

## M4 最终验证 — 2026-10-11（进行中）

最终编译/安全/MCP 单元专项 **73 passed**（27.49s），PostgreSQL 实际执行专项 **7 passed**；新增合计 **80 个回归变体**。ruff 全量通过。最终 API 全量启用隔离 PostgreSQL 测试入口运行，输出 `apps/api/.pytest_cache/p4-api-final.log`；Web 完整输出 `apps/api/.pytest_cache/p4-web-final.log`，均在本 worktree 忽略目录，便于中断恢复。已知边界：跨数据集不执行；外部 MySQL 只有方言编译单测，本地未配置真实 MySQL 执行环境；目录 executable 表示结构与连接配置具备，网络/物理类型/实时权限在执行时验证。

两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。

全量首轮检测出 2 个旧 MCP 协议测试固定工具数量为 11；新增两个工具后已更新为 13，并验证现代/旧版协议均返回新工具。属于测试合同更新，指标专项和实际查询无此失败。首轮继续检查其他回归，尚不标记 M4 完成；测试收集总数为 674。
