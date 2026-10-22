# 数据连接删除实施计划

依据：[连接删除设计](../design/2026-10-22-connection-deletion.md)，用户已确认方案 A。

1. 在服务层推导四类引用，增加 409 业务错误和本地元数据显式清理；路由仅做权限检查与委托。
2. 同步引用诊断的 Pydantic、JSON Schema 和前端类型；连接行增加确认删除及错误引用列表。
3. 补后端接口与持久化断言，覆盖引用、同步状态、权限、空间隔离；补前端成功、取消、409 和权限测试。
4. 全部编辑结束后统一执行 pytest、ruff、build、vitest、eslint；尝试视觉测试、1440×900 截图和局域网 IP 验证，准确记录环境限制。
5. 在数据表设计 v0.2.2 之后追加连接删除说明；不 commit、不改版本号。


## 改动文件

- 后端路由与服务：`apps/api/src/ontofoundry_api/api/connections.py`、`apps/api/src/ontofoundry_api/services/connections.py`、`apps/api/src/ontofoundry_api/services/errors.py`。
- 契约：`apps/api/src/ontofoundry_api/contracts/connections.py`、`apps/api/src/ontofoundry_api/contracts/ontofoundry.connections.v1.schema.json`、`apps/api/src/ontofoundry_api/contracts/export_schema.py`。
- 后端测试：`apps/api/tests/test_connection_deletion.py`。
- 前端：`apps/web/src/components/DataConnections.tsx`、`apps/web/src/api/client.ts`、`apps/web/src/api/types.ts`。
- 前端测试：`apps/web/src/pages/ConnectionsPage.test.tsx`、`apps/web/src/api/connections.test.ts`。
- 文档：`docs/design/2026-10-21-data-tables-page.md`、`docs/design/2026-10-22-connection-deletion.md`、本实施计划。

## 验证命令

```sh
cd apps/api
PYTHONPATH=src /Users/guoruping/project/bigdata/ontograph/apps/api/.venv/bin/pytest -q -p no:cacheprovider
/Users/guoruping/project/bigdata/ontograph/apps/api/.venv/bin/ruff check src tests
cd ../web
npm run build
npx vitest run
npx vitest run --maxWorkers=2
npx eslint src
npm run test:visual
npx vite --host 172.20.10.3 --port 5199 --strictPort
```

## 实施结果

已完成全部代码、契约、界面、回归与文档；当前模型无 abandoned_at，所有现存会话参与引用检查，未增加字段或迁移。详细结果记录在[数据表设计的连接删除验证结果](../design/2026-10-21-data-tables-page.md)。


### 验证结果

- 指定 pytest 全量：**1103 passed、17 skipped、0 failed、0 errors、3 warnings，480.56 秒**；新增删除回归 14 项，包含外键约束下的多库元数据清理、四类引用及同时列出、pending 创建/修改/删除提案、queued/running、非管理员、空间隔离、历史版本和已决提案。日志 `/private/tmp/connection-delete-pytest.log`。
- 指定 `ruff check src tests` 全量通过，日志 `/private/tmp/connection-delete-ruff.log`。
- `npm run build` 通过，仅有现有大 chunk 提示；`npx eslint src` 通过，日志 `/private/tmp/connection-delete-eslint.log`。前端新增 6 项删除及接口回归。
- `npx vitest run` 首轮默认并发：227 passed、12 failed（既有用例超时及异步校验断言未及时完成）；新增删除用例通过。未修改超时阈值或测试断言，改用 `npx vitest run --maxWorkers=2` 重跑全量：**51 个文件、239 passed、0 failed、0 skipped，128.66 秒**。日志 `/private/tmp/connection-delete-vitest.log`。
- UI 检测器无发现，`git diff --check` 通过。验证时为避免向主目录的只读 node_modules 链接写缓存，使用本工作区的临时缓存目录；验证结束已恢复原链接，未改依赖或锁文件。
- **视觉和局域网验收未完成**：已执行 `npm run test:visual`，Vite 监听 `127.0.0.1:5199` 被沙箱以 `listen EPERM` 拒绝；使用当前局域网 IP `172.20.10.3` 启动 Vite 也被同样拒绝。无法取得本次 1440×900 截图、对比连接页基准或完成 HTTP 非安全上下文验证；未更新截图基准。日志 `/private/tmp/connection-delete-visual.log`、`/private/tmp/connection-delete-lan.log`。
- 未连接真实业务数据源；无数据库迁移、版本号变更、commit 或 push。
