# of-frontend：nginx 托管构建产物，并把 /api 反代到 of-backend。
#
# 构建上下文是仓库根目录，因为 npm workspace 的 lockfile 在根上——只拷 apps/web
# 的话 `npm ci` 会因为拿不到 workspace 定义而失败。

FROM node:22-bookworm-slim AS build
WORKDIR /build

# 先只拷清单，让依赖层能被缓存复用。runtime-pi 的 package.json 也要带上：
# 它是同一个 workspace 的成员，缺了它 npm ci 会拒绝按 lockfile 安装。
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/
COPY dataagent/dataagent-runtime-pi/package.json ./dataagent/dataagent-runtime-pi/
RUN npm ci --ignore-scripts

COPY apps/web ./apps/web
RUN npm run build -w ontofoundry-web

FROM nginx:1.27-alpine

COPY --from=build /build/apps/web/dist /usr/share/nginx/html
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
