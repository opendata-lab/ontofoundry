# 语义模型与关系编辑实施进度

分支 `feat/semantic-layer-editing`。原型已审阅；只在本 worktree 修改，不执行 git 写操作，不操作 8000、演示目录或 opendataworks。测试优先使用临时 SQLite 和自动创建/清理的隔离 PostgreSQL 库。

## M1 原生局部编辑服务（初始记录）

已核对保存合同：目录是干净投影，不可直接回写；现有元素保存拒绝 n 元关系与语义集合变更，简单映射写入器拒绝复杂树。实现将从完整快照应用显式局部操作，保留未编辑节点及原生出现状态；复用版本 CAS、会话 revision CAS、三方合并和发布校验。

计划里程碑：M1 局部保存/引用保护/树投影/草稿 SQL 编译预览及 API 专项；M2 语义模型工作台和表单；M3 元素卡片角色、复合键与复杂映射；M4 API（含隔离 PG）、ruff、web、lint、tsc 与无损最终验收。产品统一用“语义描述”，显示名仅取平台 display_names，长说明用 HintIcon。

初始状态：当时尚未测试；最新状态和结果见文末各里程碑。

### M1 后端基础已完成
- 原生对象局部保存、引用保护、映射树投影、草稿 SQL 仅编译接口已接入。
- 新增 API 测试：20 passed（SQLite 与隔离 PostgreSQL）；相关回归：94 passed。
- 下一步：语义模型工作台及元素卡片编辑，补齐联动与全量验证。

## 2026-10-12 恢复后的里程碑记录

### M1 原生局部编辑服务（完成）

- 新增 `/semantic-saves`、`/semantic-change-preview`、`/metrics/{metric_id}/sql-preview`。保存从完整快照应用显式字段修改，按元素聚合隔离，会话 revision CAS / 版本 CAS / 三方合并 / 发布校验复用原流程。
- 删除保护返回具体引用清单；重命名同步修改逻辑引用、主键与连接键，SQL 字符串和注释不改；映射节点按稳定 ID 和各 slot 的顺序保存。
- 语义模型 / 数据集 / 字段 / 指标等中文显示名仅进入 `extension_v4.display_names`，原生 `name` 不改。导出与再次导入保留这些显示名。平台新建模型保留 Schema 必需的 concept_mappings 容器。
- API 专项：28 passed（SQLite + 隔离 PostgreSQL）；后续预览纯函数/范围隔离 2 passed，一元关系保存 2 passed。此前元素保存、P3 视图与 P4 指标相关回归 94 passed。ruff 通过。

### M2 语义模型工作台（完成）

- 页面撑满可用区域，左目录 + 右详情 + 编辑抽屉。四个目录：数据集、数据集关系、指标、概念映射；数据集按引用分组，目录和字段分页。
- 数据集详情展示 source、主键/唯一键、字段表达式/方言/类型/维度/同义词，以及关联概念、指标与连接；复用 ConceptTag、TagList、HintIcon。
- 支持语义对象新增/编辑/删除，重命名前展示引用影响，删除拒绝保留清单；编辑期间冻结目录来源，避免外部刷新让旧表单取得新 CAS 基线。
- SQL 预览不执行查询，支持目标方言、分组、结构化筛选、快照等值或 as_of，保留 P4 安全与时间约束。
两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。
- web 全量 145 passed，lint / tsc -b 通过。语义页相关组件 10 项通过。

### M3 元素卡片编辑（完成）

- 移除 n 元关系编辑禁用分支；有序角色可增删/移动，支持实体、值概念、内置类型与 Any；角色名为空时不推断。
- 多重性按原生 OneToOne / ManyToOne / 未声明编辑。语义描述支持 chip 插入、未知占位符校验，显式名称和角色类型变动同步更新对应占位符。
- 二元关系复合键表单保持 owner/role 语义；复杂映射直接编辑完整树，原生修改经 explicit semantic_changes 附带到元素保存。n 元映射可按角色及语义模型查看连接，不压平成兼容二元端点。
- 元素卡片相关测试：ElementInspector 15、NativeRolesEditor 2、nativeDraft 15，均通过；API 覆盖 n 元换序、显式/空角色名、未知占位符拒绝、一元保存、复杂树保存范围隔离。

### M4 最终验收（当时进行中，完成结果见文末）

- 第一轮 API 全量：701 passed / 1 skipped，包含隔离 PostgreSQL；后续新增 4 项及预览/作用域修正已进入最终全量重跑。
- 最新 web：145 passed（29 文件），lint / tsc -b 均通过。
- 下一步：完成浏览器 SQL / 关系 / 复杂树保存验证，核对最新 API 全量、A/B 无损和编辑后 Schema + lint，清理自己启动的隔离验证进程。
- 未决：最终全量尚在运行。BuilderPage.tsx、SDK 包、演示目录及 opendataworks 未修改；8000/8010 未启停，业务数据库未操作。

