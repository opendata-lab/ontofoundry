# 服务级连接的库名调用链修复计划

依据：[设计](../design/2026-10-22-connection-schema-callers.md)。

1. 核查全部 catalogApi、连接 workspaceRequest、normalize_schema、require_schema 和 require_source_schema 调用方，记录入口与空库行为。
2. 补 MySQL/Doris 空数据库连接的页面渲染测试及实际 client URL 断言，覆盖数据表全部库、同步、详情、数据集选表、构建关联表与旧表材料入口。
3. 修复数据集尚未选库及切换连接的空库请求；移除连接数据库列，PostgreSQL 地址附库名，隐藏字段不保留旧数据库。
4. 补 SQLite/mock API 回归，保持空库拒绝；全部编辑完成后统一运行测试，并在隔离副本对修复前源码运行新增回归以取得失败证据。
5. 执行用户指定 pytest、build、vitest、eslint；执行 test:visual、1440×900 截图对比和局域网 IP 浏览器验证，记录环境限制。
6. 更新数据表设计 v0.2.2 说明与最终结果，不改版本号、不 commit/push。

## 实施结果

1. 完成全部前后端调用清单，含行号、空库行为及不经过 require_schema 的数据集/关联表入口，记录在数据表设计 v0.2.2 小节。
2. 复现并修复数据集两条空库路径，补齐连接列表及隐藏数据库字段回归；PostgreSQL 默认 schema 和必填连接数据库均保留。
3. 修复前隔离副本 6 failed、9 passed；修复后全量前端 233 passed，后端 1089 passed、17 skipped；build、eslint 和更新测试文件 ruff 通过。
4. test:visual、1440×900 截图和局域网验证受环境阻断：监听端口 EPERM，Chromium 被沙箱终止，浏览器拒绝 file:// 离线页面。视觉基准待可运行环境审核更新，未将其标为通过。
5. 文档更新完成，不修改版本号，不 commit/push。
