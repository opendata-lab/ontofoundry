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

# 创建数据连接时必填。生成 Fernet key：
# python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
ONTOFOUNDRY_CONNECTION_KEY=
ENV

cat > "$OUT_DIR/install.sh" <<'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER="${DOCKER:-docker}"

[ -f "$HERE/.env" ] || {
  echo "先把 .env.example 复制成 .env 并填好模型接入信息" >&2
  exit 1
}

echo "==> 加载镜像"
"$DOCKER" load -i "$HERE/images/infra.tar"
"$DOCKER" load -i "$HERE/images/ontofoundry.tar"

echo "==> 启动"
"$DOCKER" compose --env-file "$HERE/.env" -f "$HERE/compose.yaml" up -d

echo "前端: http://127.0.0.1:8080"
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
cp .env.example .env    # 填写模型接入信息
./install.sh
```

DOC

echo
echo "完成: $OUT_DIR"
du -sh "$OUT_DIR" 2>/dev/null || true
