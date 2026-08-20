#!/usr/bin/env bash
# thin ssh helper: direct mapped port, key pinned
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST=$(cat "$ROOT/tools/assetgen/.state/host" 2>/dev/null)
PORT=$(cat "$ROOT/tools/assetgen/.state/port" 2>/dev/null)
exec ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
     -o UserKnownHostsFile=/dev/null -o ConnectTimeout=25 -o ServerAliveInterval=30 \
     -p "$PORT" "root@$HOST" "$@"
