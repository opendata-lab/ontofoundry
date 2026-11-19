# 日志统一标准与 OntoFoundry 实现

日期：2026-11-19
状态：待评审
计划：[2026-11-19-logging-standard-plan.md](../plans/2026-11-19-logging-standard-plan.md)

## 1. 现状

- 后端各模块用 `logging.getLogger(__name__)`，但没有统一配置：业务日志、Uvicorn 错误日志和访问日志各用各的默认文本格式，异常堆栈跨多行。
- 日志只到容器控制台。`compose.yaml` 和 `scripts/offline-compose.yaml` 没有日志目录挂载，也没有 Docker 日志限额，保留多久取决于部署机的 Docker 配置；容器重建后历史日志丢失。
- 没有请求关联 ID，排查一次失败的建模请求只能按时间猜。
- OntoFoundry、OpenDataWorks、DataAgent 三个项目各有一套做法，内网运维需要分别学习。

## 2. 目标

运维在部署目录下打开 `logs/` 就能看到每个服务的日志，按天自动归档、自动清理；三个项目格式相同，可以用同一个请求 ID 把一次操作串起来。不引入日志收集服务。

## 统一标准（OntoFoundry、OpenDataWorks、DataAgent 三仓库相同）

三个仓库各自实现，下面的约定逐字相同。改动约定时三处同步修改。

### 目录

部署目录下有一个 `logs/`，每个服务一个子目录，由 Compose 绑定挂载到容器内 `/var/log/<服务名>`：

```text
<部署目录>/logs/
  <服务名>/
    app.log                    当前日志
    app.log.2026-11-18.gz      已轮转的历史日志，按 UTC 日期命名
  dataagent-backend/
    app.log
    runtime.log                仅 DataAgent：Pi 运行时与沙箱的诊断
```

- 目录名与日志里的 `service` 字段相同，三个项目不重名：`of-backend`、`dataagent-backend`、`opendataworks-backend`。
- 应用通过环境变量 `<前缀>_LOG_DIR` 得到目录；未设置时（本地源码运行）只输出到控制台，不写文件。
- 宿主机上的日志文件属主是容器内运行服务的用户：OntoFoundry、OpenDataWorks 为 root，DataAgent 为运行时用户（默认 uid 1000，入口脚本负责建目录并授权）。

### 轮转与保留

- 应用自己写文件、自己轮转：每天 UTC 零点切分，历史文件 gzip 压缩，保留 30 天，更早的自动删除。Java（Logback）的滚动策略要求文件名带序号，历史文件名为 `app.log.2026-11-18.0.gz`。
- 每个日志文件只能有一个进程写入。服务以单进程运行；改为多进程前必须先改为每进程一个文件。
- 同一行同时写控制台（stdout），`docker logs` 仍可用于实时查看。Docker 自身的日志用 `json-file` 驱动并限额（`max-size: 10m`、`max-file: 3`），只作临时缓冲，不作历史。
- 数据库、Redis、Nginx 等第三方服务不写 `logs/`，只用上面的 Docker 限额。Nginx 的访问记录已由后端的请求日志覆盖。

### 格式

UTF-8，每个事件一行 JSON，不换行、不带颜色，异常堆栈作为字符串字段。

| 字段 | 说明 |
| --- | --- |
| `timestamp` | UTC，RFC 3339，毫秒，例如 `2026-11-19T08:03:12.345Z` |
| `level` | `DEBUG`、`INFO`、`WARN`、`ERROR` |
| `service` | 服务名，与目录名相同 |
| `logger` | 模块或类名 |
| `message` | 一句话说明 |
| `request_id` | HTTP 请求关联 ID，非请求上下文省略 |
| `task_id`、`run_id`、`topic_id`、`session_id` | 已有业务 ID，适用时附带，不新造 |
| `source` | 仅 DataAgent `runtime.log`：`runtime` 或 `sandbox` |
| `error_code`、`stack_trace` | 出错时附带 |

请求完成时记一条：`method`、`path`（不含查询串）、`status_code`、`duration_ms`。

### 请求关联

HTTP 入口读取 `X-Request-ID`（1～64 位字母、数字、`-`、`_`），缺失或不合法时生成新值，并在响应头返回；调用其他服务时带上同一个值。后台任务显式带上自己的 `task_id`/`run_id`，不依赖已结束的请求上下文。

