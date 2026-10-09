#!/usr/bin/env bash
# After the Mac sleeps, the Podman VM clock falls behind and catches up in a
# jump. DataAgent reads task leases and heartbeats from MySQL inside that VM,
# so a skewed clock suspends or stalls modeling runs. Set the VM clock from
# the host and show all three clocks.
set -euo pipefail

PODMAN="$(command -v podman)"
MACHINE="${PODMAN_MACHINE:-podman-machine-default}"
DOCKER="${DOCKER:-$(command -v docker || command -v podman)}"

now="$(date -u '+%Y-%m-%d %H:%M:%S')"
"$PODMAN" machine ssh "$MACHINE" "sudo date -u -s '$now'" >/dev/null
echo "主机  UTC $(date -u '+%H:%M:%S')"
echo "MySQL UTC $("$DOCKER" exec data-portal-mysql date -u '+%H:%M:%S')"
echo "PG    UTC $("$DOCKER" exec of-local-pg date -u '+%H:%M:%S')"