### M4 浏览器验收与中断恢复（2026-10-12）

- 修复 SemanticModels.tsx 中 `<article>` 的闭合标签，并修复新增角色测试的 TypeScript 参数错误。
- web 全量 149 passed（29 文件），lint / tsc -b 通过。浏览器发现日期输入的 input 事件未同步状态，已兼容 input / change；回归用 input 事件验证快照日期。后续相关组件/适配器 28 passed，lint / tsc -b 通过，不重复无关全量。
- 关系目录发现起点空白：对外投影使用了内部键 `from_`；改用原生别名 `from`，元素卡片完整快照适配兼容内部键。增加 API 投影回归。
两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。
- 浏览器发布快照重新编译：Apache Ossie 0.2.0.dev0 官方 Schema passed / semantic lint passed，0 errors / 0 warnings。发布后的连接键、角色名与复杂表达式均再次读取确认。
- 本地验证截图保存在仓库外的私有验证目录，不随源码提交。
- 下一步：记录本轮 API 全量与最终专项结果、清理隔离进程。上一轮中断的全量没有最终结果，已补跑一次；后续投影小修复单独跑受影响专项。
- 清理完成：本次启动的隔离 API（8027，PID 78667）和 Vite（5178，PID 76219）已停止，端口检查无监听；验证浏览器页已关闭。8000/8010、业务数据库、演示目录与 opendataworks 均未操作。BuilderPage.tsx / SDK 包无差异；git diff --check 通过。
- 最后受影响 API 专项：`tests/test_semantic_editing.py` 36 passed（597.32s），SQLite / 隔离 PostgreSQL 均执行；A/B 无编辑导出各为 0 差异，编辑后导出均经官方 Schema + semantic lint。包含复合关系投影 `from` 回归、字段/数据集重命名、引用保护、映射树、n 元/一元、值概念属性和草稿编译预览。

### M4 最终结果（完成，2026-10-12）

- API 全量：`cd apps/api && ONTOFOUNDRY_TEST_POSTGRES_URL=postgresql+psycopg://of:of@127.0.0.1:55432/of_test uv run --python 3.13 pytest -q -rs` → **709 passed / 1 skipped**（1607.56s），隔离 PostgreSQL 已执行。唯一跳过为 `tests/test_stage_a_mysql.py:25`：未提供 Disposable MySQL 配置；另有 2 条现有测试依赖弃用警告。
- 全量启动后的最后小修复（关系目录 `from` 别名）已以语义编辑专项 **36 passed** 验证，未再重跑无关全量。专项同样使用 SQLite / 隔离 PostgreSQL，含 A/B 无损和编辑后校验。
- web 全量 **149 passed / 29 文件**；最后日期事件与完整快照关系适配修正后，受影响组件 / 适配器 **28 passed**。`npm run lint`、`npx tsc -b`、`ruff check src tests` 均通过；`git diff --check` 通过。
两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。
- 未决项：隔离 MySQL 集成环境未配置，保留上述 1 条跳过；本阶段没有已知功能阻断项。未做 git 写操作，未修改 BuilderPage.tsx / SDK 包，未操作演示目录、opendataworks、8000 / 8010 或业务数据库。

#### 改动入口

- 后端：`api/semantic_editing.py`（局部保存、引用影响预览、草稿 SQL 编译）、`domain/semantic_authoring.py`（原生局部操作、引用保护、重命名与树处理），以及 modeling / element_save / semantic_views / metric_query / Ossie 扩展投影。
- 前端：`SemanticModels.tsx` 工作台、`semantic/SemanticObjectForm.tsx` 与 `MappingTreeEditor.tsx`、元素卡片 `NativeRolesEditor.tsx` / `NativeMappingEditor.tsx`，以及 nativeDraft 适配、ConceptTag / HintIcon 和紧凑样式。用词统一为“语义描述”；恢复编辑入口，中文显示名仅取平台扩展。
- 测试与说明：`tests/test_semantic_editing.py`、语义页 / 角色 / 元素卡片 / nativeDraft 组件测试、本文及浏览器截图。


### 私有验证资料隔离（2026-10-12）

- 原始本地验证模型、演示素材、原型、截图与往返审计产物移出仓库，自动化测试改用合成夹具。
- 可选的真实模型测试和演示场景从仓库外读取；演示脚本使用 `ONTOFOUNDRY_PRIVATE_DIR`，缺少配置时跳过该阶段。
- 清理后的 API 全量（含隔离 PostgreSQL）：709 passed、1 skipped（未配置隔离 MySQL）；仓库外私有验证：241 passed。
- Web 全量：150 passed；TypeScript、ESLint、Ruff 通过；PostgreSQL 指标专项：7 passed。
- 工作区泄漏检查：0 命中，通用工程词汇豁免另行记录；`git diff --check` 通过。
