#!/usr/bin/env bash
# Vast.ai control for the Red Valley asset-generation pilot.
#
# Cost safety is the whole point of this wrapper:
#   * the instance id is recorded the moment it is created, so it can always
#     be found and destroyed even if an agent session dies;
#   * a detached local watchdog destroys the instance at a hard deadline;
#   * `panic` destroys every instance on the account, no questions asked.
#
# Vast bills while an instance is RUNNING. Stopping halts GPU billing but
# keeps paying for storage; destroying ends all billing. This pilot destroys.
#
# The account auto-refills below $5, so that balance is a wall rather than a
# budget: crossing it charges the card. Every command that can spend money
# goes through budget.py, which refuses on projected balance rather than
# current balance. See docs/VAST_BUDGET.md.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
set -a; . ./.env 2>/dev/null; set +a
V="$ROOT/tools/assetgen/.venv/bin/vastai"
GUARD="$ROOT/tools/assetgen/budget.py"
STATE="$ROOT/tools/assetgen/.state"
mkdir -p "$STATE"
IDFILE="$STATE/instance_id"
LOGDIR="$ROOT/tools/assetgen/.state/logs"; mkdir -p "$LOGDIR"

usage() {
  cat <<EOF
usage: vast.sh <cmd>
  up <offer_id> [hours]  create instance, record id, arm watchdog (default 6h)
  id                     print recorded instance id
  status                 show instance state + accrued cost
  ssh -- <cmd...>        run a command on the instance
  put <src> <dst>        copy up
  fetch <src> <dst>      copy down
  down                   destroy the recorded instance (ends billing)
  panic                  destroy ALL instances on the account
  cost                   balance + running instances
  guard                  spend guard: balance, burn, runway to the stop line
EOF
}

inst_id() { cat "$IDFILE" 2>/dev/null; }

case "${1:-}" in
up)
  OFFER="${2:?offer id required}"; HOURS="${3:-6}"
  # Refuse before spending anything: balance clear of the stop line, nothing
  # already running, no parked storage quietly draining the account.
  if ! python3 "$GUARD" assess; then
    echo "!! spend guard refused — not creating an instance (see above)" >&2
    exit 1
  fi
  # PyTorch+CUDA devel image: compilers present for the CUDA extensions
  IMG="pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel"
  echo ">> creating instance from offer $OFFER (image $IMG, disk 300G)"
  OUT=$("$V" create instance "$OFFER" \
        --image "$IMG" --disk 300 --ssh --direct \
        --env '-e HF_HOME=/workspace/hf -e TORCH_HOME=/workspace/torch' \
        --onstart-cmd 'touch /workspace/.rv_booted' --raw 2>&1)
  echo "$OUT" | head -5
  ID=$(echo "$OUT" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin); print(d.get('new_contract') or d.get('id') or '')
except Exception: print('')" 2>/dev/null)
  [ -z "$ID" ] && { echo "!! could not parse instance id — check output above"; exit 1; }
  echo "$ID" > "$IDFILE"
  date -u +%s > "$STATE/started_at"
  echo "$HOURS" > "$STATE/budget_hours"
  echo ">> instance $ID recorded in $IDFILE"
  # The price is only knowable once the instance exists: this CLI's
  # `search offers 'id=...'` filter returns nothing, so an offer cannot be
  # priced up front. Check the real rate immediately and destroy on failure --
  # that costs seconds of billing instead of hours.
  if ! python3 "$GUARD" postcheck --instance "$ID" --hours "$HOURS"; then
    echo "!! $ID cannot finish ${HOURS}h above the stop line — destroying it now" >&2
    printf "y\n" | "$V" destroy instance "$ID" >/dev/null
    rm -f "$IDFILE"
    exit 1
  fi
  # detached watchdog: survives this shell, destroys at the deadline or when
  # the balance approaches the floor, whichever comes first
  nohup "$ROOT/tools/assetgen/watchdog.sh" "$ID" "$HOURS" \
        >"$LOGDIR/watchdog.log" 2>&1 &
  disown || true
  echo ">> watchdog armed: destroy after ${HOURS}h or on spend-guard breach"
  echo "   (log: $LOGDIR/watchdog.log)"
  ;;
guard)
  python3 "$GUARD" assess
  ;;
id) inst_id ;;
status)
  ID=$(inst_id); [ -z "$ID" ] && { echo "no instance recorded"; exit 0; }
  "$V" show instance "$ID" --raw 2>/dev/null | python3 -c "
import sys,json,time
d=json.load(sys.stdin)
st=d.get('actual_status') or d.get('cur_state')
dph=d.get('dph_total',0)
start=d.get('start_date') or 0
el=(time.time()-start)/3600 if start else 0
print(f\"id={d.get('id')} status={st} gpu={d.get('gpu_name')} dph=\${dph:.3f}\")
print(f\"elapsed={el:.2f}h  accrued=\${el*dph:.2f}\")
print(f\"ssh={d.get('ssh_host')}:{d.get('ssh_port')}\")"
  ;;
ssh)
  ID=$(inst_id); shift; [ "${1:-}" = "--" ] && shift
  "$V" ssh-url "$ID" >/dev/null 2>&1
  URL=$("$V" ssh-url "$ID" 2>/dev/null)
  HOST=$(echo "$URL" | sed -E 's#ssh://([^@]+)@([^:]+):([0-9]+)#\2#')
  PORT=$(echo "$URL" | sed -E 's#ssh://([^@]+)@([^:]+):([0-9]+)#\3#')
  USER=$(echo "$URL" | sed -E 's#ssh://([^@]+)@([^:]+):([0-9]+)#\1#')
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=20 -p "$PORT" "$USER@$HOST" "$@"
  ;;
put)
  ID=$(inst_id); "$V" copy "$2" "$ID:$3" ;;
fetch)
  ID=$(inst_id); "$V" copy "$ID:$2" "$3" ;;
down)
  ID=$(inst_id); [ -z "$ID" ] && { echo "nothing to destroy"; exit 0; }
  echo ">> destroying $ID";  printf "y\n" | "$V" destroy instance "$ID" >/dev/null; rm -f "$IDFILE"
  ;;
panic)
  echo ">> destroying ALL instances on this account"
  "$V" show instances --raw 2>/dev/null | python3 -c "
import sys,json
for i in json.load(sys.stdin): print(i.get('id'))" | while read -r i; do
    [ -n "$i" ] && { echo "   destroy $i";  printf "y\n" | "$V" destroy instance "$i" >/dev/null; }
  done
  rm -f "$IDFILE"
  ;;
cost)
  "$V" show user --raw 2>/dev/null | python3 -c "
import sys,json; d=json.load(sys.stdin); print(f\"balance \${d.get('credit',0):.2f}\")"
  echo "running instances:"
  "$V" show instances --raw 2>/dev/null | python3 -c "
import sys,json,time
rows=json.load(sys.stdin)
if not rows: print('  (none — not billing)')
for i in rows:
    st=i.get('actual_status'); dph=i.get('dph_total',0)
    s=i.get('start_date') or 0; el=(time.time()-s)/3600 if s else 0
    print(f\"  id={i.get('id')} {st} \${dph:.3f}/h elapsed={el:.2f}h accrued=\${el*dph:.2f}\")"
  ;;
*) usage ;;
esac
