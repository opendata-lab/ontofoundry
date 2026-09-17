# 三种角色共用一个镜像内容，只有 CMD 不同：
#
#   of-backend  默认 target，跑 API（OntoFoundry + DataAgent 路由）
#                前端由独立的 of-frontend 提供，见 apps/web/Dockerfile
#   of-runner   多一个 docker CLI，跑 sandbox runner，负责 spawn 子容器
#   子容器      复用 of-backend，CMD 换成 sandbox_task_main.py
#
# 子容器之所以不能是"纯 Pi runtime 镜像"：sandbox_runner_main 启动它时执行的是
# `python <包路径>/sandbox_task_main.py`，所以它需要完整的 Python 包；Pi 由那个
# 脚本在子容器内部以 stdio 子进程方式拉起。DATAAGENT_SANDBOX_IMAGE 因此直接指向
# of-backend，不需要第三个镜像。

# ---- Pi Cell build stage ----------------------------------------------
# NODE_ENV 故意不设：npm 的 omit 配置在 NODE_ENV=production 时默认为 ["dev"]，
# 会把 typescript 一起丢掉，下面的 build 就没法跑。
FROM node:22-bookworm-slim AS pi-cell
WORKDIR /build
COPY dataagent/dataagent-runtime-pi/package.json dataagent/dataagent-runtime-pi/package-lock.json dataagent/dataagent-runtime-pi/tsconfig.json ./
RUN npm ci --ignore-scripts
COPY dataagent/dataagent-runtime-pi/src ./src
RUN npm run build && npm prune --omit=dev

# ---- Shared runtime base ----------------------------------------------
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOME=/dataagent_runtime
ENV DATAAGENT_RUNTIME_ROOT=/dataagent_runtime

WORKDIR /opt/ontofoundry-api

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 依赖单一来源：两个包的依赖都声明在 apps/api/pyproject.toml 里
COPY apps/api/pyproject.toml apps/api/README.md* /opt/ontofoundry-api/
COPY apps/api/src /opt/ontofoundry-api/src
RUN pip install --no-cache-dir /opt/ontofoundry-api
RUN mkdir -p /dataagent_runtime /app/.claude/skills && chmod 1777 /dataagent_runtime

# Node 运行时 + 构建好的 Pi Cell。两个镜像都是 debian bookworm，所以 node 二进制
# 的 glibc/libstdc++ 依赖在这里已经满足。
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-cell /build/dist /opt/dataagent-runtime-pi/dist
COPY --from=pi-cell /build/node_modules /opt/dataagent-runtime-pi/node_modules
ENV DATAAGENT_NODE_BIN=/usr/local/bin/node
ENV DATAAGENT_RUNTIME_PI_DIR=/opt/dataagent-runtime-pi

# ---- of-backend --------------------------------------------------------
FROM base AS backend

EXPOSE 8900

# 迁移脚本随 dataagent_backend 包一起安装，alembic 从包内位置读取配置。
# 单一进程同时提供 OntoFoundry 与 DataAgent 路由。
CMD ["sh", "-c", "alembic -c /opt/ontofoundry-api/src/dataagent_backend/alembic.ini upgrade head && uvicorn ontofoundry_api.main:app --host 0.0.0.0 --port 8900"]

# ---- of-runner ---------------------------------------------------------
FROM base AS runner

# runner 通过共享的 docker socket 启动子容器，所以只有它需要 CLI。
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

EXPOSE 8910

CMD ["uvicorn", "dataagent_backend.sandbox_runner_main:app", "--host", "0.0.0.0", "--port", "8910"]
