#!/usr/bin/env bash
# Put the demo back to its starting point after a rehearsal.
#
#   ./reset_demo.sh snapshot   # save the current platform database as the start
#   ./reset_demo.sh restore    # with OntoFoundry stopped: restore, re-point DataAgent,
#                              # drop rehearsal agents
#
# Only the OntoFoundry platform database is restored. DataAgent keeps its own
# database: the restore re-imports the MCP config (the token in it lives in the
# snapshot) and deletes agents named in REHEARSAL_AGENTS.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE="$(cd "$HERE/.." && pwd)"
SNAPSHOT="$CASE/generated/platform-db.sql"
CONTAINER="${OF_PG_CONTAINER:-of-local-pg}"
DB_USER="${OF_PG_USER:-ontofoundry}"
DB_NAME="${OF_PG_DB:-ontofoundry}"
DATAAGENT="${DATAAGENT_API:-http://127.0.0.1:8900}/api/v1/dataagent"
REHEARSAL_AGENTS=("渠道销售问数")
# This machine runs Podman with a `docker` shell alias, which scripts do not see.
DOCKER="${DOCKER:-$(command -v docker || command -v podman)}"

case "${1:-}" in
snapshot)
  mkdir -p "$CASE/generated"
  "$DOCKER" exec "$CONTAINER" pg_dump -U "$DB_USER" --clean --if-exists "$DB_NAME" >"$SNAPSHOT"
  echo "已保存演示起点: $SNAPSHOT"
  ;;
restore)
  [[ -f "$SNAPSHOT" ]] || { echo "没有快照，先执行 $0 snapshot" >&2; exit 1; }
  echo "恢复平台库（先停止 OntoFoundry，恢复后再 make serve）"
  "$DOCKER" exec -i "$CONTAINER" psql -q -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <"$SNAPSHOT" >/dev/null
  curl -sf -X POST "$DATAAGENT/mcp/servers/import" -H 'Content-Type: application/json' \
    --data @"$CASE/generated/mcp-config.json" >/dev/null && echo "已重新导入 DataAgent MCP 配置"
  for name in "${REHEARSAL_AGENTS[@]}"; do
    for id in $(curl -sf "$DATAAGENT/agents/workbench" | python3 -c "
import json, sys
print(' '.join(a['agent_id'] for a in json.load(sys.stdin) if a.get('name') == sys.argv[1]))
" "$name"); do
      curl -sf -X DELETE "$DATAAGENT/agents/$id" >/dev/null && echo "已删除彩排智能体 $name ($id)"
    done
  done
  echo "完成。重启 OntoFoundry（make serve）后，按演示手册的检查清单核对一遍。"
  ;;
*)
  sed -n '2,9p' "$0"
  exit 1
  ;;
esac
