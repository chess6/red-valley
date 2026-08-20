"""Bounded SPAR3D character retry: N deterministic seeds, native geometry.

Model is loaded once and reused across seeds; each seed re-seeds every RNG so
runs are individually reproducible. Nothing is remeshed, repaired or edited.
"""
import gc, hashlib, json, os, random, sys, time
import numpy as np, torch
from PIL import Image

REPO = "/home/thomas/Dev/red-valley/tools/spar3d_eval/stable-point-aware-3d"
sys.path.insert(0, REPO)
from spar3d import utils as spar3d_utils          # noqa: E402
from spar3d.system import SPAR3D                  # noqa: E402

REF = "/home/thomas/Dev/red-valley/art/character/ai_generated/player_v01/reference/tq_ref_rgba512.png"
OUT = "/home/thomas/Dev/red-valley/art/character/ai_generated/spar3d_retry/out"
MODEL = "/home/thomas/.cache/huggingface/hub/models--stabilityai--stable-point-aware-3d/snapshots/5699918cb34f55cd7d828493d2725f3038313761"
SEEDS = list(range(12))
BAKE = 2048
os.makedirs(OUT, exist_ok=True)

model = SPAR3D.from_pretrained(MODEL, config_name="config.yaml",
                               weight_name="model.safetensors", low_vram_mode=True)
model.to("cuda"); model.eval()
assert float(model.cfg.guidance_scale) == 3.0

img = Image.open(REF).convert("RGBA")
assert img.getchannel("A").getextrema()[0] == 0, "reference must carry alpha"
# already framed at 87% of a 512 canvas -> no further cropping
img_in = spar3d_utils.foreground_crop(img, crop_ratio=1.0, no_crop=True)

results = []
for seed in SEEDS:
    random.seed(seed); torch.manual_seed(seed); np.random.seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        mesh, gd = model.run_image(img_in, bake_resolution=BAKE, remesh="none",
                                   vertex_count=-1, return_points=True,
                                   estimate_illumination=False)
    dt = time.time() - t0
    glb = os.path.join(OUT, f"seed{seed:02d}.glb")
    mesh.export(glb, include_normals=True)
    gd["point_clouds"][0].export(os.path.join(OUT, f"seed{seed:02d}_points.ply"))
    peak = torch.cuda.max_memory_allocated() / 1024 / 1024
    results.append({"seed": seed, "seconds": round(dt, 1), "peak_vram_mb": round(peak, 1),
                    "glb": os.path.basename(glb),
                    "sha256": hashlib.sha256(open(glb, "rb").read()).hexdigest()})
    print(f"seed {seed:02d}  {dt:5.1f}s  {peak:7.1f}MB  {os.path.basename(glb)}", flush=True)
    del mesh, gd; gc.collect(); torch.cuda.empty_cache()

json.dump({"reference": REF, "seeds": SEEDS, "bake_resolution": BAKE,
           "remesh": "none", "guidance_scale": 3.0, "low_vram": True,
           "runs": results}, open(os.path.join(OUT, "batch_settings.json"), "w"), indent=2)
print("TOTAL", round(sum(r["seconds"] for r in results), 1), "s")
