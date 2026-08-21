#!/usr/bin/env bash
# ONE constrained water_can candidate: seed 0, 8 s, single sample.
# The constraint file is built and proven locally (tools/ardy/prove_constraints.py)
# BEFORE this script ever runs; here it is only consumed via --constraints.
set -uo pipefail
W=/workspace; export HF_HOME=$W/hf
mkdir -p $W/{logs,out}; LOG=$W/logs/water_c.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
die(){ echo "STOP: $*" | tee -a $LOG; echo "$*" > $W/logs/failed; exit 1; }
ARDY_SHA=693f74d13b3d04a0a22ce127ee79c929dd89756b
CKPT_REV=abe6c43beb28c867c950acb824b9c4ef3d63fb76

[ -s $W/water_constraints.json ] || die "constraints file missing"
step "packages"
pip install -q --upgrade pip setuptools wheel >>$LOG 2>&1
cd $W; [ -d ardy ] || git clone -q https://github.com/nv-tlabs/ardy.git
cd ardy && git checkout -q $ARDY_SHA && pip install -q -e . >>$LOG 2>&1 || die "ardy install"
python - <<PY >>$LOG 2>&1 || die "hf auth"
import os; from huggingface_hub import login; login(token=os.environ["HF_TOKEN"]); print("ok")
PY
step "prefetch"
python - <<PY >>$LOG 2>&1 || die "prefetch"
from huggingface_hub import snapshot_download
snapshot_download("nvidia/ARDY-Core-RP-20FPS-Horizon40", revision="$CKPT_REV", max_workers=8)
for r in ["meta-llama/Meta-Llama-3-8B-Instruct",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised"]:
    snapshot_download(r, max_workers=8, allow_patterns=["*.json","*.safetensors","*.model","*.py","tokenizer*"])
print("prefetched")
PY

step "constrained generation: 1 sample, seed 0, 8s"
P="A person stands upright with both feet planted flat on the ground and leans forward only slightly from the waist, extending the right arm down and forward to hold a watering can out away from the body, tilting the wrist so the spout angles downward toward the soil while pouring; the left arm hangs relaxed at the side; the person stays standing and does not crouch, kneel or squat."
# --no-postprocess: skips the MotionCorrection C++ build (cmake/g++ apt installs)
# to keep the run inside the $0.10 cap; contact cleanup happens in our retarget.
python scripts/generate.py "$P" --model core --duration 8.0 --seed 0 \
    --num_samples 1 --constraints $W/water_constraints.json \
    --cfg_weight 2.0 2.0 --no-postprocess \
    --output $W/out/water_c 2>&1 | tee $W/logs/gen_stdout.log | tail -12
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "generation"
grep -q "set of constraints" $W/logs/gen_stdout.log || die "constraints were NOT loaded by generate.py"

step "outputs"; ls -la $W/out 2>/dev/null | tee -a $LOG
find $W/out -name '*.npz' -exec sha256sum {} \; | tee -a $LOG
date -u +%FT%TZ > $W/logs/done; step "WATER_CONSTRAINED DONE"
