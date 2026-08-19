"""One bounded local SPAR3D generation. Evaluation only.

Uses the upstream library API without modifying any upstream file. run.py is
not used directly because it exposes neither seed nor guidance scale, and its
--foreground-ratio default (0.85) crops INSIDE the subject's bounding box,
clipping the head and boots. The official Gradio app calls the same helper
with a "Padding Ratio" whose minimum is 1.0 and default is 1.3, so 1.3 is the
intended framing and is what this uses.

Background removal is deliberately skipped: the input already carries a real
alpha channel, which foreground_crop consumes directly.
"""
import hashlib
import json
import os
import random
import sys
import time
from contextlib import nullcontext

import numpy as np
import torch
from PIL import Image

REPO = "/home/thomas/Dev/red-valley/tools/spar3d_eval/stable-point-aware-3d"
sys.path.insert(0, REPO)

from huggingface_hub import snapshot_download  # noqa: E402
from spar3d import utils as spar3d_utils  # noqa: E402
from spar3d.system import SPAR3D  # noqa: E402

SRC = "/home/thomas/Dev/red-valley/art/character/ai_generated/player_v01/reference/front_ref_rgba1024.png"
OUT = "/home/thomas/Dev/red-valley/art/character/ai_generated/spar3d_eval/out"
MODEL_REPO = "stabilityai/stable-point-aware-3d"
MODEL_REV = "5699918cb34f55cd7d828493d2725f3038313761"
SEED, BAKE_RES, CROP_RATIO = 0, 2048, 1.3

os.makedirs(OUT, exist_ok=True)
t_start = time.time()

print("== pinning model revision ==", flush=True)
local_model = snapshot_download(MODEL_REPO, revision=MODEL_REV,
                                token=os.environ.get("HF_TOKEN"))
print("model dir:", local_model, flush=True)
t_dl = time.time()

print("== seeding (seed=%d) ==" % SEED, flush=True)
random.seed(SEED)
torch.manual_seed(SEED)
np.random.seed(SEED)
torch.cuda.manual_seed_all(SEED)

print("== loading model (low VRAM) ==", flush=True)
model = SPAR3D.from_pretrained(
    local_model, config_name="config.yaml", weight_name="model.safetensors",
    low_vram_mode=True,
)
model.to("cuda")
model.eval()
guidance = float(model.cfg.guidance_scale)
print("guidance_scale from config:", guidance, flush=True)
assert guidance == 3.0, f"expected guidance 3.0, got {guidance}"
t_load = time.time()

print("== preparing image (alpha preserved, no background removal) ==", flush=True)
image = Image.open(SRC).convert("RGBA")
assert image.getchannel("A").getextrema()[0] == 0, "input lacks real transparency"
image = spar3d_utils.foreground_crop(image, crop_ratio=CROP_RATIO)
image.save(os.path.join(OUT, "input_prepared.png"))

print("== inference (one attempt) ==", flush=True)
torch.cuda.reset_peak_memory_stats()
with torch.no_grad():
    with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        mesh, glob_dict = model.run_image(
            image, bake_resolution=BAKE_RES, remesh="none", vertex_count=-1,
            return_points=True, estimate_illumination=True,
        )
t_inf = time.time()
peak = torch.cuda.max_memory_allocated() / 1024 / 1024

glb = os.path.join(OUT, "mesh.glb")
mesh.export(glb, include_normals=True)
pts = os.path.join(OUT, "points.ply")
glob_dict["point_clouds"][0].export(pts)

illum_path = None
illum = glob_dict.get("illumination")
if illum is not None:
    arr = illum.cpu().float().numpy() if torch.is_tensor(illum) else np.asarray(illum)
    illum_path = os.path.join(OUT, "illumination.npy")
    np.save(illum_path, arr)
    print("illumination saved:", arr.shape, flush=True)

settings = {
    "repo": "https://github.com/Stability-AI/stable-point-aware-3d",
    "repo_commit": "fdc311b16809e6a8adc2f5a3407ebb3db1a95bd1",
    "model_repo": MODEL_REPO, "model_revision": MODEL_REV,
    "seed": SEED, "guidance_scale": guidance,
    "texture_resolution": BAKE_RES, "remesh": "none", "vertex_count": -1,
    "estimate_illumination": True, "return_points": True,
    "background_removal": False, "alpha_preserved": True,
    "foreground_crop_ratio": CROP_RATIO,
    "low_vram_mode": True, "SPAR3D_LOW_VRAM": os.environ.get("SPAR3D_LOW_VRAM"),
    "device": torch.cuda.get_device_name(0), "torch": torch.__version__,
    "input_image": SRC,
    "peak_vram_mb": round(peak, 1),
    "seconds": {"download": round(t_dl - t_start, 1),
                "model_load": round(t_load - t_dl, 1),
                "inference": round(t_inf - t_load, 1),
                "total": round(t_inf - t_start, 1)},
}
json.dump(settings, open(os.path.join(OUT, "settings.json"), "w"), indent=2)

sums = {}
for f in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, f)
    if os.path.isfile(p):
        sums[f] = hashlib.sha256(open(p, "rb").read()).hexdigest()
with open(os.path.join(OUT, "SHA256SUMS"), "w") as fh:
    for k, v in sums.items():
        fh.write(f"{v}  {k}\n")

print(json.dumps(settings, indent=2))
print("PEAK VRAM MB:", round(peak, 1))
print("DONE")
