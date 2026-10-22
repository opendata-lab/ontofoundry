# of-frontend：nginx 托管构建产物，并把 /api 反代到 of-backend。
#
# 构建上下文是仓库根目录，因为 npm workspace 的 lockfile 在根上——只拷 apps/web
# 的话 `npm ci` 会因为拿不到 workspace 定义而失败。
#
# 构建阶段固定跑在构建机自己的架构上：产物是与架构无关的静态文件，多架构发布时
# 不必在 qemu 模拟的 arm64 里再跑一遍 npm ci 和 vite（CI 里那一份要 5 分多钟）。

FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS build
WORKDIR /build

# 先只拷清单和本地依赖包，让依赖层能被缓存复用。
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/vendor-agent-conversation-*.tgz ./apps/web/
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts --no-audit --no-fund

COPY apps/web ./apps/web
RUN npm run build -w ontofoundry-web

FROM nginx:1.27-alpine

COPY --from=build /build/apps/web/dist /usr/share/nginx/html
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