### 级别

生产默认 `INFO`，第三方库 `WARN`，`DEBUG` 只临时开启。请求完成、任务开始与结束、超时、重试、异常各记一条；不记录逐 token 输出或完整协议帧。

### 禁止记录

令牌、密码、API Key、Cookie、`Authorization` 头、私钥、带凭据的连接串和 URL、完整环境变量或配置对象；默认也不记录请求和响应正文、完整 SQL 及参数、用户提示词、模型回答、工具原始输出。异常消息和子进程输出写入前先脱敏并限制长度。

### 库

- Python：标准库 `logging`，配一个约 40 行的 JSON Formatter；文件用 `TimedRotatingFileHandler(when="midnight", utc=True, backupCount=30)`，用 `namer`/`rotator` 压缩（Python 官方 Logging Cookbook 的写法）。不引入 structlog、loguru。
- Java：SLF4J + Logback（Spring Boot 自带），用 Spring Boot 的结构化日志和滚动策略配置，不加依赖。
- Node（DataAgent 运行时）：stdout 只用于协议；诊断以 JSON 行写 stderr，由 Python 后端接收后写入 `runtime.log`。

### 不在范围内

ELK、Loki、OpenTelemetry 等日志收集与检索系统；日志收集容器（OpenDataWorks 现有的 log-collector 删除）。

## 3. OntoFoundry 的实现

### 3.1 后端 `of-backend`

- 新增 `ontofoundry_api/logging_config.py`：JSON Formatter、请求 ID 上下文（`contextvars`）、`configure_logging(settings)`。
  - 根 logger 接控制台；设置了 `ONTOFOUNDRY_LOG_DIR` 时再接 `app.log` 的按天轮转文件。
  - `uvicorn`、`uvicorn.error` 去掉自带 handler，交给根 logger；`uvicorn.access` 关闭，由请求中间件代替。
  - 第三方 logger（`httpx`、`sqlalchemy`、`alembic` 等）设为 `WARN`。
  - 级别由 `ONTOFOUNDRY_LOG_LEVEL` 控制，默认 `INFO`。
- `main.py`：`create_app` 开头调用 `configure_logging`；新增请求中间件，处理 `X-Request-ID` 并在请求结束时记一条请求日志。`/healthz` 不记录，避免每 10 秒一条。
- `services/dataagent.py`：调用 DataAgent 时带上当前 `X-Request-ID`。
- 脱敏：JSON Formatter 输出前对 `message` 和 `stack_trace` 调用现有的 `redact_credentials` 同类规则，并截断到 8 KB。
- 迁移命令 `alembic upgrade` 在应用启动前运行，沿用 Alembic 自己的输出，不纳入本标准。
- Python 警告（`warnings`）经 `logging.captureWarnings` 进入同一格式；在日志配置之前、导入模块时触发的警告仍以原始文本到控制台，不进 `app.log`。

### 3.2 前端 `of-frontend`（Nginx）

不写 `logs/`，只加 Docker 日志限额。页面请求的结果已经由后端请求日志记录。

### 3.3 Compose

`compose.yaml` 和 `scripts/offline-compose.yaml`：

- 新增 `x-logging` 锚点（`json-file`、`10m`×3），所有服务引用。
- `of-backend` 增加 `ONTOFOUNDRY_LOG_DIR=/var/log/of-backend` 和绑定挂载 `./logs/of-backend:/var/log/of-backend`。
- `.gitignore` 忽略 `logs/`；离线安装包创建空的 `logs/` 目录。

### 3.4 文档

`docs/deployment.md` 说明日志位置、保留期和查看方法。

## 4. 取舍

- **应用写文件而不是只靠 Docker 轮转**：用户要求部署目录下有可直接查看、容器重建后仍保留的日志目录。代价是每个服务要配置文件 handler，且只能单进程写一个文件；当前都是单进程。
- **按天轮转、不按大小**：内网访问量小，按天便于按日期查找。单日日志异常增大时不会提前切分；如出现，再加大小上限。
- **不用 structlog**：现有代码全部使用标准库 `logging`，换库要改所有调用点，收益只是写法更短。
