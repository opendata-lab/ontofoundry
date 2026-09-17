#!/usr/bin/env bash
# 打一个可在无外网机器上部署的离线包。
#
# 目标机器拉不到任何镜像，所以第三方基础镜像也要一并导出。我们自己的三个镜像已经
# 把 nginx / node / python 烘进各自的层里，不需要单独导出；postgres 与 redis 是
# 独立服务，必须单独 save。
#
#   ./scripts/create-offline-package.sh [输出目录]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$REPO_ROOT/dist/offline}"
STAMP="$(date +%Y%m%d%H%M%S)"

BACKEND_IMAGE="${OF_BACKEND_IMAGE:-of-backend:local}"
RUNNER_IMAGE="${OF_RUNNER_IMAGE:-of-runner:local}"
FRONTEND_IMAGE="${OF_FRONTEND_IMAGE:-of-frontend:local}"

# 与 compose.yaml 保持一致。写死而不是解析 yaml：解析要引入依赖，而版本漂移会
# 立刻在 `docker compose up` 时暴露，不会静默。
POSTGRES_IMAGE="postgres:17-alpine"
REDIS_IMAGE="redis:7.2-alpine"

DOCKER="${DOCKER:-docker}"
command -v "$DOCKER" >/dev/null 2>&1 || {
  echo "需要 $DOCKER，可用 DOCKER=podman 覆盖" >&2
  exit 1
}

echo "==> 构建三个自有镜像"
"$DOCKER" build -t "$BACKEND_IMAGE"  --target backend -f "$REPO_ROOT/apps/api/Dockerfile" "$REPO_ROOT"
"$DOCKER" build -t "$RUNNER_IMAGE"   --target runner  -f "$REPO_ROOT/apps/api/Dockerfile" "$REPO_ROOT"
"$DOCKER" build -t "$FRONTEND_IMAGE" -f "$REPO_ROOT/apps/web/Dockerfile" "$REPO_ROOT"

echo "==> 拉取第三方镜像"
"$DOCKER" pull "$POSTGRES_IMAGE"
"$DOCKER" pull "$REDIS_IMAGE"

mkdir -p "$OUT_DIR/images"

echo "==> 导出镜像"
# 一次 save 多个镜像可以共享公共层，比逐个 save 小得多——三个自有镜像共用同一个
# base stage，分开导出会把那层复制三份。
"$DOCKER" save -o "$OUT_DIR/images/ontofoundry.tar" \
  "$BACKEND_IMAGE" "$RUNNER_IMAGE" "$FRONTEND_IMAGE"
"$DOCKER" save -o "$OUT_DIR/images/infra.tar" \
  "$POSTGRES_IMAGE" "$REDIS_IMAGE"

echo "==> 复制部署文件"
cp "$REPO_ROOT/compose.yaml" "$OUT_DIR/"
# skills 目录是 bind mount 进容器的，不在镜像里，所以必须随包带走。
mkdir -p "$OUT_DIR/dataagent"
cp -R "$REPO_ROOT/dataagent/.claude" "$OUT_DIR/dataagent/"

cat > "$OUT_DIR/.env.example" <<'ENV'
# 离线包内的镜像标签。load 之后名字就是这三个，不要改成带 registry 前缀的形式，
# 否则 compose 会试图去拉取而不是用本地已加载的。
OF_BACKEND_IMAGE=of-backend:local
OF_RUNNER_IMAGE=of-runner:local
OF_FRONTEND_IMAGE=of-frontend:local

# 模型接入。离线环境通常指向内网网关。
DATAAGENT_LLM_PROVIDER=anthropic_compatible
ONTOFOUNDRY_ANTHROPIC_BASE_URL=
ONTOFOUNDRY_ANTHROPIC_API_KEY=
ONTOFOUNDRY_ANTHROPIC_MODEL=
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
| `images/ontofoundry.tar` | of-backend、of-runner、of-frontend |
| `images/infra.tar` | postgres:17-alpine、redis:7.2-alpine |
| `compose.yaml` | 部署编排 |
| `dataagent/.claude/skills` | Skill 目录，bind mount 进容器，不在镜像里 |

nginx、node、python 已经烘在自有镜像的层里，不需要单独提供。

## 部署

```sh
cp .env.example .env    # 填写模型接入信息
./install.sh
```

## 需要宿主机提供

`of-runner` 会挂载宿主的 `/var/run/docker.sock` 来启动 agent 子容器。能访问该
socket 等同于宿主 root 权限，这是本拓扑里权限最大的一处；只有 runner 挂它。
如果目标环境不允许，就不能用容器沙箱模式。
DOC

echo
echo "完成: $OUT_DIR"
du -sh "$OUT_DIR" 2>/dev/null || true
