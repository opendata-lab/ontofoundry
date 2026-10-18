# core-1 P4 导入闭环实施记录

日期：2026-10-18。工作树：`codex/core1-remaining`，基线 `32b56ee`。全部改动尚未 commit/push。

## 已完成

- 新增 `ontology_imports` 与 `20261018_000001` Alembic revision，保存原始文件、独立 SHA、格式化材料、不可变报告和核心产物、预览匹配结果、基线及确认/补全历史。
- UUID 全量锁定优先于技术键；对象、归属成员、规则、Dataset、Mapping 一对一匹配。事实与证据不按业务值或引文合并。九集合及表达式解析引用重写，字面量不替换。
- 候选图不生成 delete；冲突及反向依赖闭包单独阻断，独立合法内容继续。合法名字交换保持原子性，包括同时存在其他无关冲突的情况。原有人工证据不可改作者、内容或转归属。
- 两步 API `/api/v1/modeling/workspaces/{workspace_id}/imports/{adapter_id}`，原始 bytes 上传、预览、确认、报告重开与人工补全。`ossie` 只作地址别名，拒绝旧 replace/publish 参数。
- 确认检查预览、材料、报告和产物完整性、已发布基线及身份登记。在同一事务创建草稿仍等于基线的会话和 pending 批次；不伪造 DataAgent task。SQLite 与 PostgreSQL 实测并发确认只创建一个会话。
- 裸 COUNT(*) 显式选择统计 Dataset；补方言/列元数据；修订来源定义重新转换。新批次沿 revision/hash/正常审阅，旧报告不改。当前阻断实时重算，修复父定义后，反向依赖可进入新提案。重复修订不会因批次唯一约束变成 500。
- Ant Design 三步导入弹窗、中文报告筛选/展开、材料定位、预览过期重试、取消与重开重置、提交防重。构建页、会话选择器和提案面板识别导入来源，支持重开报告和补全。
- 新增 imports Pydantic 接口模型、JSON Schema 和前端类型；核心模型仍不依赖格式适配器。可信导入使用独立提案构造，不放宽 Agent 结果协议。

## 统一验证

| 检查 | 结果 |
|---|---|
| 完整后端 pytest，配置一次性 PostgreSQL | **853 passed，2 skipped，0 failed/error** |
| 跳过原因 | 仅 2 项已有 MySQL 外部集成测试未提供一次性配置 |
| ruff check / format --check | 通过，174 个文件格式一致 |
| schema export --check | 通过 |
| DataAgent 建模技能契约测试 | 3 passed |
| check:core-types | 通过 |
| 完整前端 vitest | **42 files，186 passed** |
| tsc -b、eslint、生产 build | 通过 |
| test:visual，1440×900 | **33 passed** |

完整日志：`/tmp/ontograph-p4-final.log`、`/tmp/ontograph-p4-web-complete.log`、`/tmp/ontograph-p4-visual-complete.log`。3 个后端 warning 为已有 Starlette/httpx、anyio 弃用提示，以及 P3 既定 `construct` 报告字段与 BaseModel 方法同名。

13 份原生示例全部执行实际 HTTP 预览、确认、接受和发布，人工证据作者保留，缺材料逐项 dropped；重复导入 no-op。原始 A/B Ossie 示例未预处理，均执行同一闭环，机械结果不计入人工补全。覆盖哈希篡改、基线过期、权限隔离、并发/重复确认、重复修订、候选引用、同名交换与冲突闭包。

实际 Alembic 从空库及 `20261016_000001` 升级到 head，无 create_all 替代；迁移后用 HTTP 导入/审阅/发布，重复升级不改变新模型。旧 cutover 测试固定验证其自身 revision，新迁移测试负责 head。

## 局域网与视觉验收

Chrome 经 `http://192.168.0.107:5198` 访问真实前后端与迁移后的临时 PostgreSQL；`isSecureContext=false`，`crypto.randomUUID` 不可用。导入确认和提案接受使用 `newId()` 正常工作。

- 13 指标文件：7 条提案，无业务对象；正常接受与发布 v1。
- B 图书馆文件：103 条提案、225 条转换报告记录；条目级问题不阻止合法内容确认。
- 07 事实与证据文件：13 项定义转换、5 项缺材料证据 dropped；可筛选查看，未误删事实。
- 报告重开、人工补全折叠区、可搜索数据库方言 Select 的弹层、滚动、文件选择与重置均实测。

截图保存在 `/Users/guoruping/.codex/visualizations/2026/10/18/01a14d03-89dc-76d2-9e4d-505d36ada283/core1-p4/`。检查容器层级、对齐、字号、状态和表格密度均沿用 U4/U6 规则。新增两个导入截图基准，原有 32 个场景的基准文件未改。

用相同依赖单独构建 HEAD 基线：主 index 为 1,799.38 kB / gzip 568.63 kB；本轮 1,800.02 kB / gzip 568.80 kB，增加 0.64 / 0.17 kB。既有大 chunk 提示仍存在。

临时 API、Vite、专用浏览器已停止，一次性 `of-pg-p4` 容器及其数据库已删除；其他容器未动。工作树保留供审阅与 P5 继续使用。未执行开发/生产数据库迁移，未部署 DataAgent。

## 后续

P5：原生/Ossie 导出、下载与报告、官方结构校验和定向往返。P2 的外部部署与完整现场链路仍是单独事项。结构化 OR 多分支/多跳编辑继续保持低优先级。

## 提交前核对

2026-10-18：P3～P5 进入同一 PR/CI 交付流程，P5 已完成，阶段记录见对应进度文档。补齐跨工作空间切换时的文件/预览清理，以及导入报告切换会话或来源时的重置与迟到响应隔离，防止展示上一会话内容。

全部编辑后统一验证：Node 22.19.0 下 `npm test -- --run --maxWorkers=2` 为 44 files、193 passed，`npm exec -- tsc -b`、`npm run lint`、`npm run check:core-types`、`npm run build` 全部通过；`npm run test:visual` 为 34 passed，未产生额外基准变化。后端没有新增实现改动，沿用 P5 的 937 项完整回归与 82 项最终定向验证，本次重新执行 ruff、format、Schema check 和 diff check 通过。日志 `/tmp/ontograph-pr-{web,tsc,lint,types,build,visual}.log`。
