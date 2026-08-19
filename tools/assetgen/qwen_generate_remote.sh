#!/usr/bin/env bash
# Runs ON the remote instance. Builds a clean conda env for Qwen-Image-Edit,
# separate from rv310 (no shared packages, no interference with the CUDA
# extension build), generates the 4 concept-guided player reference
# candidates, then exits -- which frees the GPU memory since nothing is left
# resident. Must finish before Pixal3D touches the GPU (see
# rv310_continuation.sh's qwen_done gate).
set -uo pipefail
W=/workspace
export HF_HOME=$W/hf TORCH_HOME=$W/torch
LOG=$W/logs/qwen_gen.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a "$LOG"; }
die(){  echo "[$(date -u +%H:%M:%S)] STOP: $*" | tee -a "$LOG"; exit 1; }

source /opt/conda/etc/profile.d/conda.sh
step "creating fresh env qwen_gen (python 3.11), isolated from rv310"
conda create -y -q -n qwen_gen python=3.11 >>"$LOG" 2>&1 || die "conda create failed"
conda activate qwen_gen
PY=$(which python); PIP="$PY -m pip"
$PIP install -q --upgrade pip >>"$LOG" 2>&1
$PIP install -q torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124 >>"$LOG" 2>&1 \
  || die "torch install failed"
$PIP install -q "git+https://github.com/huggingface/diffusers.git" transformers accelerate \
  safetensors sentencepiece protobuf einops pillow >>"$LOG" 2>&1 || die "diffusers stack install failed"

step "running generation"
mkdir -p "$W/out/qwen_candidates"
$PY "$W/qwen_generate.py" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
[ "$RC" -ne 0 ] && die "qwen_generate.py exited $RC"

step "QWEN GENERATION COMPLETE"
date -u +%FT%TZ > "$W/logs/qwen_done"
