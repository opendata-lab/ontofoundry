# 实例库实施计划

设计：`docs/design/2026-10-21-instance-store.md`（IS-01～IS-12 已确认）。路线图步骤 3。

## 分块

| 块 | 内容 | 负责 | 依赖 |
|---|---|---|---|
| A 后端主体 | 实例库四张表与迁移；core-1 移除 `material_objects`／`material_links`（Pydantic、JSON Schema、校验）；切换清单（IS-02：删字段、重算哈希、失效旧运行固定草稿与未确认导入）；实例服务（读写、revision 比较更新、历史、软删除）；提案链路改用实例基线（运行上下文、结果解析、有效状态、接受与撤销、待发布与生效 IS-04、放弃会话 IS-10）；共享发布服务中的引用检查（IS-05、IS-08）；读取接口（MCP `search_objects`／`get_object`、REST 实例接口、固定版本过滤 IS-09）；材料用量（IS-07 与 M7）；Ossie 导出移除事实读取 | Codex | 无 |
| B Skill 脚本 | entity-extraction 与共享脚本（`show_element`、`check_part`、`prepare_result`、`check_result`）按实例基线定位实例目标、生成 before/hash；示例与写法包同步；体积预算不放宽 | Codex | A 的契约 |
| C 前端 | 类型同步（含生成的 `core.generated.ts`）；实例页、提案详情、发布面板、文档用量改读实例库；“放弃会话”操作与待发布实例列表；界面文案“事实”改为“实例”（IS-12）；1440×900 截图与视觉测试 | Claude | A 的接口 |

## 验收

- 后端：pytest 全量、ruff、契约导出检查；新增用例覆盖并发覆盖被拒、跨会话、待发布生效与放弃、发布阻止（两条发布通路）、固定版本过滤、切换后旧运行被拒。
- Skill：`integrations/dataagent/tests` 全量与预算。
- 前端：tsc、eslint、vitest、视觉测试，局域网地址联调。
- 真实建模验收（DeepSeek）暂缓。
