#!/usr/bin/env bash
# 打一个可在无外网机器上部署的离线包。
#
# 目标机器拉不到任何镜像，所以第三方基础镜像也要一并导出。两个业务镜像已经把
# nginx / node / python 烘进各自的层里，不需要单独导出；PostgreSQL 是独立服务，
# 必须单独 save。
#
#   ./scripts/create-offline-package.sh [输出目录]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$REPO_ROOT/dist/offline}"
STAMP="$(date +%Y%m%d%H%M%S)"

BACKEND_IMAGE="${OF_BACKEND_IMAGE:-of-backend:local}"
FRONTEND_IMAGE="${OF_FRONTEND_IMAGE:-of-frontend:local}"

# 与 compose.yaml 保持一致。写死而不是解析 yaml：解析要引入依赖，而版本漂移会
# 立刻在 `docker compose up` 时暴露，不会静默。
POSTGRES_IMAGE="postgres:17-alpine"

DOCKER="${DOCKER:-docker}"
command -v "$DOCKER" >/dev/null 2>&1 || {
  echo "需要 $DOCKER，可用 DOCKER=podman 覆盖" >&2
  exit 1
}

# SKIP_BUILD=1 时复用已存在的镜像。CI 里镜像已经由上游 job 构建过，重复构建
# 只是浪费几分钟；本地直接跑脚本时仍然需要构建这一步。
if [ "${SKIP_BUILD:-0}" = "1" ]; then
  echo "==> 跳过构建，复用已有镜像"
  for img in "$BACKEND_IMAGE" "$FRONTEND_IMAGE"; do
    "$DOCKER" image inspect "$img" >/dev/null 2>&1 || {
      echo "SKIP_BUILD=1 但本地没有 $img" >&2
      exit 1
    }
  done
else
  echo "==> 构建两个自有镜像"
  "$DOCKER" build -t "$BACKEND_IMAGE"  --target backend -f "$REPO_ROOT/apps/api/Dockerfile" "$REPO_ROOT"
  "$DOCKER" build -t "$FRONTEND_IMAGE" -f "$REPO_ROOT/apps/web/Dockerfile" "$REPO_ROOT"
fi

echo "==> 拉取第三方镜像"
"$DOCKER" pull "$POSTGRES_IMAGE"

mkdir -p "$OUT_DIR/images"

echo "==> 导出镜像"
# 一次 save 两个业务镜像，方便目标机器一次加载。
"$DOCKER" save -o "$OUT_DIR/images/ontofoundry.tar" \
  "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
"$DOCKER" save -o "$OUT_DIR/images/infra.tar" \
  "$POSTGRES_IMAGE"

echo "==> 复制部署文件"
cp "$REPO_ROOT/scripts/offline-compose.yaml" "$OUT_DIR/compose.yaml"

cat > "$OUT_DIR/.env.example" <<'ENV'
# 离线包内的镜像标签。load 之后名字就是这两个，不要改成带 registry 前缀的形式，
# 否则 compose 会试图去拉取而不是用本地已加载的。
OF_BACKEND_IMAGE=of-backend:local
OF_FRONTEND_IMAGE=of-frontend:local

# 前端对外端口，浏览器访问 http://<服务器IP>:<端口>。
OF_HTTP_PORT=8080

# ---- DataAgent（建模/问数 Agent）。不填则平台可用，只是 Agent 功能不可用。----
# DataAgent 后端地址：只写 协议://主机:端口，不带路径。这是从 of-backend 容器里
# 访问的地址，不能写 127.0.0.1 / localhost（那指容器自己），要写服务器 IP 或域名。
ONTOFOUNDRY_DATAAGENT_BASE_URL=
# 可选，一般留空。只有 DataAgent 上用接口为该站点开启了服务端接入校验时才填。
ONTOFOUNDRY_DATAAGENT_ACCESS_KEY=
# 管理端创建 Agent 后返回的 agent_id，形如 agent_7895f271d13c40f9bc2fabf7。
ONTOFOUNDRY_DATAAGENT_AGENT_ID=
# 一般不用改：站点 ID 与接口前缀。
ONTOFOUNDRY_DATAAGENT_WEBSITE_ID=ontofoundry
ONTOFOUNDRY_DATAAGENT_API_PREFIX=/api/v1/nl2sql
# DataAgent 回调本平台 MCP 用的地址。留空即用浏览器访问的地址
# （http://<服务器IP>:8080），DataAgent 能访问到它就不用填。
# ONTOFOUNDRY_PUBLIC_BASE_URL=http://<服务器IP>:8080

# 一般不用填：直接用 IP / 域名访问上面的端口都是同源，后端自动放行。
# 只有外层再套一层反代 / HTTPS 终止，浏览器地址与前端容器看到的不一致时，
# 才把浏览器地址栏里的源（协议+主机+端口）填进来，逗号分隔。
# ONTOFOUNDRY_CORS_ORIGINS=https://ontofoundry.example.com
ENV

cat > "$OUT_DIR/install.sh" <<'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER="${DOCKER:-docker}"

[ -f "$HERE/.env" ] || {
  echo "先把 .env.example 复制成 .env（默认值即可直接启动）" >&2
  exit 1
}

echo "==> 加载镜像"
"$DOCKER" load -i "$HERE/images/infra.tar"
"$DOCKER" load -i "$HERE/images/ontofoundry.tar"

echo "==> 启动"
"$DOCKER" compose --env-file "$HERE/.env" -f "$HERE/compose.yaml" up -d

PORT="$(sed -n 's/^OF_HTTP_PORT=//p' "$HERE/.env" | tail -1)"
echo "前端: http://<服务器IP>:${PORT:-8080}"
INSTALL
chmod +x "$OUT_DIR/install.sh"

cat > "$OUT_DIR/README.md" <<'DOC'
# OntoFoundry 离线部署包

## 包含内容

| 文件 | 内容 |
| --- | --- |
| `images/ontofoundry.tar` | of-backend、of-frontend |
| `images/infra.tar` | postgres:17-alpine |
| `compose.yaml` | 部署编排 |

nginx、node、python 已经烘在自有镜像的层里，不需要单独提供。

## 部署

```sh
cp .env.example .env    # 默认值即可直接启动
./install.sh
```

DOC

echo
echo "完成: $OUT_DIR"
du -sh "$OUT_DIR" 2>/dev/null || true
