#!/usr/bin/env bash
# Refresh the rolling main download. Immutable v* releases are never touched.
set -euo pipefail

PACKAGE_FILE="${1:?Usage: publish-latest-release.sh PACKAGE.tar.gz}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
SOURCE_SHA="${GITHUB_SHA:?GITHUB_SHA is required}"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid source commit" >&2; exit 1; }
[ -s "$PACKAGE_FILE" ] || { echo "Package is missing or empty" >&2; exit 1; }

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
ASSET_NAME="ontofoundry-offline-latest.tar.gz"
cp "$PACKAGE_FILE" "$WORK_DIR/$ASSET_NAME"
(cd "$WORK_DIR" && shasum -a 256 "$ASSET_NAME" > "$ASSET_NAME.sha256")

cat > "$WORK_DIR/release-notes.md" <<EOF
OntoFoundry latest — main 分支的最新构建，每次成功发布后更新。

源码提交：[${SOURCE_SHA}](https://github.com/${REPO}/commit/${SOURCE_SHA})

下载 [离线安装包](https://github.com/${REPO}/releases/download/latest/${ASSET_NAME})
及 [SHA-256 校验和](https://github.com/${REPO}/releases/download/latest/${ASSET_NAME}.sha256)。
离线包包含 linux/amd64 的前端、后端和 PostgreSQL 镜像，解压后按 README.md 安装。

这是滚动构建。需要固定版本时，请使用 v* Release。
EOF
if [ -n "${DOCKER_NAMESPACE:-}" ]; then
  cat >> "$WORK_DIR/release-notes.md" <<EOF

Docker 镜像：
- ${DOCKER_NAMESPACE}/of-backend:latest
- ${DOCKER_NAMESPACE}/of-frontend:latest
EOF
fi

if gh release view latest --repo "$REPO" >/dev/null 2>&1; then
  # Validate/build happens before this script; upload must succeed before moving the tag.
  gh release upload latest "$WORK_DIR/$ASSET_NAME" "$WORK_DIR/$ASSET_NAME.sha256" \
    --repo "$REPO" --clobber
  gh api --method PATCH "repos/$REPO/git/refs/tags/latest" -f sha="$SOURCE_SHA" -F force=true
  gh release edit latest --repo "$REPO" --title "OntoFoundry latest" \
    --notes-file "$WORK_DIR/release-notes.md" --latest
else
  gh release create latest "$WORK_DIR/$ASSET_NAME" "$WORK_DIR/$ASSET_NAME.sha256" \
    --repo "$REPO" --target "$SOURCE_SHA" --title "OntoFoundry latest" \
    --notes-file "$WORK_DIR/release-notes.md" --latest
fi
