# Ossie 原生化 P1 实施进度

M1–M5 为当时的阶段记录。2026-10-09 产品决定由 M6 清理非 v3 会话，替代 M2/M5 中的旧会话切换及审计方案；当前代码不再提供旧会话兼容。

约束：仅当前 worktree；不启动/重启服务，不 make build，不 commit/push。测试使用隔离的临时 SQLite/PostgreSQL 数据库；不修改实际业务数据库，未访问演示目录。

## M1 — 2026-10-09

已完成：显式 v3 原生导入/编译入口；ValueType、EntityType、owner_ref、有序角色、一元/二元/多元关系、Any/内置值概念；字段出现状态、共享 position、读法/表达式原文与重复规则独立 ID。概念及关系数组按原位置恢复。为 v3 发布补齐继承与属性读取。语义层只做已冻结结构的保真承载，现有运行路径尚未切换。

验收：A account-model-v2 的 **6/6**、B architecture-governance 的 **8/8** 多元 relationships 节点经过导入→持久化→发布→导出与原节点 JSON 等价（包括角色/读法顺序及缺省）；专项 4 passed。两文件在该显式入口整体 JSON 亦等价，第二次导入/导出幂等。

全量：`cd apps/api && uv run --python 3.13 pytest -q` → **444 passed, 9 skipped, 0 failures**（48.67s）；`uv run --python 3.13 ruff check src tests` → **通过**。9 项为现有需外部环境的跳过项。

下一步：M2 接回已保存的运行时切换基础，统一业务 reader/writer 为 v3；实现独立 CAS 会话迁移事务，保留旧 manifest/哈希与历史版本；保持 DataMapping/data_join 链路。

未决：M1 期间业务导入默认仍 v2，v3 必须显式选择，将在 M2 切换。平台扩展身份投影、旧 Action/显示信息恢复与读写兼容在运行时切换时一起验证。旧快照丢失的原生信息无法重建。

## M2 — 2026-10-09

已完成：业务草稿/版本读取与新写入统一显式 v3；历史 v1/v2 默认 reader、快照行与哈希算法保留。base/latest/draft 先纯迁移再三方合并。新增 migrate-v3 端点与独立事务，按 workspace/revision/状态/原 schema+草稿 CAS；原子写新 hash、revision、identity 与迁移审计，旧 mapping ID 退休且记录 provenance。旧 manifest、原草稿/哈希/候选保存在审计中；旧 token 清除，批次 expired、待接受项 superseded，旧提案提示重新生成，迟到结果被租约/CAS 隔离。

验收：纯读不写数据库、切换幂等、旧提案拒收、旧 pinned 哈希验证、revision/identity 失败整笔回滚均通过；既有 DataMapping/data_join 查询通过临时兼容适配继续工作，v3 存储 mappings 为空，未启用 P3 通用语义派生视图。

全量：API **447 passed, 9 skipped, 0 failures**；ruff **通过**（仅修正 import 排序后复检）。下一步 M3：嵌套角色 client_ref、角色内容/顺序合并专项、实例角色校验与建模提示词。

未决：前端还未接入 v3 读写；M3 完成后验证映射提案与现有表建模路径；M4 补全多元图谱与实例邻域。

## M3 — 2026-10-09

已完成：v3 提案 schema；roles[].concept.ref 与角色自身 client_ref 解析、角色值 client_ref 依赖，owner 引用 `关系client_ref:owner`，持久化前消除全部 client_ref。角色内容按 ID 合并，角色顺序独立在 `/roles/order` 合并，重建 position。material_links 校验角色覆盖、重复、实体继承、值概念/builtin、显式 ManyToOne/OneToOne 与二元端点一致性。保留 Action 与实例属性安全校验。建模提示词说明 ValueType、一元/多元关系与 role_values 写法。简单映射提案经既有 DataMapping 合同适配到 v3 节点，查询回归通过。

验收：新增 6 项运行时专项（角色/事实引用接受、重复引用拒绝、换序冲突及解决、内容+单边换序独立合并、OneToOne 逆向基数与继承、映射提案存储）全部通过。

全量：API **453 passed, 9 skipped, 0 failures**（118.57s）；ruff **通过**。

下一步：M4 MCP 完整角色、角色搜索、多元语义超边与实例邻域。未决：前端 v3 兼容与只读交互留 M5；通用复杂映射编辑与派生视图仍属 P3。

