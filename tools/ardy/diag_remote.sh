#!/usr/bin/env bash
# Final bounded ARDY diagnostic: 2 prompts x 3 seeds at 8s, Core defaults.
# Step 1 verifies text conditioning is actually live; if it is not, this exits
# non-zero and the caller destroys the instance without generating anything.
set -uo pipefail
W=/workspace
export HF_HOME=$W/hf
mkdir -p $W/{logs,out}
LOG=$W/logs/diag.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
die(){ echo "[$(date -u +%H:%M:%S)] STOP: $*" | tee -a $LOG; echo "$*" > $W/logs/failed; exit 1; }

ARDY_SHA=693f74d13b3d04a0a22ce127ee79c929dd89756b
CKPT_REV=abe6c43beb28c867c950acb824b9c4ef3d63fb76

step "packages"
apt-get update -qq >>$LOG 2>&1; apt-get install -y -qq git cmake build-essential >>$LOG 2>&1
pip install -q --upgrade pip setuptools wheel >>$LOG 2>&1
pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124 >>$LOG 2>&1 || die torch
cd $W; [ -d ardy ] || git clone -q https://github.com/nv-tlabs/ardy.git
cd ardy && git checkout -q $ARDY_SHA && pip install -q -e . >>$LOG 2>&1 || die "ardy install"
python - <<PY >>$LOG 2>&1 || die "hf auth"
import os; from huggingface_hub import login; login(token=os.environ["HF_TOKEN"]); print("ok")
PY

step "CONDITIONING CHECK: are text embeddings finite and distinct?"
python - <<'PY' 2>&1 | tee -a $LOG
import numpy as np, torch, json, sys
from ardy.model.load_model import load_text_encoder
enc = load_text_encoder()
probes = ["stand still", "walk forward", "bend toward the ground"]
out = enc(probes)
E = out[0] if isinstance(out, (tuple, list)) else out
if hasattr(E, "detach"): E = E.detach().float().cpu().numpy()
E = np.asarray(E)
print("embedding array shape:", E.shape, "dtype:", E.dtype)
V = E.reshape(len(probes), -1)
finite = bool(np.isfinite(V).all())
norms = np.linalg.norm(V, axis=1)
print("finite:", finite, "| norms:", np.round(norms, 3).tolist())
Vn = V / np.clip(norms[:, None], 1e-9, None)
import itertools
worst = 1.0
for a, b in itertools.combinations(range(len(probes)), 2):
    cos = float(np.dot(Vn[a], Vn[b]))
    print(f"  cos('{probes[a]}','{probes[b]}') = {cos:+.4f}")
    worst = min(worst, 1.0 - cos)
print("smallest pairwise cosine DISTANCE:", round(worst, 5))
ok = finite and float(norms.min()) > 1e-6 and worst > 0.01
json.dump({"finite": finite, "norms": norms.tolist(), "min_cos_distance": worst, "ok": bool(ok)},
          open("/workspace/out/conditioning_check.json", "w"), indent=2)
print("CONDITIONING_OK" if ok else "CONDITIONING_DEAD")
sys.exit(0 if ok else 3)
PY
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "text conditioning ineffective -- refusing to generate"

step "GENERATION: 2 prompts x seeds 0-2, 8.0s, Core defaults"
WALK="A person walks forward continuously at a natural pace."
BEND="A person bends at the knees and waist, reaches their right hand toward the ground, tilts the wrist downward, then returns upright."
for SEED in 0 1 2; do
  python scripts/generate.py "$WALK" --model core --duration 8.0 --seed $SEED \
      --output $W/out/walk8_s$SEED 2>&1 | tail -2 | tee -a $LOG
  [ ${PIPESTATUS[0]:-1} -eq 0 ] || die "walk seed $SEED"
  python scripts/generate.py "$BEND" --model core --duration 8.0 --seed $SEED \
      --output $W/out/bend8_s$SEED 2>&1 | tail -2 | tee -a $LOG
  [ ${PIPESTATUS[0]:-1} -eq 0 ] || die "bend seed $SEED"
done

step "outputs"
ls -la $W/out | tee -a $LOG
cd $W/out && sha256sum *.npz > SHA256SUMS && cat SHA256SUMS | tee -a $LOG
date -u +%FT%TZ > $W/logs/done
step "DIAG DONE"
