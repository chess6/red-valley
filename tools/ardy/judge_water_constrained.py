"""Judge the RAW constrained Core output before any retargeting.

Criteria are Core-skeleton scale (hips ~0.97, shoulder 1.479, arm 0.528):
  start -> lean/pour -> return cycle, both feet planted, no deep crouch,
  right hand moves down-and-forward into the pour, liveness (not static).

  python3 tools/ardy/judge_water_constrained.py <npz>
"""
import sys
import numpy as np

NPZ = sys.argv[1]
IDX = {"Hips": 0, "Neck": 5, "RightHand": 10, "RightFoot": 21, "LeftFoot": 25}
d = np.load(NPZ)
J = d["posed_joints"]; F = J.shape[0]
hips = J[:, IDX["Hips"]]; hand = J[:, IDX["RightHand"]]
fR = J[:, IDX["RightFoot"]]; fL = J[:, IDX["LeftFoot"]]
v = J[:, IDX["Neck"]] - J[:, IDX["Hips"]]
lean = np.degrees(np.arctan2(np.linalg.norm(v[:, [0, 2]], axis=1), v[:, 1]))
POUR = slice(56, 96); START = slice(0, 12); END = slice(148, 160)
fails = []

def chk(name, cond, detail):
    print("  %-34s %s  (%s)" % (name, "ok" if cond else "FAIL", detail))
    if not cond: fails.append(name)

pl = lean[POUR].mean()
chk("pour lean 8-20 deg", 8 <= pl <= 20, "mean %.1f, max %.1f" % (pl, lean[POUR].max()))
chk("no deep crouch (hips >= 0.90)", hips[:, 1].min() >= 0.90, "min hips %.3f" % hips[:, 1].min())
hf = (hand[POUR, 2] - hips[POUR, 2]).mean()
chk("hand forward of hips at pour", hf >= 0.20, "mean fwd %.3f" % hf)
hy = hand[POUR, 1].mean()
chk("hand lowered at pour", hy <= 1.05, "mean hand y %.3f (rest-hang ~0.97+arm-raise)" % hy)
for nm, f in (("right", fR), ("left", fL)):
    drift = np.linalg.norm(f[:, [0, 2]] - f[0, [0, 2]], axis=1).max()
    chk("%s foot planted" % nm, f[:, 1].max() < 0.14 and drift < 0.08,
        "max y %.3f, xz drift %.3f" % (f[:, 1].max(), drift))
path = np.linalg.norm(np.diff(hand, axis=0), axis=1).sum()
chk("liveness (hand path >= 0.30 m)", path >= 0.30, "total path %.2f m" % path)
ret = np.linalg.norm(hand[END].mean(0) - hand[START].mean(0))
chk("returns near start", ret <= 0.20, "start-end hand gap %.3f m" % ret)
dstart = np.linalg.norm(hand[START].mean(0) - hand[POUR].mean(0))
chk("pour differs from start", dstart >= 0.15, "start->pour hand travel %.3f m" % dstart)
print("VERDICT:", "PASS" if not fails else "FAIL: %s" % ", ".join(fails))
sys.exit(0 if not fails else 1)