## M4 — 2026-10-09

已完成：MCP get/list 元素与 get_ontology_type 返回 owner_ref、有序 roles、owner_role_id 和含隐含 owner 的 all_roles；ValueType 可列出。搜索包含角色名称/概念与读法。语义图谱对不能表示为两个实体端点的关系生成 link_type 超边节点与有序 role incidence 边，保留所有值/Any 角色。expand_object_graph 通过 role_values 查找所有实体角色，返回角色定义与原事实；现有数据库二元邻域也返回完整角色。

验收：新增 4 项 MCP/图谱专项；多元角色、值概念、搜索、角色顺序、自关系重复角色连接、实例邻域及一元 owner 均通过。前端改动前基线为 22 files / 103 tests passed。

全量：API **457 passed, 9 skipped, 0 failures**（120.81s）；ruff **通过**。

下一步：M5 前端角色列表/读法、暂只读保护、小菱形超边；接入原生编辑适配，确保二元编辑与简单映射表单可继续工作。

未决：P3 通用语义派生查询、复杂映射编辑未启用；M5 进行中。

## M5 — 2026-10-09

已完成：前端原生 v3 类型与读写适配；关系目录、元素面板展示隐含 owner 与全部附加角色、值/Any 概念及有序读法。多元关系编辑按钮和直接编辑链接均保护为“暂只读”。语义图谱使用小菱形超边节点，保留每个角色的独立连接；实例图支持 role_values。二元关系沿用编辑表单，保存时回写 v3，不把端点兼容字段写入快照。旧会话仅在用户写操作时先显式 revision CAS 切换。简单 DataMapping/data_join 表单通过请求中的独立兼容参数提交，草稿中不保存派生字段；未改动表单保持原生节点原样。补齐二次导入的语义节点身份、角色换序身份、规则 owner 的有序引用及 identifier 编辑保真。

验收：前端新增原生草稿保真、只读编辑保护、二元保存、超边全部角色、实例多元邻域、兼容表单与切换 CAS 测试。API 新增 6 项表单/提案/再次导入回归：A/B 未改表单原样、改简单映射保留其他原生结构、语义节点 ID 往返稳定、元素保存同步会话与发布版本、规则提案挂回 owner、平台二元默认兼容。

全量：API **463 passed, 9 skipped, 0 failures**（142.23s，2 项依赖弃用警告）；`uv run --python 3.13 ruff check src tests` **通过**。Web `npx vitest run` **25 files / 113 tests passed**（最终复检 3.85s）；`npm run lint` 与 `npx tsc -b` **通过**。`git diff --check` 通过。

下一步：M1–M5 实施与本地检查全部完成，交评审方审阅并提交。未执行 git commit/push，未启动或重启服务，未 make build，未修改演示目录。

遗留与边界：

- 9 项既有 PostgreSQL/MySQL 外部测试因未提供隔离环境而跳过；本次会话迁移事务在临时 SQLite 中验证，真实 PostgreSQL 并发锁/迁移运行仍需部署环境检查。
- 新增 Alembic `20261008_000001_session_v3_cutover` 审计表迁移已提供，未对实际数据库执行；部署时须先应用。
- 历史 v1/v2 已丢失的原生字段、多元角色与复杂映射不能凭迁移恢复，保持 migrated 标识，需重新导入源 Ossie 才能恢复。
- P2 概念同义词及扩展碰撞 UI、P3 通用语义派生视图/复杂映射交互、P4 指标查询仍按原计划后续实施；当前简单 DataMapping/data_join 兼容路径继续工作。

## 最终往返结果

A（account-model-v2）：**6/6** 多元 relationships 节点等价；B（architecture-governance）：**8/8** 等价。导入→持久化→发布→导出保留数组顺序、缺省与原生表达式；两份文件在专项中整体 JSON 亦等价，第二次导入/导出幂等。ValueType、一元关系、值与 Any/builtin 角色、重复长表达式专项通过。历史 v1/v2 reader 与原哈希回归保持通过。

## M6 — 2026-10-09（产品修订：清理旧会话，撤除兼容方案）

