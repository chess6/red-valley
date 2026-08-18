#!/usr/bin/env bash
# Detached killer. Destroys the instance when EITHER limit is reached:
#
#   * the time budget expires, or
#   * the spend guard says the balance is approaching the $5 auto-refill
#     floor (budget.py, polled every 5 minutes).
#
# The second limit is the one that matters when an estimate was wrong. A time
# budget only bounds cost if the hourly rate is what you thought it was; the
# balance check bounds it whatever the rate turns out to be, and also catches
# spending this pilot knows nothing about.
#
# This survives the orchestrating session dying, which is the whole point.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"; set -a; . ./.env 2>/dev/null; set +a
V="$ROOT/tools/assetgen/.venv/bin/vastai"
GUARD="$ROOT/tools/assetgen/budget.py"
ID="${1:?instance id}"; HOURS="${2:-6}"
DEADLINE=$(python3 -c "print(int($HOURS*3600))")

# How long the guard may be unreadable before we stop anyway. Sitting next to
# a hard floor with no idea what the balance is doing is not a safe state, so
# it resolves to "destroy" rather than "carry on".
BLIND_LIMIT=4   # consecutive failed polls, at 5 min each = 20 minutes

destroy() {
  echo "[watchdog] $1 — destroying $ID at $(date -u +%FT%TZ)"
  printf "y\n" | "$V" destroy instance "$ID"
  echo "[watchdog] destroyed"
  exit 0
}

echo "[watchdog] instance=$ID budget=${HOURS}h pid=$$ started=$(date -u +%FT%TZ)"
SLEPT=0; STEP=60; BLIND=0
while [ "$SLEPT" -lt "$DEADLINE" ]; do
  sleep "$STEP"; SLEPT=$((SLEPT+STEP))

  # already gone: nothing to guard
  if ! "$V" show instance "$ID" --raw >/dev/null 2>&1; then
    echo "[watchdog] instance $ID no longer exists at ${SLEPT}s — exiting"; exit 0
  fi

  if [ $((SLEPT % 300)) -eq 0 ]; then
    GUARD_OUT=$(python3 "$GUARD" assess 2>&1); GUARD_RC=$?
    case "$GUARD_RC" in
      0) BLIND=0 ;;
      1) echo "$GUARD_OUT"; destroy "SPEND GUARD BREACH" ;;
      *) BLIND=$((BLIND+1))
         echo "[watchdog] spend guard unreadable (${BLIND}/${BLIND_LIMIT}): $GUARD_OUT"
         [ "$BLIND" -ge "$BLIND_LIMIT" ] && destroy "SPEND GUARD UNREADABLE for $((BLIND*5))m"
         ;;
    esac
  fi

  if [ $((SLEPT % 900)) -eq 0 ]; then
    echo "[watchdog] $((SLEPT/60))m elapsed of $((DEADLINE/60))m"
    python3 "$GUARD" assess 2>&1 | sed 's/^/[watchdog] /'
  fi
done
destroy "DEADLINE REACHED"
