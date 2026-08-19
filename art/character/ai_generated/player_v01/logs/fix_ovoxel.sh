#!/usr/bin/env bash
set -uo pipefail
W=/workspace
export CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:$PATH
export TORCH_CUDA_ARCH_LIST="8.0" MAX_JOBS=32 PIP_NO_BUILD_ISOLATION=1
LOG=$W/logs/fix_ovoxel.log
source /opt/conda/etc/profile.d/conda.sh && conda activate rv310
step(){ echo "[$(date -u +%H:%M:%S)] == $*" | tee -a $LOG; }

step "o-voxel: check submodule state in the ORIGINAL repo"
ls -A $W/repos/TRELLIS.2/o-voxel/third_party/eigen 2>/dev/null | head -3 | tee -a $LOG
step "populating submodules in TRELLIS.2 (Eigen lives here)"
cd $W/repos/TRELLIS.2 && git submodule update --init --recursive >>$LOG 2>&1
ls -A o-voxel/third_party/eigen 2>/dev/null | head -3 | tee -a $LOG

# if the submodule is still empty, fetch Eigen directly — it is a plain header lib
if [ -z "$(ls -A $W/repos/TRELLIS.2/o-voxel/third_party/eigen 2>/dev/null)" ]; then
  step "submodule still empty -> cloning Eigen directly"
  rm -rf /tmp/eigen && git clone -q --depth 1 -b 3.4.0 https://gitlab.com/libeigen/eigen.git /tmp/eigen >>$LOG 2>&1
  mkdir -p $W/repos/TRELLIS.2/o-voxel/third_party/eigen
  cp -r /tmp/eigen/* $W/repos/TRELLIS.2/o-voxel/third_party/eigen/
fi
test -f $W/repos/TRELLIS.2/o-voxel/third_party/eigen/Eigen/Dense \
  && echo "  Eigen/Dense present" | tee -a $LOG \
  || { echo "  Eigen STILL MISSING" | tee -a $LOG; exit 1; }

step "rebuilding o_voxel from the populated source"
rm -rf /tmp/ext/o-voxel && cp -r $W/repos/TRELLIS.2/o-voxel /tmp/ext/o-voxel
cd /tmp/ext/o-voxel && rm -rf build
pip install --no-build-isolation /tmp/ext/o-voxel >>$LOG 2>&1 \
  && echo "  BUILD OK" | tee -a $LOG || { echo "  BUILD FAILED" | tee -a $LOG; tail -40 $LOG > $W/logs/second_traceback.txt; exit 1; }
python -c "import o_voxel; print('  VERIFIED o_voxel')" 2>&1 | tee -a $LOG

step "flexgemm + natten"
pip install --no-build-isolation /tmp/ext/FlexGEMM >>$LOG 2>&1
python -c "import flexgemm" 2>/dev/null && echo "  VERIFIED flexgemm" | tee -a $LOG || \
  python -c "import flex_gemm; print('  VERIFIED flex_gemm (module name)')" 2>&1 | tee -a $LOG
pip install -q natten >>$LOG 2>&1
python -c "import natten; print('  VERIFIED natten', natten.__version__)" 2>&1 | tee -a $LOG

step "FINAL IMPORT MATRIX"
python - <<'PY' 2>&1 | tee -a $LOG
import torch, importlib
print("  torch", torch.__version__, "cuda", torch.version.cuda, "avail", torch.cuda.is_available())
for m in ["cumesh","o_voxel","flexgemm","flex_gemm","natten","diffusers","transformers","trimesh","moge"]:
    try: importlib.import_module(m); print("  ok      ", m)
    except Exception as e: print("  MISSING ", m, type(e).__name__, str(e)[:60])
PY
step "FIX DONE"; date -u +%FT%TZ > $W/logs/fix_done
