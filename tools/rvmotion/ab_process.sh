#!/usr/bin/env bash
# Process both A/B outputs through the SAME pipeline: adapt -> validate native ->
# retarget -> validate production -> scorecard. Same code path for both, so any
# difference in the result is a difference in the motion.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
SP=/tmp/claude-1000/-home-thomas-Dev-red-valley/e3d960f9-063f-4ad9-a150-9030f429b74c/scratchpad
BLENDER=/opt/blender/blender
KVENV="$SP/kvenv/bin/python"

process() { # name  npz  adapter-module  src  contract-summary
  local NAME="$1" NPZ="$2" MOD="$3" SRC="$4" SUM="$5"
  local OUT="art/animation/ab/$NAME"
  mkdir -p "$OUT"
  echo "== $NAME =="
  [ -f "$NPZ" ] || { echo "   missing $NPZ -- skipped"; return 0; }

  local PY=python3
  [ "$MOD" = "kimodo_soma30" ] && PY="$KVENV"
  $PY "tools/rvmotion/adapters/$MOD.py" "$SRC" "$NPZ" "art/animation/ab/canonical_$NAME" \
    2>&1 | grep -E "FK |up-axis|wrote" | sed 's/^/   /'

  python3 tools/rvmotion/native_view.py "art/animation/ab/canonical_$NAME" \
    "$OUT/native" >/dev/null 2>&1 && echo "   native views rendered"

  timeout 3500 "$BLENDER" --background art/animation/rigify/rv_bound.blend \
    --python tools/rvmotion/retarget_rigify_v2.py -- \
    "art/animation/ab/canonical_$NAME" "$OUT" 2>&1 \
    | grep -E "RETARGET_V2_DONE|Traceback" | sed 's/^/   /'

  timeout 3000 "$BLENDER" --background "$OUT/$(basename $OUT).blend" \
    --python tools/rvmotion/validate.py -- "art/animation/ab/canonical_$NAME" \
    "$OUT/validation.json" --label "$NAME" >/dev/null 2>&1

  python3 tools/rvmotion/scorecard.py --native "art/animation/ab/canonical_$NAME" \
    --contract "$SUM" --production "$OUT/validation.json" \
    --out "art/animation/ab/scorecard_$NAME.json" --label "$NAME" \
    2>&1 | tail -2 | sed 's/^/   /'
}

process kimodo art/animation/ab/raw/kimodo_water.npz kimodo_soma30 \
  "$(cat $SP/kimodo_path)" art/animation/kimodo/constraints/water_contract_summary.json
process ardy art/animation/ab/raw/ardy_water.npz ardy_core27 \
  "$SP/ardy" art/animation/ardy_pilot/constraints_v2/water_contract_summary.json

echo
echo "=== SCORECARDS ==="
python3 - <<'PY'
import json, glob, os
rows=[]
for f in sorted(glob.glob("art/animation/ab/scorecard_*.json")):
    d=json.load(open(f)); a=d["A_morphology_normalised"]; b=d["B_production"]; c=d["contract"]
    rows.append((d["label"], c, a, b))
if not rows:
    print("  (no scorecards yet)"); raise SystemExit
print("  %-26s %-14s %-14s"%("metric", *[r[0] for r in rows][:2]))
def line(lbl, fn):
    print("  %-26s %-14s %-14s"%(lbl, *[str(fn(r)) for r in rows][:2]))
line("contract lean needed", lambda r: "%s deg"%r[1].get("min_trunk_lean_deg"))
line("pelvis drop asked", lambda r: "%.3f m"%(r[1].get("pelvis_drop_m") or 0))
line("A: trunk lean at pour", lambda r: "%.1f deg"%r[2]["trunk_lean_at_pour_deg"]["mean"])
line("A: arm extension", lambda r: "%.2f"%r[2]["arm_extension_at_pour"]["mean"])
line("A: lead foot advance", lambda r: "%.3f hip"%r[2]["lead_foot_advance_hip_fraction"])
line("A: rear foot drift", lambda r: "%.3f hip"%r[2]["rear_foot_drift_hip_fraction"])
line("A: stepped?", lambda r: r[2]["gate_lead_foot_stepped"])
line("A: rear stayed?", lambda r: r[2]["gate_rear_foot_stayed"])
line("B: spout in band", lambda r: r[3].get("spout_in_band"))
line("B: reach ratio", lambda r: r[3].get("forward_reach_ratio"))
line("B: body collisions", lambda r: r[3].get("body_collisions"))
PY
