#!/usr/bin/env bash
# Bounded water_can pilot: ONE encoder load, three 8s samples.
# generate.py reloads the 8B LLM2Vec encoder on every invocation (~2 min each),
# so three separate calls would burn most of a $0.10 cap on loading. --num_samples
# draws three independent samples from a single load.
set -uo pipefail
W=/workspace; export HF_HOME=$W/hf
mkdir -p $W/{logs,out}; LOG=$W/logs/water.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
die(){ echo "STOP: $*" | tee -a $LOG; echo "$*" > $W/logs/failed; exit 1; }
ARDY_SHA=693f74d13b3d04a0a22ce127ee79c929dd89756b
CKPT_REV=abe6c43beb28c867c950acb824b9c4ef3d63fb76

step "packages"
apt-get update -qq >>$LOG 2>&1; apt-get install -y -qq git cmake build-essential >>$LOG 2>&1
pip install -q --upgrade pip setuptools wheel >>$LOG 2>&1
pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124 >>$LOG 2>&1 || die torch
cd $W; [ -d ardy ] || git clone -q https://github.com/nv-tlabs/ardy.git
cd ardy && git checkout -q $ARDY_SHA && pip install -q -e . >>$LOG 2>&1 || die "ardy"
python - <<PY >>$LOG 2>&1 || die "hf auth"
import os; from huggingface_hub import login; login(token=os.environ["HF_TOKEN"]); print("ok")
PY
step "prefetch"
python - <<PY >>$LOG 2>&1
from huggingface_hub import snapshot_download
snapshot_download("nvidia/ARDY-Core-RP-20FPS-Horizon40", revision="$CKPT_REV", max_workers=8)
for r in ["meta-llama/Meta-Llama-3-8B-Instruct",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised"]:
    snapshot_download(r, max_workers=8, allow_patterns=["*.json","*.safetensors","*.model","*.py","tokenizer*"])
print("prefetched")
PY

step "water_can: 3 samples x 8s, one encoder load"
P="A person stands upright with both feet planted flat on the ground and leans forward only slightly from the waist, extending the right arm down and forward to hold a watering can out away from the body, tilting the wrist so the spout angles downward toward the soil while pouring; the left arm hangs relaxed at the side; the person stays standing and does not crouch, kneel or squat."
python scripts/generate.py "$P" --model core --duration 8.0 --seed 0 \
    --num_samples 3 --output $W/out/water8 2>&1 | tail -3 | tee -a $LOG
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "generation"

step "outputs"; ls -la $W/out $W/out/water8 2>/dev/null | tee -a $LOG
find $W/out -name '*.npz' -exec sha256sum {} \; | tee -a $LOG
date -u +%FT%TZ > $W/logs/done; step "WATER DONE"
