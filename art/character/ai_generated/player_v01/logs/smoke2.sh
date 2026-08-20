#!/usr/bin/env bash
set -uo pipefail
source /opt/conda/etc/profile.d/conda.sh && conda activate rv310
export CUDA_HOME=/usr/local/cuda PATH=/usr/local/cuda/bin:$PATH
export ATTN_BACKEND=sdpa HF_HOME=/workspace/hf
cd /workspace/repos/Pixal3D
mkdir -p /workspace/out
python - <<'PY' 2>&1
import sys, json, time, importlib, torch
from PIL import Image

# The pipeline constructs BiRefNet(briaai/RMBG-2.0) at load time. That repo is
# GATED and non-commercial. Our inputs are RGBA with real alpha, and the
# pipeline's own preprocess_image() short-circuits background removal in that
# case -- so the model is constructed but never invoked. Stub it here, in the
# DRIVER, leaving the generator source untouched.
rembg = importlib.import_module("pixal3d.pipelines.rembg")
class _UnusedRembg:
    def __init__(self, *a, **k): pass
    def to(self, *a, **k): return self
    def cpu(self): return self
    def __call__(self, img):
        raise RuntimeError("background removal was invoked; input lacked alpha")
rembg.BiRefNet = _UnusedRembg
print("[driver] BiRefNet stubbed (gated briaai/RMBG-2.0 avoided)")

from pixal3d.pipelines import Pixal3DImageTo3DPipeline
t0=time.time()
pipe = Pixal3DImageTo3DPipeline.from_pretrained("/workspace/models/trellis2-4b")
pipe.cuda()
print(f"[driver] pipeline loaded in {time.time()-t0:.1f}s")

img = Image.open("assets/images/1_img.png")
print("[driver] input", img.mode, img.size)
t1=time.time()
out = pipe.run(img, seed=1, formats=["mesh"], preprocess_image=True)
dt=time.time()-t1
print(f"[driver] inference {dt:.1f}s -> {list(out.keys())}")

loaded = sorted(m for m in sys.modules if any(k in m for k in
        ("nvdiffrast","nvdiffrec","o_voxel","cumesh","flex_gemm","natten","flash_attn","rembg")))
json.dump({"ok":True,"load_s":round(t1-t0,1),"infer_s":round(dt,1),
           "outputs":list(out.keys()),
           "peak_vram_gb":round(torch.cuda.max_memory_allocated()/1e9,2),
           "runtime_modules":loaded},
          open("/workspace/out/smoke_modules.json","w"), indent=1)
print("SMOKE_OK peak_vram_gb=%.2f" % (torch.cuda.max_memory_allocated()/1e9))
PY
date -u +%FT%TZ > /workspace/logs/smoke2_done
