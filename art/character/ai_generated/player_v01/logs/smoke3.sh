#!/usr/bin/env bash
set -uo pipefail
source /opt/conda/etc/profile.d/conda.sh && conda activate rv310
export CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:$PATH
export ATTN_BACKEND=sdpa HF_HOME=/workspace/hf
cd /workspace/repos/Pixal3D
mkdir -p /workspace/out
python - <<'PY' 2>&1
import sys, json, time, runpy, importlib, torch
# stub the gated, non-commercial background remover BEFORE inference.py loads.
# Inputs are RGBA with real alpha, so the pipeline never invokes it.
rembg = importlib.import_module("pixal3d.pipelines.rembg")
class _Unused:
    def __init__(self,*a,**k): pass
    def to(self,*a,**k): return self
    def cpu(self): return self
    def __call__(self,img): raise RuntimeError("rembg invoked; input lacked alpha")
rembg.BiRefNet = _Unused
print("[driver] gated briaai/RMBG-2.0 stubbed out")

sys.argv = ["inference.py",
            "--image","assets/images/1_img.png",
            "--output","/workspace/out/smoke_1024.glb",
            "--seed","1",
            "--resolution","1024",
            "--model_path","/workspace/models/trellis2-4b"]
t0=time.time(); ok=True
try:
    runpy.run_path("inference.py", run_name="__main__")
except SystemExit as e:
    ok = e.code in (0,None)
except Exception:
    ok=False; import traceback; traceback.print_exc()
dt=time.time()-t0
loaded=sorted(m for m in sys.modules if any(k in m for k in
        ("nvdiffrast","nvdiffrec","o_voxel","cumesh","flex_gemm","natten","flash_attn")))
json.dump({"ok":ok,"seconds":round(dt,1),"runtime_modules":loaded,
           "peak_vram_gb":round(torch.cuda.max_memory_allocated()/1e9,2)},
          open("/workspace/out/smoke_modules.json","w"),indent=1)
print(f"RESULT ok={ok} {dt:.1f}s peak_vram={torch.cuda.max_memory_allocated()/1e9:.2f}GB")
PY
ls -la /workspace/out/
date -u +%FT%TZ > /workspace/logs/smoke3_done
