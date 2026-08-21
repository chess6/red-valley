"""Part A: look at the SOURCE skeleton before anything is retargeted.

Renders the canonical clip as a stick figure with orientation triads on both
wrists and both feet, and the source's own contact labels drawn as filled/hollow
markers. This is the step v1 skipped: every v1 gate ran downstream of the
retarget, so a lossy retarget and a bad source were indistinguishable.

  python3 tools/rvmotion/native_view.py <base.rvm> <outdir> [frames...]
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rvmotion.canonical import RVMotion, quat_to_mat  # noqa: E402

BASE, OUT = sys.argv[1], sys.argv[2]
FRAMES = [int(x) for x in sys.argv[3:]] or [0, 40, 73, 96, 120, 159]
os.makedirs(OUT, exist_ok=True)
m = RVMotion.load(BASE)
P = m.positions
G = quat_to_mat(m.global_quat)
JN = m.joints
AXIS_JOINTS = ["RightHand", "LeftHand", "RightFoot", "LeftFoot"]
CONTACT_OF = {"LeftFoot": "LeftFoot", "RightFoot": "RightFoot"}
bones = [(int(p), j) for j, p in enumerate(m.parents) if p >= 0]

for f in FRAMES:
    fig = plt.figure(figsize=(11, 5.2))
    for k, (elev, azim, tag) in enumerate([(8, -75, "side"), (8, -25, "three-quarter")]):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        for a, b in bones:
            ax.plot(*zip(P[f, a], P[f, b]), color="#5a6470", lw=1.6)
        ax.scatter(P[f, :, 0], P[f, :, 1], P[f, :, 2], s=9, color="#2b3138")
        for jn in AXIS_JOINTS:
            j = JN.index(jn)
            o = P[f, j]
            for c, col, lab in ((0, "#d9534f", "x"), (1, "#5cb85c", "y"), (2, "#4a90d9", "z")):
                v = G[f, j][:, c] * 0.12
                ax.plot(*zip(o, o + v), color=col, lw=2.2)
            ch = CONTACT_OF.get(jn)
            if ch:
                on = bool(m.contacts[f, m.contact_channels.index(ch)])
                ax.scatter(*o, s=90, facecolor=("#e8a33d" if on else "none"),
                           edgecolor="#e8a33d", lw=1.8, zorder=5)
        c = P[f, 0]
        ax.set_xlim(c[0] - 0.9, c[0] + 0.9); ax.set_ylim(c[1] - 0.9, c[1] + 0.9)
        ax.set_zlim(0, 1.9)
        ax.set_box_aspect((1, 1, 1.05)); ax.view_init(elev=elev, azim=azim)
        ax.set_title("%s  f=%d" % (tag, f), fontsize=9)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
    fig.suptitle("native source skeleton — triads = wrist/foot orientation, "
                 "filled ring = source contact label", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "native_f%03d.png" % f), dpi=110)
    plt.close(fig)
print("wrote %d native frames to %s" % (len(FRAMES), OUT))

# --- anatomical checks on the SOURCE, before any retarget ------------------
def ang(a, b):
    a, b = a / np.linalg.norm(a, axis=-1, keepdims=True), b / np.linalg.norm(b, axis=-1, keepdims=True)
    return np.degrees(np.arccos(np.clip((a * b).sum(-1), -1, 1)))

def idx(n): return JN.index(n)
rep = {}
for side in ("Right", "Left"):
    sh, el, wr = idx(side + "Arm"), idx(side + "ForeArm"), idx(side + "Hand")
    elbow = ang(P[:, sh] - P[:, el], P[:, wr] - P[:, el])
    # elbow must not hyperextend (>180 impossible) nor lock dead straight all clip
    rep[side + "_elbow_deg"] = {"min": round(float(elbow.min()), 1),
                                "max": round(float(elbow.max()), 1),
                                "mean": round(float(elbow.mean()), 1)}
    hip, kn, an = idx(side + "UpLeg"), idx(side + "Leg"), idx(side + "Foot")
    knee = ang(P[:, hip] - P[:, kn], P[:, an] - P[:, kn])
    rep[side + "_knee_deg"] = {"min": round(float(knee.min()), 1),
                               "max": round(float(knee.max()), 1)}
    # wrist deviation: hand bone vs forearm bone direction
    fore = P[:, wr] - P[:, el]
    hand = P[:, idx(side + "HandEnd")] - P[:, wr]
    rep[side + "_wrist_deviation_deg"] = {"max": round(float(ang(fore, hand).max()), 1),
                                          "mean": round(float(ang(fore, hand).mean()), 1)}
print()
for k, v in rep.items():
    print("  %-28s %s" % (k, v))
import json
json.dump(rep, open(os.path.join(OUT, "native_anatomy.json"), "w"), indent=2)
