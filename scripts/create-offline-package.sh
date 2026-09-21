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
"$DOCKER" pull "$REDIS_IMAGE"

mkdir -p "$OUT_DIR/images"

echo "==> 导出镜像"
# 一次 save 多个镜像可以共享公共层，比逐个 save 小得多——三个自有镜像共用同一个
# base stage，分开导出会把那层复制三份。
"$DOCKER" save -o "$OUT_DIR/images/ontofoundry.tar" \
  "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
"$DOCKER" save -o "$OUT_DIR/images/infra.tar" \
  "$POSTGRES_IMAGE" "$REDIS_IMAGE"

echo "==> 复制部署文件"
cp "$REPO_ROOT/compose.yaml" "$OUT_DIR/"
# Agent 能力由外部 OpenDataWorks DataAgent 提供，不再随包分发 Skill。接入步骤见
# integrations/dataagent/README.md，Skill 的 ZIP 在目标环境用 `make -C
# integrations/dataagent zip` 现场生成。
cp -R "$REPO_ROOT/integrations" "$OUT_DIR/"

cat > "$OUT_DIR/.env.example" <<'ENV'
# 离线包内的镜像标签。load 之后名字就是这三个，不要改成带 registry 前缀的形式，
# 否则 compose 会试图去拉取而不是用本地已加载的。
OF_BACKEND_IMAGE=of-backend:local
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
| `images/ontofoundry.tar` | of-backend、of-frontend |
| `images/infra.tar` | postgres:17-alpine、redis:7.2-alpine |
| `compose.yaml` | 部署编排 |
| `dataagent/.claude/skills` | Skill 目录，bind mount 进容器，不在镜像里 |

nginx、node、python 已经烘在自有镜像的层里，不需要单独提供。

## 部署

```sh
cp .env.example .env    # 填写模型接入信息
./install.sh
```

## 需要外部提供

本包不含 Agent 运行时。会话、任务、Skill 与沙箱由一个可达的 OpenDataWorks
DataAgent 提供，按 `integrations/dataagent/README.md` 接入并配置六个
`ONTOFOUNDRY_DATAAGENT_*` 变量。

未配置时应用照常启动：本体的查看、编辑、发布与 MCP 都不依赖它。

这也意味着部署不再需要宿主的 `/var/run/docker.sock`——旧拓扑里 agent 子容器由挂载
该 socket 的 runner 启动，那是权限最大的一处，现在整个删掉了。
DOC

echo
echo "完成: $OUT_DIR"
du -sh "$OUT_DIR" 2>/dev/null || true
