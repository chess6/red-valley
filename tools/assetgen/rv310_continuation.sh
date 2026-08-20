#!/usr/bin/env bash
# Detached watcher for the in-progress rv310 clean-env build (see
# clean_env_remote.sh) on the recorded Vast.ai instance. Polls at most once a
# minute. Never touches the build itself -- only observes it and reacts once
# it quiesces.
#
#   build succeeds -> verify imports fresh, run one 512-res Pixal3D smoke
#                      test (ATTN_BACKEND=sdpa), save output + logs locally
#   build fails     -> preserve the first genuine traceback, stop
#   either way      -> once results are copied locally, stop the instance
#     (billing ends; storage still bills, so this does not park it)
#
# The build had already failed once (O-Voxel) before this watcher started;
# that stale clean_env_failed marker must not be mistaken for the outcome of
# the retry in progress. So failure is only declared when the marker's mtime
# is NEWER than this watcher's start time AND no build process is still
# active under /tmp/ext (the extension build workdir).
#
# A prior run of this script spent ~9h silently polling a dead instance
# after it was deleted out from under it (ssh calls failed fast, so no
# money was wasted, but nothing was ever reported). "instance no longer
# exists" is now checked explicitly every poll and treated as its own
# terminal condition instead of falling through to empty/zero values.
#
# Also waits for a local Qwen-completion sentinel before running the smoke
# test, since Qwen and Pixal3D must not run on the GPU at the same time.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
LOGDIR="$ROOT/tools/assetgen/.state/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/rv310_continuation.log"
OUTDIR="$ROOT/art/character/ai_generated/player_v01"
RESULT="$OUTDIR/logs/rv310_result"
VAST="$ROOT/tools/assetgen/vast.sh"
QWEN_DONE="$ROOT/tools/assetgen/.state/qwen_done"

log(){ echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
rssh(){ "$VAST" ssh -- "$@"; }
instance_alive(){
  ID=$(cat "$ROOT/tools/assetgen/.state/instance_id" 2>/dev/null)
  [ -n "$ID" ] && "$ROOT/tools/assetgen/.venv/bin/vastai" show instance "$ID" --raw 2>/dev/null | grep -q '"id"'
}

log "watcher started pid=$$"
BASELINE_FAILED_MTIME=$(rssh 'stat -c %Y /workspace/logs/clean_env_failed 2>/dev/null || echo 0' 2>/dev/null | tail -1)
BASELINE_FAILED_MTIME=${BASELINE_FAILED_MTIME:-0}
log "baseline clean_env_failed mtime=$BASELINE_FAILED_MTIME (retry already in flight from an earlier O-Voxel failure)"

finish() {
  mkdir -p "$RESULT"
  log "copying results locally, then stopping the instance"
  "$VAST" fetch /workspace/logs/clean_env.log "$RESULT/clean_env.log" >>"$LOG" 2>&1 || true
  "$VAST" fetch /workspace/logs/first_traceback.txt "$RESULT/first_traceback.txt" >>"$LOG" 2>&1 || true
  "$VAST" down >>"$LOG" 2>&1
  log "instance stopped -- DONE ($1)"
  exit "$2"
}

while true; do
  sleep 60

  if ! instance_alive; then
    log "instance no longer exists -- stopping (not a build outcome, something external removed it)"
    mkdir -p "$RESULT"
    echo "instance vanished at $(date -u +%FT%TZ), watcher had no build result yet" > "$RESULT/instance_vanished.txt"
    exit 2
  fi

  ACTIVE=$(rssh 'pgrep -af "/tmp/ext" 2>/dev/null | wc -l' 2>/dev/null | tail -1)
  ACTIVE=${ACTIVE:-1}
  DONE=$(rssh '[ -f /workspace/logs/clean_env_done ] && echo 1 || echo 0' 2>/dev/null | tail -1)
  FAILED_MTIME=$(rssh 'stat -c %Y /workspace/logs/clean_env_failed 2>/dev/null || echo 0' 2>/dev/null | tail -1)
  FAILED_MTIME=${FAILED_MTIME:-0}

  log "poll: active_build_procs=$ACTIVE done=$DONE failed_mtime=$FAILED_MTIME"

  if [ "$DONE" = "1" ]; then
    log "rv310 build SUCCEEDED"
    break
  fi
  if [ "$FAILED_MTIME" -gt "$BASELINE_FAILED_MTIME" ] && [ "$ACTIVE" = "0" ]; then
    log "rv310 build FAILED (fresh failure marker, no build process still running)"
    finish "failure" 1
  fi
done

log "rv310 build done -- waiting for Qwen generation to finish and unload before touching the GPU"
while [ ! -f "$QWEN_DONE" ]; do
  sleep 60
  if ! instance_alive; then
    log "instance vanished while waiting for Qwen to finish"
    exit 2
  fi
done
log "Qwen sentinel present ($(cat "$QWEN_DONE"))"

log "verifying imports fresh in rv310 before touching Pixal3D"
IMPORT_OUT=$(rssh 'source /opt/conda/etc/profile.d/conda.sh && conda activate rv310 && python -c "
import importlib
mods = [\"torch\",\"cumesh\",\"o_voxel\",\"flexgemm\",\"natten\",\"diffusers\",\"transformers\",\"trimesh\",\"moge\"]
missing = []
for m in mods:
    try: importlib.import_module(m)
    except Exception as e: missing.append(f\"{m}: {e}\")
if missing:
    print(\"MISSING:\"); [print(\" \", m) for m in missing]
else:
    print(\"ALL_OK\")
"' 2>&1)
mkdir -p "$RESULT"
echo "$IMPORT_OUT" > "$RESULT/import_check.log"
log "import check: $(echo "$IMPORT_OUT" | tail -1)"

if ! echo "$IMPORT_OUT" | grep -q "ALL_OK"; then
  log "import verification failed -- not running the smoke test"
  finish "import-check-failed" 1
fi

log "imports OK -- running one 512 Pixal3D smoke test (ATTN_BACKEND=sdpa, --low_vram)"
mkdir -p "$OUTDIR/renders/smoke512"
SMOKE_OUT=$(rssh 'source /opt/conda/etc/profile.d/conda.sh && conda activate rv310 && \
  export HF_HOME=/workspace/hf TORCH_HOME=/workspace/torch CUDA_HOME=/usr/local/cuda \
  ATTN_BACKEND=sdpa && \
  mkdir -p /workspace/out/smoke512 && \
  cd /workspace/repos/Pixal3D && \
  python inference.py --image assets/images/0_img.png \
    --output /workspace/out/smoke512/output.glb --low_vram --resolution 512' 2>&1)
SMOKE_RC=$?
echo "$SMOKE_OUT" > "$RESULT/pixal3d_smoke512.log"
log "smoke test exit code=$SMOKE_RC (log saved to $RESULT/pixal3d_smoke512.log)"

"$VAST" fetch /workspace/out/smoke512 "$OUTDIR/renders/smoke512" >>"$LOG" 2>&1 || true

if [ "$SMOKE_RC" -ne 0 ]; then
  log "smoke test FAILED -- output/logs saved for inspection"
  finish "smoke-test-failed" 1
fi

log "smoke test PASSED"
finish "success" 0
