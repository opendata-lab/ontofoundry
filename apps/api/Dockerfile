# ---- Pi Cell build stage ----------------------------------------------
# Built here so the backend image can spawn the Node data plane as a child
# process. NODE_ENV is deliberately
# left unset: npm's `omit` config defaults to ["dev"] when NODE_ENV=production,
# which would drop typescript and break the build below.
FROM node:22-bookworm-slim AS pi-cell
WORKDIR /build
COPY dataagent/dataagent-runtime-pi/package.json dataagent/dataagent-runtime-pi/package-lock.json dataagent/dataagent-runtime-pi/tsconfig.json ./
RUN npm ci --ignore-scripts
COPY dataagent/dataagent-runtime-pi/src ./src
RUN npm run build && npm prune --omit=dev

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOME=/dataagent_runtime
ENV DATAAGENT_RUNTIME_ROOT=/dataagent_runtime

WORKDIR /opt/ontofoundry-api

# 依赖单一来源：两个包的依赖都声明在 apps/api/pyproject.toml 里
COPY apps/api/pyproject.toml apps/api/README.md* /opt/ontofoundry-api/
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api/src /opt/ontofoundry-api/src
RUN pip install --no-cache-dir /opt/ontofoundry-api
RUN mkdir -p /dataagent_runtime /app/.claude/skills && chmod 1777 /dataagent_runtime

# Node runtime + built Pi Cell. Both images are debian bookworm, so the node
# binary's glibc/libstdc++ dependencies are already satisfied here. Same
# COPY --from pattern the runner image already uses for the docker CLI.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-cell /build/dist /opt/dataagent-runtime-pi/dist
COPY --from=pi-cell /build/node_modules /opt/dataagent-runtime-pi/node_modules
ENV DATAAGENT_NODE_BIN=/usr/local/bin/node
ENV DATAAGENT_RUNTIME_PI_DIR=/opt/dataagent-runtime-pi


EXPOSE 8900

# 迁移脚本随 dataagent_backend 包一起安装，alembic 从包内位置读取配置。
# 单一进程同时提供 OntoFoundry 与 DataAgent 路由。
CMD ["sh", "-c", "alembic -c /opt/ontofoundry-api/src/dataagent_backend/alembic.ini upgrade head && uvicorn ontofoundry_api.main:app --host 0.0.0.0 --port 8900"]
