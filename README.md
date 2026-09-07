# OntoFoundry

OntoFoundry 是面向企业业务人员的本体工程平台。V0.1 聚焦 Markdown 与数据库映射驱动的 Object、Link、Object Type、Link Type 建模、可视化编辑、实例浏览、版本发布、Apache Ossie JSON 校验，以及面向应用和 Agent 的 REST API / MCP 本体服务。

当前已进入正式代码实现：React + TypeScript 前端、FastAPI 后端，保留 HTML 原型作为历史参考。只维护一份权威设计：

- [V0.1 完整设计](./docs/design/2026-09-01-enterprise-ontology-intelligence-platform-design.md)

已迁入的内置建模资产：

- [md2ossie Skill](./.claude/skills/md2ossie/SKILL.md)：将 Markdown 转换为 Apache Ossie 0.2.0.dev0 Ontology JSON，并执行离线官方 Schema 校验和 semantic lint。

所有范围变化直接修订该文档，不另建精益版或平行方案。

## 本地运行

需要 Node.js 20.19+、Python 3.13 和 uv。默认仅监听本机，开发身份是 `admin`，不可直接用于生产。

```sh
make install
make api-dev
# 另一个终端
make web-dev
```

前端 http://127.0.0.1:5174，API http://127.0.0.1:8000/docs。首次启动创建明确标注的制造供应链示例。默认使用本地 SQLite，便于无需外部服务就检查页面与编辑/发布流程；正式部署使用 PostgreSQL。

可将根目录 `.env.example` 复制到 `apps/api/.env` 再配置。数据库数据和材料文件分别保存在 `apps/api/ontofoundry.db` 与 `apps/api/.data/files`，均不纳入 Git。PostgreSQL 开发实例可选用 `docker compose up -d postgres`；这不是生产配置。

## 已接通的流程

- 本体视图、对象/关系目录、详情和人工编辑；对象五步编辑，关系字段映射。
- 建模工作台三栏布局：Markdown 材料、通用对话、候选列表/语义图谱。明确点击“开始建模”后才抽取；未配置模型时提示配置问题，不生成假数据。
- 服务端会话与草稿保存、候选接受/忽略、同字段冲突提示、三方结构化合并、工作空间整体发布和历史 JSON 下载。
- 文档实例详情与 1–3 跳关系；数据库只读预览、实例详情及同连接等值 Join 邻域。数据库行不全量同步。
- 当前/历史已发布 TBox REST API，以及只读 MCP HTTP endpoint；空间成员和服务令牌管理。

界面按给定参考图的头部、侧栏、三栏工作台、卡片目录、步骤条和表格布局实现。小于 1100px 时整体缩放，不改成另一套移动布局。右侧只保留“本体模型列表 / 语义图谱概览”两个页签。所有值来自 API，没有把原型的模拟结果当作模型输出。

## 配置与部署边界

- 内网模型：`ONTOFOUNDRY_ANTHROPIC_BASE_URL`、`ANTHROPIC_MODEL`、`ANTHROPIC_API_KEY`，实际环境变量均带 `ONTOFOUNDRY_` 前缀。接口需兼容 Anthropic Messages 的 tools/tool_choice。
- 数据库连接密码：配置固定的 Fernet `ONTOFOUNDRY_CONNECTION_KEY` 后才能新增连接。部署时用源库只读账号，不将密码写入本体版本。
- OAuth：配置服务端地址、client ID/secret、回调 URI；启用 `AUTH_MODE=oauth`。生产启用 HTTPS 安全 Cookie、随机 session secret，关闭 demo seed。

构建后可由同一个 API 进程托管前端，无需生产 Vite：

```sh
make build
make serve
```

`make serve` 用 `ONTOFOUNDRY_WEB_DIST=../web/dist` 托管 SPA 与 API。同域 HTTPS 入口由部署环境的反向代理提供。应用目前只支持单进程；后台模型请求受 10 并发信号量限制，重启标记中断任务供人工重试，不引入消息队列或自动补偿。正式上线前必须完成真实内网模型、OAuth、PostgreSQL/MySQL/Doris 联调、并发与大文件测试。尚不具备完整生产验收结论。

暂未完成的设计项：通用规则/约束表达式编辑与完整 Ossie mapping 导出、通用中间表关系映射、文档/数据库事实的同屏混合浏览、消费端实例 REST/MCP、完整历史 Diff 页面及升级迁移脚本。名称唯一、引用端点和基数定义校验已实现；属性必填/值类型目前是模型元数据，尚未完整校验文档实例值。规则缺少可靠表达式时保持待澄清，不虚构推理。

MCP 当前实现 2026-07-28 的 `server/discover`、`tools/list`、`tools/call`，使用本平台签发的只读 Bearer 令牌；尚未实现 MCP OAuth 动态发现或兼容旧版 `initialize` 客户端。上线前需与实际消费端核对版本。

## 验证

```sh
make test
make lint
make build
```

测试使用临时 SQLite 和受控模型协议响应，SQL 查询测试在真实 SQLite 测试表上执行；不等同于真实 PG/MySQL/Doris 或内网 LLM 集成验证。浏览器截图在 `output/playwright/formal-*.png`。实际状态、消融结果与未通过的验收项持续记录在唯一设计文档末尾。
