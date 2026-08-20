#!/usr/bin/env bash
# Inference -> copy back -> verify -> destroy. Written before the build
# finishes so that none of it is composed while the GPU is billing.
#
# The instance is destroyed in a trap: whether inference succeeds, fails or
# this script dies, the rental ends. Leaving it up is the expensive failure.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
set -a; . ./.env 2>/dev/null; set +a
SSH="$ROOT/tools/assetgen/ssh.sh"
V="$ROOT/tools/assetgen/.venv/bin/vastai"
ID=$(cat tools/assetgen/.state/instance_id)
DEST="art/character/ai_generated/player_v01"
mkdir -p "$DEST/out" "$DEST/logs" "$DEST/renders"

destroy_now() {
  echo ">> destroying $ID"
  printf "y\n" | "$V" destroy instance "$ID" >/dev/null 2>&1
  LEFT=$("$V" show instances --raw 2>/dev/null | python3 -c '
import json,sys
rows=json.load(sys.stdin) or []
A={"running","loading","created","starting"}
print(" ".join(str(r["id"]) for r in rows
      if (r.get("actual_status") or r.get("cur_state") or "").lower() in A))' 2>/dev/null)
  if [ -n "$LEFT" ]; then echo "!! STILL ACTIVE AFTER DESTROY: $LEFT — STILL BILLING"; else echo ">> confirmed: nothing active"; fi
}
trap destroy_now EXIT

echo "=== reconcile before inference ==="
python3 tools/assetgen/provision.py reconcile || exit 1

echo "=== inference (gate asserts image_attn_mode == proj first) ==="
# detached on the host: an ssh drop must not kill a job the GPU is billing for
timeout 120 "$SSH" 'cd /workspace && rm -f logs/run2_done logs/run2_failed && \
  setsid nohup ./run2.sh infer > /workspace/logs_infer.out 2>&1 < /dev/null & echo launched'
for i in $(seq 1 60); do
  sleep 30
  ST=$(timeout 60 "$SSH" 'if [ -f /workspace/logs/run2_done ]; then echo DONE;
       elif [ -f /workspace/logs/run2_failed ]; then echo FAILED; else tail -1 /workspace/logs_infer.out; fi' 2>/dev/null | tr -d "\r" | tail -1)
  echo "  [$(date -u +%H:%M:%S)] $ST"
  case "$ST" in DONE) break;; FAILED) echo "!! inference failed"; break;; esac
done
timeout 120 "$SSH" 'tail -40 /workspace/logs_infer.out' 2>/dev/null | grep -v "^Welcome\|^Have fun"

echo "=== copy back ==="
timeout 600 "$SSH" 'ls -la /workspace/out/; cat /workspace/out/SHA256SUMS 2>/dev/null' | tee "$DEST/logs/remote_out_listing.txt"
for f in $(timeout 120 "$SSH" 'ls /workspace/out/ 2>/dev/null' | tr -d "\r"); do
  echo "  fetching $f"
  timeout 900 "$SSH" "cat /workspace/out/$f" > "$DEST/out/$f"
done
timeout 300 "$SSH" 'cat /workspace/logs/run2_infer.log' > "$DEST/logs/run2_infer.log" 2>/dev/null
timeout 300 "$SSH" 'cat /workspace/logs/run2_install.log | tail -400' > "$DEST/logs/run2_install_tail.log" 2>/dev/null

echo "=== checksum verification (remote vs local) ==="
timeout 120 "$SSH" 'sha256sum /workspace/out/*.glb 2>/dev/null' | tr -d "\r" \
  | sed "s#/workspace/out/#$DEST/out/#" > /tmp/remote_sums.txt
cat /tmp/remote_sums.txt
sha256sum -c /tmp/remote_sums.txt && echo "CHECKSUMS MATCH" || echo "!! CHECKSUM MISMATCH"
