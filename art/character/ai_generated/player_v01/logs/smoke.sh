#!/usr/bin/env bash
set -uo pipefail
source /opt/conda/etc/profile.d/conda.sh && conda activate rv310
export CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:$PATH
export ATTN_BACKEND=sdpa HF_HOME=/workspace/hf SPCONV_ALGO=native
cd /workspace/repos/Pixal3D
mkdir -p /workspace/out
LOG=/workspace/logs/smoke.log
echo "[$(date -u +%H:%M:%S)] smoke test: official example @1024, sdpa" | tee -a $LOG
python - <<'PY' 2>&1 | tee -a $LOG
import sys, json, time, runpy, torch
sys.argv = ["inference.py",
            "--image", "assets/images/0_img.png",
            "--output", "/workspace/out/smoke_1024.glb",
            "--seed", "1",
            "--resolution", "1024",
            "--model_path", "/workspace/models/trellis2-4b"]
t0=time.time()
try:
    runpy.run_path("inference.py", run_name="__main__")
    ok=True
except SystemExit as e:
    ok = (e.code in (0,None))
except Exception as e:
    ok=False
    import traceback; traceback.print_exc()
dt=time.time()-t0
# RUNTIME evidence of which restricted modules were actually loaded
loaded = sorted(m for m in sys.modules if any(k in m for k in
          ("nvdiffrast","nvdiffrec","o_voxel","cumesh","flex_gemm","natten","flash_attn")))
json.dump({"ok":ok,"seconds":round(dt,1),"loaded_modules":loaded,
           "peak_vram_gb":round(torch.cuda.max_memory_allocated()/1e9,2)},
          open("/workspace/out/smoke_modules.json","w"), indent=1)
print("RESULT ok=%s %.1fs" % (ok, dt))
print("LOADED:", loaded)
PY
ls -la /workspace/out/ | tee -a $LOG
echo "[$(date -u +%H:%M:%S)] SMOKE DONE" | tee -a $LOG
date -u +%FT%TZ > /workspace/logs/smoke_done