已完成：按产品负责人最新决策停止旧会话兼容。新增 Alembic `20261009_000001_discard_legacy_sessions`，在同一迁移事务中按子表依赖顺序删除 draft.schema_version 非字符串 "3" 的建模会话、提案批次/项/依赖、决定请求/项与会话运行状态；缺失/null/数字 schema、非对象草稿亦删除。按 400 个会话分批执行，JSON 由 SQLAlchemy 解码后判定，兼容 PostgreSQL/SQLite，重复执行不影响保留数据。删除废弃的会话/逐项迁移审计表；保留已经部署过的 `20261008_000001` revision 文件及迁移链，支持从已安装 P1 revision 继续升级。downgrade 仅恢复上一 revision 的空审计表，不重建已删除用户数据。

保留：所有已发布版本的原 snapshot_json、ossie_json、sha256，材料/块、空间/成员、连接/元数据、服务令牌/作用域、元素身份登记及 v3 会话。签名运行 grant 无独立凭据表，旧会话删除后认证失效；服务令牌不删除。历史版本/快照的纯读迁移、旧哈希验证、base/latest/draft 先统一迁移再三方合并继续使用。新会话直接 v3，正常 revision CAS、建模结果回收、提案接受、发布和实例查询继续工作。

已撤除：旧提案 before/after/expected_target_hash 翻译与逐项审计、透明自动切换服务、旧提案 ValueType 同步、migrate-v3 路由/前端调用/返回字段、会话迁移运行时模型和旧切换专项测试。保留新会话同样需要的简单 DataMapping/data_join 表单和提案适配、同名关系 join 作用域修复、结果租约/任务锁保护（避免新运行的迟到回调存入错误批次）。这属于 P1 既有链路适配，未启用 P3 通用派生视图。保留元素保存“结构→作用域→合并→领域”校验顺序及 ELEMENT_SCOPE_INVALID 错误码修正；保留 Settings/.env 与 Alembic 日志配置 UTF-8 读取，alembic.ini 注释采用 ASCII 兼容 Alembic 自身在 C locale 下的初次解析。

导入报告：新增类计数比较现有元素与实际导入身份，不再按输入数组大小计数，replace 同样比较已有集合；concept_mappings 按 ID 计算 mappings_added/mappings_updated。A/B 导出再次导入在 merge/replace 下全部报告计数为 0，草稿 JSON 不变；B 的 mappings_added 从错误的 21 修正为 0。局部导入新增 1 个概念及 1 条映射只计 1，同时已有概念的说明修改计 objects_updated=1。A **6/6**、B **8/8** 多元关系原生往返、ValueType、旧快照与哈希回归仍通过。

新增验收：清理/保留与新提案接受→发布→实例邻域查询各在 SQLite（启用外键）和真实 PostgreSQL 临时库执行，共 4 项；A/B × merge/replace 再导入零计数及局部新增，共 5 项。真实 PostgreSQL Alembic 从旧 head 升级、降级、再次升级与历史 identity/约束测试同步删除策略。新建运行回归改用 v3 fixture，继续验证结果回收、重试、任务/租约隔离。清理及导入/Alembic 专项 **11 passed**，版本/材料/连接/令牌保留、旧 grant 失效、清理幂等均通过。覆盖矩阵生成脚本和方案第 7 节同步本次产品修订。

最终全量：设置 ONTOFOUNDRY_TEST_POSTGRES_URL 指向已有 PostgreSQL 服务，所有 PostgreSQL 测试自行创建/删除隔离数据库，执行 `cd apps/api && uv run --python 3.13 pytest -q` → **477 passed, 1 skipped, 0 failures**（173.20s，2 项现有依赖弃用警告）；`uv run --python 3.13 ruff check src tests` **通过**。Web `npx vitest run` → **25 files / 113 tests passed**；`npm run lint`、`npx tsc -b` **通过**。`git diff --check` **通过**。

下一步：交评审方审阅/提交，部署时应用最新 Alembic revision。当前 worktree 已完成 M6，不再推进旧会话兼容。

未决与边界：仅 1 项 MySQL 外部测试因未配置隔离环境跳过；最新清理迁移尚未对实际 ontofoundry_ossie 业务数据库执行。M5 记录中 PostgreSQL 未验证的限制已由本轮临时库验证覆盖。历史源信息恢复及 P2/P3/P4 边界不变。未执行 commit/push，未启动/重启服务，未 make build，未访问或修改演示目录。

