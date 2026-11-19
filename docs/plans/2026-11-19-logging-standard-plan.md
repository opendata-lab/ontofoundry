# 日志统一标准计划（OntoFoundry）

日期：2026-11-19
设计：[2026-11-19-logging-standard.md](../design/2026-11-19-logging-standard.md)

OpenDataWorks、DataAgent 按同一标准在各自仓库实现，本计划只覆盖 OntoFoundry。

## 任务

1. `apps/api/src/ontofoundry_api/logging_config.py`：JSON Formatter、脱敏与截断、请求 ID 上下文、按天轮转文件 handler、`configure_logging`（含 Uvicorn 日志接管、第三方库降级、`captureWarnings`）。
2. `config.py`：`log_dir`、`log_level`。
3. `main.py`：模块加载时配置日志；最外层请求中间件处理 `X-Request-ID` 并记录请求完成（跳过 `/healthz`）。
4. `services/dataagent.py`：请求头带 `X-Request-ID`。
5. `compose.yaml`、`scripts/offline-compose.yaml`：所有服务 Docker 日志限额；`of-backend` 挂载 `./logs/of-backend` 并设置 `ONTOFOUNDRY_LOG_DIR`、`ONTOFOUNDRY_LOG_LEVEL`。`.gitignore` 忽略 `/logs/`。
6. `docs/deployment.md`：日志位置、保留期、查看方法。

## 验证

- `apps/api/tests/test_logging_config.py`：单行 JSON 字段、堆栈在行内且脱敏、凭据脱敏、超长截断、文件创建与 30 天保留、Uvicorn 接管、请求 ID 透传与重新生成、请求完成日志、调用 DataAgent 带请求 ID。
- 全量 API 测试；`ruff check` 本次改动的文件。
- 本地以 SQLite 启动后端并设置日志目录：确认 `app.log` 为单行 JSON、请求日志带请求 ID、响应头返回同值。按天轮转与 `.gz` 保留在 Python 3.13 上用模拟时间验证过（30 份之外的旧文件被删除）。
- `docker compose config` 校验两份 Compose。

## 上线与回退

- 重建 `of-backend` 容器后生效；宿主机自动创建 `logs/of-backend/`。
- 回退：去掉 `ONTOFOUNDRY_LOG_DIR` 即只输出控制台；代码回退不涉及数据。
