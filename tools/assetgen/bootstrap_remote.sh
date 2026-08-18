#!/usr/bin/env bash
# Remote bootstrap for the Red Valley asset-generation pilot.
#
# Runs detached on the Vast instance. Everything is timestamped so the
# orchestrator can enforce the 2.5 h install budget from outside.
#
# Weight downloads run in PARALLEL with the CUDA-extension builds, because
# those are the two slowest steps and they do not contend for the same
# resource (network vs CPU).
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
W=/workspace
export HF_HOME=$W/hf
export HF_HUB_ENABLE_HF_TRANSFER=1
export TORCH_HOME=$W/torch
export PIP_DISABLE_PIP_VERSION_CHECK=1
mkdir -p $W/{hf,torch,repos,out,logs}
LOG=$W/logs/bootstrap.log
step() { echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
ok()   { echo "[$(date -u +%H:%M:%S)] OK $*" | tee -a $LOG; }
fail() { echo "[$(date -u +%H:%M:%S)] FAIL $*" | tee -a $LOG; }

# pinned commits, audited 2026-08-18
QWEN_SHA=6b5e1f5cec98
PIXAL_SHA=cdbb2bbffbf4
TRELLIS_SHA=75fbf0183001
SKIN_SHA=273b691d3598

step "system packages"
apt-get update -qq >>$LOG 2>&1
apt-get install -y -qq git git-lfs build-essential ninja-build cmake \
    libgl1 libglib2.0-0 libx11-6 wget curl unzip xz-utils >>$LOG 2>&1 && ok "apt" || fail "apt"
git lfs install >>$LOG 2>&1

step "python tooling"
pip install -q --upgrade pip setuptools wheel >>$LOG 2>&1
pip install -q huggingface_hub[hf_transfer] hf_transfer >>$LOG 2>&1 && ok "hf cli" || fail "hf cli"

# ---------------------------------------------------------------- downloads
step "starting weight downloads in background"
dl() {  # repo -> local dir
  local repo="$1" dest="$2"
  ( python - <<PY >>$W/logs/dl_$(basename "$dest").log 2>&1
from huggingface_hub import snapshot_download
p = snapshot_download("$repo", local_dir="$dest", max_workers=16)
print("DONE", p)
PY
  ) &
  echo $!
}
# Qwen-Image-Edit is the one the brief actually needs (concept-guided edit).
# The base generation model is only fetched if editing proves insufficient.
PID_QWEN=$(dl "Qwen/Qwen-Image-Edit-2511" "$W/models/qwen-image-edit-2511")
PID_TREL=$(dl "microsoft/TRELLIS.2-4B"    "$W/models/trellis2-4b")
PID_SKIN=$(dl "VAST-AI/SkinTokens"        "$W/models/skintokens")
echo "download pids: qwen=$PID_QWEN trellis=$PID_TREL skin=$PID_SKIN" | tee -a $LOG

# ---------------------------------------------------------------- repos
step "cloning repos at pinned commits"
cd $W/repos
clone() { # url dir sha
  [ -d "$2/.git" ] || git clone -q "$1" "$2" >>$LOG 2>&1
  ( cd "$2" && git fetch -q --all >>$LOG 2>&1; git checkout -q "$3" >>$LOG 2>&1 \
    && echo "  $2 @ $(git rev-parse --short HEAD)" | tee -a $LOG )
}
clone https://github.com/QwenLM/Qwen-Image.git            Qwen-Image   $QWEN_SHA
clone https://github.com/TencentARC/Pixal3D.git           Pixal3D      $PIXAL_SHA
clone https://github.com/microsoft/TRELLIS.2.git          TRELLIS.2    $TRELLIS_SHA
clone https://github.com/VAST-AI-Research/SkinTokens.git  SkinTokens   $SKIN_SHA
ok "repos cloned"

step "recording install requirements for audit"
for r in Pixal3D TRELLIS.2 SkinTokens Qwen-Image; do
  echo "--- $r ---" >> $W/logs/requirements_seen.txt
  ls $W/repos/$r | head -20 >> $W/logs/requirements_seen.txt
  for f in requirements.txt setup.py pyproject.toml environment.yml install.sh setup.sh; do
    [ -f "$W/repos/$r/$f" ] && echo "  has $f" >> $W/logs/requirements_seen.txt
  done
done

# ---------------------------------------------------------------- python deps
step "qwen image deps"
pip install -q "diffusers>=0.31" "transformers>=4.46" accelerate safetensors \
    sentencepiece protobuf einops pillow >>$LOG 2>&1 && ok "qwen deps" || fail "qwen deps"

step "trellis2 / pixal3d deps (CUDA extensions — slowest step)"
pip install -q trimesh pymeshlab scikit-image opencv-python-headless \
    imageio imageio-ffmpeg rembg onnxruntime plyfile pygltflib xatlas \
    open3d scipy tqdm omegaconf easydict >>$LOG 2>&1 && ok "geometry deps" || fail "geometry deps"

step "waiting for downloads"
for p in $PID_QWEN $PID_TREL $PID_SKIN; do wait $p 2>/dev/null; done
ok "downloads finished"
du -sh $W/models/* 2>/dev/null | tee -a $LOG

step "BOOTSTRAP COMPLETE"
date -u +%FT%TZ | tee -a $W/logs/bootstrap_done
