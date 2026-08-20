#!/usr/bin/env bash
# Generation -> copy back -> verify locally -> destroy. In that order: the
# instance is only destroyed once the local copies are proven, because a
# corrupt transfer discovered after destruction cannot be re-fetched.
#
# Destruction itself is in an EXIT trap, so the rental ends whether generation
# succeeds, fails, or this script dies.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
set -a; . ./.env 2>/dev/null; set +a
SSH="$ROOT/tools/assetgen/ssh.sh"
V="$ROOT/tools/assetgen/.venv/bin/vastai"
ID=$(cat tools/assetgen/.state/instance_id)
DEST="art/character/ai_generated/player_v01"
mkdir -p "$DEST/out" "$DEST/logs" "$DEST/renders"

destroy_now() {
  echo ""; echo ">> destroying $ID"
  printf "y\n" | "$V" destroy instance "$ID" >/dev/null 2>&1
  LEFT=$("$V" show instances --raw 2>/dev/null | python3 -c '
import json,sys
rows=json.load(sys.stdin) or []
A={"running","loading","created","starting"}
print(" ".join(str(r["id"]) for r in rows
      if (r.get("actual_status") or r.get("cur_state") or "").lower() in A))' 2>/dev/null)
  if [ -n "$LEFT" ]; then echo "!! STILL ACTIVE: $LEFT — STILL BILLING"
  else echo ">> confirmed: nothing active, nothing billing"; fi
}
trap destroy_now EXIT

echo "=== reconcile before generation ==="
python3 tools/assetgen/provision.py reconcile || exit 1

echo "=== generation (detached: an ssh drop must not kill a billing job) ==="
timeout 120 "$SSH" 'cd /workspace && rm -f logs/run3_done logs/run3_failed && \
  setsid nohup ./run3.sh gen > /workspace/logs_gen.out 2>&1 < /dev/null & echo launched'
for i in $(seq 1 90); do
  sleep 30
  ST=$(timeout 60 "$SSH" 'if [ -f /workspace/logs/run3_done ]; then echo DONE;
       elif [ -f /workspace/logs/run3_failed ]; then echo FAILED;
       else grep -E "^\[|^=== " /workspace/logs_gen.out | tail -1; fi' 2>/dev/null | tr -d "\r" | tail -1)
  echo "  [$(date -u +%H:%M:%S)] $ST"
  case "$ST" in DONE) break;; FAILED) break;; esac
done

echo "=== copy back ==="
timeout 300 "$SSH" 'cat /workspace/logs_gen.out' > "$DEST/logs/run3_gen.out" 2>/dev/null
timeout 300 "$SSH" 'cat /workspace/logs/run3_install.log 2>/dev/null | tail -600' > "$DEST/logs/run3_install_tail.log" 2>/dev/null
timeout 120 "$SSH" 'ls -la /workspace/out/' 2>/dev/null | tee "$DEST/logs/remote_out_listing.txt"
for f in $(timeout 120 "$SSH" 'ls /workspace/out/ 2>/dev/null' 2>/dev/null | tr -d "\r"); do
  echo "  fetching $f"
  timeout 1200 "$SSH" "cat /workspace/out/$f" > "$DEST/out/$f"
done

echo "=== checksum verification: remote manifest vs local files ==="
timeout 120 "$SSH" 'cat /workspace/out/SHA256SUMS' 2>/dev/null | tr -d "\r" \
  | sed "s#^\([0-9a-f]\{64\}\)  #\1  $DEST/out/#" > /tmp/rv_remote_sums.txt
cat /tmp/rv_remote_sums.txt
if [ -s /tmp/rv_remote_sums.txt ] && sha256sum -c /tmp/rv_remote_sums.txt; then
  echo "CHECKSUMS MATCH — local copies verified"
else
  echo "!! CHECKSUM MISMATCH OR NO MANIFEST — not destroying on a bad copy"
  exit 1
fi

GLB=$(ls "$DEST"/out/*.glb 2>/dev/null | head -1)
if [ -z "$GLB" ]; then echo "!! no GLB produced"; exit 1; fi

echo "=== local validation: does the GLB import and render? (before destroy) ==="
timeout 600 /opt/blender/blender --background --python tools/assetgen/render_review.py \
  -- "$GLB" "$DEST/renders" 2>&1 | grep -E 'RENDER_STATS|Traceback|FAIL' | tail -3
ls -la "$DEST/renders/"
echo "=== local copies verified; destroying ==="
