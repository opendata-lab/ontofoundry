# core-1 P5 导出与往返验收记录

日期：2026-10-18。基线 `32b56ee`，沿用 `codex/core1-remaining` 工作树中的 P3/P4；本阶段未 commit/push。依据主设计第 6、7、14.6 节和原计划 P5-01～P5-07，不新增核心业务字段。

## 已完成

- 原生四字段单文件保留全部定义、UUID、事实、人工证据及材料证据引用；明确不包含材料原文，不作为完整备份。
- Ossie 输出对象、七值类型、有效标识、单父、规则、成员分支与有方向路径、自关联正反读法及批准的显示扩展。标识值概念忽略大小写避让对象与内置名，稳定分配后缀。数组按规定规范化顺序。
- 每个 Dataset 和 Metric 恰好输出一项。属性字段与物理辅助列合并，冲突稳定分配别名并重写引用；来源键与业务标识分开处理。保留主身份、平铺附来源、复合键、映射表及可成立的物理连接；非主键 unique 不能表达业务目标身份时，仅报告业务映射损失，保留物理连接与 unique_keys。
- 连接作用域来自服务端 `resolve_dataset`，不从相同表名或 schema 猜连接。来源不明确时分开输出，不能成立的跨来源绑定明确报告；同一 Dataset 内的自关联仍可表达。
- COUNT 行数使用带本数据集登记列的精确 CASE；固定条件逐项回读，nullable COUNT 保持列计数，COUNT(*) 表达式只改该 AST 节点。比率展开完整分量、保留过滤、NULLIF 与小数除法，不造辅助指标。显式小数精度避免 MySQL 默认 DECIMAL 将分子取整；这属于导出 SQL，不进入核心模型，目标引擎精度仍由查询 Agent 调整。
- 快照和时间字段逐项 RT-60、物理元数据 RT-66；事实实例逐项 dropped，证据与规则元数据文档级说明一次。没有复用 RT-26 等既定编号表示其他含义。
- 每份可交付 Ossie 都跑固定官方 Schema 和现有语义检查。语义检查补上沿继承链解析标识属性；官方 Schema 未修改。09 空模型、13 仅指标模型及不能完整表达的必需指标稳定 error、无文件，不伪造业务对象。
- 导出 API 从明确指定的发布版本读取。报告、文件名、SHA 与下载 URL 对应同一产物；下载重验工作空间、版本、实例/映射读取权限及文件 SHA。GET 不写模型或创建版本；产物缓存只写应用文件目录。
- 发布页、历史表和版本比较接入 Ant Design 导出弹窗。格式/版本改变、关闭重开、旧响应到达、重新生成权限失败时均清理过期下载；不能自动换原生格式冒充 Ossie 成功。Pydantic、JSON Schema 与前端类型同步。
- A/B 原文件不预处理；定向测试核对核心定义、精确映射损失归属，以及再次导出剩余的 4 处字段/指标引用差异。只允许两个已核对别名按 RT-40/47 转换，排序按 RT-10 忽略；不允许整文件差异盖同一个 RT。删除旧覆盖率脚本及活动调用，历史覆盖率文档注明取代。

## 自动验证

| 检查 | 结果 |
|---|---|
| 完整后端 pytest，实际一次性 PostgreSQL/MySQL | **937 passed，0 skipped，0 failures/errors** |
| 原生/Ossie 导出、往返、API、复算定向检查 | 82 项；小数公式修订后重新核验受影响组 |
| ruff check / format --check | 通过，188 个文件 |
| JSON Schema export --check / core TS check | 通过 |
| DataAgent 技能契约 | 3 passed |
| 完整前端 vitest | **43 files，191 passed** |
| tsc -b / eslint / production build | 通过 |
| 1440×900 视觉回归 | **34 passed** |

13 份原生逐字段、UUID 往返；01–08/10–12 Ossie 通过官方 Schema 与语义检查，09/13 无 artifact。13 的指标互译使用单独明确的业务容器，原始示例 JSON 未加占位对象。

在 PostgreSQL 17 和 MySQL 8 的一次性数据库同时比较原核心与导出再导入的指标结果，并直接执行文件内公式，覆盖小数分子、过滤、复杂 CASE、去重、NULL 与行计数。RT-66 丢失的引擎声明由测试明确补选，不从 ANSI_SQL 猜回。测试只建虚构临时表，结束删除。

主要日志：`/tmp/ontograph-p5-release-api.log`、`/tmp/ontograph-p5-release-web.log`、`/tmp/ontograph-p5-verified-visual.log`；定向公式验证日志 `/tmp/ontograph-p5-delivery-directed.log`。后端 3 个 warning 为既有 Starlette/httpx、anyio 弃用提示和 P3 `construct` 字段与 BaseModel 方法同名。

## 局域网、视觉与包体

真实 Chrome 通过 `192.168.0.107` 的 HTTP 开发服务和生产预览访问真实 API；`isSecureContext=false`，`crypto.randomUUID` 不可用，未修改浏览器安全设置。

- 历史 v1 的仅指标模型原生下载成功，6 个指标完整，下载字节 SHA 与报告一致；Ossie 明确报错、下载入口为 0。
- v2 销售模型的 Ossie 下载成功，2 个数据集各一项，文件 SHA、官方 Schema 与语义校验通过。
- 明确选择历史版本、切格式后清理旧文件、报告分页/滚动与弹窗底部操作可见；生产预览也实际下载并核验原生文件。

截图：`/Users/guoruping/.codex/visualizations/2026/10/18/01a14d03-89dc-76d2-9e4d-505d36ada283/core1-p5/`。新增 2 张导出基准；审阅后仅更新 3 张既有基准：服务接入、历史比较、发布冲突。新增标准高度页头操作使相关容器下移 8px，历史表增加导出列，比较区增加导出目标版本按钮；对齐、字号、状态与表格密度正常，其他基准未改。

同一依赖环境下，P4 主 index 1,800.02 kB / gzip 568.80 kB；P5 为 1,800.18 / 568.83 kB，增加 0.16 / 0.03 kB。相对 main 基线 1,799.38 / 568.63 kB，累计增加 0.80 / 0.20 kB。DeliveryPage chunk 从 39.03 / 14.13 增至 42.53 / 15.23 kB。CSS 55.94 / 10.91 kB 不变，未新增依赖；既有大 chunk 提示保留。

CSS 台账：本轮新增/删除 CSS 均为 0；旧 `reference.css`、`publish.css`、`ontology-reading.css` 已在前阶段退役，不重新引入。导出与报告复用布局组件、Ant Design、Tailwind 和现有 tokens。

## 收尾与剩余边界

专用浏览器、API、开发与生产预览服务均已停止；一次性 `of-pg-p5`、`of-mysql-p5` 及临时数据库/下载文件已清理，其他容器未动。保留当前工作树和审阅截图。

P3～P5 本地实现完成；本记录形成时尚未提交/推送，后续代码交付状态以 `codex/core1-remaining` 分支的 PR 为准。开发/生产数据库切换、DataAgent 技能包与提示词部署继续作为独立事项；未执行真实数据库迁移或外部部署。结构化 OR/多跳编辑仍是低优先级；原生 ZIP、通用自动往返分类器和导入后 AI 补全运行仍按原计划另期处理。

提交前补齐导入弹窗切换工作空间与报告切换来源的状态回归后，前端最新结果为 44 files、193 passed；类型、lint、构建及 34 项视觉检查全部通过。主 index 与 CSS 体积不变，DeliveryPage chunk 为 42.53 kB / gzip 15.22 kB。详见 P4 进度文档的“提交前核对”。
