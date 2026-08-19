#!/usr/bin/env bash
set -uo pipefail
W=/workspace; export HF_HOME=$W/hf; export TORCH_HOME=$W/torch
export MAX_JOBS=32 TORCH_CUDA_ARCH_LIST="8.0"
# THE FIX: pip build isolation hid torch from every CUDA extension's setup.py
export PIP_NO_BUILD_ISOLATION=1
export CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}
LOG=$W/logs/phase3.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
step "toolchain check"
{ which nvcc; nvcc --version | tail -2; echo "CUDA_HOME=$CUDA_HOME"; python -c "import torch;print('torch',torch.__version__)"; } >>$LOG 2>&1
step "build deps present in the build env"
pip install -q packaging setuptools wheel ninja psutil >>$LOG 2>&1
cd $W/repos/TRELLIS.2
for f in --flash-attn --cumesh --o-voxel --flexgemm --nvdiffrast --nvdiffrec; do
  step "setup.sh $f"
  bash setup.sh $f >>$LOG 2>&1 && echo "  OK $f" | tee -a $LOG || echo "  FAIL $f" | tee -a $LOG
done
step "import check"
python - <<'PY' 2>&1 | tee -a $LOG
for m in ["flash_attn","cumesh","o_voxel","flexgemm","nvdiffrast.torch","nvdiffrec_render","moge","diffusers"]:
    try:
        __import__(m); print("  ok", m)
    except Exception as e: print("  MISSING", m, type(e).__name__, str(e)[:70])
PY
step "PHASE3 DONE"; date -u +%FT%TZ > $W/logs/phase3_done
