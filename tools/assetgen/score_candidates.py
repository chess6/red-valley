"""Score Qwen-Image-Edit player-reference candidates against the concept-art
source on silhouette match, coarse likeness, left-right symmetry (a proxy for
plausible anatomy, not a real pose/anatomy detector), and sharpness.

This is a new heuristic scorer written for this task -- not a previously
existing, validated rubric. It ranks candidates to make the pick legible and
reproducible; it is not a substitute for a human looking at the contact
sheet before anything downstream depends on the choice.

  python3 tools/assetgen/score_candidates.py --source ref.png --out report.json cand1.png cand2.png ...
"""
import argparse
import json

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

WEIGHTS = {"silhouette_iou": 0.35, "fidelity_ssim": 0.30, "symmetry": 0.20, "sharpness": 0.15}
CANVAS = (512, 512)


def load_gray(path):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"could not read {path}")
    img = cv2.resize(img, CANVAS)
    return img, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def silhouette_mask(bgr):
    """Foreground mask via distance from the image's own background color,
    sampled as the median of the four corner pixels (candidates are prompted
    for a plain studio background, so the corners are reliably background)."""
    h, w = bgr.shape[:2]
    corners = np.array([bgr[0, 0], bgr[0, w - 1], bgr[h - 1, 0], bgr[h - 1, w - 1]], dtype=np.float32)
    bg = np.median(corners, axis=0)
    dist = np.linalg.norm(bgr.astype(np.float32) - bg, axis=2)
    mask = (dist > 18).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    return mask


def iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 0.0


def symmetry_score(mask):
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return 0.0
    cx = int(xs.mean())
    left = mask[:, :cx]
    right = mask[:, cx:]
    right_flipped = np.fliplr(right)
    w = min(left.shape[1], right_flipped.shape[1])
    if w == 0:
        return 0.0
    return iou(left[:, -w:], right_flipped[:, :w])


def sharpness_score(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def score_one(source_bgr, source_gray, source_mask, path):
    bgr, gray = load_gray(path)
    mask = silhouette_mask(bgr)

    metrics = {
        "silhouette_iou": iou(mask, source_mask),
        "fidelity_ssim": float(ssim(gray, source_gray)),
        "symmetry": symmetry_score(mask),
        "sharpness_raw": sharpness_score(gray),
    }
    return metrics


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("images", nargs="+")
    args = ap.parse_args(argv)

    source_bgr, source_gray = load_gray(args.source)
    source_mask = silhouette_mask(source_bgr)

    results = []
    for path in args.images:
        m = score_one(source_bgr, source_gray, source_mask, path)
        results.append({"path": path, "metrics": m})

    max_sharp = max((r["metrics"]["sharpness_raw"] for r in results), default=1.0) or 1.0
    for r in results:
        m = r["metrics"]
        m["sharpness"] = m["sharpness_raw"] / max_sharp
        r["score"] = sum(WEIGHTS[k] * m[k] for k in WEIGHTS)

    results.sort(key=lambda r: r["score"], reverse=True)
    report = {"weights": WEIGHTS, "source": args.source, "results": results,
              "picked": results[0]["path"] if results else None}

    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)

    print(f"rubric (weights={WEIGHTS}):")
    for r in results:
        print(f"  {r['score']:.3f}  {r['path']}")
    print(f"picked: {report['picked']}")
    print("NOTE: heuristic pick -- confirm by eye on the contact sheet before using downstream.")


if __name__ == "__main__":
    main()
