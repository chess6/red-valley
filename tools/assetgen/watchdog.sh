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
ID="${1:?instance id, or ACCOUNT to guard every instance}"; HOURS="${2:-6}"

# ACCOUNT mode exists because the watchdog must be armed BEFORE `vastai create`
# is called -- that is the window in which a create can silently spawn a
# contract nobody recorded. There is no ID to guard yet, so it guards the whole
# account: on a breach or the deadline it destroys every active instance, not
# one remembered ID.
account_mode=0
[ "$ID" = "ACCOUNT" ] && account_mode=1

active_ids() {
  "$V" show instances --raw 2>/dev/null | python3 -c '
import json,sys
try: rows=json.load(sys.stdin) or []
except Exception: sys.exit(9)
A={"running","loading","created","starting"}
print(" ".join(str(r["id"]) for r in rows
      if (r.get("actual_status") or r.get("cur_state") or "").lower() in A))
'
}
DEADLINE=$(python3 -c "print(int($HOURS*3600))")

# How long the guard may be unreadable before we stop anyway. Sitting next to
# a hard floor with no idea what the balance is doing is not a safe state, so
# it resolves to "destroy" rather than "carry on".
BLIND_LIMIT=4   # consecutive failed polls, at 5 min each = 20 minutes

destroy() {
  if [ "$account_mode" -eq 1 ]; then
    TARGETS=$(active_ids)
    echo "[watchdog] $1 — destroying ALL active instances [${TARGETS:-none}] at $(date -u +%FT%TZ)"
    for t in $TARGETS; do printf "y\n" | "$V" destroy instance "$t"; done
    LEFT=$(active_ids)
    [ -n "$LEFT" ] && echo "[watchdog] WARNING: still active after destroy: $LEFT — STILL BILLING"
  else
    echo "[watchdog] $1 — destroying $ID at $(date -u +%FT%TZ)"
    printf "y\n" | "$V" destroy instance "$ID"
  fi
  echo "[watchdog] destroyed"
  exit 0
}

echo "[watchdog] instance=$ID budget=${HOURS}h pid=$$ started=$(date -u +%FT%TZ)"
SLEPT=0; STEP=60; BLIND=0; SEEN=0; EMPTY=0
while [ "$SLEPT" -lt "$DEADLINE" ]; do
  sleep "$STEP"; SLEPT=$((SLEPT+STEP))

  # already gone: nothing to guard. In account mode "nothing yet" is normal
  # right after arming, so only a sustained absence counts as finished.
  if [ "$account_mode" -eq 1 ]; then
    NOW_ACTIVE=$(active_ids)
    if [ -n "$NOW_ACTIVE" ]; then SEEN=1; EMPTY=0
    else
      EMPTY=$((EMPTY+STEP))
      if [ "${SEEN:-0}" -eq 1 ] && [ "$EMPTY" -ge 600 ]; then
        echo "[watchdog] account empty for 10m after a rental — exiting"; exit 0
      fi
      if [ "${SEEN:-0}" -eq 0 ] && [ "$EMPTY" -ge 900 ]; then
        echo "[watchdog] no instance ever appeared within 15m — exiting"; exit 0
      fi
    fi
  elif ! "$V" show instance "$ID" --raw >/dev/null 2>&1; then
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
