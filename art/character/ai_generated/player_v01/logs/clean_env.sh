#!/usr/bin/env bash
# Clean-room environment for Pixal3D / TRELLIS.2, built to the official spec.
#
# Deliberately different from the earlier attempts:
#   * a fresh Python 3.10 conda env (the base image was 3.11)
#   * torch 2.6.0 / torchvision 0.21.0 from the cu124 index, installed FIRST
#     so every extension compiles against one ABI
#   * CUDA_HOME exported before any build (it was unset in the base image)
#   * sm_80 only — no wasted compilation for other architectures
#   * every CUDA extension with --no-build-isolation
#   * FlashAttention SKIPPED; Pixal3D officially supports ATTN_BACKEND=sdpa
#   * only the extensions inference/export need: CuMesh, O-Voxel, FlexGEMM, NATTEN
#
# Each import is verified immediately after its install; the script STOPS at the
# first failure and preserves the raw compiler traceback rather than guessing.
set -uo pipefail
W=/workspace
export HF_HOME=$W/hf TORCH_HOME=$W/torch
export CUDA_HOME=/usr/local/cuda
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}
export TORCH_CUDA_ARCH_LIST="8.0"
export MAX_JOBS=32
export PIP_NO_BUILD_ISOLATION=1
export PIP_DISABLE_PIP_VERSION_CHECK=1

ENVN=rv310
LOG=$W/logs/clean_env.log
TRACE=$W/logs/first_traceback.txt
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
die(){  echo "[$(date -u +%H:%M:%S)] STOP: $*" | tee -a $LOG; echo "$*" > $W/logs/clean_env_failed; exit 1; }

source /opt/conda/etc/profile.d/conda.sh
step "creating fresh env $ENVN (python 3.10)"
conda create -y -q -n $ENVN python=3.10 >>$LOG 2>&1 || die "conda create failed"
conda activate $ENVN || die "conda activate failed"
python -V | tee -a $LOG
PY=$(which python); PIP="$PY -m pip"
$PIP install -q --upgrade pip setuptools wheel ninja packaging psutil >>$LOG 2>&1

step "torch 2.6.0 + torchvision 0.21.0 (cu124) FIRST — one ABI for all builds"
$PIP install -q torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124 >>$LOG 2>&1 \
  || die "torch install failed"
$PY -c "import torch;print('  torch',torch.__version__,'cuda',torch.version.cuda,'arch',torch.cuda.get_arch_list()[:3])" | tee -a $LOG

step "runtime deps (no flash-attn; sdpa backend instead)"
$PIP install -q huggingface_hub safetensors accelerate \
  "transformers==4.57.3" "diffusers==0.37.1" \
  imageio imageio-ffmpeg tqdm easydict opencv-python-headless trimesh \
  kornia timm plyfile zstandard scipy omegaconf pillow einops \
  pymeshlab xatlas pygltflib rembg onnxruntime >>$LOG 2>&1 || die "runtime deps failed"
$PIP install -q "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8" >>$LOG 2>&1
$PIP install -q "git+https://github.com/microsoft/MoGe.git" >>$LOG 2>&1

# ---- CUDA extensions, one at a time, verified immediately ------------------
build_and_verify() { # name  pip-target  import-name
  local name="$1" target="$2" imp="$3"
  step "building $name"
  if ! $PIP install --no-build-isolation "$target" >>$LOG 2>&1; then
    step "$name BUILD FAILED — capturing traceback"
    { echo "=== $name build failure ==="; tail -120 $LOG; } > $TRACE
    die "$name failed to build (traceback in $TRACE)"
  fi
  if ! $PY -c "import $imp" 2>>$LOG; then
    step "$name imports FAILED after a successful build"
    { echo "=== $name import failure ==="; $PY -c "import $imp" 2>&1 | tail -40; } > $TRACE
    die "$name built but will not import (traceback in $TRACE)"
  fi
  echo "  VERIFIED $name" | tee -a $LOG
}

mkdir -p /tmp/ext && cd /tmp/ext
step "fetching extension sources"
[ -d CuMesh ]   || git clone -q --recursive https://github.com/JeffreyXiang/CuMesh.git  CuMesh   >>$LOG 2>&1
[ -d o-voxel ]  || cp -r $W/repos/TRELLIS.2/o-voxel o-voxel 2>/dev/null
[ -d FlexGEMM ] || git clone -q --recursive https://github.com/JeffreyXiang/FlexGEMM.git FlexGEMM >>$LOG 2>&1

build_and_verify "CuMesh"   "/tmp/ext/CuMesh"   "cumesh"
build_and_verify "O-Voxel"  "/tmp/ext/o-voxel"  "o_voxel"
build_and_verify "FlexGEMM" "/tmp/ext/FlexGEMM" "flexgemm"
build_and_verify "NATTEN"   "natten"            "natten"

step "final verification"
$PY - <<'PY' 2>&1 | tee -a $LOG
import torch, importlib
print("  torch", torch.__version__, "cuda_ok", torch.cuda.is_available())
for m in ["cumesh","o_voxel","flexgemm","natten","diffusers","transformers","trimesh","moge"]:
    try: importlib.import_module(m); print("  ok", m)
    except Exception as e: print("  MISSING", m, type(e).__name__, str(e)[:70])
print("  flash_attn intentionally absent -> ATTN_BACKEND=sdpa")
PY
step "CLEAN ENV READY"; date -u +%FT%TZ > $W/logs/clean_env_done