## M7 — 2026-10-09（可选角色名与读法回归）

已完成：检查提案、编辑、v2→v3 快照迁移和 Ossie 原生导入/导出的全部角色构造。`contracts/proposals.py` 的新 v3 运行输入适配将二元端点写法确定性转换为 owner_ref/roles；只复制显式的 target_role_name/source_role_name，未提供时 role.name 保持 None，绝不查询或填入目标概念的中文显示名。原生 roles[].name 原样处理；新增/修改角色的 name 出现状态只对应非 null 的显式值，清除名称时移除 name 出现标记，防止导出 name:null。输入原始字节/result_sha256、依赖和嵌套 client_ref 保持原合同。这是新 v3 运行的输入适配，不恢复 M6 已撤除的旧会话/历史提案翻译。

修复受影响位置：`domain/snapshot.py` 撤除未命名自关系的 related 推断；`ossie/native.py` 撤除平台角色导出时补 related/role_N；`apps/web/src/lib/nativeDraft.ts` 与 API 类型补齐显式 source/target 角色名的正反向投影与回写，未命名角色不从概念显示名推断，清空角色名保留 null 并移除原生 name 标记。元素保存通过已有纯函数转换继续遵守上述规则；原生导入已经只从源 Role.name 键复制名称，无额外推断，保持不变。冻结的历史 v2 reader、哈希与 v2 编译合同保持不变。

显示与校验：中文概念/关系显示名继续放在 ai_context.ontofoundry.display_names；不写入原生 role.name。建模提示词说明：未命名角色读法使用 {concept}，显式命名角色使用 {concept:name}。未放宽 UNKNOWN_VERBALIZATION_ROLE/AMBIGUOUS_ROLE_NAME 校验；自关系没有可区分的显式角色名时由语义校验报歧义，不自动补名字。覆盖矩阵及其生成脚本同步这一可选字段合同。

新增验收：API 新增 16 项。二元端点输入和原生 roles 输入各覆盖命名/未命名，在 SQLite 和真实 PostgreSQL 临时库接受全部提案→预览无错误→发布→导出→重新导入；使用退货单/客户/订单中文显示名和 {return_order}、{customer}、{order} 技术名占位符复现，未命名时导出 roles 完全不含 name，显式命名时准确保留 name 与 {concept:name}。另覆盖错误的显式占位符阻止发布、元素保存保留未命名角色、提案清除显式角色名不导出 null，以及正/反方向的 v2 自关系纯迁移。M7 + 既有表单专项 **22 passed**。Web 新增 5 项验证新建正反向关系显式名、显示名编辑不影响未命名角色及清空名称。

最终全量：已有 PostgreSQL 服务上仅创建/删除临时测试数据库；设置 ONTOFOUNDRY_TEST_POSTGRES_URL 后执行 `cd apps/api && uv run --python 3.13 pytest -q` → **493 passed, 1 skipped, 0 failures**（199.11s，2 项现有依赖弃用警告）；`uv run --python 3.13 ruff check src tests` **通过**。Web `npx vitest run` → **25 files / 118 tests passed**；`npm run lint`、`npx tsc -b` **通过**。`git diff --check` **通过**。A **6/6**、B **8/8** 多元关系原生往返、历史快照/哈希、M6 清理与计数回归仍通过。

下一步：交评审方审阅/提交，并重新验证真实 DataAgent 的备用会话流程。未提交、未启动/重启服务、未 make build、未访问演示目录。

未决与边界：1 项 MySQL 外部测试仍因未配置隔离环境跳过。没有对 ontofoundry_ossie 业务库中的既有提案/已接受草稿做猜测性角色名改写；已显式存入角色的名字可能来自用户或智能体，不能仅凭中文名称判断可删除。真实 DataAgent 未在本轮重新运行；测试使用相同提案形状、真实 PostgreSQL 持久化和完整 API 发布链路。

## M8 — 2026-10-09（二元实例角色值与端点合同统一，真实结果回放）

根因：M3 提案合同允许 material_link 只提供 role_values，但二元实例领域校验仍要求 source_id/target_id 已存在；解析器没有生成兼容端点。提案名称和元素实例表又直接使用空端点，因而出现“? → ?”。这是新 v3 事实输入与兼容视图之间的缺口，与旧会话迁移无关。

