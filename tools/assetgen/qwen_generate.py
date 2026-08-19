"""Generate 4 concept-guided player reference candidates with Qwen-Image-Edit.

Pushed to and run on the remote instance by qwen_generate_remote.sh, inside
the isolated `qwen_gen` conda env. Not run locally -- no Qwen weights here.

The pipeline class is read from the checkpoint's own model_index.json rather
than hardcoded, since guessing wrong burns paid GPU time on an ImportError
instead of a fast, free, pre-flight check.
"""
import json
import traceback
from pathlib import Path

import torch
from PIL import Image

MODEL_DIR = "/workspace/models/qwen-image-edit-2511"
SOURCE_IMAGE = "/workspace/refs/turnaround_front_crop.png"
OUT_DIR = Path("/workspace/out/qwen_candidates")
MANIFEST = OUT_DIR / "manifest.json"

# Source crop is 401x941 (odd full-body portrait crop of a concept
# turnaround sheet). Resized to multiples of 16 for the pipeline while
# preserving aspect ratio.
TARGET_H = 1024
TARGET_W = 432

BASE_NOTE = (
    "Keep the exact same person: same face, same hairstyle, same vest, "
    "same cream shirt, same belt, same dark jeans, same brown boots. "
    "Photorealistic, consistent proportions, no text, no watermark, no "
    "additional panels or insets, single full-body figure only."
)

CANDIDATES = [
    {
        "name": "candidate_01_tpose_studio",
        "seed": 101,
        "prompt": (
            "Redraw this character standing on a seamless plain light-grey "
            "studio background with soft even three-point lighting and no "
            "harsh shadows. Relaxed T-pose: both arms held slightly away "
            "from the torso, palms facing inward, feet shoulder-width "
            "apart, full body visible head to toe, facing the camera. "
            + BASE_NOTE
        ),
    },
    {
        "name": "candidate_02_tpose_hands",
        "seed": 102,
        "prompt": (
            "Redraw this character standing on a seamless plain light-grey "
            "studio background with soft even three-point lighting and no "
            "harsh shadows. Relaxed T-pose: both arms held slightly away "
            "from the torso, palms facing inward, feet shoulder-width "
            "apart, full body visible head to toe, facing the camera. Pay "
            "close attention to anatomically correct hands, five fingers "
            "per hand, natural finger proportions and joints. "
            + BASE_NOTE
        ),
    },
    {
        "name": "candidate_03_three_quarter",
        "seed": 103,
        "prompt": (
            "Redraw this character standing on a seamless plain light-grey "
            "studio background with soft even three-point lighting and no "
            "harsh shadows. Body turned to a three-quarter stance (about "
            "30 degrees from camera-facing), weight balanced on both feet, "
            "arms relaxed slightly away from the torso, full body visible "
            "head to toe. " + BASE_NOTE
        ),
    },
    {
        "name": "candidate_04_material_fidelity",
        "seed": 104,
        "prompt": (
            "Redraw this character standing on a seamless plain light-grey "
            "studio background with soft even three-point lighting and no "
            "harsh shadows. Relaxed T-pose: both arms held slightly away "
            "from the torso, palms facing inward, feet shoulder-width "
            "apart, full body visible head to toe, facing the camera. "
            "Increase fine material detail: visible leather grain on the "
            "vest, woven cotton texture on the shirt, denim weave on the "
            "jeans, leather and stitching detail on the boots. "
            + BASE_NOTE
        ),
    },
]


def resolve_pipeline_class():
    with open(f"{MODEL_DIR}/model_index.json") as f:
        idx = json.load(f)
    class_name = idx["_class_name"]
    import diffusers

    return class_name, getattr(diffusers, class_name)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    class_name, PipeCls = resolve_pipeline_class()
    print(f"[qwen_generate] pipeline class: {class_name}")

    pipe = PipeCls.from_pretrained(MODEL_DIR, torch_dtype=torch.bfloat16)
    pipe = pipe.to("cuda")

    src = Image.open(SOURCE_IMAGE).convert("RGB").resize((TARGET_W, TARGET_H))

    manifest = {"source_image": SOURCE_IMAGE, "pipeline_class": class_name, "candidates": []}
    for c in CANDIDATES:
        entry = {"name": c["name"], "seed": c["seed"], "prompt": c["prompt"]}
        try:
            gen = torch.Generator(device="cuda").manual_seed(c["seed"])
            result = pipe(image=src, prompt=c["prompt"], generator=gen)
            image = result.images[0]
            out_path = OUT_DIR / f"{c['name']}.png"
            image.save(out_path)
            entry["status"] = "ok"
            entry["output"] = str(out_path)
            print(f"[qwen_generate] wrote {out_path}")
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = f"{type(e).__name__}: {e}"
            entry["traceback"] = traceback.format_exc()
            print(f"[qwen_generate] FAILED {c['name']}: {e}")
        manifest["candidates"].append(entry)

    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)

    del pipe
    torch.cuda.empty_cache()

    n_ok = sum(1 for c in manifest["candidates"] if c["status"] == "ok")
    print(f"[qwen_generate] {n_ok}/{len(CANDIDATES)} candidates generated")
    if n_ok == 0:
        raise SystemExit("all candidates failed -- see manifest.json for tracebacks")


if __name__ == "__main__":
    main()
