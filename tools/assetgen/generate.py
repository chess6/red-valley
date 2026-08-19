"""One 1024 candidate, run against the pipeline preflight already built.

Importing preflight runs every check and leaves a fully instantiated pipeline
behind. init_pipeline is then swapped for a function returning that object, so
run_inference uses the components preflight verified instead of loading ~23GB a
second time. One rental, one attempt.
"""
import json
import os
import subprocess
import sys
import time

import torch

sys.path.insert(0, "/workspace/tools")
import preflight  # noqa: E402  -- import *is* the preflight

MODEL = "/workspace/models/pixal3d"
REF = "/workspace/ref.png"
OUT = "/workspace/out/player_v01_seed1_1024.glb"
SEED, RES = 1, 1024

inf = preflight.inf
inf.init_pipeline = lambda *a, **k: preflight.pipeline   # reuse, do not reload

settings = {
    "checkpoint": "TencentARC/Pixal3D",
    "checkpoint_revision": "0b31f9160aa400719af409098bff7936a932f726",
    "pixal3d_code": "cdbb2bbffbf4",
    "trellis2_code": "75fbf0183001",
    "image": REF, "output": OUT, "seed": SEED, "resolution": RES,
    "fov": -1.0, "low_vram": False,
    "attn_backend": os.environ.get("ATTN_BACKEND"),
    "torch": torch.__version__,
    "gpu": torch.cuda.get_device_name(0),
    "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
}
print("\n=== GENERATION SETTINGS ===")
print(json.dumps(settings, indent=2), flush=True)

print("\n=== GENERATING (one attempt, seed %d, %d) ===" % (SEED, RES), flush=True)
t0 = time.time()
status, tb = "ok", None
try:
    inf.run_inference(image_path=REF, output_path=OUT, seed=SEED,
                      manual_fov=-1.0, model_path=MODEL, low_vram=False,
                      resolution=RES)
except SystemExit as e:
    if e.code not in (0, None):
        status, tb = "failed", f"SystemExit({e.code})"
except BaseException:
    import traceback
    status, tb = "failed", traceback.format_exc()
    traceback.print_exc()
dt = time.time() - t0

trace = sorted(m for m in sys.modules if any(
    k in m for k in ("nvdiffrast", "nvdiffrec", "o_voxel", "cumesh",
                     "flex_gemm", "natten", "diffusers", "transformers")))
result = {
    "status": status, "seconds": round(dt, 1), "traceback": tb,
    "settings": settings,
    "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
    "network_attempts_during_run": preflight.report["network_attempts"],
    "runtime_modules": trace,
    "preflight": preflight.report,
}
os.makedirs("/workspace/out", exist_ok=True)
json.dump(result, open("/workspace/out/generation_report.json", "w"), indent=2)
json.dump(settings, open("/workspace/out/generation_settings.json", "w"), indent=2)

print(f"\n=== RESULT status={status} {dt:.1f}s ===")
print("network attempts during generation:",
      preflight.report["network_attempts"] or "NONE (fully offline)")
if status != "ok":
    raise SystemExit(1)

if not os.path.exists(OUT):
    print("!! reported success but no GLB on disk")
    raise SystemExit(1)
print("GLB:", OUT, os.path.getsize(OUT), "bytes")
subprocess.run("cd /workspace/out && sha256sum * > SHA256SUMS && cat SHA256SUMS",
               shell=True)
