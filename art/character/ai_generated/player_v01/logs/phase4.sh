#!/usr/bin/env bash
set -uo pipefail
W=/workspace; export HF_HOME=$W/hf; export TORCH_HOME=$W/torch
# FIX 1: nvcc exists but CUDA_HOME was unset -> extension builds could not find CUDA
export CUDA_HOME=/usr/local/cuda
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}
export MAX_JOBS=32 TORCH_CUDA_ARCH_LIST="8.0"
export PIP_NO_BUILD_ISOLATION=1
LOG=$W/logs/phase4.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }

step "torch state before"
python -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda)" | tee -a $LOG

# FIX 2: settle on ONE torch (the version setup.sh pins) BEFORE building anything,
# then build every extension against it. Mixed ABIs caused cumesh's undefined symbol.
step "pinning torch 2.6.0+cu124 (setup.sh's version) and purging mismatched builds"
pip install -q torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124 >>$LOG 2>&1 \
  && echo "  OK torch pinned" | tee -a $LOG || echo "  FAIL torch pin" | tee -a $LOG
pip uninstall -y -q cumesh o_voxel flexgemm nvdiffrast nvdiffrec_render flash-attn >>$LOG 2>&1
python -c "import torch;print('  now:',torch.__version__,torch.version.cuda)" | tee -a $LOG

step "rebuilding extensions against the pinned torch"
cd $W/repos/TRELLIS.2
for f in --cumesh --o-voxel --flexgemm --nvdiffrast --nvdiffrec --flash-attn; do
  step "setup.sh $f"
  timeout 2400 bash setup.sh $f >>$LOG 2>&1 && echo "  OK $f" | tee -a $LOG || echo "  FAIL $f" | tee -a $LOG
done

step "import check"
python - <<'PY' 2>&1 | tee -a $LOG
import importlib
need = ["cumesh","o_voxel","flexgemm","nvdiffrast.torch"]
opt  = ["flash_attn","nvdiffrec_render"]
for m in need+opt:
    tag = "REQUIRED" if m in need else "optional"
    try:
        importlib.import_module(m); print(f"  ok       {m}")
    except Exception as e:
        print(f"  MISSING  {m} [{tag}] {type(e).__name__}: {str(e)[:80]}")
import torch; print("  torch", torch.__version__, "cuda", torch.cuda.is_available())
PY
step "PHASE4 DONE"; date -u +%FT%TZ > $W/logs/phase4_done