已完成：新增纯函数 `domain/fact_views.py::binary_fact_view`，仅对 owner 和唯一附加角色均为 object_type 的可表达二元关系补全兼容视图。通过稳定角色 ID（owner 为关系 ID 派生的 role:owner，另一端为附加角色 ID）定位角色，遵循 endpoint_direction，不依赖 role_values 数组排列。只给角色值时派生端点；只给端点时生成 owner/附加角色的有序 role_values；两者都有时拒绝矛盾、重复或不完整角色。多元、一元和值端点事实仍只使用角色值，不生成二元端点；已有概念类型、继承与基数校验继续执行。

提案解析在 client_ref/依赖解析完成后统一事实表示，再计算规范化 fingerprint；结果原始字节哈希保持不变。新建输入 schema 允许端点写法省略 role_values，持久化 v3 schema 仍要求原生角色值。领域校验复用同一纯函数，因此当前已存储、只有 role_values 的 v3 pending 提案直接接受即可补全端点，无需重跑智能体、迁移会话或改写原始批次。提案显示名也按角色 ID 投影端点并解析待创建对象名称；MCP 文档/数据库邻域补齐 source_name/target_name。Web 元素实例表、对象邻域与实例图使用只读端点投影，二元事实仍画直接边，多元事实仍画超边；不修改输入草稿的角色内容或顺序。提示词同步说明二元两种输入写法及一致性约束。

真实用例：按评审提供路径将两份文件原字节复制到 `apps/api/tests/fixtures/real_runs/`。原始结果 SHA-256 为 `91d9409fc6789c7f324f5809ca4ee0b61d7476c6e44cc752ed30d705d4c0bac5`，转换批次/快照文件为 `4086def709678252fd706b05128db62542dd8aa76e949fbf34bf9e8dca2bae85`。保留原 workspace/session/base_version ID、revision、原始输入哈希及证据引用。完整材料文件未提供，回放只按引用行重建证据 quote 并调用真实 material_lookup/证据校验，未声称验证原材料全文哈希；已发布快照是读投影，保留输入头中的历史版本哈希。上述边界在 fixture README 与测试注释中明确记录。

新增验收：API 14 项——SQLite 与真实 PostgreSQL 临时库分别回放原始角色值输入、仅端点输入及提供的已存储 v3 角色值批次，共 6 条完整链路；另有 6 项正/反方向 × 两种输入/同时输入的纯函数、幂等、乱序角色值与显示名测试，以及 2 项矛盾/重复角色、多元端点拒绝和持久化 schema 约束测试。每条完整链路均 **26/26 提案接受、6/6 实例关系显示正确、预览零错误、发布成功、Ossie 导出合法**。MCP search_objects/get_object/expand_object_graph 均通过：**3/3 退货单**（RT-202601-001/002/003），每个实例邻域均含该退货单、关联客户与订单，共 3 个对象和 2 条关系，两端名称齐全。原始角色值写法与仅端点写法的规范化内容、fingerprint、依赖完全相同。Web 新增 5 项覆盖正反向二元实例图、元素表名称及对象邻域导航。

最终全量：仅使用已有 PostgreSQL 服务创建/删除隔离测试数据库；设置 ONTOFOUNDRY_TEST_POSTGRES_URL 后执行 `cd apps/api && uv run --python 3.13 pytest -q` → **507 passed, 1 skipped, 0 failures**（192.87s，2 项现有依赖弃用警告）；`uv run --python 3.13 ruff check src tests` **通过**。Web `npx vitest run` → **26 files / 123 tests passed**（4.55s）；`npm run lint`、`npx tsc -b` **通过**。`git diff --check` **通过**。A **6/6**、B **8/8** 原生多元关系往返、M6 清理/计数、M7 可选角色名与旧快照/哈希回归全部保持通过。

下一步：交评审方审阅/提交，并部署后在现有备用会话接受这批提案；不需要重新生成。未执行 commit/push，未启动或重启服务，未 make build，未访问或修改演示目录及 ontofoundry_ossie 业务库。

未决与边界：1 项 MySQL 外部测试仍因未配置隔离环境跳过。本轮使用实际 DataAgent 输出回放，没有重新发起模型运行；原材料全文未提供的限制如上。历史源信息及 P2/P3/P4 边界不变。
