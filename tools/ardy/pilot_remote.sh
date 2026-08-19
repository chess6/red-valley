#!/usr/bin/env bash
# ARDY two-clip pilot, remote. Generates walk_fwd and water_can, nothing else.
# The 8B LLM2Vec text encoder needs ~14GB VRAM, which is why this runs on a
# rented 24GB card instead of the local RTX 3060 (12GB).
set -uo pipefail
W=/workspace
export HF_HOME=$W/hf
mkdir -p $W/{logs,out}
LOG=$W/logs/pilot.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
die(){ echo "[$(date -u +%H:%M:%S)] STOP: $*" | tee -a $LOG; echo "$*" > $W/logs/failed; exit 1; }

ARDY_SHA=693f74d13b3d04a0a22ce127ee79c929dd89756b
CKPT_REV=abe6c43beb28c867c950acb824b9c4ef3d63fb76

step "system packages"
apt-get update -qq >>$LOG 2>&1
apt-get install -y -qq git cmake build-essential >>$LOG 2>&1
pip install -q --upgrade pip setuptools wheel >>$LOG 2>&1

step "torch cu124"
pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124 >>$LOG 2>&1 || die torch
python -c "import torch;print('torch',torch.__version__,torch.cuda.get_device_name(0))" | tee -a $LOG

step "ardy @ $ARDY_SHA"
cd $W
[ -d ardy ] || git clone -q https://github.com/nv-tlabs/ardy.git
cd ardy && git checkout -q $ARDY_SHA
pip install -q -e . >>$LOG 2>&1 || die "ardy install"
python -c "import ardy; print('ardy ok')" | tee -a $LOG

step "hugging face auth"
python - <<PY >>$LOG 2>&1 || die "hf auth"
import os
from huggingface_hub import login
login(token=os.environ["HF_TOKEN"])
print("logged in")
PY

step "pre-fetching checkpoints (ARDY pinned, Llama, LLM2Vec adapters)"
python - <<PY 2>&1 | tee -a $LOG
import os
from huggingface_hub import snapshot_download
p=snapshot_download("nvidia/ARDY-Core-RP-20FPS-Horizon40", revision="$CKPT_REV", max_workers=8)
print("ardy ckpt:", p)
for r in ["meta-llama/Meta-Llama-3-8B-Instruct",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp",
          "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised"]:
    print(r, "->", snapshot_download(r, max_workers=8, allow_patterns=["*.json","*.safetensors","*.model","*.py","tokenizer*"]))
PY
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "checkpoint download"

cd $W/ardy
step "CLIP 1/2: walk_fwd (locomotion, text-driven)"
python scripts/generate.py \
  "A person walks forward at a steady, even pace." \
  --model core --duration 2.0 --seed 0 --output $W/out/walk_fwd 2>&1 | tee -a $LOG
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "walk_fwd generation"

step "CLIP 2/2: water_can (farming interaction, text pass)"
python scripts/generate.py \
  "A person holds a watering can in the right hand, bends down and pours water onto the ground in front, then stands up." \
  --model core --duration 2.0 --seed 0 --output $W/out/water_can 2>&1 | tee -a $LOG
[ ${PIPESTATUS[0]:-1} -eq 0 ] || die "water_can generation"

step "outputs"
ls -la $W/out | tee -a $LOG
cd $W/out && sha256sum * > SHA256SUMS 2>/dev/null; cat SHA256SUMS | tee -a $LOG
date -u +%FT%TZ > $W/logs/done
step "PILOT DONE"
