#!/usr/bin/env bash
set -uo pipefail
W=/workspace; export HF_HOME=$W/hf; export TORCH_HOME=$W/torch
export MAX_JOBS=32
export TORCH_CUDA_ARCH_LIST="8.0"
LOG=$W/logs/phase2.log
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }
step "Pixal3D requirements"
cd $W/repos/Pixal3D
pip install -q -r requirements.txt >>$LOG 2>&1 && echo "OK pixal reqs" | tee -a $LOG || echo "FAIL pixal reqs" | tee -a $LOG
step "TRELLIS.2 setup.sh (basic, flash-attn, cumesh, o-voxel, flexgemm)"
cd $W/repos/TRELLIS.2
bash setup.sh --basic --flash-attn --cumesh --o-voxel --flexgemm >>$LOG 2>&1 \
  && echo "OK trellis core" | tee -a $LOG || echo "FAIL trellis core" | tee -a $LOG
step "nvdiffrast + nvdiffrec (texturing path only; NON-COMMERCIAL licence)"
bash setup.sh --nvdiffrast --nvdiffrec >>$LOG 2>&1 \
  && echo "OK nvdiffr" | tee -a $LOG || echo "FAIL nvdiffr" | tee -a $LOG
step "import check"
python - <<'PY' 2>&1 | tee -a $LOG
mods = ["torch","diffusers","transformers","trimesh","kornia","timm","plyfile"]
for m in mods:
    try:
        __import__(m); print("  ok", m)
    except Exception as e: print("  MISSING", m, type(e).__name__, str(e)[:60])
for m in ["flash_attn","nvdiffrast.torch","moge"]:
    try:
        __import__(m); print("  ok", m)
    except Exception as e: print("  MISSING", m, type(e).__name__, str(e)[:60])
import torch; print("  cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0))
PY
step "PHASE2 DONE"; date -u +%FT%TZ > $W/logs/phase2_done
